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
		# Update timestamp
		timestamp = request.POST.get('timestamp')
		if timestamp:
			from django.utils.dateparse import parse_datetime
			import datetime
			# Convert from HTML5 datetime-local to Python datetime
			if 'T' in timestamp:
				timestamp = timestamp.replace('T', ' ')
			try:
				ballot.timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M')
			except Exception:
				pass
		# Update is_checked
		is_checked = request.POST.get('is_checked')
		ballot.is_checked = (is_checked == 'True')
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
	
	# Lấy tất cả phiếu bầu của poll này (đã sắp xếp theo ID)
	all_ballots = Ballot.objects.filter(poll=poll).order_by('ballot_id')
	total_ballots = all_ballots.count()
	
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
	
	# ImageFieldFile: dùng .name để lấy relative path
	original_path = ballot.ballot_image.name if ballot.ballot_image else ''
	folder, filename = os.path.split(original_path)
	detect_filename = "detect_" + filename
	detect_path = os.path.join(folder, detect_filename) if folder else detect_filename

	context = {
		'poll': poll,
		'current_ballot': ballot,
		'ballot_results': ballot_results,
		'total_ballots': total_ballots,
		'current_index': current_index,
		'prev_ballot_id': prev_ballot_id,
		'next_ballot_id': next_ballot_id,
		'prev_ballot_url': prev_ballot_url,
		'next_ballot_url': next_ballot_url,
		'detect_ballot_image': detect_path,
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
