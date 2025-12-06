"""
API Views cho Mobile App
Đơn giản, không dùng DRF
"""
import os
import uuid
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import APIToken
from .authentication import require_api_token
from poll.models import Poll, Candidate, PollMember
from ballot.models import Ballot


# =====================================================
# AUTHENTICATION APIs
# =====================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    """
    API Login - Trả về token
    
    POST /api/login/
    Body (JSON):
    {
        "username": "string",
        "password": "string"
    }
    
    Response:
    {
        "success": true,
        "token": "abc123...",
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
        
        # Update last used
        token.last_used = timezone.now()
        token.save(update_fields=['last_used'])
        
        return JsonResponse({
            'success': True,
            'token': token.token,
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
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
            'role': user.role,
            'created_at': user.created_at.isoformat() if user.created_at else None
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
    
    Response:
    {
        "success": true,
        "polls": [...]
    }
    """
    user = request.api_user
    
    # Admin xem tất cả, user khác chỉ xem của mình
    if user.role == 'admin':
        polls = Poll.objects.all()
    else:
        polls = Poll.objects.filter(created_by=user)
    
    polls = polls.order_by('-poll_id')[:50]  # Limit 50 polls gần nhất
    
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
        'count': len(poll_list),
        'polls': poll_list
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
        # 1. Admin toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên của poll có role là 'admin' hoặc 'assistant'
        has_permission = False
        
        if user.role == 'admin':
            # Admin toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên đã được duyệt của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='approved')
                # Kiểm tra role của user trong Account model
                if user.role in ['admin', 'assistant']:
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
                'candidates': candidate_list
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
    Upload phiếu bầu từ mobile
    
    POST /api/polls/<poll_id>/upload/
    Header: Authorization: Bearer <token>
    Body: multipart/form-data
        - ballot_file: file ảnh
    
    Response:
    {
        "success": true,
        "ballot_id": 123,
        "message": "Upload thành công"
    }
    """
    try:
        # Check poll exists
        poll = Poll.objects.get(poll_id=poll_id)
        
        # Check permission
        user = request.api_user
        
        # Kiểm tra quyền:
        # 1. Admin toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên của poll có role là 'admin' hoặc 'operator'
        has_permission = False
        
        if user.role == 'admin':
            # Admin toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên đã được duyệt của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='approved')
                # Kiểm tra role của user trong Account model
                if user.role in ['admin', 'operator']:
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
        
        # Save file
        with transaction.atomic():
            # Create directory
            poll_dir = os.path.join(settings.MEDIA_ROOT, str(poll_id))
            os.makedirs(poll_dir, exist_ok=True)
            
            # Generate unique filename
            unique_id = uuid.uuid4().hex[:8]
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ballot_{timestamp}_{unique_id}.{file_ext}"
            file_path = os.path.join(poll_dir, filename)
            
            # Write file
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Create Ballot record
            rel_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
            ballot = Ballot.objects.create(
                poll=poll,
                ballot_file_path=rel_path,
                timestamp=timezone.now(),
                metadata={
                    'uploaded_by': user.username,
                    'upload_method': 'mobile_api',
                    'original_filename': uploaded_file.name
                }
            )
            
            return JsonResponse({
                'success': True,
                'ballot_id': ballot.ballot_id,
                'filename': filename,
                'message': 'Upload phiếu bầu thành công'
            }, status=201)
        
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
        "status": "approved" hoặc "pending"
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
            if existing_member.status == 'approved':
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
                status = 'approved'
                message = 'Đã tham gia cuộc bỏ phiếu thành công'
            
            member = PollMember.objects.create(
                poll=poll,
                account=user,
                status=status,
                assigned_by=None  # Tự xin vào
            )
            
            # Nếu tự động duyệt, ghi nhận thời gian duyệt
            if status == 'approved':
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
        
        # Validate requested role
        if requested_role not in ['operator', 'assistant']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid role',
                'message': 'Role yêu cầu phải là "operator" hoặc "assistant"'
            }, status=400)
        
        # Kiểm tra user đã là thành viên chưa
        try:
            member = PollMember.objects.get(poll=poll, account=user, status='approved')
        except PollMember.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Not a member',
                'message': 'Bạn chưa là thành viên của cuộc bỏ phiếu này'
            }, status=403)
        
        # Kiểm tra role hiện tại của user trong Account
        current_account_role = user.role
        
        # Nếu đã là admin thì không cần nâng cấp
        if current_account_role == 'admin':
            return JsonResponse({
                'success': False,
                'error': 'Already admin',
                'message': 'Bạn đã có quyền admin, không cần nâng cấp'
            }, status=400)
        
        # Nếu role hiện tại đã cao hơn hoặc bằng role yêu cầu
        role_hierarchy = {'user': 0, 'operator': 1, 'assistant': 2, 'admin': 3}
        if role_hierarchy.get(current_account_role, 0) >= role_hierarchy.get(requested_role, 0):
            return JsonResponse({
                'success': False,
                'error': 'Role already sufficient',
                'message': f'Role hiện tại của bạn ({current_account_role}) đã đủ hoặc cao hơn role yêu cầu'
            }, status=400)
        
        # Kiểm tra xem đã có yêu cầu nâng cấp chưa
        if member.requested_role_change:
            return JsonResponse({
                'success': False,
                'error': 'Request pending',
                'message': f'Bạn đã có yêu cầu nâng cấp lên {member.requested_role_change} đang chờ duyệt'
            }, status=400)
        
        # Cập nhật yêu cầu nâng cấp role (GIỮ NGUYÊN status='approved')
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
        
        # Kiểm tra quyền: chỉ admin toàn hệ thống hoặc người tạo poll
        if user.role != 'admin' and poll.created_by != user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ admin hoặc người tạo poll mới có quyền duyệt yêu cầu'
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
                # Nâng cấp role trong Account
                requested_role = member.requested_role_change
                member.account.role = requested_role
                member.account.save(update_fields=['role'])
                
                # Xóa yêu cầu và ghi nhận thông tin duyệt
                member.requested_role_change = None
                member.approved_at = timezone.now()
                member.approved_by = user
                member.save(update_fields=['requested_role_change', 'approved_at', 'approved_by'])
                
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
                'current_role': member.account.role
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
        
        # Kiểm tra quyền: chỉ admin toàn hệ thống hoặc người tạo poll
        if user.role != 'admin' and poll.created_by != user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ admin hoặc người tạo poll mới có quyền xem yêu cầu'
            }, status=403)
        
        # Lấy danh sách member có yêu cầu nâng cấp role
        members = PollMember.objects.filter(
            poll=poll,
            status='approved',
            requested_role_change__isnull=False
        ).select_related('account').order_by('-assigned_at')
        
        requests = []
        for member in members:
            requests.append({
                'member_id': member.member_id,
                'username': member.account.username,
                'full_name': member.account.last_name or member.account.username,
                'current_role': member.account.role,
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
        
        # Kiểm tra quyền: chỉ admin toàn hệ thống hoặc người tạo poll
        if user.role != 'admin' and poll.created_by != user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ admin hoặc người tạo poll mới có quyền xem yêu cầu'
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
                'role': member.account.role,
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
        
        # Kiểm tra quyền: chỉ admin toàn hệ thống hoặc người tạo poll
        if user.role != 'admin' and poll.created_by != user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'Chỉ admin hoặc người tạo poll mới có quyền duyệt yêu cầu'
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
                # Duyệt tham gia
                member.status = 'approved'
                member.approved_at = timezone.now()
                member.approved_by = user
                member.save(update_fields=['status', 'approved_at', 'approved_by'])
                
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
        # 1. Admin toàn hệ thống
        # 2. Người tạo poll
        # 3. Thành viên của poll có role là 'admin' hoặc 'assistant'
        has_permission = False
        
        if user.role == 'admin':
            # Admin toàn hệ thống
            has_permission = True
        elif poll.created_by == user:
            # Người tạo poll
            has_permission = True
        else:
            # Kiểm tra xem user có phải là thành viên đã được duyệt của poll không
            try:
                poll_member = PollMember.objects.get(poll=poll, account=user, status='approved')
                # Kiểm tra role của user trong Account model
                if user.role in ['admin', 'assistant']:
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
                'file_url': f"{settings.MEDIA_URL}{ballot.ballot_file_path}" if ballot.ballot_file_path else None
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
