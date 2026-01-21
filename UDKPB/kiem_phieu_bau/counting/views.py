from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.db import models
from django.views.decorators.http import require_http_methods
from poll.models import Poll, Candidate
from ballot.models import Ballot, BallotSelection
from preprocessing.models import BallotCell, PreprocessedBallot
from .models import AIModelResult
from . import config_model
import requests
import os
import time
import difflib
from typing import List, Dict, Tuple
import json


@require_http_methods(["POST"])
def save_configuration(request, poll_id):
	"""
	Lưu cấu hình model cho tất cả các ballot trong poll
	
	Expects JSON: {"config_type": 1 hoặc 2}
	"""
	try:
		# Parse request body
		data = json.loads(request.body)
		config_type = data.get('config_type')
		
		if config_type not in [1, 2]:
			return JsonResponse({
				'status': 'error',
				'message': 'config_type phải là 1 hoặc 2'
			}, status=400)
		
		# Lấy poll
		poll = get_object_or_404(Poll, poll_id=poll_id)
		
		# Kiểm tra trạng thái poll - không cho sửa nếu đã kiểm phiếu
		if poll.status in ['counted', 'Đã kiểm phiếu']:
			return JsonResponse({
				'status': 'error',
				'message': 'Không thể sửa cấu hình vì poll đã được kiểm phiếu!'
			}, status=400)
		
		# Lưu config_number vào Poll
		poll.config_number = config_type
		poll.save()
		
		# Lấy tất cả ballots trong poll
		ballots = Ballot.objects.filter(poll=poll)
		
		if not ballots.exists():
			return JsonResponse({
				'status': 'error',
				'message': 'Không có phiếu bầu nào trong poll này'
			}, status=404)
		
		# Đếm số lượng đã cấu hình
		configured_count = 0
		error_count = 0
		errors = []
		
		# Lặp qua từng ballot và tạo/cập nhật AIModelResult
		for ballot in ballots:
			try:
				# Tạo hoặc lấy AIModelResult cho ballot
				ai_result, created = AIModelResult.objects.get_or_create(
					ballot=ballot,
					defaults={
						'status': 'pending',
						'config_model': {},
						'result_model': {}
					}
				)
				
				# Nếu đã tồn tại, reset lại config và result để cập nhật mới
				if not created:
					ai_result.config_model = {}
					ai_result.result_model = {}
					ai_result.status = 'pending'
					ai_result.save()
				
				# Áp dụng cấu hình tương ứng
				if config_type == 1:
					config_model.apply_config1(ai_result)
				elif config_type == 2:
					config_model.apply_config2(ai_result)
				
				configured_count += 1
				
			except Exception as e:
				error_count += 1
				errors.append(f"Ballot {ballot.ballot_id}: {str(e)}")
		
		# Trả về kết quả
		return JsonResponse({
			'status': 'success',
			'message': f'Đã lưu cấu hình {config_type} cho {configured_count}/{ballots.count()} phiếu bầu',
			'config_type': config_type,
			'total_ballots': ballots.count(),
			'configured_count': configured_count,
			'error_count': error_count,
			'errors': errors if error_count > 0 else None
		})
		
	except json.JSONDecodeError:
		return JsonResponse({
			'status': 'error',
			'message': 'Invalid JSON'
		}, status=400)
	except Exception as e:
		return JsonResponse({
			'status': 'error',
			'message': str(e)
		}, status=500)



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
	
	# Mở file trong context manager để tự động đóng (tránh file handle leak)
	file_handles = []
	try:
		files = []
		for path in image_paths:
			filename = os.path.basename(path)
			fh = open(path, 'rb')
			file_handles.append(fh)
			files.append(('images', (filename, fh, 'image/jpeg')))
		
		# Giảm timeout xuống 300s (5 phút) - tránh worker bị block quá lâu
		# Nếu AI server xử lý chậm hơn 5 phút thì có vấn đề nghiêm trọng cần xử lý
		response = requests.post(api_url, files=files, timeout=300)
		response.raise_for_status()
		result = response.json()
		
		# CLEANUP: Giải phóng memory sau khi nhận response
		import gc
		gc.collect()
		
		return result
	except requests.exceptions.RequestException as e:
		return {
			'success': False,
			'error': str(e)
		}
	finally:
		# Đảm bảo đóng TẤT CẢ file handles, kể cả khi có exception
		for fh in file_handles:
			try:
				fh.close()
			except:
				pass


