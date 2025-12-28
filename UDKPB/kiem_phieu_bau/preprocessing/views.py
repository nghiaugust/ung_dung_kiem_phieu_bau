import os
import cv2
import numpy as np
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.conf import settings
from ballot.models import Ballot
from poll.models import Poll
from form.models import BallotDocument
from .models import PreprocessedBallot, BallotCell
from .b1_lam_phang_anh import lam_phang_anh


def preprocess_poll_ballots(request, poll_id):
	"""
	Xử lý tất cả ballot của một poll
	
	Args:
		poll_id: ID của poll cần xử lý
	
	Returns:
		JSON response với thông tin xử lý
	"""
	# Lấy poll
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Lấy tất cả ballot của poll
	ballots = Ballot.objects.filter(poll=poll, ballot_image__isnull=False)
	
	if not ballots.exists():
		return JsonResponse({
			'status': 'error',
			'message': f'Không tìm thấy ballot nào có ảnh cho poll {poll_id}'
		}, status=404)
	
	# Tạo thư mục preprocessing trong media nếu chưa có
	preprocessing_dir = os.path.join(settings.MEDIA_ROOT, 'preprocessing')
	os.makedirs(preprocessing_dir, exist_ok=True)
	
	# Thống kê
	total_ballots = ballots.count()
	success_count = 0
	error_count = 0
	results = []
	
	print(f"[INFO] Bắt đầu xử lý {total_ballots} ballot của poll {poll_id}")
	
	for ballot in ballots:
		try:
			result = process_single_ballot(ballot, preprocessing_dir)
			results.append(result)
			
			if result['status'] == 'success':
				success_count += 1
			else:
				error_count += 1
				
		except Exception as e:
			error_count += 1
			results.append({
				'ballot_id': ballot.ballot_id,
				'status': 'error',
				'message': str(e)
			})
			print(f"[ERROR] Lỗi xử lý ballot {ballot.ballot_id}: {e}")
	
	return JsonResponse({
		'status': 'completed',
		'poll_id': poll_id,
		'total_ballots': total_ballots,
		'success_count': success_count,
		'error_count': error_count,
		'results': results
	})


