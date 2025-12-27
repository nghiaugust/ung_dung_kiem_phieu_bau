"""
API Views cho Mobile App
"""
import json
import os
import uuid
import tempfile
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import APIToken
from .authentication import require_api_token
from .image_optimizer import optimize_ballot_image
from poll.models import Poll, Candidate, PollMember, Voter
from ballot.models import Ballot
from ballot.doc_qr import read_qr_code_only
from security.hmac_utils import verify_ballot_from_qr

User = get_user_model()


# =====================================================
# AUTHENTICATION APIs
# =====================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_register(request):
    """
    API Register - Đăng ký tài khoản mới
    
    POST /api/register/
    Body (JSON):
    {
        "username": "string",
        "password": "string",
        "password_confirm": "string",
        "email": "string" (optional),
        "last_name": "string" (optional)
    }
    
    Response:
    {
        "success": true,
        "message": "Đăng ký thành công",
        "user": {
            "id": 1,
            "username": "john"
        }
    }
    """
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        password = data.get('password', '')
        password_confirm = data.get('password_confirm', '')
        email = data.get('email', '').strip()
        last_name = data.get('last_name', '').strip()
        
        # Validate input
        if not username or not password or not password_confirm:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields',
                'message': 'Vui lòng điền đầy đủ thông tin bắt buộc (username, password, password_confirm)'
            }, status=400)
        
        if password != password_confirm:
            return JsonResponse({
                'success': False,
                'error': 'Password mismatch',
                'message': 'Mật khẩu xác nhận không khớp'
            }, status=400)
        
        if len(password) < 6:
            return JsonResponse({
                'success': False,
                'error': 'Password too short',
                'message': 'Mật khẩu phải có ít nhất 6 ký tự'
            }, status=400)
        
        # Check if username already exists
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                'success': False,
                'error': 'Username exists',
                'message': 'Tên đăng nhập đã tồn tại'
            }, status=400)
        
        # Create new user
        from django.contrib.auth.hashers import make_password
        user = User.objects.create(
            username=username,
            password=make_password(password),
            email=email,
            last_name=last_name,
            is_active=True
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Đăng ký thành công! Vui lòng đăng nhập.',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.last_name
            }
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    """
    API Login - Trả về Access Token và Refresh Token
    
    POST /api/login/
    Body (JSON):
    {
        "username": "string",
        "password": "string"
    }
    
    Response:
    {
        "success": true,
        "access_token": "abc123...",
        "refresh_token": "xyz789...",
        "expires_in": 3600,
        "user": {
            "id": 1,
            "username": "john",
            "role": "user"
        }
    }
    """
    import json
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return JsonResponse({
                'success': False,
                'error': 'Missing credentials',
                'message': 'Vui lòng nhập username và password'
            }, status=400)
        
        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if user is None:
            return JsonResponse({
                'success': False,
                'error': 'Invalid credentials',
                'message': 'Tên đăng nhập hoặc mật khẩu không đúng'
            }, status=401)
        
        if not user.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Account disabled',
                'message': 'Tài khoản đã bị vô hiệu hóa'
            }, status=403)
        
        # Get or create token
        token, created = APIToken.objects.get_or_create(user=user)
        
        # Làm mới token mỗi lần đăng nhập
        now = timezone.now()
        
        # Lấy thời gian sống từ settings (đơn vị: giây)
        access_token_lifetime = int(os.environ.get('ACCESS_TOKEN_LIFETIME', 3600))  # Mặc định 1 giờ
        refresh_token_lifetime = int(os.environ.get('REFRESH_TOKEN_LIFETIME', 2592000))  # Mặc định 30 ngày
        
        # Tạo token mới
        token.token = APIToken.generate_token()
        token.expires_at = now + timedelta(seconds=access_token_lifetime)
        
        # Tạo refresh token mới
        token.refresh_token = APIToken.generate_token()
        token.refresh_token_expires_at = now + timedelta(seconds=refresh_token_lifetime)
        
        # Update last used
        token.last_used = now
        token.is_active = True
        token.save()
        
        return JsonResponse({
            'success': True,
            'access_token': token.token,
            'refresh_token': token.refresh_token,
            'expires_in': access_token_lifetime,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_superuser': user.is_superuser,
                'email': user.email or '',
                'full_name': user.last_name or ''
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_refresh_token(request):
    """
    API Refresh Token - Làm mới Access Token bằng Refresh Token
    
    POST /api/refresh-token/
    Body (JSON):
    {
        "refresh_token": "xyz789..."
    }
    
    Response:
    {
        "success": true,
        "access_token": "new_abc123...",
        "expires_in": 3600
    }
    """
    try:
        data = json.loads(request.body)
        refresh_token = data.get('refresh_token', '').strip()
        
        if not refresh_token:
            return JsonResponse({
                'success': False,
                'error': 'Missing refresh token',
                'message': 'Vui lòng cung cấp refresh token'
            }, status=400)
        
        # Tìm token
        try:
            token = APIToken.objects.get(refresh_token=refresh_token, is_active=True)
        except APIToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid refresh token',
                'message': 'Refresh token không hợp lệ'
            }, status=401)
        
        # Kiểm tra refresh token chưa hết hạn
        now = timezone.now()
        if token.refresh_token_expires_at and token.refresh_token_expires_at < now:
            return JsonResponse({
                'success': False,
                'error': 'Refresh token expired',
                'message': 'Refresh token đã hết hạn. Vui lòng đăng nhập lại'
            }, status=401)
        
        # Tạo access token mới
        access_token_lifetime = int(os.environ.get('ACCESS_TOKEN_LIFETIME', 3600))
        
        token.token = APIToken.generate_token()
        token.expires_at = now + timedelta(seconds=access_token_lifetime)
        token.last_used = now
        token.save()
        
        return JsonResponse({
            'success': True,
            'access_token': token.token,
            'expires_in': access_token_lifetime
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@require_api_token
@require_http_methods(["POST"])
def api_logout(request):
    """
    API Logout - Vô hiệu hóa token
    
    POST /api/logout/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "message": "Đăng xuất thành công"
    }
    """
    try:
        # Deactivate token
        token = APIToken.objects.get(user=request.api_user)
        token.is_active = False
        token.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Đăng xuất thành công'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_api_token
@require_http_methods(["GET"])
def api_me(request):
    """
    Lấy thông tin user hiện tại
    
    GET /api/me/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "user": {...}
    }
    """
    user = request.api_user
    return JsonResponse({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email or '',
            'full_name': user.last_name or '',
            'is_superuser': user.is_superuser,
            'created_at': user.date_joined.isoformat() if user.date_joined else None
        }
    })


# =====================================================
# POLL APIs
# =====================================================

@require_api_token
@require_http_methods(["GET"])
def api_poll_list(request):
    """
    Danh sách cuộc bỏ phiếu
    
    GET /api/polls/
    Header: Authorization: Bearer <token>
    
    Query params:
        - limit: số lượng (default 20, max 100)
        - offset: vị trí bắt đầu (default 0)
        - status: filter theo trạng thái poll (optional)
    
    Response:
    {
        "success": true,
        "total": 100,
        "count": 20,
        "limit": 20,
        "offset": 0,
        "polls": [...]
    }
    """
    user = request.api_user
    
    # Superuser xem tất cả, user khác xem polls mình tạo + polls mình tham gia
    if user.is_superuser:
        polls = Poll.objects.all()
    else:
        # Lấy polls mình tạo
        created_polls = Poll.objects.using('api_pool').filter(created_by=user)
        
        # Lấy polls mình là thành viên (status='active')
        member_poll_ids = PollMember.objects.using('api_pool').filter(
            account=user, 
            status='active'
        ).values_list('poll_id', flat=True)
        member_polls = Poll.objects.using('api_pool').filter(poll_id__in=member_poll_ids)
        
        # Gộp 2 queryset
        polls = (created_polls | member_polls).distinct()
    
    # Filter by status if provided
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        polls = polls.filter(status=status_filter)
    
    # Get total count before pagination
    total_count = polls.count()
    
    # Pagination
    try:
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        # Limit max 100
        limit = min(limit, 100)
        
        # Ensure offset is not negative
        offset = max(offset, 0)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameters',
            'message': 'Tham số limit hoặc offset không hợp lệ'
        }, status=400)
    
    # Apply pagination and order
    polls = polls.order_by('-poll_id')[offset:offset + limit]
    
    poll_list = []
    for poll in polls:
        poll_list.append({
            'poll_id': poll.poll_id,
            'title': poll.title,
            'description': poll.description,
            'status': poll.status,
            'start_time': poll.start_time.isoformat() if poll.start_time else None,
            'end_time': poll.end_time.isoformat() if poll.end_time else None,
            'created_by': poll.created_by.username if poll.created_by else None
        })
    
    return JsonResponse({
        'success': True,
        'total': total_count,
        'count': len(poll_list),
        'limit': limit,
        'offset': offset,
        'polls': poll_list
    })


