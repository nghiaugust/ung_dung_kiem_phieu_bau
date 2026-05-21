import os
import json
import zipfile
from io import BytesIO
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.http import JsonResponse
from django.urls import reverse
from django.db import transaction
from account.models import Account
from poll.models import Poll, Candidate, PollMember
from .models import Ballot, BallotSelection
from counting import config_crossed
from counting.configurations import config2_resnet18_x, config3_ocr_resnet18_x
from counting.configurations.base import has_x_mark


REVIEW_STATE_AGREE = 'agree'
REVIEW_STATE_DISAGREE = 'disagree'
REVIEW_STATE_ERROR = 'error'
REVIEW_ROW_STATES_METADATA_KEY = 'hau_kiem_row_states'


def _percent(value):
	try:
		return round(float(value or 0) * 100, 1)
	except (TypeError, ValueError):
		return 0


def _crossed_label_text(label):
	if label == config_crossed.CROSSED_LABEL:
		return 'Gach ten'
	if label == config_crossed.NOT_CROSSED_LABEL:
		return 'Ten binh thuong'
	return 'Unknown'


def _probability_label(raw_label):
	return _crossed_label_text(config_crossed.normalize_crossed_label(raw_label))


def _format_two_label_probabilities(probabilities):
	if not isinstance(probabilities, dict) or not probabilities:
		return ''

	prob_by_label = {}
	for raw_label, value in probabilities.items():
		normalized_label = config_crossed.normalize_crossed_label(raw_label)
		prob_by_label[normalized_label] = _percent(value)

	ordered_labels = [
		config_crossed.CROSSED_LABEL,
		config_crossed.NOT_CROSSED_LABEL,
	]
	parts = [
		f"{_crossed_label_text(label)} {prob_by_label[label]}%"
		for label in ordered_labels
		if label in prob_by_label
	]

	if parts:
		return ', '.join(parts)

	return ', '.join(
		f"{_probability_label(raw_label)} {_percent(value)}%"
		for raw_label, value in probabilities.items()
	)


def _crossed_output_line(model_name, output):
	if not isinstance(output, dict):
		return None
	label = _crossed_label_text(config_crossed.normalize_crossed_label(output.get('label')))
	two_label_text = _format_two_label_probabilities(output.get('probabilities'))
	if two_label_text:
		return f"{model_name}: {two_label_text} => {label}"
	return f"{model_name}: {_percent(output.get('confidence'))}% - {label}"


def _build_crossed_mark_result(cell_data):
	result = cell_data.get('result', {}) if isinstance(cell_data, dict) else {}
	if not isinstance(result, dict):
		return {'ai_voted': False, 'confidence': 0, 'display_text': '0% - none', 'detail_lines': []}

	label = config_crossed.normalize_crossed_label(result.get('label'))
	is_crossed = result.get('is_crossed')
	if not isinstance(is_crossed, bool):
		is_crossed = label == config_crossed.CROSSED_LABEL

	confidence = _percent(cell_data.get('confidence', result.get('confidence', 0)))
	label_text = _crossed_label_text(label)
	detail_lines = []

	stage = result.get('decision_stage')
	if stage:
		detail_lines.append(f"Stage: {stage}")

	model_outputs = result.get('model_outputs', {})
	pipeline_parts = []
	resnet_line = _crossed_output_line('ResNet18', model_outputs.get('resnet18'))
	if resnet_line:
		pipeline_parts.append('ResNet18')
		detail_lines.append(resnet_line)

	svm_line = _crossed_output_line('SVM', model_outputs.get('svm'))
	if svm_line:
		pipeline_parts.append('SVM')
		detail_lines.append(svm_line)

	ocr = result.get('ocr', {})
	if isinstance(ocr, dict):
		ocr_text = ocr.get('text') or ''
		ocr_similarity = _percent(ocr.get('similarity'))
		ocr_used = bool(ocr.get('used')) or bool(ocr_text) or bool(ocr_similarity) or result.get('decision_stage') == 'ocr'
		if ocr_used:
			pipeline_parts.append('OCR')
			detail_lines.append(f"OCR: {ocr_similarity}% - {ocr_text}")

	if result.get('needs_review'):
		detail_lines.append('Can hau kiem')

	pipeline_text = ' + '.join(pipeline_parts) if pipeline_parts else 'AI'

	return {
		'ai_voted': not is_crossed,
		'confidence': confidence,
		'display_text': f"{confidence}% - {label_text} | {pipeline_text}",
		'detail_lines': detail_lines,
		'needs_review': bool(result.get('needs_review')),
	}


