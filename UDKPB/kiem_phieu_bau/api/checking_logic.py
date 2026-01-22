"""
Checking Logic - Hệ thống phân phối và quản lý hậu kiểm phiếu bầu
"""
from django.db import transaction
from django.utils import timezone
from ballot.models import Ballot


class CheckingDistributionService:
    """
    Service xử lý phân phối phiếu bầu cho hậu kiểm với cơ chế khóa
    """
    
    @staticmethod
    def get_tasks_for_checking(user, poll_id=None, batch_size=10):
        """
        Lấy phiếu cho User để hậu kiểm.
        
        Logic:
        1. Nếu User đang có phiếu chưa làm xong -> Trả lại phiếu đó (Xử lý F5).
        2. Nếu không -> Lấy batch_size phiếu mới và khóa lại (Database Lock).
        
        Args:
            user: Account object - người dùng yêu cầu lấy phiếu
            poll_id: int (optional) - ID cuộc bỏ phiếu (nếu muốn filter theo poll)
            batch_size: int - số lượng phiếu tối đa lấy ra (default 10)
            
        Returns:
            list: Danh sách các Ballot objects đã được gán cho user
        """
        
        # BƯỚC 1: Kiểm tra "Hàng tồn"
        # Tìm các phiếu user này đang giữ mà chưa làm xong
        existing_tasks_query = Ballot.objects.filter(
            checking_locked_by=user,
            checking_status='PROCESSING'
        )
        
        # Filter theo poll nếu được chỉ định
        if poll_id:
            existing_tasks_query = existing_tasks_query.filter(poll_id=poll_id)
        
        existing_tasks = existing_tasks_query.select_related('poll')
        
        # Nếu tìm thấy -> Trả về ngay (User F5 hoặc mở lại trình duyệt)
        if existing_tasks.exists():
            return list(existing_tasks)

        # BƯỚC 2: Nếu rảnh rỗi -> Phân phối phiếu mới
        # Dùng transaction.atomic để đảm bảo tính toàn vẹn dữ liệu
        with transaction.atomic():
            # KỸ THUẬT: select_for_update(skip_locked=True)
            # - Khóa các dòng này lại để user khác không lấy được.
            # - skip_locked=True: Nếu dòng đang bị user khác khóa, bỏ qua luôn không cần chờ
            new_tasks_query = Ballot.objects.filter(
                checking_status='NEW',
                process_status='completed',   # Đã hoàn thành upload
                counting_status='completed'   # Đã hoàn thành kiểm phiếu (counting)
            ).select_for_update(skip_locked=True).order_by('ballot_id')
            
            # Filter theo poll nếu được chỉ định
            if poll_id:
                new_tasks_query = new_tasks_query.filter(poll_id=poll_id)
            
            new_tasks = list(new_tasks_query[:batch_size])

            # Nếu kho hết phiếu
            if not new_tasks:
                return []

            # Cập nhật trạng thái phiếu: Gán cho User này
            now = timezone.now()
            ids_to_update = [task.ballot_id for task in new_tasks]
            
            Ballot.objects.filter(ballot_id__in=ids_to_update).update(
                checking_status='PROCESSING',
                checking_locked_by=user,
                checking_locked_at=now
            )
            
            # Trả về danh sách phiếu vừa lấy được (đã cập nhật object trong memory để trả về API)
            for task in new_tasks:
                task.checking_status = 'PROCESSING'
                task.checking_locked_by = user
                task.checking_locked_at = now
                
            return new_tasks

    @staticmethod
    def submit_checking_result(user, ballot_id, result_data):
        """
        Xử lý nộp kết quả hậu kiểm.
        
        Kiểm tra kỹ xem phiếu có còn của User không 
        (đề phòng trường hợp đã bị Timeout thu hồi hoặc admin can thiệp).
        Kiểm tra timeout 5 phút - nếu quá thời gian thì không cho nộp.
        
        Args:
            user: Account object - người dùng nộp kết quả
            ballot_id: int - ID phiếu bầu
            result_data: dict - Kết quả hậu kiểm, ví dụ:
                {
                    "is_post_checked": True,
                    "is_valid": True/False,
                    "notes": "Ghi chú nếu có"
                }
                
        Returns:
            tuple: (is_success: bool, message: str)
        """
        CHECKING_TIMEOUT_MINUTES = 5
        
        try:
            with transaction.atomic():
                # Tìm và khóa dòng dữ liệu để update
                ballot = Ballot.objects.select_for_update().get(
                    ballot_id=ballot_id,
                    checking_locked_by=user,        # BẮT BUỘC: Phải đúng là user này
                    checking_status='PROCESSING'    # BẮT BUỘC: Phải đang ở trạng thái làm việc
                )
                
                # Kiểm tra timeout 5 phút
                if ballot.checking_locked_at:
                    now = timezone.now()
                    time_elapsed = now - ballot.checking_locked_at
                    timeout_seconds = CHECKING_TIMEOUT_MINUTES * 60
                    
                    if time_elapsed.total_seconds() > timeout_seconds:
                        # Quá thời gian - Kiểm tra kỹ xem phiếu có đúng đang do user này lock không
                        # (Tránh trường hợp cronjob đã thu hồi và người khác đã lock lại)
                        if ballot.checking_locked_by == user:
                            # Chắc chắn đúng user này đang lock -> Mở khóa
                            ballot.checking_status = 'NEW'
                            ballot.checking_locked_by = None
                            ballot.checking_locked_at = None
                            ballot.save()
                            
                            return False, f"Đã hết thời gian hậu kiểm ({CHECKING_TIMEOUT_MINUTES} phút). Phiếu không được kiểm."
                        else:
                            # Phiếu không còn thuộc user này (đã bị thu hồi và người khác lock)
                            return False, "Phiếu này đã hết hạn hoặc không còn thuộc về bạn."
                
                # Update kết quả hậu kiểm (is_post_checked tự động = True khi checking_status='DONE')
                ballot.is_valid = result_data.get('is_valid', ballot.is_valid)
                ballot.checking_status = 'DONE'
                
                # Có thể lưu thêm notes vào metadata nếu cần
                if result_data.get('notes'):
                    if ballot.metadata is None:
                        ballot.metadata = {}
                    ballot.metadata['checking_notes'] = result_data.get('notes')
                
                ballot.save()
                return True, "Hậu kiểm thành công"
                
        except Ballot.DoesNotExist:
            # Rơi vào đây nghĩa là:
            # 1. Phiếu không tồn tại
            # 2. Hoặc phiếu đã bị Cronjob thu hồi do làm quá lâu
            # 3. Hoặc phiếu đã bị người khác làm xong
            # 4. Hoặc phiếu đã bị admin thu hồi
            return False, "Phiếu này đã hết hạn hoặc không thuộc về bạn. Vui lòng tải lại trang."
    
    @staticmethod
    def release_checking_lock(user, ballot_id):
        """
        Mở khóa phiếu đang hậu kiểm (User muốn bỏ qua phiếu này).
        
        Args:
            user: Account object - người dùng yêu cầu mở khóa
            ballot_id: int - ID phiếu bầu
            
        Returns:
            tuple: (is_success: bool, message: str)
        """
        try:
            with transaction.atomic():
                ballot = Ballot.objects.select_for_update().get(
                    ballot_id=ballot_id,
                    checking_locked_by=user,
                    checking_status='PROCESSING'
                )
                
                # Reset về trạng thái NEW
                ballot.checking_status = 'NEW'
                ballot.checking_locked_by = None
                ballot.checking_locked_at = None
                ballot.save()
                
                return True, "Đã mở khóa phiếu thành công"
                
        except Ballot.DoesNotExist:
            return False, "Không thể mở khóa phiếu này"
    
    @staticmethod
    def get_checking_statistics(user=None, poll_id=None):
        """
        Lấy thống kê hậu kiểm.
        
        Args:
            user: Account object (optional) - nếu muốn xem thống kê của 1 user
            poll_id: int (optional) - nếu muốn xem thống kê của 1 poll
            
        Returns:
            dict: Thống kê hậu kiểm
        """
        query = Ballot.objects.filter(counting_status='completed')  # Chỉ đếm phiếu đã kiểm counting
        
        if poll_id:
            query = query.filter(poll_id=poll_id)
        
        if user:
            # Thống kê của 1 user cụ thể
            stats = {
                'total_assigned': query.filter(checking_locked_by=user).count(),
                'processing': query.filter(checking_locked_by=user, checking_status='PROCESSING').count(),
                'completed': query.filter(checking_locked_by=user, checking_status='DONE').count(),
            }
        else:
            # Thống kê tổng quát
            stats = {
                'total_ballots': query.count(),
                'new': query.filter(checking_status='NEW').count(),
                'processing': query.filter(checking_status='PROCESSING').count(),
                'done': query.filter(checking_status='DONE').count(),
            }
        
        return stats
