"""
Auto Check Scheduler - Định kỳ quét và kiểm phiếu tự động
Chạy mỗi 15 giây, quét các phiếu chưa kiểm và tự động xử lý
"""
import threading
import time
from django.db.models import Q
from django.db import models
from ballot.models import Ballot
from preprocessing.models import PreprocessedBallot, BallotCell
from .models import AIModelResult
from preprocessing.views import process_single_ballot_wrapper
import logging

logger = logging.getLogger(__name__)


class AutoCheckScheduler:
    """
    Background scheduler tự động kiểm phiếu
    - Chạy mỗi 15 giây
    - Quét các poll đã bật auto_check_enabled
    - Tìm phiếu chưa kiểm → Tiền xử lý → Kiểm phiếu
    """
    
    def __init__(self, interval=15):
        self.interval = interval  # Giây
        self.running = False
        self.thread = None
        self._lock = threading.Lock()
    
    def start(self):
        """Khởi động scheduler"""
        with self._lock:
            if self.running:
                logger.warning("[AUTO_CHECK_SCHEDULER] Already running")
                return
            
            self.running = True
            self.thread = threading.Thread(
                target=self._run,
                name="AutoCheckScheduler",
                daemon=True
            )
            self.thread.start()
            logger.info(f"[AUTO_CHECK_SCHEDULER] Started (interval={self.interval}s)")
    
    def stop(self):
        """Dừng scheduler"""
        with self._lock:
            if not self.running:
                return
            
            self.running = False
            logger.info("[AUTO_CHECK_SCHEDULER] Stopped")
    
    def _run(self):
        """Main loop của scheduler"""
        logger.info("[AUTO_CHECK_SCHEDULER] Main loop started")
        
        while self.running:
            try:
                self._check_and_process_ballots()
            except Exception as e:
                logger.error(f"[AUTO_CHECK_SCHEDULER] Error in main loop: {e}", exc_info=True)
            
            # Sleep 15 giây
            time.sleep(self.interval)
        
        logger.info("[AUTO_CHECK_SCHEDULER] Main loop exited")
    
    def _check_and_process_ballots(self):
        """
        Quét và xử lý các phiếu chưa kiểm
        """
        try:
            # Tìm các poll đã bật auto_check
            ai_results = AIModelResult.objects.filter(
                auto_check_enabled=True
            ).select_related('poll').order_by('-created_at')
            
            if not ai_results:
                return
            
            # Group by poll để tránh xử lý trùng
            processed_polls = set()
            
            for ai_result in ai_results:
                poll = ai_result.poll
                
                # Skip nếu đã xử lý poll này
                if poll.poll_id in processed_polls:
                    continue
                
                processed_polls.add(poll.poll_id)
                
                # Kiểm tra giới hạn
                if ai_result.auto_check_max_ballots:
                    if ai_result.auto_check_processed >= ai_result.auto_check_max_ballots:
                        logger.info(f"[AUTO_CHECK_SCHEDULER] Poll {poll.poll_id}: Reached limit {ai_result.auto_check_max_ballots}, disabling auto check")
                        ai_result.auto_check_enabled = False
                        ai_result.save(update_fields=['auto_check_enabled'])
                        continue
                
                # Tìm các ballot chưa kiểm của poll này
                unchecked_ballots = Ballot.objects.filter(
                    poll=poll,
                    is_checked=False,
                    ballot_image__isnull=False  # Phải có ảnh
                ).exclude(
                    ballot_image=''  # Loại trừ ảnh rỗng
                ).order_by('ballot_id')[:5]  # Mỗi lần xử lý tối đa 5 phiếu
                
                if not unchecked_ballots:
                    continue
                
                logger.info(f"[AUTO_CHECK_SCHEDULER] Poll {poll.poll_id}: Found {len(unchecked_ballots)} unchecked ballots")
                
                # Xử lý từng ballot trong thread riêng
                for ballot in unchecked_ballots:
                    # Kiểm tra lại giới hạn
                    ai_result.refresh_from_db()
                    if ai_result.auto_check_max_ballots:
                        if ai_result.auto_check_processed >= ai_result.auto_check_max_ballots:
                            logger.info(f"[AUTO_CHECK_SCHEDULER] Poll {poll.poll_id}: Reached limit during processing")
                            ai_result.auto_check_enabled = False
                            ai_result.save(update_fields=['auto_check_enabled'])
                            break
                    
                    # Khởi động thread xử lý cho ballot này
                    self._process_ballot_async(ballot, ai_result)
                    
                    # Delay nhỏ giữa các ballot
                    time.sleep(0.5)
        
        except Exception as e:
            logger.error(f"[AUTO_CHECK_SCHEDULER] Error checking ballots: {e}", exc_info=True)
    
    def _process_ballot_async(self, ballot, ai_result):
        """
        Xử lý ballot trong thread riêng
        Luồng: Kiểm tra tiền xử lý → Tiền xử lý (nếu cần) → Kiểm phiếu
        """
        thread = threading.Thread(
            target=self._process_ballot_worker,
            args=(ballot.ballot_id, ai_result.result_id),
            name=f"AutoCheck-Ballot-{ballot.ballot_id}",
            daemon=True
        )
        thread.start()
    
    def _process_ballot_worker(self, ballot_id, ai_result_id):
        """
        Worker xử lý ballot
        """
        try:
            # Lấy lại ballot từ DB
            ballot = Ballot.objects.select_related('poll').get(ballot_id=ballot_id)
            ai_result = AIModelResult.objects.get(result_id=ai_result_id)
            
            logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Starting processing")
            
            # Bước 1: Kiểm tra xem đã tiền xử lý chưa
            preprocessed = PreprocessedBallot.objects.filter(
                ballot=ballot,
                status='completed'
            ).first()
            
            if not preprocessed:
                # Chưa tiền xử lý → Tiền xử lý trước
                logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Starting preprocessing")
                
                try:
                    result = process_single_ballot_wrapper(ballot)
                    
                    if result.get('status') != 'success':
                        logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Preprocessing failed - {result.get('message')}")
                        return
                    
                    # Lấy kết quả tiền xử lý
                    preprocessed = PreprocessedBallot.objects.filter(
                        ballot=ballot,
                        status='completed'
                    ).first()
                    
                    if not preprocessed:
                        logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Preprocessing completed but no result found")
                        return
                    
                    logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Preprocessing completed")
                
                except Exception as e:
                    logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Preprocessing error - {e}", exc_info=True)
                    return
            
            # Bước 2: Kiểm tra xem đã kiểm phiếu chưa
            ballot.refresh_from_db()
            if ballot.is_checked:
                logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Already checked, skip")
                return
            
            # Bước 3: Kiểm phiếu
            logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Starting auto check")
            
            try:
                # Import hàm xử lý từ signal
                from counting.signals import process_single_ballot_auto
                
                # Lấy config từ ai_result
                config = ai_result.result_model.get('config', {})
                config_type = config.get('type')
                
                if config_type not in ['config1', 'config2']:
                    logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Invalid config type {config_type}")
                    return
                
                # Lấy start_row và end_row
                start_row = config.get('start_row', 2)
                end_row = config.get('end_row')
                
                # Xác định các dòng cần xử lý
                if end_row is not None:
                    rows_to_process = list(range(start_row, end_row + 1))
                else:
                    # Lấy tất cả các dòng từ start_row
                    max_row = BallotCell.objects.filter(
                        preprocessed_ballot=preprocessed
                    ).aggregate(max_row=models.Max('row'))['max_row']
                    if max_row:
                        rows_to_process = list(range(start_row, max_row + 1))
                    else:
                        logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: No rows found")
                        return
                
                logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Processing {len(rows_to_process)} rows")
                
                # Gọi hàm xử lý chung
                process_single_ballot_auto(ballot, ai_result, config_type, config, rows_to_process)
                
                # Kiểm tra kết quả
                ballot.refresh_from_db()
                ai_result.refresh_from_db()
                
                if ballot.is_checked:
                    logger.info(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Auto check completed ({ai_result.auto_check_processed}/{ai_result.auto_check_max_ballots or 'unlimited'})")
                else:
                    logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Ballot not marked as checked after processing")
            
            except Exception as e:
                logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Auto check error - {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"[AUTO_CHECK_SCHEDULER] Ballot {ballot_id}: Worker error - {e}", exc_info=True)


# Global scheduler instance
_scheduler = None


def start_scheduler(interval=15):
    """Khởi động global scheduler"""
    global _scheduler
    
    if _scheduler is None:
        _scheduler = AutoCheckScheduler(interval=interval)
    
    _scheduler.start()
    return _scheduler


def stop_scheduler():
    """Dừng global scheduler"""
    global _scheduler
    
    if _scheduler:
        _scheduler.stop()


def get_scheduler():
    """Lấy global scheduler instance"""
    return _scheduler