def _normalize_review_state(state, voted=False):
	state = str(state or '').strip().lower()
	if state in (REVIEW_STATE_AGREE, REVIEW_STATE_DISAGREE, REVIEW_STATE_ERROR):
		return state
	return REVIEW_STATE_AGREE if voted else REVIEW_STATE_DISAGREE


def _review_state_to_voted(state):
	return state == REVIEW_STATE_AGREE


def _get_saved_review_row_states(ballot):
	metadata = ballot.metadata if isinstance(ballot.metadata, dict) else {}
	row_states = metadata.get(REVIEW_ROW_STATES_METADATA_KEY, {})
	if not isinstance(row_states, dict):
		return {}

	return {
		str(candidate_id): _normalize_review_state(state)
		for candidate_id, state in row_states.items()
	}


def _set_saved_review_row_states(ballot, row_states):
	metadata = dict(ballot.metadata) if isinstance(ballot.metadata, dict) else {}
	metadata[REVIEW_ROW_STATES_METADATA_KEY] = {
		str(candidate_id): _normalize_review_state(state)
		for candidate_id, state in row_states.items()
	}
	ballot.metadata = metadata


def _parse_bool(value):
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		return value.strip().lower() in ('true', '1', 'yes')
	return bool(value)


def _get_x_mark_config(config_number):
	if config_number == 2:
		return config2_resnet18_x.START_ROW, config2_resnet18_x.AGREE_COL, config2_resnet18_x.DISAGREE_COL
	if config_number == 3:
		return config3_ocr_resnet18_x.START_ROW, config3_ocr_resnet18_x.AGREE_COL, config3_ocr_resnet18_x.DISAGREE_COL
	return None


def _x_mark_cell_summary(cell_data):
	if not isinstance(cell_data, dict):
		return False, 0, 'none'

	result = cell_data.get('result', {})
	confidence = _percent(cell_data.get('confidence', result.get('confidence', 0) if isinstance(result, dict) else 0))
	label = result.get('label', 'none') if isinstance(result, dict) else str(result or 'none')
	return has_x_mark(result), confidence, label or 'none'


def _build_x_mark_row_result(agree_cell, disagree_cell):
	agree_marked, agree_conf, agree_label = _x_mark_cell_summary(agree_cell)
	disagree_marked, disagree_conf, disagree_label = _x_mark_cell_summary(disagree_cell)
	confidence = max(agree_conf, disagree_conf)
	mark_count = int(agree_marked) + int(disagree_marked)

	detail_lines = [
		f"Dong y: {agree_conf}% - {agree_label}",
		f"Khong dong y: {disagree_conf}% - {disagree_label}",
	]

	if mark_count != 1:
		reason = 'ca 2 o deu co dau X' if mark_count > 1 else 'khong co dau X'
		detail_lines.append(f"Loi dong: {reason}")
		return {
			'ai_voted': False,
			'state': REVIEW_STATE_ERROR,
			'is_error': True,
			'confidence': confidence,
			'display_text': f"{confidence}% - Loi ({reason})",
			'detail_lines': detail_lines,
		}

	state = REVIEW_STATE_AGREE if agree_marked else REVIEW_STATE_DISAGREE
	label = 'Dong y' if state == REVIEW_STATE_AGREE else 'Khong dong y'
	return {
		'ai_voted': state == REVIEW_STATE_AGREE,
		'state': state,
		'is_error': False,
		'confidence': confidence,
		'display_text': f"{confidence}% - {label}",
		'detail_lines': detail_lines,
	}