def call_yolo_api(image_paths: List[str]) -> Dict:
	"""
	Gọi YOLO API để detect dấu X
	
	Args:
		image_paths: Danh sách đường dẫn ảnh
		
	Returns:
		Dict chứa kết quả từ API
	"""
	import json
	api_url = "http://localhost:8080/api/yolo/detect/"
	
	# Mở file trong context manager để tự động đóng (tránh file handle leak)
	file_handles = []
	try:
		files = []
		image_paths_map = {}  # Mapping filename -> full_path
		
		for path in image_paths:
			filename = os.path.basename(path)
			fh = open(path, 'rb')
			file_handles.append(fh)
			files.append(('images', (filename, fh, 'image/jpeg')))
			image_paths_map[filename] = path
		
		# Gửi cả image_paths để API có thể lưu ảnh có box
		data = {
			'image_paths': json.dumps(image_paths_map)
		}
		
		# Giảm timeout xuống 300s (5 phút) - tránh worker bị block quá lâu
		response = requests.post(api_url, files=files, data=data, timeout=300)
		response.raise_for_status()
		result = response.json()
		
		# CLEANUP: Giải phóng memory sau khi nhận response
		import gc
		gc.collect()
		
		return result
	except requests.exceptions.RequestException as e:
		return {
			'success': False,
			'error': str(e)
		}
	finally:
		# Đảm bảo đóng TẤT CẢ file handles, kể cả khi có exception
		for fh in file_handles:
			try:
				fh.close()
			except:
				pass




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
		health_response = requests.get('http://localhost:8080/api/health/', timeout=0.5)
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
		# Thêm config_number và status để kiểm tra
		'config_number': poll.config_number,
		'is_counted': poll.status in ['counted', 'Đã kiểm phiếu'],
	}
	
	return render(request, 'counting/counting_form.html', context)


