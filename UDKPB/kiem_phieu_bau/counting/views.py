from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.db import models
from poll.models import Poll, Candidate
from ballot.models import Ballot
from preprocessing.models import BallotCell, PreprocessedBallot
from .models import AIModelResult
import requests
import os
import time
from typing import List, Dict, Tuple


def get_cell_image_paths(ballot_id: int, rows: List[int], cols: List[int]) -> List[str]:
	"""
	Lấy đường dẫn ảnh các ô dựa trên ballot_id, rows và cols
	
	Args:
		ballot_id: ID của ballot
		rows: Danh sách số hàng cần lấy
		cols: Danh sách số cột cần lấy
		
	Returns:
		List các đường dẫn ảnh tuyệt đối
	"""
	cells = BallotCell.objects.filter(
		preprocessed_ballot__ballot_id=ballot_id,
		row__in=rows,
		col__in=cols
	).select_related('preprocessed_ballot')
	
	image_paths = []
	for cell in cells:
		# Tạo đường dẫn tuyệt đối từ MEDIA_ROOT
		full_path = os.path.join(settings.MEDIA_ROOT, cell.cell_image)
		if os.path.exists(full_path):
			image_paths.append(full_path)
	
	return image_paths


def get_ballot_cell_image_paths(ballot_id: int, rows: List[int] = None, cols: List[int] = None) -> List[str]:
	"""
	Lấy đường dẫn ảnh các ô của một ballot
	
	Args:
		ballot_id: ID của ballot
		rows: Danh sách số hàng (None = tất cả)
		cols: Danh sách số cột (None = tất cả)
		
	Returns:
		List các đường dẫn ảnh
	"""
	query = BallotCell.objects.filter(preprocessed_ballot__ballot_id=ballot_id)
	
	if rows is not None:
		query = query.filter(row__in=rows)
	if cols is not None:
		query = query.filter(col__in=cols)
	
	cells = query.select_related('preprocessed_ballot')
	
	image_paths = []
	for cell in cells:
		full_path = os.path.join(settings.MEDIA_ROOT, cell.cell_image)
		if os.path.exists(full_path):
			image_paths.append(full_path)
	
	return image_paths


def get_poll_cell_image_paths(poll_id: int, rows: List[int] = None, cols: List[int] = None) -> Dict[int, List[str]]:
	"""
	Lấy đường dẫn ảnh các ô của tất cả ballot trong poll
	
	Args:
		poll_id: ID của poll
		rows: Danh sách số hàng (None = tất cả)
		cols: Danh sách số cột (None = tất cả)
		
	Returns:
		Dict với key là ballot_id, value là list đường dẫn ảnh
	"""
	ballots = Ballot.objects.filter(poll_id=poll_id).values_list('ballot_id', flat=True)
	
	result = {}
	for ballot_id in ballots:
		image_paths = get_ballot_cell_image_paths(ballot_id, rows, cols)
		if image_paths:
			result[ballot_id] = image_paths
	
	return result


def call_trocr_api(image_paths: List[str]) -> Dict:
	"""
	Gọi TrOCR API để nhận diện text
	
	Args:
		image_paths: Danh sách đường dẫn ảnh
		
	Returns:
		Dict chứa kết quả từ API
	"""
	api_url = "http://localhost:8080/api/trocr/recognize/"
	
	files = []
	for path in image_paths:
		filename = os.path.basename(path)
		files.append(('images', (filename, open(path, 'rb'), 'image/jpeg')))
	
	try:
		# Timeout 1800s (30 phút) để xử lý được nhiều ảnh
		response = requests.post(api_url, files=files, timeout=1800)
		response.raise_for_status()
		return response.json()
	except requests.exceptions.RequestException as e:
		return {
			'success': False,
			'error': str(e)
		}
	finally:
		# Đóng tất cả file handles
		for _, (_, file_obj, _) in files:
			file_obj.close()


def call_yolo_api(image_paths: List[str]) -> Dict:
	"""
	Gọi YOLO API để detect dấu X
	
	Args:
		image_paths: Danh sách đường dẫn ảnh
		
	Returns:
		Dict chứa kết quả từ API
	"""
	api_url = "http://localhost:8080/api/yolo/detect/"
	
	files = []
	for path in image_paths:
		filename = os.path.basename(path)
		files.append(('images', (filename, open(path, 'rb'), 'image/jpeg')))
	
	try:
		# Timeout 1800s (30 phút) để xử lý được nhiều ảnh
		response = requests.post(api_url, files=files, timeout=1800)
		response.raise_for_status()
		return response.json()
	except requests.exceptions.RequestException as e:
		return {
			'success': False,
			'error': str(e)
		}
	finally:
		# Đóng tất cả file handles
		for _, (_, file_obj, _) in files:
			file_obj.close()


