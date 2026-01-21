"""
Checking Timeout Handler - Thu hồi phiếu hậu kiểm bị timeout
"""
from django.utils import timezone
from datetime import timedelta
from ballot.models import Ballot


def cleanup_checking_stuck_tasks(timeout_minutes=5):
    """
    Thu hồi các phiếu hậu kiểm mà User giữ quá lâu (treo máy, tắt trình duyệt, quên không nộp).
    
    Hàm này cần được chạy định kỳ (ví dụ: 5 phút/lần) qua Cronjob hoặc Celery Beat.
    
    Args:
        timeout_minutes: int - Thời gian timeout tính bằng phút (default: 5 phút)
        
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

def force_release_checking_by_ballot_id(ballot_id):
    """
    Buộc mở khóa một phiếu hậu kiểm cụ thể (Admin intervention)
    
    Args:
        ballot_id: int - ID phiếu bầu cần mở khóa
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        ballot = Ballot.objects.get(
            ballot_id=ballot_id,
            checking_status='PROCESSING'
        )
        
        ballot.checking_status = 'NEW'
        ballot.checking_locked_by = None
        ballot.checking_locked_at = None
        ballot.save()
        
        return True, f"Đã mở khóa phiếu {ballot_id} thành công"
        
    except Ballot.DoesNotExist:
        return False, f"Không tìm thấy phiếu {ballot_id} đang ở trạng thái PROCESSING"
    except Exception as e:
        return False, f"Lỗi: {str(e)}"


def force_release_checking_by_user(user):
    """
    Buộc mở khóa tất cả phiếu hậu kiểm của một user (Admin intervention)
    
    Args:
        user: Account object - User cần mở khóa phiếu
        
    Returns:
        tuple: (success: bool, count: int, message: str)
    """
    try:
        ballots = Ballot.objects.filter(
            checking_locked_by=user,
            checking_status='PROCESSING'
        )
        
        count = ballots.count()
        
        if count > 0:
            ballots.update(
                checking_status='NEW',
                checking_locked_by=None,
                checking_locked_at=None
            )
            return True, count, f"Đã mở khóa {count} phiếu của user {user.username}"
        else:
            return True, 0, f"User {user.username} không có phiếu nào đang giữ"
            
    except Exception as e:
        return False, 0, f"Lỗi: {str(e)}"