@transaction.atomic
def process_single_ballot(ballot, preprocessing_dir):
	"""
	Xử lý một ballot đơn lẻ
	
	Args:
		ballot: Ballot object
		preprocessing_dir: Thư mục lưu kết quả
		
	Returns:
		dict: Kết quả xử lý
	"""
	ballot_id = ballot.ballot_id
	
	print(f"\n[INFO] Xử lý ballot {ballot_id}...")
	
	# Kiểm tra xem ballot đã được xử lý chưa
	try:
		preprocessed = PreprocessedBallot.objects.get(ballot=ballot)
		
		# Xóa các file cũ trước khi xử lý lại
		print(f"[INFO] Ballot {ballot_id} đã được xử lý trước đó, xóa dữ liệu cũ...")
		
		# Xóa file ảnh detection cũ
		if preprocessed.detection_image:
			old_detection_path = os.path.join(settings.MEDIA_ROOT, preprocessed.detection_image)
			if os.path.exists(old_detection_path):
				os.remove(old_detection_path)
				print(f"[INFO] Đã xóa ảnh detection cũ: {old_detection_path}")
		
		# Xóa các file ảnh cell cũ
		old_cells = BallotCell.objects.filter(preprocessed_ballot=preprocessed)
		for cell in old_cells:
			old_cell_path = os.path.join(settings.MEDIA_ROOT, cell.cell_image)
			if os.path.exists(old_cell_path):
				os.remove(old_cell_path)
		print(f"[INFO] Đã xóa {old_cells.count()} ảnh cell cũ")
		
		# Xóa records trong database
		old_cells.delete()
		preprocessed.delete()
		print(f"[INFO] Đã xóa dữ liệu cũ trong database")
		
	except PreprocessedBallot.DoesNotExist:
		print(f"[INFO] Ballot {ballot_id} chưa được xử lý, bắt đầu xử lý mới...")
	
	# Tạo PreprocessedBallot mới
	preprocessed = PreprocessedBallot.objects.create(
		ballot=ballot,
		status='processing'
	)
	
	try:
		# Đường dẫn ảnh gốc (đã được làm phẳng khi upload)
		input_image_path = ballot.ballot_image.path
		
		if not os.path.exists(input_image_path):
			raise FileNotFoundError(f"Không tìm thấy ảnh ballot: {input_image_path}")
		
		# Đọc ảnh đã được làm phẳng từ trước
		warped = cv2.imread(input_image_path)
		if warped is None:
			raise ValueError(f"Không thể đọc ảnh từ: {input_image_path}")
		
		print(f"[INFO] Đọc ảnh đã làm phẳng từ: {input_image_path}")
		
		# Định nghĩa đường dẫn output
		temp_flattened_path = input_image_path  # Sử dụng ảnh gốc đã làm phẳng
		
		# B1: Phát hiện grid và cắt ô (lưu ảnh có grid detection)
		print(f"[INFO] B1: Phát hiện grid và cắt ô ballot {ballot_id}...")
		
		# Lấy số hàng và cột từ BallotDocument của poll (created_at gần nhất)
		try:
			ballot_doc = BallotDocument.objects.filter(poll=ballot.poll).order_by('-created_at').first()
			
			if ballot_doc:
				num_rows, num_cols = ballot_doc.get_first_table_dimensions()
				
				if num_rows is not None and num_cols is not None:
					# Số đường kẻ = số hàng/cột + 1
					target_h_lines = num_rows + 1
					target_v_lines = num_cols + 1
					print(f"[INFO] Sử dụng kích thước bảng từ BallotDocument: {num_rows} hàng x {num_cols} cột → {target_h_lines} đường ngang x {target_v_lines} đường dọc")
				else:
					# Fallback nếu không có bảng trong document
					target_h_lines = 4
					target_v_lines = 5
					print(f"[WARNING] BallotDocument không có bảng, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
			else:
				# Fallback nếu không tìm thấy BallotDocument
				target_h_lines = 4
				target_v_lines = 5
				print(f"[WARNING] Không tìm thấy BallotDocument cho poll {ballot.poll.poll_id}, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
		except Exception as e:
			# Fallback nếu có lỗi
			target_h_lines = 4
			target_v_lines = 5
			print(f"[WARNING] Lỗi khi lấy kích thước bảng từ BallotDocument: {e}, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
		
		# Gọi hàm phat_hien_duong_ke_edge_projection để lưu cả ảnh grid và histogram
		from .b2_cat_noi_dung_tu_bang import phat_hien_duong_ke_edge_projection
		
		grid_result = phat_hien_duong_ke_edge_projection(
			duong_dan_anh=temp_flattened_path,
			hien_thi=True,
			target_h_lines=target_h_lines,
			target_v_lines=target_v_lines
		)
		
		if grid_result is None or 'grid' not in grid_result:
			raise ValueError("Không phát hiện được grid từ ảnh")
		
		grid = grid_result['grid']
		
		if len(grid) == 0:
			raise ValueError("Grid rỗng, không có ô nào")
		
		print(f"[INFO] Đã lưu ảnh grid detection và histogram")
		
		# Cắt các ô và lưu
		print(f"[INFO] Cắt {len(grid)} dòng x {len(grid[0]) if grid else 0} cột...")
		
		cell_count = 0
		
		for row_idx, row in enumerate(grid):
			for col_idx, cell in enumerate(row):
				# Cắt ô
				cropped = warped[cell['y_min']:cell['y_max'], cell['x_min']:cell['x_max']]
				
				if cropped.size == 0:
					print(f"[WARNING] Ô [{row_idx}, {col_idx}] rỗng, bỏ qua")
					continue
				
				# Tên file: <ballot_id>_<row>_<col>.jpg
				cell_filename = f"{ballot_id}_{row_idx}_{col_idx}.jpg"
				cell_path = os.path.join(preprocessing_dir, cell_filename)
				
				# Lưu ảnh ô
				cv2.imwrite(cell_path, cropped)
				
				# Lưu vào database
				BallotCell.objects.create(
					preprocessed_ballot=preprocessed,
					row=row_idx,
					col=col_idx,
					cell_image=os.path.join('preprocessing', cell_filename)
				)
				
				cell_count += 1
		
		print(f"[INFO] Đã cắt và lưu {cell_count} ô")
		
		# Lưu đường dẫn detection_image (file được tạo bởi phat_hien_duong_ke_edge_projection)
		# File detection được lưu tại: <ballot_image_path_without_ext>_detection.jpg
		# Ví dụ: ballots/123.jpg -> ballots/123_detection.jpg
		ballot_image_relative = ballot.ballot_image.name  # Ví dụ: 'ballots/123.jpg'
		base_name_relative = os.path.splitext(ballot_image_relative)[0]  # 'ballots/123'
		detection_relative = f"{base_name_relative}_detection.jpg"  # 'ballots/123_detection.jpg'
		
		# Cập nhật PreprocessedBallot
		preprocessed.detection_image = detection_relative
		preprocessed.status = 'completed'
		preprocessed.cell_count = cell_count
		preprocessed.error_message = None
		preprocessed.save()
		
		print(f"[SUCCESS] Hoàn thành xử lý ballot {ballot_id}")
		
		return {
			'ballot_id': ballot_id,
			'status': 'success',
			'cell_count': cell_count,
			'detection_image': preprocessed.detection_image
		}
		
	except Exception as e:
		# Lưu lỗi vào database
		preprocessed.status = 'failed'
		preprocessed.error_message = str(e)
		preprocessed.save()
		
		print(f"[ERROR] Lỗi xử lý ballot {ballot_id}: {e}")
		
		raise e


def get_preprocessed_status(request, poll_id):
	"""
	Lấy trạng thái xử lý của tất cả ballot trong poll
	
	Args:
		poll_id: ID của poll
		
	Returns:
		JSON response với thông tin trạng thái
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	ballots = Ballot.objects.filter(poll=poll)
	
	total_ballots = ballots.count()
	preprocessed_ballots = PreprocessedBallot.objects.filter(ballot__poll=poll)
	
	status_counts = {
		'processing': preprocessed_ballots.filter(status='processing').count(),
		'completed': preprocessed_ballots.filter(status='completed').count(),
		'failed': preprocessed_ballots.filter(status='failed').count(),
		'not_started': total_ballots - preprocessed_ballots.count()
	}
	
	# Lấy danh sách chi tiết
	details = []
	for ballot in ballots:
		try:
			preprocessed = ballot.preprocessed
			details.append({
				'ballot_id': ballot.ballot_id,
				'status': preprocessed.status,
				'cell_count': preprocessed.cell_count,
				'error_message': preprocessed.error_message,
				'processed_at': preprocessed.processed_at.isoformat() if preprocessed.processed_at else None
			})
		except PreprocessedBallot.DoesNotExist:
			details.append({
				'ballot_id': ballot.ballot_id,
				'status': 'not_started',
				'cell_count': 0,
				'error_message': None,
				'processed_at': None
			})
	
	return JsonResponse({
		'poll_id': poll_id,
		'total_ballots': total_ballots,
		'status_counts': status_counts,
		'details': details
	})


