"""
API View for Checking Cleanup
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from poll.models import Poll


@csrf_exempt
@require_http_methods(["POST"])
def api_cleanup_checking_timeout(request):
    """
    Thu hồi các phiếu hậu kiểm bị timeout (User giữ quá lâu)
    
    POST /api/checking/cleanup-timeout/
    
    Response:
    {
        "success": true,
        "recovered": 5,
        "message": "Đã thu hồi 5 phiếu hậu kiểm bị treo."
    }
    """
    try:
        from .checking_timeout import cleanup_checking_stuck_tasks
        
        # Gọi hàm cleanup với timeout 5 phút
        result = cleanup_checking_stuck_tasks(timeout_minutes=5)
        
        return JsonResponse(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_toggle_checking_cleanup(request):
    """
    Bật/tắt tự động cleanup hậu kiểm (toggle cờ is_checking_started)
    
    POST /api/checking/toggle-cleanup/
    Body: {
        "poll_id": 123
    }
    
    Response:
    {
        "success": true,
        "is_active": true,
        "message": "Đã bật tự động thu hồi phiếu hậu kiểm"
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        poll_id = data.get('poll_id')
        
        if not poll_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing poll_id'
            }, status=400)
        
        # Lấy Poll
        try:
            poll = Poll.objects.get(poll_id=poll_id)
        except Poll.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Poll không tồn tại'
            }, status=404)
        
        # Toggle cờ is_checking_started
        poll.is_checking_started = not poll.is_checking_started
        poll.save(update_fields=['is_checking_started'])
        
        # Trả về trạng thái mới
        if poll.is_checking_started:
            message = "Đã bật tự động thu hồi phiếu hậu kiểm (chạy mỗi 3 phút)"
        else:
            message = "Đã tắt tự động thu hồi phiếu hậu kiểm"
        
        return JsonResponse({
            'success': True,
            'is_active': poll.is_checking_started,
            'message': message
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)