def process_counting(request, poll_id):
	"""
	Xử lý kiểm phiếu khi submit form - Áp dụng cấu hình và lưu kết quả cho từng ballot
	"""
	if request.method != 'POST':
		return redirect('counting_form', poll_id=poll_id)
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Kiểm tra nếu đã kiểm phiếu và có config_number thì chỉ cho phép kiểm lại với cùng cấu hình
	if poll.status in ['counted', 'Đã kiểm phiếu'] and poll.config_number:
		# Lấy config_number đã lưu
		saved_config = poll.config_number
		# Kiểm tra xem user có đang chọn config khác không
		requested_config = 1 if request.POST.get('config1') == '1' else 2
		if saved_config != requested_config:
			messages.error(request, f'Poll đã được kiểm phiếu với cấu hình {saved_config}. Không thể thay đổi cấu hình!')
			return redirect('counting_form', poll_id=poll_id)
	
	# Parse dữ liệu từ form
	config1 = request.POST.get('config1') == '1'
	config2 = request.POST.get('config2') == '1'
	
	# Kiểm tra phải chọn đúng 1 cấu hình
	if not config1 and not config2:
		messages.warning(request, 'Vui lòng chọn một cấu hình!')
		return redirect('counting_form', poll_id=poll_id)
	
	if config1 and config2:
		messages.warning(request, 'Chỉ được chọn một cấu hình!')
		return redirect('counting_form', poll_id=poll_id)
	
	# Xác định loại cấu hình
	config_type = 'config1' if config1 else 'config2'
	config_number = 1 if config1 else 2
	
	# Lưu config_number vào Poll
	poll.config_number = config_number
	poll.save()
	
	# Lấy tất cả ballot trong poll
	ballots = Ballot.objects.filter(poll=poll)
	
	if not ballots.exists():
		messages.error(request, 'Không có phiếu bầu nào trong poll này!')
		return redirect('counting_form', poll_id=poll_id)
	
	# Xóa kết quả cũ của tất cả ballot trong poll
	AIModelResult.objects.filter(ballot__poll=poll).delete()
	
	total_processed_ballots = 0
	total_processed_cells = 0
	start_time_total = time.time()
	
	# Xử lý từng ballot
	for ballot in ballots:
		try:
			# 1. Tạo AIModelResult cho ballot
			ai_result = AIModelResult.objects.create(
				ballot=ballot,
				status='processing'
			)
			
			# 2. Áp dụng cấu hình (config1 hoặc config2)
			if config_type == 'config1':
				config_model.apply_config1(ai_result)
			else:
				config_model.apply_config2(ai_result)
			
			# 3. Lấy cấu hình đã được khởi tạo
			rows, cols = ai_result.get_table_dimensions()
			all_cell_models = ai_result.get_all_cell_models()
			
			if not all_cell_models:
				ai_result.status = 'failed'
				ai_result.error_message = 'Không có cấu hình cell nào'
				ai_result.save()
				continue
			
			# 4. Xử lý từng ô theo cấu hình
			for cell_key, model_name in all_cell_models.items():
				# Parse cell_key: "row_col"
				row, col = map(int, cell_key.split('_'))
				
				# Lấy BallotCell tương ứng
				ballot_cells = BallotCell.objects.filter(
					preprocessed_ballot__ballot=ballot,
					row=row,
					col=col
				).select_related('preprocessed_ballot')
				
				if not ballot_cells.exists():
					continue
				
				ballot_cell = ballot_cells.first()
				cell_image_path = os.path.join(settings.MEDIA_ROOT, ballot_cell.cell_image)
				
				if not os.path.exists(cell_image_path):
					continue
				
				# Gọi model tương ứng
				if model_name == 'trocr':
					# Gọi TrOCR API
					trocr_result = call_trocr_api([cell_image_path])
					
					if trocr_result.get('success') and trocr_result.get('results'):
						recognized_text = trocr_result['results'][0].get('text', '')
						confidence = trocr_result['results'][0].get('confidence', 0)
						
						# Lưu kết quả vào result_model
						ai_result.set_cell_result(row, col, recognized_text, confidence)
						total_processed_cells += 1
					else:
						ai_result.set_cell_result(row, col, "[Lỗi TrOCR]", 0)
				
				elif model_name == 'yolo':
					# Gọi YOLO API
					yolo_result = call_yolo_api([cell_image_path])
					
					if yolo_result.get('success') and yolo_result.get('results'):
						detection = yolo_result['results'][0]
						label = detection.get('label', 'none')
						detections = detection.get('detections', [])
						
						# Lấy confidence cao nhất
						confidence = 0
						if detections:
							max_conf_detection = max(detections, key=lambda d: d.get('confidence', 0))
							confidence = max_conf_detection.get('confidence', 0)
						
						# Lưu kết quả (label + detections)
						result_data = {
							'label': label,
							'detections': detections
						}
						ai_result.set_cell_result(row, col, result_data, confidence)
						total_processed_cells += 1
					else:
						ai_result.set_cell_result(row, col, "[Lỗi YOLO]", 0)
			
			# 5. Cập nhật trạng thái thành công
			processing_time = time.time() - start_time_total
			ai_result.status = 'success'
			ai_result.processing_time = processing_time
			ai_result.save()
			
			total_processed_ballots += 1
			
		except Exception as e:
			# Lưu lỗi vào database
			ai_result.status = 'failed'
			ai_result.error_message = str(e)
			ai_result.save()
			print(f"[ERROR] Lỗi xử lý ballot {ballot.ballot_id}: {e}")
	
	# 6. Tự động tạo BallotSelection từ kết quả
	try:
		# Lấy tất cả AIModelResult đã xử lý thành công
		successful_results = AIModelResult.objects.filter(
			ballot__poll=poll,
			status='success'
		)
		
		# Lấy danh sách ứng viên
		candidate_list = list(Candidate.objects.filter(poll=poll).order_by('candidate_id'))
		candidate_names = {c.candidate_id: c.name for c in candidate_list}
		
		# Xóa BallotSelection cũ
		BallotSelection.objects.filter(ballot__poll=poll).delete()
		
		selections_to_create = []
		
		for ai_result in successful_results:
			ballot = ai_result.ballot
			
			# Lấy config_number từ Poll
			config_number = poll.config_number
			
			# Lấy config để biết start_row
			start_row = 1  # Dòng 2 trong UI → index 1 trong DB
			
			# Lấy tất cả cells có YOLO
			yolo_cells = ai_result.get_cells_by_model('yolo')
			
			# Lấy tất cả cells có TrOCR (nếu có)
			trocr_cells = ai_result.get_cells_by_model('trocr')
			
			# Group theo row để xử lý từng dòng
			rows_dict = {}
			for cell_key, cell_data in yolo_cells.items():
				row, col = map(int, cell_key.split('_'))
				if row not in rows_dict:
					rows_dict[row] = {'yolo': [], 'trocr': None}
				rows_dict[row]['yolo'].append((col, cell_data))
			
			# Thêm TrOCR vào rows_dict
			for cell_key, cell_data in trocr_cells.items():
				row, col = map(int, cell_key.split('_'))
				if row not in rows_dict:
					rows_dict[row] = {'yolo': [], 'trocr': None}
				rows_dict[row]['trocr'] = cell_data
			
			# Xử lý từng dòng
			for row, row_data in rows_dict.items():
				yolo_results = row_data['yolo']
				trocr_result = row_data['trocr']
				
				# Sắp xếp yolo_results theo col để lấy đúng cột đồng ý (cột đầu tiên)
				yolo_results.sort(key=lambda x: x[0])
				
				if not yolo_results:
					continue
				
				# Lấy cột đồng ý (cột đầu tiên)
				agree_col, agree_result = yolo_results[0]
				result_data = agree_result.get('result', {})
				
				if isinstance(result_data, dict):
					label = result_data.get('label', 'none')
				else:
					continue
				
				# Kiểm tra có dấu X không
				if 'x_mark' not in label.lower():
					continue
				
				# Xác định candidate dựa trên config_number từ database
				candidate_to_select = None
				
				if config_number == 1 and trocr_result:
					# Config1: Sử dụng TrOCR để matching tên
					recognized_name = trocr_result.get('result', '').strip()
					
					if recognized_name and recognized_name != "[Lỗi TrOCR]":
						# Tìm candidate giống nhất với recognized_name
						best_match_id = None
						best_match_ratio = 0.0
						
						for candidate_id, candidate_name in candidate_names.items():
							# Sử dụng difflib để so sánh tên
							ratio = difflib.SequenceMatcher(
								None, 
								recognized_name.upper(), 
								candidate_name.upper()
							).ratio()
							
							if ratio > best_match_ratio:
								best_match_ratio = ratio
								best_match_id = candidate_id
						
						# Chỉ chọn nếu tỉ lệ khớp >= 0.6 (60%)
						if best_match_id and best_match_ratio >= 0.6:
							candidate_to_select = next(
								(c for c in candidate_list if c.candidate_id == best_match_id),
								None
							)
				else:
					# Config2: Sử dụng thứ tự dòng
					candidate_index = row - start_row
					
					if 0 <= candidate_index < len(candidate_list):
						candidate_to_select = candidate_list[candidate_index]
				
				# Tạo BallotSelection nếu đã xác định được candidate
				if candidate_to_select:
					selections_to_create.append(
						BallotSelection(
							ballot=ballot,
							candidate_id=candidate_to_select.candidate_id
						)
					)
		
		# Bulk create
		if selections_to_create:
			BallotSelection.objects.bulk_create(selections_to_create)
			print(f"[BallotSelection] ✅ Đã tạo {len(selections_to_create)} lựa chọn")
		
	except Exception as e:
		print(f"[ERROR] Lỗi tạo BallotSelection: {e}")
	
	# 7. Cập nhật trạng thái Poll và Ballot
	poll.status = 'Đã kiểm phiếu'
	poll.save()
	
	Ballot.objects.filter(poll=poll).update(is_checked=True)
	
	messages.success(request, f'Đã xử lý thành công {total_processed_ballots} phiếu bầu với {total_processed_cells} ô!')
	
	# Chuyển đến trang hậu kiểm của phiếu đầu tiên
	first_ballot = Ballot.objects.filter(poll=poll).order_by('ballot_id').first()
	if first_ballot:
		from django.urls import reverse
		return redirect(reverse('ballot:hau_kiem_ballot', kwargs={'ballot_id': first_ballot.ballot_id}))
	else:
		return redirect('counting_results', poll_id=poll_id)


