"""
Signal handlers cho tự động tiền xử lý
Luồng: Upload → (commit) → Background Preprocessing → (commit) → Background Auto Check
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from ballot.models import Ballot
from .models import PreprocessedBallot
from .views import process_single_ballot_wrapper
import threading
import time


@receiver(post_save, sender=Ballot)
def auto_preprocess_ballot_on_upload(sender, instance, created, **kwargs):
	"""
	Tự động tiền xử lý khi có ballot mới được upload ảnh
	
	QUAN TRỌNG:
	- Chạy SAU KHI transaction upload commit (không block upload)
	- Chạy trong background thread riêng
	- Khi hoàn thành sẽ trigger auto_check_ballot_on_preprocess
	"""
	# Chỉ xử lý khi ballot có ảnh
	if not instance.ballot_image:
		return
	
	# Kiểm tra xem ballot đã được tiền xử lý chưa
	if PreprocessedBallot.objects.filter(ballot=instance, status='completed').exists():
		return
	
	# Lên lịch chạy SAU KHI transaction upload hoàn tất
	transaction.on_commit(lambda: _start_auto_preprocess_background(instance.ballot_id))


def _start_auto_preprocess_background(ballot_id):
	"""
	Khởi động preprocessing trong background thread
	Mỗi ballot có thread riêng, không ảnh hưởng lẫn nhau
	"""
	thread = threading.Thread(
		target=_auto_preprocess_worker,
		args=(ballot_id,),
		name=f"AutoPreprocess-{ballot_id}",
		daemon=True
	)
	thread.start()
	print(f"[WORKFLOW] Ballot {ballot_id}: Started preprocessing thread")


def _auto_preprocess_worker(ballot_id):
	"""
	Worker function - Bước 2: TIỀN XỬ LÝ
	Chạy trong background thread riêng cho từng ballot
	"""
	start_time = time.time()
	
	try:
		print(f"[WORKFLOW] Ballot {ballot_id}: Step 2 - Preprocessing started")
		
		# Lấy lại instance từ database trong thread mới
		ballot = Ballot.objects.select_related('poll').get(ballot_id=ballot_id)
		
		# Kiểm tra lại điều kiện
		if not ballot.ballot_image:
			print(f"[WORKFLOW] Ballot {ballot_id}: No image, skip")
			return
		
		if PreprocessedBallot.objects.filter(ballot=ballot, status='completed').exists():
			print(f"[WORKFLOW] Ballot {ballot_id}: Already preprocessed, skip")
			return
		
		# Kiểm tra xem có bật auto check không
		from counting.models import AIModelResult
		poll = ballot.poll
		ai_result = AIModelResult.objects.filter(poll=poll).order_by('-created_at').first()
		
		if not ai_result or not ai_result.auto_check_enabled:
			print(f"[WORKFLOW] Ballot {ballot_id}: Auto check disabled, skip")
			return
		
		# Kiểm tra giới hạn
		if ai_result.auto_check_max_ballots:
			if ai_result.auto_check_processed >= ai_result.auto_check_max_ballots:
				print(f"[WORKFLOW] Ballot {ballot_id}: Reached limit {ai_result.auto_check_max_ballots}, skip")
				return
		
		# THỰC HIỆN TIỀN XỬ LÝ
		print(f"[WORKFLOW] Ballot {ballot_id}: Processing...")
		result = process_single_ballot_wrapper(ballot)
		
		elapsed = time.time() - start_time
		print(f"[WORKFLOW] Ballot {ballot_id}: Step 2 - Preprocessing completed in {elapsed:.2f}s")
		print(f"[WORKFLOW] Ballot {ballot_id}: Next → Auto check will start after commit")
		
	except Exception as e:
		elapsed = time.time() - start_time
		print(f"[WORKFLOW] Ballot {ballot_id}: Step 2 - Preprocessing FAILED in {elapsed:.2f}s")
		print(f"[WORKFLOW ERROR] {e}")