@login_required
def upload_ballots(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')

	if request.method == 'POST' and request.FILES.getlist('ballot_files'):
		files = request.FILES.getlist('ballot_files')
		poll_dir = os.path.join(settings.MEDIA_ROOT, str(poll_id))
		os.makedirs(poll_dir, exist_ok=True)
		count = 0
		for f in files:
			file_path = os.path.join(poll_dir, f.name)
			with open(file_path, 'wb+') as destination:
				for chunk in f.chunks():
					destination.write(chunk)
			rel_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
			Ballot.objects.create(poll=poll, ballot_image=rel_path)
			count += 1
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': f'Tải lên {count} phiếu bầu thành công!'
			})
	return render(request, 'ballot/upload.html', {'poll': poll})

# Danh sách phiếu bầu cho 1 poll
@login_required
def ballot_list(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	filter_type = request.GET.get('filter')
	ballots = Ballot.objects.filter(poll=poll).order_by('timestamp')
	if filter_type == 'valid':
		ballots = ballots.filter(is_valid=True)
	elif filter_type == 'invalid':
		ballots = ballots.filter(is_valid=False)

	# Add ballot_name property to each ballot
	def extract_ballot_name(ballot_image):
		if not ballot_image:
			return None
		# ImageFieldFile: dùng .name để lấy relative path
		filename = os.path.basename(ballot_image.name)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]
		return os.path.splitext(filename)[0]
		return os.path.splitext(filename)[0]

	for ballot in ballots:
		ballot.ballot_name = extract_ballot_name(ballot.ballot_image)

	return render(request, 'ballot/list.html', {
		'poll': poll,
		'ballots': ballots,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def ballot_view(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	filter_type = request.GET.get('filter')
	ballots = Ballot.objects.filter(poll=poll).order_by('timestamp')
	if filter_type == 'valid':
		ballots = ballots.filter(is_valid=True)
	elif filter_type == 'invalid':
		ballots = ballots.filter(is_valid=False)
	# Add ballot_name property to each ballot (reuse logic from ballot_list)
	def extract_ballot_name(ballot_image):
		if not ballot_image:
			return None
		filename = os.path.basename(ballot_image)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]
	for ballot in ballots:
		ballot.ballot_name = extract_ballot_name(ballot.ballot_image)
	return render(request, 'ballot/view.html', {
		'poll': poll,
		'ballots': ballots,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def ballot_view_detail(request, ballot_id):
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	# Add ballot_name property for display
	def extract_ballot_name(ballot_image):
		if not ballot_image:
			return None
		filename = os.path.basename(ballot_image)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]
	ballot.ballot_name = extract_ballot_name(ballot.ballot_image)
	return render(request, 'ballot/view_detail.html', {
		'ballot': ballot,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def ballot_list_redirect(request, poll_id):
	# Nếu là admin hoặc manager thì vào trang quản lý, còn lại thì vào trang view
	is_manager = PollMember.objects.filter(poll_id=poll_id, account=request.user, role='manager', status='active').exists()
	if (request.user.is_superuser and request.user.is_active) or is_manager:
		return redirect('ballot:ballot_list', poll_id=poll_id)
	else:
		return redirect('ballot:ballot_view', poll_id=poll_id)

@login_required
def delete_all_ballots(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')

	ballots = poll.ballot_set.all()
	count = ballots.count()
	for ballot in ballots:
		if ballot.ballot_image:
			# ImageFieldFile: dùng .path để lấy absolute path
			file_path = ballot.ballot_image.path
			if os.path.exists(file_path):
				try:
					os.remove(file_path)
				except Exception:
					pass
		ballot.delete()
	# Redirect to poll detail with notification
	return redirect(f'/poll/{poll_id}/?deleted_ballots={count}')

@login_required
def ballot_detail(request, ballot_id):
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	poll = ballot.poll
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	if request.method == 'POST':
		# is_checked removed - use counting_status instead
		# Nếu cần update is_checked, hãy update counting_status = 'completed'
		# Update is_valid
		is_valid = request.POST.get('is_valid')
		ballot.is_valid = (is_valid == 'True')
		# Handle file upload
		if request.FILES.get('ballot_file'):
			f = request.FILES['ballot_file']
			poll_id = ballot.poll.poll_id
			poll_dir = os.path.join(settings.MEDIA_ROOT, str(poll_id))
			os.makedirs(poll_dir, exist_ok=True)
			file_path = os.path.join(poll_dir, f.name)
			with open(file_path, 'wb+') as destination:
				for chunk in f.chunks():
					destination.write(chunk)
			rel_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
			ballot.ballot_image = rel_path
		ballot.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('ballot:ballot_detail', kwargs={'ballot_id': ballot.ballot_id}),
				'message': 'Cập nhật phiếu bầu thành công!'
			})
		return redirect('ballot:ballot_detail', ballot_id=ballot.ballot_id)
	return render(request, 'ballot/detail.html', {
		'ballot': ballot,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def delete_ballot(request, ballot_id):
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	poll = ballot.poll
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll_id = ballot.poll.poll_id
	# Xoá file đã upload nếu có
	if ballot.ballot_image:
		# ImageFieldFile: dùng .path để lấy absolute path
		file_path = ballot.ballot_image.path
		if os.path.exists(file_path):
			try:
				os.remove(file_path)
			except Exception:
				pass
	ballot.delete()
	return redirect('ballot:ballot_list', poll_id=poll_id)

def download_sample_ballots(request):
	"""
	View để tải về 5 file mẫu phiếu bầu trong 1 file ZIP
	"""
	# Tạo file ZIP trong bộ nhớ
	zip_buffer = BytesIO()
	
	with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
		# Đường dẫn đến thư mục chứa các file mẫu
		ballot_dir = os.path.join(settings.BASE_DIR, 'static', 'ballot')
		
		# Thêm 5 file vào ZIP
		for i in range(1, 6):
			file_name = f'ballot_{i}.jpg'
			file_path = os.path.join(ballot_dir, file_name)
			
			if os.path.exists(file_path):
				# Đọc file và thêm vào ZIP với tên mới
				with open(file_path, 'rb') as f:
					zip_file.writestr(f'Phieu_bau_{i}.jpg', f.read())
	
	# Trả về file ZIP
	zip_buffer.seek(0)
	response = HttpResponse(zip_buffer.read(), content_type='application/zip')
	response['Content-Disposition'] = 'attachment; filename="Mau_5_Phieu_Bau.zip"'
	
	return response

@login_required
def hau_kiem_ballot(request, ballot_id):
	"""
	Trang hậu kiểm - xem và chỉnh sửa kết quả kiểm phiếu
	"""
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	poll = ballot.poll
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		return redirect('permission_denied')
	
	# Lấy tất cả phiếu bầu của poll này đã kiểm phiếu (đã sắp xếp theo ID)
	all_ballots = Ballot.objects.filter(poll=poll, counting_status='completed').order_by('ballot_id')
	total_ballots = all_ballots.count()
	
	# Nếu không có phiếu nào đã kiểm, redirect về trang thống kê
	if total_ballots == 0:
		return redirect('poll:thong_ke_detail', poll_id=poll.poll_id)
	
	# Tìm vị trí hiện tại
	ballot_ids = list(all_ballots.values_list('ballot_id', flat=True))
	try:
		current_index = ballot_ids.index(ballot_id) + 1
	except ValueError:
		current_index = 1
	
	# Tìm prev và next ballot
	prev_ballot_id = None
	next_ballot_id = None
	prev_ballot_url = None
	next_ballot_url = None
	
	if current_index > 1:
		prev_ballot_id = ballot_ids[current_index - 2]
		prev_ballot_url = reverse('ballot:hau_kiem_ballot', kwargs={'ballot_id': prev_ballot_id})
	
	if current_index < total_ballots:
		next_ballot_id = ballot_ids[current_index]
		next_ballot_url = reverse('ballot:hau_kiem_ballot', kwargs={'ballot_id': next_ballot_id})
	
	# Lấy danh sách ứng viên
	candidates = Candidate.objects.filter(poll=poll).order_by('candidate_id')
	
	# Lấy các lựa chọn hiện tại
	selections = BallotSelection.objects.filter(ballot=ballot).values_list('candidate_id', flat=True)
	
	# Lay trang thai tung dong da duoc hau kiem neu co.
	saved_row_states = _get_saved_review_row_states(ballot)
	
	# Lấy ảnh detection và metadata
	from preprocessing.models import PreprocessedBallot
	from counting.models import AIModelResult
	
	detection_image = None
	try:
		preprocessed = PreprocessedBallot.objects.get(ballot=ballot)
		detection_image = preprocessed.detection_image
	except PreprocessedBallot.DoesNotExist:
		pass
	
	# Lấy horizontal_lines từ metadata
	horizontal_lines = []
	if ballot.metadata and 'horizontal_lines' in ballot.metadata:
		horizontal_lines = ballot.metadata['horizontal_lines']
	
	# Lay ket qua model_resnet18_x tu AIModelResult de hien thi confidence.
	mark_results = []  # List indexed by candidate order: [{'ai_voted': bool, 'confidence': float}, ...]
	try:
		ai_model_result = AIModelResult.objects.filter(ballot=ballot).order_by('-created_at').first()
		if ai_model_result and ai_model_result.result_model:
			cells = ai_model_result.result_model.get('cells', {})
			
			# Tạo dict để lưu kết quả theo row
			row_results = {}
			
			for cell_key, cell_data in cells.items():
				# cell_key format: "row_col" (ví dụ: "1_2" hoặc "1_3")
				parts = cell_key.split('_')
				if len(parts) == 2:
					row = int(parts[0])  # 1-10 (row index của ứng viên)
					col = int(parts[1])  # 2=Đồng ý, 3=Không đồng ý
					
					result = cell_data.get('result', {})
					confidence = cell_data.get('confidence', 0)
					
					# Kiểm tra nếu có x_mark
					if isinstance(result, dict):
						label = result.get('label', '')
						
						if row not in row_results:
							row_results[row] = {
								'ai_voted': False,
								'confidence': 0,
								'display_text': '0% - none',
								'detail_lines': [],
							}
						
						# Cột 2 là "Đồng ý" - nếu có x_mark thì AI prediction = True
						if col == 2 and label == 'x_mark':
							conf = round(confidence * 100, 1)
							row_results[row]['ai_voted'] = True
							row_results[row]['confidence'] = conf
							row_results[row]['display_text'] = f"{conf}% - Dong y"
							row_results[row]['detail_lines'] = [f"model_resnet18_x: {conf}% - x_mark"]
						# Cột 3 là "Không đồng ý" - nếu có x_mark thì AI prediction = False  
						elif col == 3 and label == 'x_mark':
							conf = round(confidence * 100, 1)
							row_results[row]['ai_voted'] = False
							row_results[row]['confidence'] = conf
							row_results[row]['display_text'] = f"{conf}% - Khong dong y"
							row_results[row]['detail_lines'] = [f"model_resnet18_x: {conf}% - x_mark"]
			
			# Chuyển dict thành list theo thứ tự candidates
			for idx, candidate in enumerate(candidates):
				# Row index bắt đầu từ 1, candidate index từ 0
				row = idx + 1
				if row in row_results:
					mark_results.append(row_results[row])
				else:
					mark_results.append({'ai_voted': False, 'confidence': 0, 'display_text': '0% - none', 'detail_lines': []})

			if poll.config_number == 1:
				crossed_mark_results = []
				for idx, candidate in enumerate(candidates):
					cell_data = cells.get(f"{idx}_0")
					if cell_data:
						crossed_mark_results.append(_build_crossed_mark_result(cell_data))
					else:
						crossed_mark_results.append({
							'ai_voted': False,
							'confidence': 0,
							'display_text': '0% - none',
							'detail_lines': [],
						})
				mark_results = crossed_mark_results

			x_mark_config = _get_x_mark_config(poll.config_number)
			if x_mark_config:
				start_row, agree_col, disagree_col = x_mark_config
				x_mark_results = []
				for idx, candidate in enumerate(candidates):
					row = start_row + idx
					agree_cell = cells.get(f"{row}_{agree_col}")
					disagree_cell = cells.get(f"{row}_{disagree_col}")
					x_mark_results.append(_build_x_mark_row_result(agree_cell, disagree_cell))
				mark_results = x_mark_results
					
	except Exception as e:
		print(f"Error loading AI model results: {e}")
		# Tạo list rỗng với số lượng bằng candidates
		mark_results = [{'ai_voted': False, 'confidence': 0, 'display_text': '0% - none', 'detail_lines': []} for _ in candidates]

	if len(mark_results) < len(candidates):
		mark_results.extend([
			{'ai_voted': False, 'state': REVIEW_STATE_DISAGREE, 'confidence': 0, 'display_text': '0% - none', 'detail_lines': []}
			for _ in range(len(candidates) - len(mark_results))
		])

	supports_row_errors = poll.config_number in (2, 3)
	ballot_results = []
	for idx, candidate in enumerate(candidates):
		candidate_id_key = str(candidate.candidate_id)
		default_state = REVIEW_STATE_AGREE if candidate.candidate_id in selections else REVIEW_STATE_DISAGREE
		if supports_row_errors and idx < len(mark_results):
			default_state = _normalize_review_state(
				mark_results[idx].get('state'),
				mark_results[idx].get('ai_voted', False)
			)
		state = saved_row_states.get(candidate_id_key, default_state)
		if not supports_row_errors and state == REVIEW_STATE_ERROR:
			state = REVIEW_STATE_DISAGREE
		ballot_results.append({
			'candidate_id': candidate.candidate_id,
			'name': candidate.name,
			'state': state,
			'is_error': state == REVIEW_STATE_ERROR,
			'voted': _review_state_to_voted(state)
		})

	context = {
		'poll': poll,
		'current_ballot': ballot,
		'ballot_results': ballot_results,  # For template loop
		'ballot_results_json': json.dumps(ballot_results),  # For JavaScript
		'total_ballots': total_ballots,
		'current_index': current_index,
		'prev_ballot_id': prev_ballot_id,
		'next_ballot_id': next_ballot_id,
		'prev_ballot_url': prev_ballot_url,
		'next_ballot_url': next_ballot_url,
		'detection_image': detection_image,
		'horizontal_lines_json': json.dumps(horizontal_lines),
		'mark_results_json': json.dumps(mark_results),
		'supports_row_errors': supports_row_errors,
		'MEDIA_URL': settings.MEDIA_URL,
	}
	
	return render(request, 'poll/thong_ke/hau_kiem.html', context)

@login_required
def save_hau_kiem(request, ballot_id):
	"""
	API để lưu thay đổi từ trang hậu kiểm
	"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
	
	try:
		ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
		poll = ballot.poll
		
		# Check permission
		is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
		if not (request.user.is_superuser and request.user.is_active) and not is_manager:
			return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

		data = json.loads(request.body)
		votes = data.get('votes', [])
		requested_is_valid = data.get('is_valid', None)
		
		# Sử dụng transaction để đảm bảo tính toàn vẹn dữ liệu
		with transaction.atomic():
			# Xóa tất cả các lựa chọn cũ
			BallotSelection.objects.filter(ballot=ballot).delete()
			
			# Tạo các lựa chọn mới dựa trên dữ liệu từ form
			row_states = {}
			for vote in votes:
				candidate_id = vote.get('candidate_id')
				state = _normalize_review_state(vote.get('state'), vote.get('voted', False))
				
				if not candidate_id:
					continue

				row_states[str(candidate_id)] = state

				if state == REVIEW_STATE_AGREE:
					BallotSelection.objects.create(
						ballot=ballot,
						candidate_id=candidate_id
					)

			_set_saved_review_row_states(ballot, row_states)
			
			# Đánh dấu đã hậu kiểm
			# is_post_checked is now a property - update checking_status instead
			ballot.checking_status = 'DONE'
			if requested_is_valid is None:
				ballot.is_valid = not any(state == REVIEW_STATE_ERROR for state in row_states.values())
			else:
				ballot.is_valid = _parse_bool(requested_is_valid)
			ballot.save(update_fields=['checking_status', 'is_valid', 'metadata'])
		
		# Tìm phiếu tiếp theo để redirect
		all_ballots = Ballot.objects.filter(poll=poll, counting_status='completed').order_by('ballot_id')
		ballot_ids = list(all_ballots.values_list('ballot_id', flat=True))
		
		next_url = None
		try:
			current_index = ballot_ids.index(ballot_id)
			if current_index < len(ballot_ids) - 1:
				next_ballot_id = ballot_ids[current_index + 1]
				next_url = reverse('ballot:hau_kiem_ballot', kwargs={'ballot_id': next_ballot_id})
			else:
				# Hết phiếu, về trang thống kê
				next_url = reverse('poll:thong_ke_detail', kwargs={'poll_id': poll.poll_id})
		except ValueError:
			next_url = reverse('poll:thong_ke_detail', kwargs={'poll_id': poll.poll_id})
		
		return JsonResponse({
			'success': True,
			'message': 'Đã duyệt phiếu thành công!',
			'next_url': next_url
		})
		
		# Sử dụng transaction để đảm bảo tính toàn vẹn dữ liệu
		with transaction.atomic():
			# Xóa tất cả selections hiện tại của ballot này
			BallotSelection.objects.filter(ballot=ballot).delete()
			
			# Tạo selections mới dựa trên votes
			for vote in votes:
				if vote.get('voted', False):
					candidate_id = vote.get('candidate_id')
					candidate = get_object_or_404(Candidate, candidate_id=candidate_id)
					BallotSelection.objects.create(
						ballot=ballot,
						candidate=candidate
					)
		
		return JsonResponse({
			'success': True,
			'message': 'Đã lưu thay đổi thành công!'
		})
		
	except Exception as e:
		return JsonResponse({
			'success': False,
			'message': str(e)
		}, status=500)


@login_required
def toggle_ballot_validity(request, ballot_id):
	"""
	API để đổi trạng thái hợp lệ của phiếu bầu trong trang hậu kiểm
	"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
	
	try:
		ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
		poll = ballot.poll
		
		# Check permission
		is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
		if not (request.user.is_superuser and request.user.is_active) and not is_manager:
			return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
		
		data = {}
		if request.body:
			try:
				data = json.loads(request.body)
			except json.JSONDecodeError:
				data = {}
		
		new_is_valid = data.get('is_valid', None)
		if isinstance(new_is_valid, str):
			new_is_valid = new_is_valid.strip().lower() in ('true', '1', 'yes')
		
		if new_is_valid is None:
			ballot.is_valid = not ballot.is_valid
		else:
			ballot.is_valid = bool(new_is_valid)
		
		ballot.save(update_fields=['is_valid'])
		
		return JsonResponse({
			'success': True,
			'is_valid': ballot.is_valid
		})
	
	except Exception as e:
		return JsonResponse({
			'success': False,
			'message': str(e)
		}, status=500)