def counting_results_view(request, poll_id):
	"""
	Hiển thị kết quả kiểm phiếu
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Lấy kết quả từ database (theo ballot)
	results = AIModelResult.objects.filter(
		ballot__poll=poll
	).select_related('ballot').order_by('ballot__ballot_id')
	
	context = {
		'poll': poll,
		'results': results,
	}
	
	return render(request, 'counting/counting_results.html', context)


def auto_counting_view(request, poll_id):
	"""
	Trang quản lý kiểm phiếu tự động
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Đếm tổng số ballot
	total_ballots = Ballot.objects.filter(poll=poll).count()
	
	context = {
		'poll': poll,
		'total_ballots': total_ballots,
	}
	
	return render(request, 'counting/auto_counting.html', context)


@require_http_methods(["POST"])
def toggle_auto_counting(request, poll_id):
	"""
	Bật/tắt chế độ kiểm phiếu tự động
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Kiểm tra phải có config_number trước khi bật
	if not poll.is_counting_started and not poll.config_number:
		messages.error(request, 'Vui lòng lưu cấu hình trước khi bật kiểm tự động!')
		return redirect('auto_counting', poll_id=poll_id)
	
	# Toggle trạng thái
	poll.is_counting_started = not poll.is_counting_started
	
	# Nếu đang BẬT, lưu total_ballots_count từ form (hoặc mặc định = tổng ballot)
	if poll.is_counting_started:
		total_ballots = Ballot.objects.filter(poll=poll).count()
		
		# Lấy giá trị từ form, nếu không có thì dùng mặc định
		total_ballots_count = request.POST.get('total_ballots_count', total_ballots)
		
		try:
			total_ballots_count = int(total_ballots_count)
			
			# Validate: không được vượt quá tổng số ballot thực tế
			if total_ballots_count > total_ballots:
				total_ballots_count = total_ballots
			
			# Validate: phải >= 0
			if total_ballots_count < 0:
				total_ballots_count = 0
			
			poll.total_ballots_count = total_ballots_count
		except (ValueError, TypeError):
			# Nếu lỗi convert, dùng giá trị mặc định
			poll.total_ballots_count = total_ballots
	
	poll.save()
	
	if poll.is_counting_started:
		# KHI BẬT: Đẩy tất cả phiếu đã xử lý xong (process_status='completed') nhưng chưa kiểm (counting_status='pending') vào queue
		from counting.tasks import counting_queue
		
		# Lấy tất cả ballot đã completed nhưng chưa kiểm
		pending_ballots = Ballot.objects.filter(
			poll=poll,
			process_status='completed',
			counting_status='pending'
		).values_list('ballot_id', flat=True)
		
		# Đẩy vào queue
		queued_count = 0
		for ballot_id in pending_ballots:
			counting_queue.delay(ballot_id)
			queued_count += 1
		
		if queued_count > 0:
			messages.success(request, f'Đã BẬT chế độ kiểm phiếu tự động! Đang xử lý {queued_count} phiếu đã upload trước đó...')
		else:
			messages.success(request, 'Đã BẬT chế độ kiểm phiếu tự động!')
	else:
		messages.info(request, 'Đã TẮT chế độ kiểm phiếu tự động!')
	
	return redirect('auto_counting', poll_id=poll_id)


def get_counting_stats(request, poll_id):
	"""
	API trả về thống kê số lượng phiếu upload và kiểm thành công
	Trả về stats riêng cho 2 luồng: Upload và Counting
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Đếm tổng số phiếu
	total_ballots = Ballot.objects.filter(poll=poll).count()
	
	# Lấy số phiếu cần kiểm (nếu không có thì lấy tổng)
	total_ballots_count = poll.total_ballots_count or total_ballots
	
	# Tính chênh lệch (offset)
	offset = max(0, total_ballots - total_ballots_count)
	
	# === LUỒNG UPLOAD ===
	# Đếm số phiếu chưa tải lên (process_status='no_upload') - offset
	no_upload_raw = Ballot.objects.filter(
		poll=poll,
		process_status='no_upload'
	).count()
	upload_no_upload = max(0, no_upload_raw - offset)
	
	# Đếm số phiếu chờ upload (process_status='pending')
	upload_pending = Ballot.objects.filter(
		poll=poll,
		process_status='pending'
	).count()
	
	# Đếm số phiếu đang upload (process_status='processing')
	upload_processing = Ballot.objects.filter(
		poll=poll,
		process_status='processing'
	).count()
	
	# Đếm số phiếu upload thành công (process_status='completed')
	upload_success = Ballot.objects.filter(
		poll=poll,
		process_status='completed'
	).count()
	
	# Đếm số phiếu upload thất bại (process_status='failed')
	upload_failed = Ballot.objects.filter(
		poll=poll,
		process_status='failed'
	).count()
	
	# === LUỒNG COUNTING ===
	# Đếm số phiếu chờ kiểm (process_status='completed' và counting_status='pending')
	counting_pending = Ballot.objects.filter(
		poll=poll,
		process_status='completed',
		counting_status='pending'
	).count()
	
	# Đếm số phiếu đang kiểm (counting_status='processing')
	counting_processing = Ballot.objects.filter(
		poll=poll,
		counting_status='processing'
	).count()
	
	# Đếm số phiếu kiểm thành công (counting_status='completed')
	counting_success = Ballot.objects.filter(
		poll=poll,
		counting_status='completed'
	).count()
	
	# Đếm số phiếu kiểm thất bại (counting_status='failed')
	counting_failed = Ballot.objects.filter(
		poll=poll,
		counting_status='failed'
	).count()
	
	return JsonResponse({
		'total': total_ballots,
		'total_ballots_count': total_ballots_count,
		'offset': offset,
		
		# Upload stats
		'upload': {
			'no_upload': upload_no_upload,
			'pending': upload_pending,
			'processing': upload_processing,
			'success': upload_success,
			'failed': upload_failed,
		},
		
		# Counting stats
		'counting': {
			'pending': counting_pending,
			'processing': counting_processing,
			'success': counting_success,
			'failed': counting_failed,
		},
		
		'is_counting_started': poll.is_counting_started,
	})




