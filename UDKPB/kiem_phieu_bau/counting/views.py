from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.db import models
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from poll.models import Poll, Candidate
from ballot.models import Ballot, BallotSelection
from preprocessing.models import BallotCell, PreprocessedBallot
from .models import AIModelResult
from . import config_crossed, config_model
from .configurations.base import (
	MODEL_RESNET18_CROSSED,
	MODEL_RESNET18_X,
	MODEL_VIETNAMEOCR,
)
from config.service_manager import get_ai_model_health_statuses, get_model_api_url
import requests
import os
import time
from typing import List, Dict, Tuple
import json


def _wants_json_response(request):
	return (
		request.headers.get('x-requested-with') == 'XMLHttpRequest'
		or 'application/json' in request.headers.get('accept', '')
		or request.headers.get('content-type', '').startswith('application/json')
	)


def _toggle_auto_response(request, poll, message, message_level='success', status=200, success=True):
	if _wants_json_response(request):
		return JsonResponse({
			'success': success,
			'message': message,
			'poll_id': poll.poll_id,
			'is_counting_started': poll.is_counting_started,
			'is_checking_started': poll.is_checking_started,
			'is_counting_active': poll.is_counting_started,
			'is_checking_cleanup_active': poll.is_checking_started,
		}, status=status)

	getattr(messages, message_level)(request, message)
	return redirect('counting_form', poll_id=poll.poll_id)


def _get_counting_poll_queryset(request):
	if request.user.is_authenticated and request.user.is_superuser and request.user.is_active:
		polls_queryset = Poll.objects.all()
	else:
		polls_queryset = Poll.objects.filter(members__account=request.user)

	return polls_queryset.annotate(
		num_candidates=models.Count('candidate', distinct=True),
		num_ballots=models.Count('ballot', distinct=True),
		num_uploaded=models.Count('ballot', filter=models.Q(ballot__process_status='completed'), distinct=True),
		num_counted=models.Count('ballot', filter=models.Q(ballot__counting_status='completed'), distinct=True),
		num_pending_check=models.Count(
			'ballot',
			filter=models.Q(
				ballot__checking_status='NEW',
				ballot__process_status='completed',
				ballot__counting_status='completed'
			),
			distinct=True
		),
		num_checked=models.Count('ballot', filter=models.Q(ballot__checking_status='DONE'), distinct=True),
	).order_by('-poll_id')


@login_required
def counting_config_list(request):
	"""
	Danh sách cuộc bỏ phiếu để cấu hình và bật/tắt kiểm phiếu.
	"""
	polls_queryset = _get_counting_poll_queryset(request)
	paginator = Paginator(polls_queryset, 10)
	page_obj = paginator.get_page(request.GET.get('page', 1))

	return render(request, 'counting/counting_config_list.html', {
		'polls': page_obj
	})