@require_api_token
@require_http_methods(["GET"])
def api_poll_list_no_pool(request):
    """
    Danh sách cuộc bỏ phiếu (KHÔNG sử dụng connection pool - for benchmark)
    
    GET /api/polls-no-pool/
    Header: Authorization: Bearer <token>
    
    Query params:
        - limit: số lượng (default 20, max 100)
        - offset: vị trí bắt đầu (default 0)
        - status: filter theo trạng thái poll (optional)
    
    Response:
    {
        "success": true,
        "total": 100,
        "count": 20,
        "limit": 20,
        "offset": 0,
        "polls": [...]
    }
    """
    import time
    
    # Mô phỏng remote database connection overhead (20-100ms)
    # Thêm delay để giả lập thời gian tạo connection mới
    time.sleep(0.050)  # 50ms delay để mô phỏng remote DB connection
    
    user = request.api_user
    
    # KHÔNG SỬ DỤNG using('api_pool') - dùng connection mặc định
    # Đóng connection sau mỗi request để mô phỏng không có pool
    from django.db import connection
    
    # Superuser xem tất cả, user khác xem polls mình tạo + polls mình tham gia
    if user.is_superuser:
        polls = Poll.objects.all()
    else:
        # Lấy polls mình tạo (KHÔNG dùng api_pool)
        created_polls = Poll.objects.filter(created_by=user)
        
        # Lấy polls mình là thành viên (status='active') (KHÔNG dùng api_pool)
        member_poll_ids = PollMember.objects.filter(
            account=user, 
            status='active'
        ).values_list('poll_id', flat=True)
        member_polls = Poll.objects.filter(poll_id__in=member_poll_ids)
        
        # Gộp 2 queryset
        polls = (created_polls | member_polls).distinct()
    
    # Filter by status if provided
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        polls = polls.filter(status=status_filter)
    
    # Get total count before pagination
    total_count = polls.count()
    
    # Pagination
    try:
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        # Limit max 100
        limit = min(limit, 100)
        
        # Ensure offset is not negative
        offset = max(offset, 0)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameters',
            'message': 'Tham số limit hoặc offset không hợp lệ'
        }, status=400)
    
    # Apply pagination and order
    polls = polls.order_by('-poll_id')[offset:offset + limit]
    
    poll_list = []
    for poll in polls:
        poll_list.append({
            'poll_id': poll.poll_id,
            'title': poll.title,
            'description': poll.description,
            'status': poll.status,
            'start_time': poll.start_time.isoformat() if poll.start_time else None,
            'end_time': poll.end_time.isoformat() if poll.end_time else None,
            'created_by': poll.created_by.username if poll.created_by else None
        })
    
    # Đóng connection để mô phỏng không có pool
    connection.close()
    
    return JsonResponse({
        'success': True,
        'total': total_count,
        'count': len(poll_list),
        'limit': limit,
        'offset': offset,
        'polls': poll_list
    })


@require_api_token
@require_http_methods(["GET"])
def api_my_poll_memberships(request):
    """
    Danh sách tất cả các poll mà user là thành viên (tất cả status)
    
    GET /api/my-poll-memberships/
    Header: Authorization: Bearer <token>
    
    Query params:
        - limit: số lượng (default 20, max 100)
        - offset: vị trí bắt đầu (default 0)
        - status: filter theo member_status (optional: active, pending, rejected)
    
    Response:
    {
        "success": true,
        "total": 50,
        "count": 20,
        "limit": 20,
        "offset": 0,
        "memberships": [
            {
                "poll_id": 1,
                "title": "...",
                "description": "...",
                "member_status": "active" | "pending" | "rejected"
            }
        ]
    }
    """
    user = request.api_user
    
    # Lấy tất cả các PollMember của user (tất cả status)
    memberships = PollMember.objects.filter(
        account=user
    ).select_related('poll')
    
    # Filter by status if provided
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        memberships = memberships.filter(status=status_filter)
    
    # Get total count before pagination
    total_count = memberships.count()
    
    # Pagination
    try:
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        # Limit max 100
        limit = min(limit, 100)
        
        # Ensure offset is not negative
        offset = max(offset, 0)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameters',
            'message': 'Tham số limit hoặc offset không hợp lệ'
        }, status=400)
    
    # Apply pagination and order
    memberships = memberships.order_by('-assigned_at')[offset:offset + limit]
    
    membership_list = []
    for membership in memberships:
        poll = membership.poll
        membership_list.append({
            'poll_id': poll.poll_id,
            'title': poll.title,
            'description': poll.description,
            'member_status': membership.status
        })
    
    return JsonResponse({
        'success': True,
        'total': total_count,
        'count': len(membership_list),
        'limit': limit,
        'offset': offset,
        'memberships': membership_list
    })


