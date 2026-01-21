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
	all_ballots = Ballot.objects.filter(poll=poll, is_checked=True).order_by('ballot_id')
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
	
	# Tạo danh sách kết quả
	ballot_results = []
	for candidate in candidates:
		ballot_results.append({
			'candidate_id': candidate.candidate_id,
			'name': candidate.name,
			'voted': candidate.candidate_id in selections
		})
	
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
	
	# Lấy kết quả YOLO detection từ AIModelResult (CHỈ để hiển thị confidence, không dùng cho voted)
	yolo_results = []  # List indexed by candidate order: [{'ai_voted': bool, 'confidence': float}, ...]
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
							row_results[row] = {'ai_voted': False, 'confidence': 0}
						
						# Cột 2 là "Đồng ý" - nếu có x_mark thì AI prediction = True
						if col == 2 and label == 'x_mark':
							row_results[row]['ai_voted'] = True
							row_results[row]['confidence'] = round(confidence * 100, 1)
						# Cột 3 là "Không đồng ý" - nếu có x_mark thì AI prediction = False  
						elif col == 3 and label == 'x_mark':
							row_results[row]['ai_voted'] = False
							row_results[row]['confidence'] = round(confidence * 100, 1)
			
			# Chuyển dict thành list theo thứ tự candidates
			for idx, candidate in enumerate(candidates):
				# Row index bắt đầu từ 1, candidate index từ 0
				row = idx + 1
				if row in row_results:
					yolo_results.append(row_results[row])
				else:
					yolo_results.append({'ai_voted': False, 'confidence': 0})
					
	except Exception as e:
		print(f"Error loading YOLO results: {e}")
		# Tạo list rỗng với số lượng bằng candidates
		yolo_results = [{'ai_voted': False, 'confidence': 0} for _ in candidates]

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
		'yolo_results_json': json.dumps(yolo_results),
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
		
		# Sử dụng transaction để đảm bảo tính toàn vẹn dữ liệu
		with transaction.atomic():
			# Xóa tất cả các lựa chọn cũ
			BallotSelection.objects.filter(ballot=ballot).delete()
			
			# Tạo các lựa chọn mới dựa trên dữ liệu từ form
			for vote in votes:
				candidate_id = vote.get('candidate_id')
				voted = vote.get('voted', False)
				
				if voted and candidate_id:
					BallotSelection.objects.create(
						ballot=ballot,
						candidate_id=candidate_id
					)
			
			# Đánh dấu đã hậu kiểm
			# is_post_checked is now a property - update checking_status instead
			ballot.checking_status = 'DONE'
			ballot.save(update_fields=['checking_status'])
		
		# Tìm phiếu tiếp theo để redirect
		all_ballots = Ballot.objects.filter(poll=poll, is_checked=True).order_by('ballot_id')
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
