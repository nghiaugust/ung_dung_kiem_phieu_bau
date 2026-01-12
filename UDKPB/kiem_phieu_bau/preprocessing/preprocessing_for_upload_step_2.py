"""
BƯỚC 2: CẮT NỘI DUNG TỪ BẢNG VÀ LƯU VÀO DATABASE
Module xử lý phát hiện grid, cắt các ô và lưu vào database
Được gọi sau khi làm phẳng ảnh (step 1)

Quy trình:
1. Nhận ảnh đã làm phẳng từ step 1
2. Phát hiện grid (đường kẻ ngang và dọc)
3. Cắt từng ô trong bảng
4. Lưu vào database (PreprocessedBallot + BallotCell)

"""

import os
import cv2
import numpy as np
from django.db import transaction
from django.conf import settings

from ballot.models import Ballot
from form.models import BallotDocument
from .models import PreprocessedBallot, BallotCell
from .b2_cat_noi_dung_tu_bang import phat_hien_duong_ke_edge_projection


@transaction.atomic
def cat_va_luu_cac_o_phieu_bau(ballot, duong_dan_anh_da_lam_phang):
	"""
	Cắt các ô từ ảnh phiếu bầu đã làm phẳng và lưu vào database
	
	Quy trình chi tiết:
	1. Kiểm tra và xóa dữ liệu cũ (nếu có)
	2. Tạo PreprocessedBallot mới với status='processing'
	3. Lấy số hàng/cột từ BallotDocument
	4. Phát hiện grid bằng Edge Projection
	5. Cắt từng ô và lưu ảnh
	6. Tạo BallotCell cho mỗi ô
	7. Cập nhật PreprocessedBallot với status='completed'
	
	Args:
		ballot: Ballot object - Phiếu bầu cần xử lý
		duong_dan_anh_da_lam_phang: str - Đường dẫn tới ảnh đã làm phẳng từ step 1
		
	Returns:
		dict: Kết quả xử lý
			{
				'ballot_id': int,
				'status': 'success' | 'error',
				'cell_count': int,
				'detection_image': str,
				'message': str (nếu có lỗi)
			}
	
	Raises:
		Exception: Nếu có lỗi trong quá trình xử lý
	"""
	ballot_id = ballot.ballot_id
	
	print(f"[STEP2] ========== BẮT ĐẦU BƯỚC 2: CẮT VÀ LƯU CÁC Ô ==========")
	print(f"[STEP2] Xử lý ballot {ballot_id}...")
	
	# Tạo thư mục preprocessing trong media nếu chưa có
	preprocessing_dir = os.path.join(settings.MEDIA_ROOT, 'preprocessing')
	os.makedirs(preprocessing_dir, exist_ok=True)
	
	# 1. Kiểm tra xem ballot đã được xử lý chưa
	try:
		preprocessed = PreprocessedBallot.objects.get(ballot=ballot)
		
		# Xóa các file cũ trước khi xử lý lại
		print(f"[STEP2] Ballot {ballot_id} đã được xử lý trước đó, xóa dữ liệu cũ...")
		
		# Xóa file ảnh detection cũ
		if preprocessed.detection_image:
			old_detection_path = os.path.join(settings.MEDIA_ROOT, preprocessed.detection_image)
			if os.path.exists(old_detection_path):
				os.remove(old_detection_path)
				# print(f"[STEP2] Đã xóa ảnh detection cũ: {old_detection_path}")
		
		# Xóa các file ảnh cell cũ
		old_cells = BallotCell.objects.filter(preprocessed_ballot=preprocessed)
		for cell in old_cells:
			old_cell_path = os.path.join(settings.MEDIA_ROOT, cell.cell_image)
			if os.path.exists(old_cell_path):
				os.remove(old_cell_path)
		# print(f"[STEP2] Đã xóa {old_cells.count()} ảnh cell cũ")
		
		# Xóa records trong database
		old_cells.delete()
		preprocessed.delete()
		# print(f"[STEP2] Đã xóa dữ liệu cũ trong database")
		
	except PreprocessedBallot.DoesNotExist:
		print(f"[STEP2] Ballot {ballot_id} chưa được xử lý, bắt đầu xử lý mới...")
	
	# 2. Tạo PreprocessedBallot mới với status='processing'
	preprocessed = PreprocessedBallot.objects.create(
		ballot=ballot,
		status='processing'
	)
	# print(f"[STEP2] Đã tạo PreprocessedBallot (ID: {preprocessed.preprocessing_id})")
	
	try:
		# 3. Kiểm tra file ảnh đầu vào
		if not os.path.exists(duong_dan_anh_da_lam_phang):
			raise FileNotFoundError(f"Không tìm thấy ảnh đã làm phẳng: {duong_dan_anh_da_lam_phang}")
		
		# Đọc ảnh đã được làm phẳng từ step 1
		warped = cv2.imread(duong_dan_anh_da_lam_phang)
		if warped is None:
			raise ValueError(f"Không thể đọc ảnh từ: {duong_dan_anh_da_lam_phang}")
		
		# print(f"[STEP2] Đọc ảnh đã làm phẳng từ: {duong_dan_anh_da_lam_phang}")
		
		# 4. Lấy số hàng và cột từ BallotDocument của poll (created_at gần nhất)
		try:
			ballot_doc = BallotDocument.objects.filter(poll=ballot.poll).order_by('-created_at').first()
			
			if ballot_doc:
				num_rows, num_cols = ballot_doc.get_first_table_dimensions()
				
				if num_rows is not None and num_cols is not None:
					# Số đường kẻ = số hàng/cột + 1
					target_h_lines = num_rows + 1
					target_v_lines = num_cols + 1
					# print(f"[STEP2] Sử dụng kích thước bảng từ BallotDocument: {num_rows} hàng x {num_cols} cột → {target_h_lines} đường ngang x {target_v_lines} đường dọc")
				else:
					# Fallback nếu không có bảng trong document
					target_h_lines = 4
					target_v_lines = 5
					# print(f"[STEP2 WARNING] BallotDocument không có bảng, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
			else:
				# Fallback nếu không tìm thấy BallotDocument
				target_h_lines = 4
				target_v_lines = 5
				print(f"[STEP2 WARNING] Không tìm thấy BallotDocument cho poll {ballot.poll.poll_id}, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
		except Exception as e:
			# Fallback nếu có lỗi
			target_h_lines = 4
			target_v_lines = 5
			print(f"[STEP2 WARNING] Lỗi khi lấy kích thước bảng từ BallotDocument: {e}, sử dụng giá trị mặc định: {target_h_lines} đường ngang x {target_v_lines} đường dọc")
		
		# 5. Phát hiện grid và lưu ảnh detection
		# print(f"[STEP2] Phát hiện grid và cắt ô ballot {ballot_id}...")
		
		# Gọi hàm phat_hien_duong_ke_edge_projection để phát hiện grid
		# Hàm này sẽ tự động lưu ảnh detection và histogram
		grid_result = phat_hien_duong_ke_edge_projection(
			duong_dan_anh=duong_dan_anh_da_lam_phang,
			hien_thi=True,  # Vẽ và lưu ảnh detection
			target_h_lines=target_h_lines,
			target_v_lines=target_v_lines
		)
		
		if grid_result is None or 'grid' not in grid_result:
			raise ValueError("Không phát hiện được grid từ ảnh")
		
		grid = grid_result['grid']
		
		if len(grid) == 0:
			raise ValueError("Grid rỗng, không có ô nào")
		
		# print(f"[STEP2] Đã phát hiện grid: {len(grid)} dòng x {len(grid[0]) if grid else 0} cột")
		# print(f"[STEP2] Đã lưu ảnh grid detection và histogram")
		
		# 6. Cắt các ô và lưu
		# print(f"[STEP2] Bắt đầu cắt {len(grid)} dòng x {len(grid[0]) if grid else 0} cột...")
		
		cell_count = 0
		
		for row_idx, row in enumerate(grid):
			for col_idx, cell in enumerate(row):
				# Cắt ô từ ảnh warped
				cropped = warped[cell['y_min']:cell['y_max'], cell['x_min']:cell['x_max']]
				
				if cropped.size == 0:
					# print(f"[STEP2 WARNING] Ô [{row_idx}, {col_idx}] rỗng, bỏ qua")
					continue
				
				# Tên file: <ballot_id>_<row>_<col>.jpg
				cell_filename = f"{ballot_id}_{row_idx}_{col_idx}.jpg"
				cell_path = os.path.join(preprocessing_dir, cell_filename)
				
				# Lưu ảnh ô
				cv2.imwrite(cell_path, cropped)
				
				# CLEANUP: Xóa cropped ngay sau khi save (tiết kiệm ~1MB/cell)
				del cropped
				
				# 7. Lưu vào database
				BallotCell.objects.create(
					preprocessed_ballot=preprocessed,
					row=row_idx,
					col=col_idx,
					cell_image=os.path.join('preprocessing', cell_filename)
				)
				
				cell_count += 1
		
		# CLEANUP: Xóa warped sau khi cắt xong tất cả cells (tiết kiệm ~17MB!)
		del warped
		import gc
		gc.collect()
		
		# print(f"[STEP2] Đã cắt và lưu {cell_count} ô vào database")
		
		# 8. Lưu đường dẫn detection_image
		# File detection được tạo bởi phat_hien_duong_ke_edge_projection
		# với tên: <ballot_image_path_without_ext>_detection.jpg
		# Ví dụ: ballots/123.jpg -> ballots/123_detection.jpg
		ballot_image_relative = ballot.ballot_image.name  # Ví dụ: 'ballots/123.jpg'
		base_name_relative = os.path.splitext(ballot_image_relative)[0]  # 'ballots/123'
		detection_relative = f"{base_name_relative}_detection.jpg"  # 'ballots/123_detection.jpg'
		
		# 9. Cập nhật PreprocessedBallot với status='completed'
		preprocessed.detection_image = detection_relative
		preprocessed.status = 'completed'
		preprocessed.cell_count = cell_count
		preprocessed.error_message = None
		preprocessed.save()
		
		# print(f"[STEP2] Cập nhật PreprocessedBallot: status=completed, cell_count={cell_count}")
		print(f"[STEP2] ========== HOÀN THÀNH BƯỚC 2: CẮT VÀ LƯU CÁC Ô ==========")
		
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
		
		print(f"[STEP2 ERROR] Lỗi xử lý ballot {ballot_id}: {e}")
		print(f"[STEP2] ========== BƯỚC 2 THẤT BẠI ==========")
		
		# Raise lại exception để caller xử lý
		raise e


def cat_va_luu_cac_o_phieu_bau_wrapper(ballot, duong_dan_anh_da_lam_phang):
	"""
	Wrapper function để gọi từ bên ngoài (API, signals, etc.)
	Tự động xử lý exception và trả về dict kết quả
	
	Args:
		ballot: Ballot object
		duong_dan_anh_da_lam_phang: str - Đường dẫn ảnh đã làm phẳng
		
	Returns:
		dict: Kết quả xử lý với status 'success' hoặc 'error'
	"""
	try:
		result = cat_va_luu_cac_o_phieu_bau(ballot, duong_dan_anh_da_lam_phang)
		return result
	except Exception as e:
		print(f"[STEP2 ERROR] Lỗi wrapper: {e}")
		return {
			'ballot_id': ballot.ballot_id,
			'status': 'error',
			'message': str(e)
		}
