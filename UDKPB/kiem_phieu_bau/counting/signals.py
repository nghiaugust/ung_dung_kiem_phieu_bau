"""
Signal handlers cho tự động kiểm phiếu
Luồng: Upload → (commit) → Background Preprocessing → (commit) → Background Auto Check
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.db import transaction, models
from ballot.models import Ballot
from preprocessing.models import PreprocessedBallot, BallotCell
from .models import AIModelResult
from .views import call_trocr_api, call_yolo_api, save_ballot_selections_from_results
from poll.models import Candidate
import os
import time
import threading


@receiver(post_save, sender=PreprocessedBallot)
def auto_check_ballot_on_preprocess(sender, instance, created, **kwargs):
	"""
	Tự động kiểm phiếu khi có ballot mới được tiền xử lý
	
	QUAN TRỌNG:
	- Chạy SAU KHI transaction preprocessing commit (không block preprocessing)
	- Chạy trong background thread riêng
	- Đây là bước cuối cùng trong luồng: Upload → Preprocessing → Auto Check
	"""
	# Debug: Log để kiểm tra điều kiện
	ballot_id = instance.ballot.ballot_id if instance.ballot else 'unknown'
	print(f"[WORKFLOW DEBUG] Ballot {ballot_id}: PreprocessedBallot post_save signal - created={created}, status={instance.status}")
	
	# Chỉ xử lý khi status = completed (có thể là created hoặc updated)
	if instance.status != 'completed':
		print(f"[WORKFLOW DEBUG] Ballot {ballot_id}: Status not completed, skip auto check")
		return
	
	# Kiểm tra xem đã được kiểm chưa (tránh xử lý lại)
	if instance.ballot and instance.ballot.is_checked:
		print(f"[WORKFLOW DEBUG] Ballot {ballot_id}: Already checked, skip auto check")
		return
	
	# Lên lịch chạy SAU KHI transaction preprocessing hoàn tất
	print(f"[WORKFLOW DEBUG] Ballot {ballot_id}: Scheduling auto check...")
	transaction.on_commit(lambda: _start_auto_check_background(instance.preprocessing_id, ballot_id))


def _start_auto_check_background(preprocessing_id, ballot_id=None):
	"""
	Khởi động auto check trong background thread
	Mỗi ballot có thread riêng, không ảnh hưởng lẫn nhau
	"""
	if ballot_id:
		print(f"[WORKFLOW] Ballot {ballot_id}: Launching auto check thread...")
	
	thread = threading.Thread(
		target=_auto_check_ballot_worker,
		args=(preprocessing_id,),
		name=f"AutoCheck-{preprocessing_id}",
		daemon=True
	)
	thread.start()
	
	if ballot_id:
		print(f"[WORKFLOW] Ballot {ballot_id}: Auto check thread started successfully")


def _auto_check_ballot_worker(preprocessing_id):
	"""
	Worker function - Bước 3: KIỂM PHIẾU
	Chạy trong background thread riêng cho từng ballot
	"""
	start_time = time.time()
	ballot_id = None
	
	try:
		# Lấy lại instance từ database trong thread mới
		preprocessed_ballot = PreprocessedBallot.objects.select_related('ballot', 'ballot__poll').get(
			preprocessing_id=preprocessing_id
		)
		
		ballot = preprocessed_ballot.ballot
		poll = ballot.poll
		ballot_id = ballot.ballot_id
		
		print(f"[WORKFLOW] Ballot {ballot_id}: Step 3 - Auto check started")
		
		# Kiểm tra xem có bật auto check không
		ai_result = AIModelResult.objects.filter(poll=poll).order_by('-created_at').first()
		if not ai_result or not ai_result.auto_check_enabled:
			print(f"[WORKFLOW] Ballot {ballot_id}: Auto check disabled, skip")
			return
		
		# Kiểm tra xem ballot đã được kiểm chưa
		if ballot.is_checked:
			print(f"[WORKFLOW] Ballot {ballot_id}: Already checked, skip")
			return
		
		# Kiểm tra xem đã đạt giới hạn chưa
		if ai_result.auto_check_max_ballots:
			if ai_result.auto_check_processed >= ai_result.auto_check_max_ballots:
				print(f"[WORKFLOW] Ballot {ballot_id}: Reached limit {ai_result.auto_check_max_ballots}, skip")
				return
		
		# Lấy cấu hình từ result_model
		config = ai_result.result_model.get('config', {})
		config_type = config.get('type', 'config1')
		start_row = config.get('start_row', 1)
		end_row = config.get('end_row')
		
		# Xác định các dòng cần xử lý
		if end_row is not None:
			rows_to_process = list(range(start_row, end_row + 1))
		else:
			# Lấy tất cả các dòng từ start_row
			max_row = BallotCell.objects.filter(
				preprocessed_ballot=preprocessed_ballot
			).aggregate(max_row=models.Max('row'))['max_row']
			if max_row:
				rows_to_process = list(range(start_row, max_row + 1))
			else:
				return
		
		# Xử lý ballot này
		process_single_ballot_auto(ballot, ai_result, config_type, config, rows_to_process)
		
		elapsed = time.time() - start_time
		print(f"[WORKFLOW] Ballot {ballot_id}: Step 3 - Auto check completed in {elapsed:.2f}s")
		print(f"[WORKFLOW] Ballot {ballot_id}: === WORKFLOW COMPLETED ===")
		
	except Exception as e:
		elapsed = time.time() - start_time
		if ballot_id:
			print(f"[WORKFLOW] Ballot {ballot_id}: Step 3 - Auto check FAILED in {elapsed:.2f}s")
		print(f"[WORKFLOW ERROR] {e}")


def process_single_ballot_auto(ballot, ai_result, config_type, config, rows_to_process):
	"""
	Xử lý tự động một ballot - gọi TrOCR + YOLO API
	"""
	ballot_id = ballot.ballot_id
	poll = ballot.poll
	
	print(f"[WORKFLOW] Ballot {ballot_id}: Processing {len(rows_to_process)} rows...")
	
	# Lấy cấu hình cột
	if config_type == 'config1':
		trocr_col = config.get('trocr_col')
		yolo_cols = config.get('yolo_cols', [])
	else:
		trocr_col = None
		yolo_cols = config.get('yolo_cols', [])
	
	# Khởi tạo danh sách kết quả
	combined_results = []
	
	# Xử lý từng dòng
	for row in rows_to_process:
		cell_info = {
			'ballot_id': ballot_id,
			'row': row,
			'images': [],
			'results': []
		}
		
		# Xử lý TrOCR (chỉ cho config1)
		if config_type == 'config1' and trocr_col is not None:
			trocr_cells = BallotCell.objects.filter(
				preprocessed_ballot__ballot_id=ballot_id,
				row=row,
				col=trocr_col
			).select_related('preprocessed_ballot')
			
			if trocr_cells.exists():
				trocr_cell = trocr_cells.first()
				trocr_image_path = os.path.join(settings.MEDIA_ROOT, trocr_cell.cell_image)
				if os.path.exists(trocr_image_path):
					cell_info['images'].append(os.path.basename(trocr_cell.cell_image))
					
					trocr_result = call_trocr_api([trocr_image_path])
					
					if trocr_result.get('success') and trocr_result.get('results'):
						recognized_text = trocr_result['results'][0].get('text', '')
						cell_info['results'].append(f"{recognized_text}")
					else:
						cell_info['results'].append("[Lỗi]")
		
		# Xử lý YOLO
		yolo_cells = BallotCell.objects.filter(
			preprocessed_ballot__ballot_id=ballot_id,
			row=row,
			col__in=yolo_cols
		).select_related('preprocessed_ballot').order_by('col')
		
		yolo_image_paths = []
		for yolo_cell in yolo_cells:
			yolo_image_path = os.path.join(settings.MEDIA_ROOT, yolo_cell.cell_image)
			if os.path.exists(yolo_image_path):
				cell_info['images'].append(os.path.basename(yolo_cell.cell_image))
				yolo_image_paths.append(yolo_image_path)
		
		if yolo_image_paths:
			yolo_result = call_yolo_api(yolo_image_paths)
			
			if yolo_result.get('success') and yolo_result.get('results'):
				for idx, detection in enumerate(yolo_result['results']):
					label = detection.get('label', 'none')
					detections = detection.get('detections', [])
					
					confidence = 0
					if detections:
						max_conf_detection = max(detections, key=lambda d: d.get('confidence', 0))
						confidence = max_conf_detection.get('confidence', 0)
						confidence = int(confidence * 100)
					
					cell_info['results'].append(f"{label} ({confidence}%)")
			else:
				for _ in yolo_image_paths:
					cell_info['results'].append("[Lỗi YOLO]")
		
		if cell_info['images']:
			combined_results.append(cell_info)
	
	# Cập nhật result_model với kết quả mới
	if combined_results:
		with transaction.atomic():
			# Lock để tránh race condition
			ai_result = AIModelResult.objects.select_for_update().get(pk=ai_result.pk)
			
			# Thêm kết quả mới vào results
			current_results = ai_result.result_model.get('results', [])
			current_results.extend(combined_results)
			ai_result.result_model['results'] = current_results
			ai_result.result_model['total_rows'] = len(current_results)
			
			# Cập nhật số phiếu đã kiểm
			ai_result.auto_check_processed += 1
			ai_result.save()
			
			# Đánh dấu ballot đã kiểm
			ballot.is_checked = True
			ballot.save()
			
			# Tự động tạo BallotSelection
			save_ballot_selections_from_results(poll, ai_result.result_model)
			
			print(f"[WORKFLOW] Ballot {ballot_id}: Saved results ({ai_result.auto_check_processed}/{ai_result.auto_check_max_ballots or 'unlimited'})")
			
			# Kiểm tra xem đã đạt giới hạn chưa
			if ai_result.auto_check_max_ballots and ai_result.auto_check_processed >= ai_result.auto_check_max_ballots:
				print(f"[WORKFLOW] Poll {poll.poll_id}: Reached limit {ai_result.auto_check_max_ballots}, disabling auto check")
				ai_result.auto_check_enabled = False
				ai_result.save()
				
				# Cập nhật status poll
				poll.status = 'Đã kiểm phiếu'
				poll.save()