@require_http_methods(["POST"])
def save_configuration(request, poll_id):
	"""
	Lưu cấu hình model cho tất cả các ballot trong poll
	
	Expects JSON: {"config_type": 1, 2 hoac 3}
	"""
	try:
		# Parse request body
		data = json.loads(request.body)
		config_type = data.get('config_type')
		
		if not config_model.is_valid_config(config_type):
			return JsonResponse({
				'status': 'error',
				'message': 'config_type phai la 1, 2 hoac 3'
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
				config_model.apply_config(ai_result, config_type)
				
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


def call_vietnameocr_api(image_paths: List[str]) -> Dict:
	"""
	Goi model_vietnameocr API de nhan dien text
	
	Args:
		image_paths: Danh sách đường dẫn ảnh
		
	Returns:
		Dict chứa kết quả từ API
	"""
	api_url = get_model_api_url(MODEL_VIETNAMEOCR)
	
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
		response = requests.post(api_url, files=files, timeout=settings.AI_SERVER_REQUEST_TIMEOUT)
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


def call_resnet18_x_api(image_paths: List[str]) -> Dict:
	"""
	Goi model_resnet18_x API de detect dau X
	
	Args:
		image_paths: Danh sách đường dẫn ảnh
		
	Returns:
		Dict chứa kết quả từ API
	"""
	api_url = get_model_api_url(MODEL_RESNET18_X)
	
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
		response = requests.post(api_url, files=files, timeout=settings.AI_SERVER_REQUEST_TIMEOUT)
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


def call_resnet18_crossed_api(image_paths: List[str], cascade: bool = False) -> Dict:
	"""
	API mau cho model phieu gach ten.

	Endpoint mac dinh: /api/model_resnet18_crossed/detect/
	Expected response:
	{
		"success": true,
		"results": [
			{
				"label": "crossed" | "not_crossed",
				"is_crossed": true,
				"confidence": 0.95,
				"detections": []
			}
		]
	}
	"""
	file_handles = []
	try:
		files = []
		for path in image_paths:
			filename = os.path.basename(path)
			fh = open(path, 'rb')
			file_handles.append(fh)
			files.append(('images', (filename, fh, 'image/jpeg')))

		data = {
			'contract': json.dumps({
				'expected_result': {
					'label': 'crossed|not_crossed',
					'is_crossed': True,
					'confidence': 0.0,
					'detections': []
				}
			})
		}
		if cascade:
			data.update(config_crossed.get_cascade_request_data())

		response = requests.post(
			get_model_api_url(MODEL_RESNET18_CROSSED),
			files=files,
			data=data,
			timeout=settings.AI_SERVER_REQUEST_TIMEOUT
		)
		response.raise_for_status()
		return response.json()
	except requests.exceptions.RequestException as e:
		return {
			'success': False,
			'error': str(e)
		}
	finally:
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
	vietnameocr_status = False
	resnet18_x_status = False
	resnet18_crossed_status = False
	try:
		health_statuses = get_ai_model_health_statuses()
		vietnameocr_status = health_statuses.get(MODEL_VIETNAMEOCR, False)
		resnet18_x_status = health_statuses.get(MODEL_RESNET18_X, False)
		resnet18_crossed_status = health_statuses.get(MODEL_RESNET18_CROSSED, False)
	except:
		pass  # Nếu lỗi thì để mặc định False
	
	ai_service_statuses = {
		MODEL_VIETNAMEOCR: vietnameocr_status,
		MODEL_RESNET18_X: resnet18_x_status,
		MODEL_RESNET18_CROSSED: resnet18_crossed_status,
	}
	required_services = config_model.get_required_services(poll.config_number) if poll.config_number else []
	ai_ready_for_config = all(ai_service_statuses.get(service, False) for service in required_services) if required_services else False
	can_start_counting = (
		candidates_count > 0
		and ballots_count > 0
		and ballots_with_image_count > 0
		and preprocessed_count == ballots_with_image_total
		and ballots_with_image_total > 0
		and ai_ready_for_config
		and bool(poll.config_number)
	)
	total_ballots_count = poll.total_ballots_count or ballots_count

	context = {
		'poll': poll,
		# Thêm thông tin điều kiện
		'candidates_count': candidates_count,
		'ballots_count': ballots_count,
		'ballots_with_image_count': ballots_with_image_count,
		'ballots_with_image_total': ballots_with_image_total,
		'preprocessed_count': preprocessed_count,
		'vietnameocr_status': vietnameocr_status,
		'resnet18_x_status': resnet18_x_status,
		'resnet18_crossed_status': resnet18_crossed_status,
		'ai_ready_for_config': ai_ready_for_config,
		'config_definitions': config_model.CONFIG_DEFINITIONS,
		# Thêm config_number và status để kiểm tra
		'config_number': poll.config_number,
		'total_ballots': ballots_count,
		'total_ballots_count': total_ballots_count,
		'can_start_counting': can_start_counting,
		'is_counting_active': poll.is_counting_started,
		'is_checking_cleanup_active': poll.is_checking_started,
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
		requested_config = int(request.POST.get('config_type') or request.POST.get('config_number') or 0)
		if not requested_config:
			requested_config = 1 if request.POST.get('config1') == '1' else (2 if request.POST.get('config2') == '1' else 3)
		if saved_config != requested_config:
			messages.error(request, f'Poll đã được kiểm phiếu với cấu hình {saved_config}. Không thể thay đổi cấu hình!')
			return redirect('counting_form', poll_id=poll_id)
	
	# Parse dữ liệu từ form
	config1 = request.POST.get('config1') == '1'
	config2 = request.POST.get('config2') == '1'
	config3 = request.POST.get('config3') == '1'
	
	# Kiểm tra phải chọn đúng 1 cấu hình
	selected_configs = [config1, config2, config3]
	if selected_configs.count(True) == 0:
		messages.warning(request, 'Vui lòng chọn một cấu hình!')
		return redirect('counting_form', poll_id=poll_id)
	
	if selected_configs.count(True) > 1:
		messages.warning(request, 'Chỉ được chọn một cấu hình!')
		return redirect('counting_form', poll_id=poll_id)
	
	# Xác định loại cấu hình
	config_number = 1 if config1 else (2 if config2 else 3)
	
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
	candidate_list = list(Candidate.objects.filter(poll=poll).order_by('candidate_id'))
	
	# Xử lý từng ballot
	for ballot in ballots:
		try:
			# 1. Tạo AIModelResult cho ballot
			ai_result = AIModelResult.objects.create(
				ballot=ballot,
				status='processing'
			)
			
			# 2. Áp dụng cấu hình (config1 hoặc config2)
			config_model.apply_config(ai_result, config_number)
			
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
				if model_name == MODEL_RESNET18_CROSSED:
					resnet18_crossed_result = call_resnet18_crossed_api([cell_image_path], cascade=True)

					if (
						resnet18_crossed_result.get('success')
						and resnet18_crossed_result.get('results')
					):
						detection = resnet18_crossed_result['results'][0]
						ocr_result = {}
						if config_crossed.needs_ocr(detection):
							vietnameocr_result = call_vietnameocr_api([cell_image_path])
							if not (vietnameocr_result.get('success') and vietnameocr_result.get('results')):
								ai_result.set_cell_result(row, col, "[Loi model_vietnameocr]", 0)
								continue
							ocr_detection = vietnameocr_result['results'][0]
							ocr_result = {
								'text': ocr_detection.get('text', ''),
								'confidence': ocr_detection.get('confidence', 0),
							}
						candidate = candidate_list[row] if 0 <= row < len(candidate_list) else None
						result_data = config_crossed.build_crossed_result(
							visual_result=detection,
							ocr_result=ocr_result,
							candidate_name=candidate.name if candidate else '',
						)
						confidence = result_data.get('confidence', 0)
						ai_result.set_cell_result(row, col, result_data, confidence)
						total_processed_cells += 1
					else:
						ai_result.set_cell_result(row, col, "[Loi model_resnet18_crossed]", 0)

				elif model_name == MODEL_VIETNAMEOCR:
					# Goi model_vietnameocr API
					vietnameocr_result = call_vietnameocr_api([cell_image_path])
					
					if vietnameocr_result.get('success') and vietnameocr_result.get('results'):
						recognized_text = vietnameocr_result['results'][0].get('text', '')
						confidence = vietnameocr_result['results'][0].get('confidence', 0)
						
						# Lưu kết quả vào result_model
						ai_result.set_cell_result(row, col, recognized_text, confidence)
						total_processed_cells += 1
					else:
						ai_result.set_cell_result(row, col, "[Loi model_vietnameocr]", 0)
				
				elif model_name == MODEL_RESNET18_X:
					# Goi model_resnet18_x API
					resnet18_x_result = call_resnet18_x_api([cell_image_path])
					
					if resnet18_x_result.get('success') and resnet18_x_result.get('results'):
						detection = resnet18_x_result['results'][0]
						label = detection.get('label', 'none')
						
						# Lay confidence tu ket qua classifier
						confidence = detection.get('confidence', 0)
						
						# Luu ket qua theo contract chung cua model dau X
						result_data = {
							'label': label,
							'raw_label': detection.get('raw_label', ''),
							'is_marked': detection.get('is_marked'),
							'is_cancelled': detection.get('is_cancelled'),
							'probabilities': detection.get('probabilities', {}),
							'detections': detection.get('detections', [])
						}
						ai_result.set_cell_result(row, col, result_data, confidence)
						total_processed_cells += 1
					else:
						ai_result.set_cell_result(row, col, "[Loi model_resnet18_x]", 0)
			
			# 5. Cập nhật trạng thái thành công
			is_valid_by_config = config_model.evaluate_ballot_validity(ai_result, config_number)
			ballot.is_valid = is_valid_by_config
			ballot.save(update_fields=['is_valid'])

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
	
	# 6. Tao BallotSelection bang dispatcher cau hinh
	try:
		successful_results = AIModelResult.objects.filter(
			ballot__poll=poll,
			status='success'
		)
		BallotSelection.objects.filter(ballot__poll=poll).delete()
		selections_count = 0
		for ai_result in successful_results:
			selections_count += config_model.create_ballot_selections(
				ai_result.ballot,
				poll,
				ai_result,
				poll.config_number
			)
		print(f"[BallotSelection] Created {selections_count} selections using config dispatcher")
	except Exception as e:
		print(f"[ERROR] Loi tao BallotSelection bang config dispatcher: {e}")

	# 7. Cap nhat trang thai Poll va Ballot
	poll.status = 'Đã kiểm phiếu'
	poll.save()

	Ballot.objects.filter(poll=poll).update(counting_status='completed')
	
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
	Giữ route cũ, chuyển về trang cấu hình đã gộp.
	"""
	return redirect('counting_form', poll_id=poll_id)


@require_http_methods(["POST"])
def toggle_auto_counting(request, poll_id):
	"""
	Bật/tắt kiểm phiếu: kiểm tự động và cleanup hậu kiểm cùng trạng thái.
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	is_turning_on = not poll.is_counting_started
	
	if is_turning_on and not poll.config_number:
		if _wants_json_response(request):
			message = 'Vui long luu cau hinh truoc khi bat kiem phieu.'
			return _toggle_auto_response(
				request,
				poll,
				message,
				message_level='error',
				status=400,
				success=False,
			)
		messages.error(request, 'Vui lòng lưu cấu hình trước khi bật kiểm phiếu!')
		return redirect('counting_form', poll_id=poll_id)
	
	poll.is_counting_started = is_turning_on
	poll.is_checking_started = is_turning_on
	
	if is_turning_on:
		total_ballots = Ballot.objects.filter(poll=poll).count()
		total_ballots_count = request.POST.get('total_ballots_count', total_ballots)
		
		try:
			total_ballots_count = int(total_ballots_count)
			if total_ballots_count > total_ballots:
				total_ballots_count = total_ballots
			if total_ballots_count < 0:
				total_ballots_count = 0
			poll.total_ballots_count = total_ballots_count
		except (ValueError, TypeError):
			poll.total_ballots_count = total_ballots
	
	poll.save()
	
	if not is_turning_on and _wants_json_response(request):
		message = 'Da tat kiem phieu va tu dong thu hoi phieu hau kiem.'
		return _toggle_auto_response(request, poll, message, message_level='info')
	
	if is_turning_on:
		from counting.tasks import counting_queue
		
		pending_ballots = Ballot.objects.filter(
			poll=poll,
			process_status='completed',
			counting_status='pending'
		).values_list('ballot_id', flat=True)
		
		queued_count = 0
		for ballot_id in pending_ballots:
			counting_queue.delay(ballot_id)
			queued_count += 1
		
		if _wants_json_response(request):
			if queued_count > 0:
				message = f'Da bat kiem phieu. Dang xu ly {queued_count} phieu da upload truoc do.'
			else:
				message = 'Da bat kiem phieu.'
			return _toggle_auto_response(request, poll, message)
		
		if queued_count > 0:
			messages.success(request, f'Đã bật kiểm phiếu. Đang xử lý {queued_count} phiếu đã upload trước đó.')
		else:
			messages.success(request, 'Đã bật kiểm phiếu.')
	else:
		messages.info(request, 'Đã tắt kiểm phiếu.')
	
	return redirect('counting_form', poll_id=poll_id)


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
		'is_checking_started': poll.is_checking_started,
		'is_counting_active': poll.is_counting_started,
		'is_checking_cleanup_active': poll.is_checking_started,
	})