def counting_form_view(request, poll_id):
	"""
	Trả về điều kiện kiểm phiếu cho poll
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	
	# Điều kiện 1: Ứng viên
	candidates_count = Candidate.objects.filter(poll=poll).count()
	
	# Điều kiện 2: Ballot
	ballots_count = Ballot.objects.filter(poll=poll).count()
	
	# Điều kiện 3: Check ảnh ballot
	ballots_with_image_count = Ballot.objects.filter(poll=poll, ballot_image__isnull=False).exclude(ballot_image='').count()
	
	# Điều kiện 4: Tiền xử lý
	# Đếm số ballot có image
	ballots_with_image_ids = Ballot.objects.filter(poll=poll, ballot_image__isnull=False).exclude(ballot_image='').values_list('ballot_id', flat=True)
	ballots_with_image_total = len(ballots_with_image_ids)
	# Đếm số ballot có image và đã được tiền xử lý
	preprocessed_count = PreprocessedBallot.objects.filter(
		ballot_id__in=ballots_with_image_ids,
		status='completed'
	).count()
	
	# Điều kiện 5: Check model AI
	trocr_status = False
	yolo_status = False
	try:
		health_response = requests.get('http://localhost:8080/api/health/', timeout=5)
		if health_response.status_code == 200:
			health_data = health_response.json()
			trocr_status = health_data.get('services', {}).get('trocr', False)
			yolo_status = health_data.get('services', {}).get('yolo', False)
	except:
		pass  # Nếu lỗi thì để mặc định False
	
	context = {
		'poll': poll,
		# Thêm thông tin điều kiện
		'candidates_count': candidates_count,
		'ballots_count': ballots_count,
		'ballots_with_image_count': ballots_with_image_count,
		'ballots_with_image_total': ballots_with_image_total,
		'preprocessed_count': preprocessed_count,
		'trocr_status': trocr_status,
		'yolo_status': yolo_status,
	}
	
	return render(request, 'counting/counting_form.html', context)


def process_counting(request, poll_id):
	"""
	Xử lý kiểm phiếu khi submit form - Cấu hình bảng biểu quyết
	"""
	if request.method != 'POST':
		return redirect('counting_form', poll_id=poll_id)
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Parse dữ liệu từ form
	config_vote_table = request.POST.get('config_vote_table') == '1'
	
	if not config_vote_table:
		messages.warning(request, 'Vui lòng chọn cấu hình bảng biểu quyết!')
		return redirect('counting_form', poll_id=poll_id)
	
	# Lấy điều kiện
	start_row = int(request.POST.get('start_row', 2)) - 1  # Trừ 1 vì DB bắt đầu từ 0
	end_row_str = request.POST.get('end_row', '').strip()
	end_row = (int(end_row_str) - 1) if end_row_str else None  # Trừ 1 vì DB bắt đầu từ 0
	yolo_confidence = int(request.POST.get('yolo_confidence', 50))
	
	# Xác định các dòng cần xử lý
	if end_row is not None:
		rows_to_process = list(range(start_row, end_row + 1))
	else:
		# Lấy tất cả các dòng từ start_row
		sample_ballot = Ballot.objects.filter(poll=poll).first()
		if sample_ballot:
			max_row = BallotCell.objects.filter(
				preprocessed_ballot__ballot=sample_ballot
			).aggregate(max_row=models.Max('row'))['max_row']
			if max_row:
				rows_to_process = list(range(start_row, max_row + 1))
			else:
				rows_to_process = []
		else:
			rows_to_process = []
	
	if not rows_to_process:
		messages.error(request, 'Không tìm thấy dữ liệu dòng nào để xử lý!')
		return redirect('counting_form', poll_id=poll_id)
	
	# Lấy cấu hình từ form (linh hoạt cho các config khác sau này)
	# Chuyển đổi từ UI (bắt đầu từ 1) sang DB (bắt đầu từ 0)
	trocr_col_ui = int(request.POST.get('vote_table_trocr_col', 2))
	yolo_cols_ui_str = request.POST.get('vote_table_yolo_cols', '3,4')
	
	# Chuyển đổi sang index DB (trừ 1)
	trocr_col = trocr_col_ui - 1
	yolo_cols = [int(col.strip()) - 1 for col in yolo_cols_ui_str.split(',')]
	
	# Lấy tất cả ballot trong poll
	ballots = Ballot.objects.filter(poll=poll)
	
	# Khởi tạo danh sách kết quả tổng hợp
	combined_results = []
	total_processed = 0
	
	# Xử lý từng ballot
	for ballot in ballots:
		ballot_id = ballot.ballot_id
		
		# Xử lý từng dòng
		for row in rows_to_process:
			# 1. Lấy ảnh cột 2 (tên) - TrOCR
			trocr_cells = BallotCell.objects.filter(
				preprocessed_ballot__ballot_id=ballot_id,
				row=row,
				col=trocr_col
			).select_related('preprocessed_ballot')
			
			# 2. Lấy ảnh cột 3, 4 (đồng ý, không đồng ý) - YOLO
			yolo_cells = BallotCell.objects.filter(
				preprocessed_ballot__ballot_id=ballot_id,
				row=row,
				col__in=yolo_cols
			).select_related('preprocessed_ballot').order_by('col')
			
			# Tạo đường dẫn ảnh
			trocr_image_path = None
			yolo_image_paths = []
			cell_info = {
				'ballot_id': ballot_id,
				'row': row,
				'images': [],
				'results': []
			}
			
			# Xử lý TrOCR
			if trocr_cells.exists():
				trocr_cell = trocr_cells.first()
				trocr_image_path = os.path.join(settings.MEDIA_ROOT, trocr_cell.cell_image)
				if os.path.exists(trocr_image_path):
					cell_info['images'].append(os.path.basename(trocr_cell.cell_image))
					
					# Gọi TrOCR API
					start_time = time.time()
					trocr_result = call_trocr_api([trocr_image_path])
					
					if trocr_result.get('success') and trocr_result.get('results'):
						recognized_text = trocr_result['results'][0].get('text', '')
						cell_info['results'].append(f"{recognized_text}")
					else:
						cell_info['results'].append("[Lỗi]")
			
			# Xử lý YOLO
			for yolo_cell in yolo_cells:
				yolo_image_path = os.path.join(settings.MEDIA_ROOT, yolo_cell.cell_image)
				if os.path.exists(yolo_image_path):
					cell_info['images'].append(os.path.basename(yolo_cell.cell_image))
					yolo_image_paths.append(yolo_image_path)
			
			if yolo_image_paths:
				start_time = time.time()
				yolo_result = call_yolo_api(yolo_image_paths)
				
				if yolo_result.get('success') and yolo_result.get('results'):
					for idx, detection in enumerate(yolo_result['results']):
						label = detection.get('label', 'trong')
						confidence = detection.get('confidence', 0)
						
						# Kiểm tra ngưỡng confidence
						# if confidence >= yolo_confidence:
						cell_info['results'].append(f"{label} ({confidence}%)")
						# else:
						# 	cell_info['results'].append(f"Không ({confidence}%)")
				else:
					for _ in yolo_image_paths:
						cell_info['results'].append("[Lỗi YOLO]")
			
			# Thêm vào kết quả nếu có dữ liệu
			if cell_info['images']:
				combined_results.append(cell_info)
				total_processed += 1
	
	# Lưu kết quả tổng hợp vào database
	if combined_results:
		result_data = {
			'success': True,
			'config': {
				'type': 'vote_table',
				'trocr_col': trocr_col,  # Giá trị DB (bắt đầu từ 0)
				'trocr_col_ui': trocr_col_ui,  # Giá trị UI (bắt đầu từ 1)
				'yolo_cols': yolo_cols,  # Giá trị DB (bắt đầu từ 0)
				'yolo_cols_ui': yolo_cols_ui_str,  # Giá trị UI (bắt đầu từ 1)
				'start_row': start_row,  # Giá trị DB (bắt đầu từ 0)
				'end_row': end_row,  # Giá trị DB (bắt đầu từ 0)
				'yolo_confidence': yolo_confidence
			},
			'total_rows': total_processed,
			'results': combined_results
		}
		
		# Xóa kết quả cũ của poll này trước khi tạo kết quả mới
		AIModelResult.objects.filter(poll=poll).delete()
		
		AIModelResult.objects.create(
			poll=poll,
			model_id='vote_table_combined',
			result_model=result_data,
			processing_time=0,  # Tổng thời gian đã được tính trong quá trình xử lý
			status='success',
			error_message=None
		)
		
		messages.success(request, f'Đã xử lý thành công {total_processed} dòng từ {len(ballots)} phiếu bầu!')
	else:
		messages.error(request, 'Không có dữ liệu để xử lý!')
	
	return redirect('counting_results', poll_id=poll_id)


def counting_results_view(request, poll_id):
	"""
	Hiển thị kết quả kiểm phiếu
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Lấy kết quả từ database
	results = AIModelResult.objects.filter(poll=poll).order_by('-created_at')
	
	context = {
		'poll': poll,
		'results': results,
	}
	
	return render(request, 'counting/counting_results.html', context)

