"""
Checking Timeout Handler - Thu hồi phiếu hậu kiểm bị timeout
"""
from django.utils import timezone
from datetime import timedelta
from ballot.models import Ballot


def cleanup_checking_stuck_tasks(timeout_minutes=5, poll_id=None):
    """
    Thu hồi các phiếu hậu kiểm mà User giữ quá lâu (treo máy, tắt trình duyệt, quên không nộp).
    
    Hàm này cần được chạy định kỳ (ví dụ: 5 phút/lần) qua Cronjob hoặc Celery Beat.
    
    Args:
        timeout_minutes: int - Thời gian timeout tính bằng phút (default: 5 phút)
        poll_id: int (optional) - ID của poll để filter (nếu None thì xử lý tất cả)
        
    Returns:
        dict: Thông tin về số lượng phiếu đã thu hồi
    """
    
    # Định nghĩa thời gian timeout
    timeout_threshold = timezone.now() - timedelta(minutes=timeout_minutes)
    
    # Tìm các phiếu đang PROCESSING nhưng đã quá hạn
    stuck_tasks = Ballot.objects.filter(
        checking_status='PROCESSING',
        checking_locked_at__lt=timeout_threshold
    )
    
    # Filter theo poll_id nếu được chỉ định
    if poll_id:
        stuck_tasks = stuck_tasks.filter(poll_id=poll_id)
    
    count = stuck_tasks.count()
    
    if count > 0:
        # Reset hàng loạt về trạng thái NEW
        # checking_locked_by = None để người khác có thể lấy được
        rows_updated = stuck_tasks.update(
            checking_status='NEW',
            checking_locked_by=None,
            checking_locked_at=None
        )
        message = f"[Checking Cronjob] Đã thu hồi {rows_updated} phiếu hậu kiểm bị treo."
        print(message)
        return {
            'success': True,
            'recovered': rows_updated,
            'message': message
        }
    else:
        message = "[Checking Cronjob] Hệ thống ổn định, không có phiếu hậu kiểm bị treo."
        print(message)
        return {
            'success': True,
            'recovered': 0,
            'message': message
        }