@require_api_token
@require_http_methods(["GET"])
def api_poll_detail(request, poll_id):
    """
    Chi tiết cuộc bỏ phiếu
    
    GET /api/polls/<poll_id>/
    Header: Authorization: Bearer <token>
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission
        user = request.api_user
        
        # Kiểm tra quyền:
        # 1. Superuser toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên active của poll (tất cả roles đều được xem)
        has_permission = False
        
        if user.is_superuser:
            # Superuser toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên active của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='active')
                # Tất cả thành viên active đều được xem chi tiết poll
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xem cuộc bỏ phiếu này'
            }, status=403)
        
        # Get candidates
        candidates = Candidate.objects.filter(poll=poll)
        candidate_list = [
            {
                'candidate_id': c.candidate_id,
                'name': c.name,
                'description': c.description
            }
            for c in candidates
        ]
        
        # Get ballot stats
        total_ballots = Ballot.objects.filter(poll=poll).count()
        checked_ballots = Ballot.objects.filter(poll=poll, is_checked=True).count()
        
        return JsonResponse({
            'success': True,
            'poll': {
                'poll_id': poll.poll_id,
                'title': poll.title,
                'description': poll.description,
                'status': poll.status,
                'start_time': poll.start_time.isoformat() if poll.start_time else None,
                'end_time': poll.end_time.isoformat() if poll.end_time else None,
                'total_ballots': total_ballots,
                'checked_ballots': checked_ballots,
                'candidates': candidate_list,
                'role': poll_member.role if 'poll_member' in locals() else 'user'
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)


# =====================================================
# BALLOT UPLOAD APIs
# =====================================================

@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_upload_ballot(request, poll_id):
    """
    Cập nhật phiếu bầu từ mobile (chỉ cho phép UPDATE, không tạo mới)
    
    POST /api/polls/<poll_id>/upload/
    Header: Authorization: Bearer <token>
    Body: multipart/form-data
        - ballot_file: file ảnh (required)
    
    Response:
    {
        "success": true,
        "ballot_id": 123,
        "is_update": true,
        "qr_ballot_id": 123,
        "qr_detected": true,
        "qr_hmac": "abc123...",
        "filename": "image.jpg",
        "message": "Cập nhật phiếu bầu thành công (từ QR code)"
    }
    
    Error Response (nếu không tìm thấy ballot_id):
    {
        "success": false,
        "error": "Ballot not found",
        "message": "Không tìm thấy phiếu bầu với ID này"
    }
    """
    try:
        # Check poll exists
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission
        user = request.api_user
        
        # Kiểm tra quyền:
        # 1. Superuser toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên active có role 'manager' hoặc 'operator'
        has_permission = False
        
        if user.is_superuser:
            # Superuser toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên active của poll không
            try:
                poll_member = PollMember.objects.using('api_pool').get(poll=poll, account=user, status='active')
                # Chỉ manager và operator mới được upload
                if poll_member.role in ['manager', 'operator']:
                    has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền upload phiếu cho cuộc bỏ phiếu này'
            }, status=403)
        
        # Check file
        if 'ballot_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Missing file',
                'message': 'Vui lòng chọn file ảnh phiếu bầu'
            }, status=400)
        
        uploaded_file = request.FILES['ballot_file']
        
        # Validate file type
        allowed_extensions = ['jpg', 'jpeg', 'png', 'bmp', 'tiff']
        file_ext = uploaded_file.name.split('.')[-1].lower()
        
        if file_ext not in allowed_extensions:
            return JsonResponse({
                'success': False,
                'error': 'Invalid file type',
                'message': f'Chỉ chấp nhận file: {", ".join(allowed_extensions)}'
            }, status=400)
        
        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return JsonResponse({
                'success': False,
                'error': 'File too large',
                'message': 'Kích thước file không được vượt quá 10MB'
            }, status=400)
        
        # Tối ưu ảnh trước khi xử lý
        optimized_file = optimize_ballot_image(uploaded_file)
        
        # Đọc QR code từ phiếu bầu đã tối ưu
        temp_file_path = None
        qr_ballot_id = None
        qr_code_raw = None
        qr_data = None
        
        try:
            # Lưu file tạm từ optimized_file để đọc QR
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_file:
                optimized_file.seek(0)
                for chunk in optimized_file.chunks():
                    temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            # Reset file pointer để có thể sử dụng lại
            optimized_file.seek(0)
            
            # Đọc chỉ QR code từ ảnh
            qr_result = read_qr_code_only(temp_file_path)
            
            # Lấy thông tin QR code nếu có
            if qr_result.get('success') and qr_result.get('qr_count', 0) > 0:
                qr_codes = qr_result.get('qr_codes', [])
                if qr_codes and 'parsed_data' in qr_codes[0]:
                    qr_data = qr_codes[0]['parsed_data']
                    qr_code_raw = qr_data.get('data')
                elif qr_codes:
                    qr_code_raw = qr_codes[0].get('data', '')
                
                # Parse QR code có dạng "0:1:abcd" -> ballot_id = 1, hmac = abcd
                qr_hmac = None
                if qr_code_raw:
                    try:
                        parts = qr_code_raw.split(':')
                        if len(parts) >= 2:
                            qr_ballot_id = int(parts[1])
                        if len(parts) >= 3:
                            qr_hmac = parts[2]  # HMAC signature
                    except (ValueError, IndexError):
                        pass  # Không parse được, bỏ qua
                        
        except Exception as qr_error:
            # Nếu đọc QR thất bại, vẫn tiếp tục upload
            pass
        finally:
            # Xóa file tạm
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
        
        # Ưu tiên ballot_id từ QR code, fallback sang parameter
        ballot_id = qr_ballot_id or request.POST.get('ballot_id', '').strip()
        if ballot_id and isinstance(ballot_id, str):
            try:
                ballot_id = int(ballot_id)
            except ValueError:
                ballot_id = None
        
        # Kiểm tra bắt buộc phải có ballot_id
        if not ballot_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing ballot_id',
                'message': 'Không tìm thấy ballot_id trong QR code hoặc tham số'
            }, status=400)
        
        # Chỉ cho phép UPDATE, không cho tạo mới
        with transaction.atomic():
            try:
                ballot = Ballot.objects.using('api_pool').get(ballot_id=ballot_id, poll=poll)
            except Ballot.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Ballot not found',
                    'message': f'Không tìm thấy phiếu bầu với ID {ballot_id} trong cuộc bỏ phiếu này'
                }, status=404)
            
            # Delete old image file if exists
            if ballot.ballot_image:
                try:
                    ballot.ballot_image.delete(save=False)
                except:
                    pass  # Ignore error if file doesn't exist
            
            # Update ballot with new image (đã được tối ưu từ trước)
            ballot.ballot_image = optimized_file
            ballot.input_by_id = user.pk  # Dùng _id để tránh lỗi database router
            
            # Chuẩn bị và update metadata
            if ballot.metadata:
                ballot.metadata.update({
                    'updated_by': user.username,
                    'last_update_method': 'mobile_api',
                    'last_updated_filename': uploaded_file.name,
                    'last_updated_at': timezone.now().isoformat(),
                    'qr_code_raw': qr_code_raw
                })
            else:
                ballot.metadata = {
                    'uploaded_by': user.username,
                    'upload_method': 'mobile_api',
                    'original_filename': uploaded_file.name,
                    'qr_code_raw': qr_code_raw
                }
            
            ballot.save()
            
            message = 'Cập nhật phiếu bầu thành công' + (' (từ QR code)' if qr_ballot_id else '')
            
            return JsonResponse({
                'success': True,
                'ballot_id': ballot.ballot_id,
                'is_update': True,
                'qr_ballot_id': qr_ballot_id,
                'qr_detected': qr_ballot_id is not None,
                'qr_hmac': qr_hmac,
                'filename': uploaded_file.name,
                'message': message
            }, status=200)
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_upload_ballots_batch(request, poll_id):
    """
    Upload hàng loạt phiếu bầu từ mobile
    
    POST /api/polls/<poll_id>/upload-batch/
    Header: Authorization: Bearer <token>
    Body: multipart/form-data
        - ballot_files: multiple files ảnh
    
    Response:
    {
        "success": true,
        "total": 10,
        "succeeded": 9,
        "failed": 1,
        "results": [
            {
                "filename": "image1.jpg",
                "success": true,
                "ballot_id": 123
            },
            {
                "filename": "image2.jpg",
                "success": false,
                "error": "File too large"
            }
        ]
    }
    """
    try:
        # Check poll exists
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission
        user = request.api_user
        
        # Kiểm tra quyền:
        # 1. Superuser toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên active có role 'manager' hoặc 'operator'
        has_permission = False
        
        if user.is_superuser:
            has_permission = True
        elif poll.created_by == user:
            has_permission = True
        else:
            try:
                poll_member = PollMember.objects.using('api_pool').get(poll=poll, account=user, status='active')
                if poll_member.role in ['manager', 'operator']:
                    has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền upload phiếu cho cuộc bỏ phiếu này'
            }, status=403)
        
        # Check files
        uploaded_files = request.FILES.getlist('ballot_files')
        
        if not uploaded_files:
            return JsonResponse({
                'success': False,
                'error': 'Missing files',
                'message': 'Vui lòng chọn ít nhất một file ảnh phiếu bầu'
            }, status=400)
        
        # Validate and process files
        allowed_extensions = ['jpg', 'jpeg', 'png', 'bmp', 'tiff']
        max_size = 10 * 1024 * 1024  # 10MB
        max_files = 50  # Giới hạn tối đa 50 file mỗi lần
        
        if len(uploaded_files) > max_files:
            return JsonResponse({
                'success': False,
                'error': 'Too many files',
                'message': f'Chỉ được upload tối đa {max_files} file mỗi lần'
            }, status=400)
        
        results = []
        succeeded = 0
        failed = 0
        
        # Sử dụng transaction để rollback nếu có lỗi
        try:
            with transaction.atomic():
                for uploaded_file in uploaded_files:
                    result = {
                        'filename': uploaded_file.name,
                        'success': False
                    }
                    
                    temp_file_path = None
                    
                    try:
                        # Validate file type
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        
                        if file_ext not in allowed_extensions:
                            result['error'] = f'Định dạng file không hợp lệ. Chỉ chấp nhận: {", ".join(allowed_extensions)}'
                            failed += 1
                            results.append(result)
                            # Hủy toàn bộ transaction
                            raise Exception(f'File {uploaded_file.name}: Định dạng không hợp lệ')
                        
                        # Validate file size
                        if uploaded_file.size > max_size:
                            result['error'] = 'Kích thước file vượt quá 10MB'
                            failed += 1
                            results.append(result)
                            # Hủy toàn bộ transaction
                            raise Exception(f'File {uploaded_file.name}: Vượt quá kích thước cho phép')
                        
                        # Tối ưu ảnh trước khi xử lý
                        optimized_file = optimize_ballot_image(uploaded_file)
                        
                        # Đọc QR code từ phiếu bầu đã tối ưu
                        qr_data = None
                        try:
                            # Lưu file tạm từ optimized_file để đọc QR
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_file:
                                optimized_file.seek(0)
                                for chunk in optimized_file.chunks():
                                    temp_file.write(chunk)
                                temp_file_path = temp_file.name
                            
                            # Reset file pointer để có thể sử dụng lại
                            optimized_file.seek(0)
                            
                            # Đọc chỉ QR code từ ảnh
                            qr_result = read_qr_code_only(temp_file_path)
                            
                            # Kiểm tra kết quả đọc QR
                            if not qr_result.get('success'):
                                result['error'] = f'Không thể đọc QR code: {qr_result.get("error", "Unknown error")}'
                                failed += 1
                                results.append(result)
                                raise Exception(f'File {uploaded_file.name}: {result["error"]}')
                            
                            if qr_result.get('qr_count', 0) == 0:
                                result['error'] = 'Không tìm thấy QR code trên phiếu bầu'
                                failed += 1
                                results.append(result)
                                raise Exception(f'File {uploaded_file.name}: Không tìm thấy QR code')
                            
                            # Lấy thông tin QR code
                            qr_codes = qr_result.get('qr_codes', [])
                            if qr_codes and 'parsed_data' in qr_codes[0]:
                                qr_data = qr_codes[0]['parsed_data']
                                result['qr_detected'] = True
                                result['qr_data'] = qr_data
                            elif qr_codes:
                                result['qr_detected'] = True
                                result['qr_data_raw'] = qr_codes[0].get('data', '')
                            else:
                                result['error'] = 'Không thể đọc dữ liệu từ QR code'
                                failed += 1
                                results.append(result)
                                raise Exception(f'File {uploaded_file.name}: Không thể đọc dữ liệu từ QR code')
                                
                        except Exception as qr_error:
                            # Nếu đọc QR thất bại, raise exception để rollback
                            if 'error' not in result:
                                result['error'] = f'Lỗi đọc QR code: {str(qr_error)}'
                                failed += 1
                                results.append(result)
                            raise
                        finally:
                            # Xóa file tạm
                            if temp_file_path and os.path.exists(temp_file_path):
                                try:
                                    os.unlink(temp_file_path)
                                except:
                                    pass
                        # Trích xuất ballot_id từ QR code
                        qr_ballot_id = None
                        qr_code_raw = None
                        
                        # Lấy dữ liệu QR code raw
                        if qr_data and 'data' in qr_data:
                            qr_code_raw = qr_data.get('data')
                        elif result.get('qr_data_raw'):
                            qr_code_raw = result['qr_data_raw']
                        
                        # Parse QR code có dạng "0:1:abcd" -> ballot_id = 1, hmac = abcd
                        qr_hmac = None
                        if qr_code_raw:
                            try:
                                parts = qr_code_raw.split(':')
                                if len(parts) < 2:
                                    result['error'] = f'Định dạng QR code không hợp lệ: {qr_code_raw}'
                                    failed += 1
                                    results.append(result)
                                    raise Exception(f'File {uploaded_file.name}: Định dạng QR code không hợp lệ')
                                
                                qr_ballot_id = int(parts[1])
                                result['qr_ballot_id'] = qr_ballot_id
                                
                                if len(parts) >= 3:
                                    qr_hmac = parts[2]  # HMAC signature
                            except (ValueError, IndexError) as parse_error:
                                result['error'] = f'Không thể parse ballot_id từ QR code: {qr_code_raw}'
                                failed += 1
                                results.append(result)
                                raise Exception(f'File {uploaded_file.name}: {result["error"]}')
                        
                        # Chuẩn bị metadata
                        metadata = {
                            'uploaded_by': user.username,
                            'upload_method': 'mobile_api_batch',
                            'original_filename': uploaded_file.name,
                            'qr_code_raw': qr_code_raw
                        }
                        
                        ballot = None
                        
                        # Kiểm tra phải có ballot_id từ QR
                        if not qr_ballot_id:
                            result['error'] = 'Không tìm thấy ballot_id trong QR code'
                            failed += 1
                            results.append(result)
                            raise Exception(f'File {uploaded_file.name}: Không tìm thấy ballot_id trong QR code')
                        
                        # Tìm ballot để update (CHỈ CHO PHÉP UPDATE)
                        try:
                            ballot = Ballot.objects.using('api_pool').get(ballot_id=qr_ballot_id, poll=poll)
                        except Ballot.DoesNotExist:
                            result['error'] = f'Không tìm thấy ballot_id {qr_ballot_id} trong cuộc bỏ phiếu này'
                            failed += 1
                            results.append(result)
                            raise Exception(f'File {uploaded_file.name}: Không tìm thấy ballot_id {qr_ballot_id}')
                        
                        # Delete old image file if exists
                        if ballot.ballot_image:
                            try:
                                ballot.ballot_image.delete(save=False)
                            except:
                                pass
                        
                        # Update ballot with new image (đã được tối ưu từ trước)
                        ballot.ballot_image = optimized_file
                        ballot.input_by_id = user.pk  # Dùng _id để tránh lỗi database router
                        #ballot.timestamp = timezone.now()
                        
                        # Update metadata
                        if ballot.metadata:
                            ballot.metadata.update({
                                'updated_by': user.username,
                                'last_update_method': 'mobile_api_batch',
                                'last_updated_filename': uploaded_file.name,
                                'last_updated_at': timezone.now().isoformat(),
                                'qr_code_raw': qr_code_raw
                            })
                        else:
                            ballot.metadata = metadata
                        
                        ballot.save()
                        
                        result['success'] = True
                        result['ballot_id'] = ballot.ballot_id
                        result['is_update'] = True
                        result['qr_hmac'] = qr_hmac
                        result['message'] = 'Đã cập nhật phiếu bầu từ QR code'
                        succeeded += 1
                        
                    except Exception as e:
                        result['error'] = str(e)
                        failed += 1
                        # Re-raise để rollback transaction
                        raise
                    finally:
                        # Đảm bảo xóa file tạm nếu còn
                        if temp_file_path and os.path.exists(temp_file_path):
                            try:
                                os.unlink(temp_file_path)
                            except:
                                pass
                    
                    results.append(result)
                
                # Nếu đến đây mà không có exception, commit transaction
                return JsonResponse({
                    'success': True,
                    'total': len(uploaded_files),
                    'succeeded': succeeded,
                    'failed': failed,
                    'message': f'Upload hoàn tất: {succeeded} thành công, {failed} thất bại',
                    'results': results
                }, status=201 if succeeded > 0 else 400)
        
        except Exception as e:
            # Transaction đã bị rollback tự động
            # Trả về lỗi chi tiết
            return JsonResponse({
                'success': False,
                'error': 'Batch upload cancelled',
                'message': f'Upload bị hủy do có lỗi: {str(e)}. Tất cả thay đổi đã được rollback.',
                'total': len(uploaded_files),
                'succeeded': 0,  # Tất cả đều bị rollback
                'failed': len(uploaded_files),
                'results': results
            }, status=400)
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_join_poll(request):
    """
    Tham gia cuộc bỏ phiếu bằng access_code
    
    POST /api/polls/join/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "access_code": "ABC-123-XYZ"
    }
    
    Response:
    {
        "success": true,
        "message": "Đã tham gia thành công" hoặc "Yêu cầu tham gia đã được gửi",
        "poll": {...},
        "status": "active" hoặc "pending"
    }
    """
    import json
    
    try:
        data = json.loads(request.body)
        access_code = data.get('access_code', '').strip().upper()
        
        if not access_code:
            return JsonResponse({
                'success': False,
                'error': 'Missing access code',
                'message': 'Vui lòng nhập mã tham gia'
            }, status=400)
        
        # Tìm poll theo access_code
        try:
            poll = Poll.objects.get(access_code=access_code)
        except Poll.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid access code',
                'message': 'Mã tham gia không hợp lệ'
            }, status=404)
        
        user = request.api_user
        
        # Kiểm tra xem user đã là thành viên chưa
        existing_member = PollMember.objects.filter(poll=poll, account=user).first()
        
        if existing_member:
            if existing_member.status == 'active':
                return JsonResponse({
                    'success': False,
                    'error': 'Already member',
                    'message': 'Bạn đã là thành viên của cuộc bỏ phiếu này'
                }, status=400)
            elif existing_member.status == 'pending':
                return JsonResponse({
                    'success': False,
                    'error': 'Request pending',
                    'message': 'Yêu cầu tham gia của bạn đang chờ được duyệt'
                }, status=400)
            elif existing_member.status == 'rejected':
                return JsonResponse({
                    'success': False,
                    'error': 'Request rejected',
                    'message': 'Yêu cầu tham gia của bạn đã bị từ chối'
                }, status=403)
        
        # Tạo PollMember mới
        with transaction.atomic():
            # Xác định status dựa vào require_approval
            if poll.require_approval:
                status = 'pending'
                message = 'Yêu cầu tham gia đã được gửi, chờ admin duyệt'
            else:
                status = 'active'
                message = 'Đã tham gia cuộc bỏ phiếu thành công'
            
            member = PollMember.objects.create(
                poll=poll,
                account=user,
                status=status,
                assigned_by=None  # Tự xin vào
            )
            
            # Nếu tự động duyệt, ghi nhận thời gian duyệt
            if status == 'active':
                member.approved_at = timezone.now()
                member.approved_by = None  # Tự động duyệt
                member.save(update_fields=['approved_at', 'approved_by'])
        
        return JsonResponse({
            'success': True,
            'message': message,
            'status': status,
            'poll': {
                'poll_id': poll.poll_id,
                'title': poll.title,
                'description': poll.description,
                'status': poll.status,
                'require_approval': poll.require_approval
            }
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_request_role_upgrade(request, poll_id):
    """
    Yêu cầu nâng cấp role trong cuộc bỏ phiếu
    
    POST /api/polls/<poll_id>/request-role/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "requested_role": "operator" hoặc "assistant"
    }
    
    Response:
    {
        "success": true,
        "message": "Yêu cầu nâng cấp role đã được gửi"
    }
    """
    import json
    
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        data = json.loads(request.body)
        requested_role = data.get('requested_role', '').lower()
        
        # Validate requested role - sử dụng roles mới trong PollMember
        if requested_role not in ['manager', 'operator', 'checkin']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid role',
                'message': 'Role yêu cầu phải là "manager", "operator" hoặc "checkin"'
            }, status=400)
        
        # Kiểm tra user đã là thành viên active chưa
        try:
            member = PollMember.objects.get(poll=poll, account=user, status='active')
        except PollMember.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Not a member',
                'message': 'Bạn chưa là thành viên của cuộc bỏ phiếu này'
            }, status=403)
        
        # Kiểm tra role hiện tại trong PollMember
        current_role = member.role
        
        # Nếu đã là manager thì không cần nâng cấp
        if current_role == 'manager':
            return JsonResponse({
                'success': False,
                'error': 'Already manager',
                'message': 'Bạn đã có quyền manager, không cần nâng cấp'
            }, status=400)
        
        # Nếu role hiện tại đã cao hơn hoặc bằng role yêu cầu
        role_hierarchy = {'user': 0, 'checkin': 1, 'operator': 2, 'manager': 3}
        if role_hierarchy.get(current_role, 0) >= role_hierarchy.get(requested_role, 0):
            return JsonResponse({
                'success': False,
                'error': 'Role already sufficient',
                'message': f'Role hiện tại của bạn ({current_role}) đã đủ hoặc cao hơn role yêu cầu'
            }, status=400)
        
        # Kiểm tra xem đã có yêu cầu nâng cấp chưa
        if member.requested_role_change:
            return JsonResponse({
                'success': False,
                'error': 'Request pending',
                'message': f'Bạn đã có yêu cầu nâng cấp lên {member.requested_role_change} đang chờ duyệt'
            }, status=400)
        
        # Cập nhật yêu cầu nâng cấp role (GIỮ NGUYÊN status='active')
        with transaction.atomic():
            member.requested_role_change = requested_role
            member.save(update_fields=['requested_role_change'])
        
        return JsonResponse({
            'success': True,
            'message': f'Yêu cầu nâng cấp lên role {requested_role} đã được gửi, chờ admin duyệt',
            'requested_role': requested_role
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_approve_role_request(request, poll_id, member_id):
    """
    Duyệt/từ chối yêu cầu nâng cấp role (chỉ admin/người tạo poll)
    
    POST /api/polls/<poll_id>/members/<member_id>/approve-role/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "action": "approve" hoặc "reject"
    }
    
    Response:
    {
        "success": true,
        "message": "Đã duyệt yêu cầu nâng cấp role"
    }
    """
    import json
    
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: chỉ superuser toàn hệ thống hoặc người tạo poll hoặc manager của poll
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            # Kiểm tra xem user có phải là manager của poll không
            try:
                manager_member = PollMember.objects.get(poll=poll, account=user, status='active', role='manager')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ superuser, người tạo poll hoặc manager mới có quyền duyệt yêu cầu'
            }, status=403)
        
        # Lấy thông tin member
        try:
            member = PollMember.objects.select_related('account').get(
                member_id=member_id,
                poll=poll
            )
        except PollMember.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Member not found',
                'message': 'Không tìm thấy thành viên này trong cuộc bỏ phiếu'
            }, status=404)
        
        # Kiểm tra có yêu cầu nâng cấp không
        if not member.requested_role_change:
            return JsonResponse({
                'success': False,
                'error': 'No request',
                'message': 'Thành viên này không có yêu cầu nâng cấp role'
            }, status=400)
        
        data = json.loads(request.body)
        action = data.get('action', '').lower()
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action',
                'message': 'Action phải là "approve" hoặc "reject"'
            }, status=400)
        
        with transaction.atomic():
            if action == 'approve':
                # Nâng cấp role trong PollMember (KHÔNG phải Account)
                requested_role = member.requested_role_change
                member.role = requested_role
                
                # Xóa yêu cầu và ghi nhận thông tin duyệt
                member.requested_role_change = None
                member.approved_at = timezone.now()
                member.approved_by = user
                member.save(update_fields=['role', 'requested_role_change', 'approved_at', 'approved_by'])
                
                message = f'Đã duyệt yêu cầu nâng cấp lên role {requested_role}'
                
            else:  # reject
                # Chỉ xóa yêu cầu, không thay đổi role
                requested_role = member.requested_role_change
                member.requested_role_change = None
                member.save(update_fields=['requested_role_change'])
                
                message = f'Đã từ chối yêu cầu nâng cấp lên role {requested_role}'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'action': action,
            'member': {
                'member_id': member.member_id,
                'username': member.account.username,
                'current_role': member.role
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@require_api_token
@require_http_methods(["GET"])
def api_get_role_requests(request, poll_id):
    """
    Lấy danh sách yêu cầu nâng cấp role (chỉ admin/người tạo poll)
    
    GET /api/polls/<poll_id>/role-requests/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "requests": [...]
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: chỉ superuser, người tạo poll hoặc manager
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            try:
                manager_member = PollMember.objects.get(poll=poll, account=user, status='active', role='manager')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ superuser, người tạo poll hoặc manager mới có quyền xem yêu cầu'
            }, status=403)
        
        # Lấy danh sách member có yêu cầu nâng cấp role
        members = PollMember.objects.filter(
            poll=poll,
            status='active',
            requested_role_change__isnull=False
        ).select_related('account').order_by('-assigned_at')
        
        requests = []
        for member in members:
            requests.append({
                'member_id': member.member_id,
                'username': member.account.username,
                'full_name': member.account.last_name or member.account.username,
                'current_role': member.role,
                'requested_role': member.requested_role_change,
                'assigned_at': member.assigned_at.isoformat() if member.assigned_at else None
            })
        
        return JsonResponse({
            'success': True,
            'count': len(requests),
            'requests': requests
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@require_api_token
@require_http_methods(["GET"])
def api_get_join_requests(request, poll_id):
    """
    Lấy danh sách yêu cầu tham gia cuộc bỏ phiếu (chỉ admin/người tạo poll)
    
    GET /api/polls/<poll_id>/join-requests/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "requests": [...]
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: chỉ superuser, người tạo poll hoặc manager
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            try:
                manager_member = PollMember.objects.get(poll=poll, account=user, status='active', role='manager')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ superuser, người tạo poll hoặc manager mới có quyền xem yêu cầu'
            }, status=403)
        
        # Lấy danh sách member đang chờ duyệt
        members = PollMember.objects.filter(
            poll=poll,
            status='pending'
        ).select_related('account').order_by('-assigned_at')
        
        requests = []
        for member in members:
            requests.append({
                'member_id': member.member_id,
                'username': member.account.username,
                'full_name': member.account.last_name or member.account.username,
                'email': member.account.email or '',
                'role': member.role,
                'assigned_at': member.assigned_at.isoformat() if member.assigned_at else None
            })
        
        return JsonResponse({
            'success': True,
            'count': len(requests),
            'requests': requests
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_approve_join_request(request, poll_id, member_id):
    """
    Duyệt/từ chối yêu cầu tham gia cuộc bỏ phiếu (chỉ admin/người tạo poll)
    
    POST /api/polls/<poll_id>/members/<member_id>/approve-join/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "action": "approve" hoặc "reject"
    }
    
    Response:
    {
        "success": true,
        "message": "Đã duyệt yêu cầu tham gia"
    }
    """
    import json
    
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: chỉ superuser, người tạo poll hoặc manager
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            try:
                manager_member = PollMember.objects.get(poll=poll, account=user, status='active', role='manager')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ superuser, người tạo poll hoặc manager mới có quyền duyệt yêu cầu'
            }, status=403)
        
        # Lấy thông tin member
        try:
            member = PollMember.objects.select_related('account').get(
                member_id=member_id,
                poll=poll
            )
        except PollMember.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Member not found',
                'message': 'Không tìm thấy thành viên này trong cuộc bỏ phiếu'
            }, status=404)
        
        # Kiểm tra trạng thái phải là pending
        if member.status != 'pending':
            return JsonResponse({
                'success': False,
                'error': 'Invalid status',
                'message': f'Thành viên này đang ở trạng thái {member.status}, không thể duyệt'
            }, status=400)
        
        data = json.loads(request.body)
        action = data.get('action', '').lower()
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action',
                'message': 'Action phải là "approve" hoặc "reject"'
            }, status=400)
        
        with transaction.atomic():
            if action == 'approve':
                # Duyệt tham gia - set status='active' và role mặc định là 'user'
                member.status = 'active'
                if not member.role:
                    member.role = 'user'  # Role mặc định khi vừa tham gia
                member.approved_at = timezone.now()
                member.approved_by = user
                member.save(update_fields=['status', 'role', 'approved_at', 'approved_by'])
                
                message = f'Đã duyệt {member.account.username} tham gia cuộc bỏ phiếu'
                
            else:  # reject
                # Từ chối tham gia
                member.status = 'rejected'
                member.save(update_fields=['status'])
                
                message = f'Đã từ chối {member.account.username} tham gia cuộc bỏ phiếu'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'action': action,
            'member': {
                'member_id': member.member_id,
                'username': member.account.username,
                'status': member.status
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_verify_ballot_hmac(request, poll_id, ballot_id):
    """
    Xác minh chữ ký HMAC của phiếu bầu
    
    POST /api/polls/<poll_id>/ballots/<ballot_id>/verify-hmac/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "hmac_signature": "abc123..."
    }
    
    Response:
    {
        "success": true,
        "verified": true,
        "ballot_id": 123,
        "message": "Chữ ký HMAC hợp lệ"
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission - Chỉ cần là thành viên active
        user = request.api_user
        has_permission = False
        
        if user.is_superuser:
            has_permission = True
        elif poll.created_by == user:
            has_permission = True
        else:
            try:
                PollMember.objects.get(poll=poll, account=user, status='active')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xác minh phiếu bầu trong cuộc bỏ phiếu này'
            }, status=403)
        
        # Get ballot
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id, poll=poll)
        except Ballot.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ballot not found',
                'message': 'Không tìm thấy phiếu bầu'
            }, status=404)
        
        # Get HMAC signature from request
        data = json.loads(request.body)
        hmac_signature = data.get('hmac_signature', '').strip()
        
        if not hmac_signature:
            return JsonResponse({
                'success': False,
                'error': 'Missing HMAC signature',
                'message': 'Vui lòng cung cấp chữ ký HMAC'
            }, status=400)
        
        # Verify HMAC
        try:
            verified = verify_ballot_from_qr(ballot, hmac_signature)
            
            if verified:
                return JsonResponse({
                    'success': True,
                    'verified': True,
                    'ballot_id': ballot_id,
                    'message': 'Chữ ký HMAC hợp lệ'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'verified': False,
                    'ballot_id': ballot_id,
                    'message': 'Chữ ký HMAC không hợp lệ. Phiếu bầu có thể bị giả mạo.'
                })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': 'HMAC verification error',
                'message': f'Lỗi xác minh HMAC: {str(e)}'
            }, status=500)
    
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@require_api_token
@require_http_methods(["GET"])
def api_ballot_list(request, poll_id):
    """
    Danh sách phiếu bầu đã upload
    
    GET /api/polls/<poll_id>/ballots/
    Header: Authorization: Bearer <token>
    
    Query params:
        - limit: số lượng (default 20)
        - offset: vị trí bắt đầu (default 0)
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission
        user = request.api_user
        
        # Kiểm tra quyền:
        # 1. Superuser toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên active của poll (tất cả roles đều được xem danh sách phiếu)
        has_permission = False
        
        if user.is_superuser:
            # Superuser toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên active của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='active')
                # Tất cả thành viên active đều được xem danh sách phiếu
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xem danh sách phiếu bầu của cuộc bỏ phiếu này'
            }, status=403)
        
        # Pagination
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        # Limit max 100
        limit = min(limit, 100)
        
        # Get ballots
        ballots = Ballot.objects.filter(poll=poll).order_by('-ballot_id')[offset:offset+limit]
        total_count = Ballot.objects.filter(poll=poll).count()
        
        ballot_list = []
        for ballot in ballots:
            ballot_list.append({
                'ballot_id': ballot.ballot_id,
                'timestamp': ballot.timestamp.isoformat() if ballot.timestamp else None,
                'is_checked': ballot.is_checked,
                'is_valid': ballot.is_valid,
                'image_url': ballot.ballot_image.url if ballot.ballot_image else None
            })
        
        return JsonResponse({
            'success': True,
            'total': total_count,
            'count': len(ballot_list),
            'limit': limit,
            'offset': offset,
            'ballots': ballot_list
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found'
        }, status=404)
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid pagination parameters'
        }, status=400)


# =====================================================
# STATISTICS APIs
# =====================================================

@require_api_token
@require_http_methods(["GET"])
def api_statistics(request):
    """
    Thống kê kết quả các cuộc bỏ phiếu
    
    GET /api/statistics/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "statistics": [
            {
                "poll_id": 1,
                "poll_title": "...",
                "top_candidate": "Nguyễn Văn A",
                "top_count": 150,
                "status": "counted",
                "first_ballot_id": 123
            }
        ]
    }
    """
    user = request.api_user
    
    # Lấy các cuộc bỏ phiếu dựa trên quyền
    if user.is_superuser:
        # Superuser xem được tất cả các cuộc bỏ phiếu
        polls = Poll.objects.all()
    else:
        # User khác chỉ xem được các cuộc bỏ phiếu mà họ là thành viên active
        polls = Poll.objects.filter(
            members__account=user,
            members__status='active'
        ).distinct()
    
    statistics_data = []
    for poll in polls:
        # Annotate số lượt chọn cho từng ứng viên thuộc poll này
        from django.db.models import Count
        candidates = Candidate.objects.filter(poll=poll).annotate(
            num_selected=Count('ballotselection')
        )
        
        # Tìm ứng viên được chọn nhiều nhất
        top_candidate = candidates.order_by('-num_selected', 'name').first()
        
        # Lấy ID của ballot đầu tiên trong poll này
        first_ballot = Ballot.objects.filter(poll=poll).order_by('ballot_id').first()
        first_ballot_id = first_ballot.ballot_id if first_ballot else None
        
        statistics_data.append({
            'poll_id': poll.poll_id,
            'poll_title': poll.title,
            'top_candidate': top_candidate.name if top_candidate else None,
            'top_count': top_candidate.num_selected if top_candidate else 0,
            'status': poll.status,
            'first_ballot_id': first_ballot_id,
        })
    
    return JsonResponse({
        'success': True,
        'count': len(statistics_data),
        'statistics': statistics_data
    })


@require_api_token
@require_http_methods(["GET"])
def api_statistics_detail(request, poll_id):
    """
    Thống kê chi tiết cho một cuộc bỏ phiếu
    
    GET /api/polls/<poll_id>/statistics/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "poll": {
            "poll_id": 1,
            "title": "...",
            "status": "counted"
        },
        "total_ballots": 100,
        "candidate_stats": [
            {
                "name": "Nguyễn Văn A",
                "count": 50
            },
            {
                "name": "Trần Thị B",
                "count": 30
            }
        ]
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền
        has_permission = False
        
        if user.is_superuser:
            has_permission = True
        elif poll.created_by == user:
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên active của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='active')
                has_permission = True
            except PollMember.DoesNotExist:
                pass
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xem thống kê của cuộc bỏ phiếu này'
            }, status=403)
        
        # Lấy danh sách ứng cử viên và số lượt được chọn
        from django.db.models import Count
        candidate_stats = Candidate.objects.filter(poll=poll).annotate(
            count=Count('ballotselection')
        ).values('name', 'count').order_by('-count', 'name')
        
        # Đếm số phiếu hợp lệ đã kiểm
        valid_checked_ballots = Ballot.objects.filter(
            poll=poll,
            is_valid=True,
            is_checked=True
        ).count()
        
        return JsonResponse({
            'success': True,
            'poll': {
                'poll_id': poll.poll_id,
                'title': poll.title,
                'description': poll.description,
                'status': poll.status
            },
            'total_ballots': valid_checked_ballots,
            'candidate_stats': list(candidate_stats)
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


# =====================================================
# VOTER MANAGEMENT APIs
# =====================================================

@require_api_token
@require_http_methods(["GET"])
def api_voter_list(request, poll_id):
    """
    Danh sách cử tri của cuộc bỏ phiếu
    
    GET /api/polls/<poll_id>/voters/
    Header: Authorization: Bearer <token>
    
    Query params:
        - limit: số lượng (default 50)
        - offset: vị trí bắt đầu (default 0)
        - search: tìm kiếm theo tên hoặc code_id
        - checked_in: filter theo trạng thái check-in (true/false)
    
    Response:
    {
        "success": true,
        "count": 100,
        "voters": [...]
    }
    """
    try:
        poll = Poll.objects.using('api_pool').get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, hoặc thành viên active của poll
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active'
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xem danh sách cử tri của cuộc bỏ phiếu này'
            }, status=403)
        
        # Parse query params
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        search = request.GET.get('search', '').strip()
        checked_in_filter = request.GET.get('checked_in', '').lower()
        
        # Query voters
        from django.db.models import Q
        voters = Voter.objects.filter(poll=poll)
        
        # Apply search filter
        if search:
            voters = voters.filter(
                Q(full_name__icontains=search) | 
                Q(code_id__icontains=search) |
                Q(email__icontains=search)
            )
        
        # Apply check-in filter
        if checked_in_filter == 'true':
            voters = voters.filter(has_checked_in=True)
        elif checked_in_filter == 'false':
            voters = voters.filter(has_checked_in=False)
        
        total_count = voters.count()
        voters = voters.order_by('-voter_id')[offset:offset + limit]
        
        voter_list = []
        for voter in voters:
            voter_list.append({
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in,
                'check_in_time': voter.check_in_time.isoformat() if voter.check_in_time else None,
                'check_in_by': voter.check_in_by.username if voter.check_in_by else None
            })
        
        return JsonResponse({
            'success': True,
            'count': total_count,
            'limit': limit,
            'offset': offset,
            'voters': voter_list
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameters',
            'message': 'Tham số không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)

@require_api_token
@require_http_methods(["GET"])
def api_voter_list_no_limit(request, poll_id):
    """
    Danh sách TẤT CẢ cử tri của cuộc bỏ phiếu (không phân trang - dùng để test)
    
    GET /api/polls/<poll_id>/voters/all/
    Header: Authorization: Bearer <token>
    
    Query params:
        - search: tìm kiếm theo tên hoặc code_id
        - checked_in: filter theo trạng thái check-in (true/false)
    
    Response:
    {
        "success": true,
        "count": 100,
        "voters": [...]
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, hoặc thành viên active của poll
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active'
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xem danh sách cử tri của cuộc bỏ phiếu này'
            }, status=403)
        
        # Parse query params
        search = request.GET.get('search', '').strip()
        checked_in_filter = request.GET.get('checked_in', '').lower()
        
        # Query voters
        from django.db.models import Q
        voters = Voter.objects.filter(poll=poll)
        
        # Apply search filter
        if search:
            voters = voters.filter(
                Q(full_name__icontains=search) | 
                Q(code_id__icontains=search) |
                Q(email__icontains=search)
            )
        
        # Apply check-in filter
        if checked_in_filter == 'true':
            voters = voters.filter(has_checked_in=True)
        elif checked_in_filter == 'false':
            voters = voters.filter(has_checked_in=False)
        
        # Lấy tất cả không phân trang
        total_count = voters.count()
        voters = voters.order_by('voter_id')  # Sắp xếp theo voter_id tăng dần
        
        voter_list = []
        for voter in voters:
            voter_list.append({
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in,
                'check_in_time': voter.check_in_time.isoformat() if voter.check_in_time else None,
                'check_in_by': voter.check_in_by.username if voter.check_in_by else None
            })
        
        return JsonResponse({
            'success': True,
            'count': total_count,
            'voters': voter_list
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_voter_create(request, poll_id):
    """
    Thêm cử tri mới vào cuộc bỏ phiếu
    
    POST /api/polls/<poll_id>/voters/create/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "full_name": "Nguyễn Văn A",
        "email": "email@example.com" (optional),
        "code_id": "CV001"
    }
    
    Response:
    {
        "success": true,
        "voter": {...}
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, manager hoặc checkin
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active',
                role__in=['manager', 'checkin']
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền thêm cử tri. Chỉ superuser, người tạo poll, manager hoặc checkin mới có quyền này'
            }, status=403)
        
        data = json.loads(request.body)
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        code_id = data.get('code_id', '').strip()
        
        # Validate input
        if not full_name:
            return JsonResponse({
                'success': False,
                'error': 'Invalid input',
                'message': 'Họ tên không được để trống'
            }, status=400)
        
        if not code_id:
            return JsonResponse({
                'success': False,
                'error': 'Invalid input',
                'message': 'Mã cử tri không được để trống'
            }, status=400)
        
        # Check duplicate code_id in this poll
        if Voter.objects.filter(poll=poll, code_id=code_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Duplicate code_id',
                'message': f'Mã cử tri {code_id} đã tồn tại trong cuộc bỏ phiếu này'
            }, status=400)
        
        # Check duplicate email in this poll (if provided)
        if email and Voter.objects.filter(poll=poll, email=email).exists():
            return JsonResponse({
                'success': False,
                'error': 'Duplicate email',
                'message': f'Email {email} đã tồn tại trong cuộc bỏ phiếu này'
            }, status=400)
        
        # Create voter
        with transaction.atomic():
            voter = Voter.objects.create(
                poll=poll,
                full_name=full_name,
                email=email if email else None,
                code_id=code_id,
                has_checked_in=False
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Thêm cử tri thành công',
            'voter': {
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in
            }
        }, status=201)
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["PUT"])
def api_voter_update(request, poll_id, voter_id):
    """
    Cập nhật thông tin cử tri
    
    PUT /api/polls/<poll_id>/voters/<voter_id>/
    Header: Authorization: Bearer <token>
    Body (JSON):
    {
        "full_name": "Nguyễn Văn A",
        "email": "email@example.com",
        "code_id": "CV001"
    }
    
    Note: Không cập nhật has_checked_in, check_in_time, check_in_by (dùng API check-in riêng)
    
    Response:
    {
        "success": true,
        "voter": {...}
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, manager hoặc checkin
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active',
                role__in=['manager', 'checkin']
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền sửa thông tin cử tri. Chỉ superuser, người tạo poll, manager hoặc checkin mới có quyền này'
            }, status=403)
        
        # Get voter
        try:
            voter = Voter.objects.get(voter_id=voter_id, poll=poll)
        except Voter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Voter not found',
                'message': 'Không tìm thấy cử tri'
            }, status=404)
        
        data = json.loads(request.body)
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        code_id = data.get('code_id', '').strip()
        
        # Validate input
        if not full_name:
            return JsonResponse({
                'success': False,
                'error': 'Invalid input',
                'message': 'Họ tên không được để trống'
            }, status=400)
        
        if not code_id:
            return JsonResponse({
                'success': False,
                'error': 'Invalid input',
                'message': 'Mã cử tri không được để trống'
            }, status=400)
        
        # Check duplicate code_id (exclude current voter)
        if Voter.objects.filter(poll=poll, code_id=code_id).exclude(voter_id=voter_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Duplicate code_id',
                'message': f'Mã cử tri {code_id} đã tồn tại trong cuộc bỏ phiếu này'
            }, status=400)
        
        # Check duplicate email (exclude current voter)
        if email and Voter.objects.filter(poll=poll, email=email).exclude(voter_id=voter_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Duplicate email',
                'message': f'Email {email} đã tồn tại trong cuộc bỏ phiếu này'
            }, status=400)
        
        # Update voter (không cập nhật has_checked_in, check_in_time, check_in_by)
        with transaction.atomic():
            voter.full_name = full_name
            voter.email = email if email else None
            voter.code_id = code_id
            voter.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Cập nhật thông tin cử tri thành công',
            'voter': {
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in,
                'check_in_time': voter.check_in_time.isoformat() if voter.check_in_time else None,
                'check_in_by': voter.check_in_by.username if voter.check_in_by else None
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["DELETE"])
def api_voter_delete(request, poll_id, voter_id):
    """
    Xóa cử tri
    
    DELETE /api/polls/<poll_id>/voters/<voter_id>/delete/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "message": "Xóa cử tri thành công"
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, manager hoặc checkin
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active',
                role__in=['manager', 'checkin']
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền xóa cử tri. Chỉ superuser, người tạo poll, manager hoặc checkin mới có quyền này'
            }, status=403)
        
        # Get and delete voter
        try:
            voter = Voter.objects.get(voter_id=voter_id, poll=poll)
            voter_name = voter.full_name
            with transaction.atomic():
                voter.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Đã xóa cử tri {voter_name} thành công'
            })
        except Voter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Voter not found',
                'message': 'Không tìm thấy cử tri'
            }, status=404)
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_voter_checkin(request, poll_id, voter_id):
    """
    Check-in cử tri (đánh dấu đã nhận phiếu)
    
    POST /api/polls/<poll_id>/voters/<voter_id>/checkin/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "message": "Check-in thành công",
        "voter": {...}
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, manager hoặc checkin
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active',
                role__in=['manager', 'checkin']
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền check-in cử tri. Chỉ superuser, người tạo poll, manager hoặc checkin mới có quyền này'
            }, status=403)
        
        # Get voter
        try:
            voter = Voter.objects.get(voter_id=voter_id, poll=poll)
        except Voter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Voter not found',
                'message': 'Không tìm thấy cử tri'
            }, status=404)
        
        # Check if already checked in
        if voter.has_checked_in:
            return JsonResponse({
                'success': False,
                'error': 'Already checked in',
                'message': f'Cử tri {voter.full_name} đã check-in lúc {voter.check_in_time.strftime("%H:%M %d/%m/%Y")}',
                'voter': {
                    'voter_id': voter.voter_id,
                    'full_name': voter.full_name,
                    'has_checked_in': voter.has_checked_in,
                    'check_in_time': voter.check_in_time.isoformat() if voter.check_in_time else None,
                    'check_in_by': voter.check_in_by.username if voter.check_in_by else None
                }
            }, status=400)
        
        # Perform check-in
        with transaction.atomic():
            voter.has_checked_in = True
            voter.check_in_time = timezone.now()
            voter.check_in_by = user
            voter.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Check-in thành công cho cử tri {voter.full_name}',
            'voter': {
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in,
                'check_in_time': voter.check_in_time.isoformat() if voter.check_in_time else None,
                'check_in_by': voter.check_in_by.username if voter.check_in_by else None
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_api_token
@require_http_methods(["POST"])
def api_voter_undo_checkin(request, poll_id, voter_id):
    """
    Hủy check-in cử tri (trường hợp check-in nhầm)
    
    POST /api/polls/<poll_id>/voters/<voter_id>/undo-checkin/
    Header: Authorization: Bearer <token>
    
    Response:
    {
        "success": true,
        "message": "Đã hủy check-in",
        "voter": {...}
    }
    """
    try:
        poll = Poll.objects.get(poll_id=poll_id)
        user = request.api_user
        
        # Kiểm tra quyền: superuser, người tạo poll, manager hoặc checkin
        has_permission = False
        if user.is_superuser or poll.created_by == user:
            has_permission = True
        else:
            member = PollMember.objects.filter(
                poll=poll, 
                account=user, 
                status='active',
                role__in=['manager', 'checkin']
            ).first()
            if member:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Bạn không có quyền hủy check-in. Chỉ superuser, người tạo poll, manager hoặc checkin mới có quyền này'
            }, status=403)
        
        # Get voter
        try:
            voter = Voter.objects.get(voter_id=voter_id, poll=poll)
        except Voter.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Voter not found',
                'message': 'Không tìm thấy cử tri'
            }, status=404)
        
        # Check if not checked in
        if not voter.has_checked_in:
            return JsonResponse({
                'success': False,
                'error': 'Not checked in',
                'message': f'Cử tri {voter.full_name} chưa check-in'
            }, status=400)
        
        # Undo check-in
        with transaction.atomic():
            voter.has_checked_in = False
            voter.check_in_time = None
            voter.check_in_by = None
            voter.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Đã hủy check-in cho cử tri {voter.full_name}',
            'voter': {
                'voter_id': voter.voter_id,
                'full_name': voter.full_name,
                'email': voter.email or '',
                'code_id': voter.code_id,
                'has_checked_in': voter.has_checked_in,
                'check_in_time': None,
                'check_in_by': None
            }
        })
        
    except Poll.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Poll not found',
            'message': 'Không tìm thấy cuộc bỏ phiếu'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)
