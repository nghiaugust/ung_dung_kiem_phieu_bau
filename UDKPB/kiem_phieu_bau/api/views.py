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
from quan_ly_phieu_bau.models import Poll, Ballot, Candidate


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
        if user.role != 'admin' and poll.created_by != user:
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
        if user.role != 'admin' and poll.created_by != user:
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
        if user.role != 'admin' and poll.created_by != user:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
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
