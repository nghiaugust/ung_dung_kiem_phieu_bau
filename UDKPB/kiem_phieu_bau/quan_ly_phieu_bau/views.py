import os
from django.conf import settings
from .models import Ballot
from django.contrib.auth import logout
# Lấy thông tin tài khoản hiện tại
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.contrib.auth.hashers import make_password
from .models import Account
from .models import Poll, Candidate, Ballot
from django.http import JsonResponse
import time # Để giả lập xử lý
import json
from django.http import StreamingHttpResponse
import subprocess
from django.db import transaction
from .models import Ballot_Selection
import glob
import json as pyjson
import datetime
from django.contrib import messages
from django.db.models import Count
from django.urls import reverse
from django.contrib.auth.decorators import login_required

def home(request):
	return render(request, 'quan_ly_phieu_bau/home.html')

def permission_denied(request):
	# messages.warning(request, 'Bạn không có quyền truy cập chức năng này!')
	return render(request, 'quan_ly_phieu_bau/common/permission_denied.html')

@login_required
def thong_ke(request):

	# Lấy tất cả các cuộc bỏ phiếu
	polls = Poll.objects.all()
	thong_ke_data = []
	for poll in polls:
		# Annotate số lượt chọn cho từng ứng viên thuộc poll này
		candidates = Candidate.objects.filter(poll=poll).annotate(
			num_selected=Count('ballot_selection')
		)
		# Tìm ứng viên được chọn nhiều nhất
		top_candidate = candidates.order_by('-num_selected', 'name').first()
		thong_ke_data.append({
			'poll_id': poll.poll_id,
			'poll_title': poll.title,
			'top_candidate': top_candidate.name if top_candidate else '-',
			'top_count': top_candidate.num_selected if top_candidate else 0,
			'status': poll.status or '-',
		})
	return render(request, 'quan_ly_phieu_bau/thong_ke.html', {'thong_ke_data': thong_ke_data})

# Thống kê chi tiết cho 1 cuộc bỏ phiếu
@login_required
def thong_ke_detail(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	# Lấy danh sách ứng cử viên và số lượt được chọn
	from django.db.models import Count
	candidate_stats = Candidate.objects.filter(poll=poll).annotate(
		count=Count('ballot_selection')
	).values('name', 'count').order_by('-count', 'name')
	valid_checked_ballots = Ballot.objects.filter(poll=poll, is_valid=True, is_checked=True).count()
	return render(request, 'quan_ly_phieu_bau/thong_ke/detail.html', {
		'poll': poll,
		'candidate_stats': candidate_stats,
		'total_ballots': valid_checked_ballots,
	})

@login_required
def tai_khoan(request):
	# Chỉ cho phép admin
	if not (request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	return render(request, 'quan_ly_phieu_bau/tai_khoan.html')

# Danh sách tài khoản
@login_required
def account_list(request):
	# Chỉ cho phép admin
	if not (request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	users = Account.objects.all().order_by('-date_joined')
	return render(request, 'quan_ly_phieu_bau/account/list.html', {'users': users})

# View đăng nhập
def login_view(request):
	error = False
	if request.method == 'POST':
		username = request.POST.get('username')
		password = request.POST.get('password')
		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)
			return redirect('home')
		else:
			error = True
	return render(request, 'quan_ly_phieu_bau/login.html', {'form': {'errors': error}})

# View đăng xuất
def logout_view(request):
	logout(request)
	# Xoá session/account info nếu có lưu thêm
	return redirect('login')

@login_required
def account_profile(request):
	return render(request, 'quan_ly_phieu_bau/account/profile.html', {'user': request.user})

# Thêm tài khoản
@login_required
def add_account(request):
	# Chỉ cho phép aadmin
	if not (request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	if request.method == 'POST':
		username = request.POST.get('username')
		name = request.POST.get('name')
		email = request.POST.get('email')
		password = request.POST.get('password')
		role = request.POST.get('role', 'user')
		is_active = bool(request.POST.get('is_active', True))
		account = Account.objects.create(
			username=username,
			last_name=name,
			email=email,
			password=make_password(password),
			role=role,
			is_active=is_active
		)
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('account_list'),
				'message': 'Thêm tài khoản thành công!'
			})
		return redirect('account_list')
	return render(request, 'quan_ly_phieu_bau/account/add_account.html')

# Sửa tài khoản
@login_required
def edit_account(request, account_id):
	# Chỉ cho phép admin
	if not (request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	account = get_object_or_404(Account, id=account_id)
	if request.method == 'POST':
		account.username = request.POST.get('username')
		account.last_name = request.POST.get('last_name', account.last_name)
		account.email = request.POST.get('email', account.email)
		password = request.POST.get('password')
		if password:
			account.password = make_password(password)
		account.role = request.POST.get('role', account.role)
		is_active_val = request.POST.get('is_active', '1')
		account.is_active = (is_active_val == '1')
		account.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('account_list'),
				'message': 'Cập nhật tài khoản thành công!'
			})
		return redirect('account_list')
	return render(request, 'quan_ly_phieu_bau/account/edit_account.html', {'account': account})

@login_required
def edit_account_user(request, account_id):
	account = get_object_or_404(Account, id=account_id)
	if request.method == 'POST':
		account.last_name = request.POST.get('last_name', account.last_name)
		account.email = request.POST.get('email', account.email)
		password = request.POST.get('password')
		if password:
			from django.contrib.auth.hashers import make_password
			account.password = make_password(password)
		account.save()
		# Nếu là AJAX thì trả về JSON
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({'success': True, 'message': 'Cập nhật thành công!'})
		# return redirect('account_profile')
	return render(request, 'quan_ly_phieu_bau/account/edit_account_user.html', {'account': account})

@login_required
def edit_account_redirect(request, account_id):
	# Nếu là admin thì vào trang quản lý, còn lại thì vào trang view
	if hasattr(request.user, 'role') and request.user.role == 'admin':
		return redirect('edit_account', account_id=account_id)
	else:
		return redirect('edit_account_user', account_id=account_id)
	
# Xoá tài khoản
@login_required
def delete_account(request, account_id):
	# Chỉ cho phép aadmin
	if not (request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	account = get_object_or_404(Account, id=account_id)
	if request.method == 'POST':
		account.delete()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('account_list'),
				'message': 'Xoá tài khoản thành công!'
			})
		return redirect('account_list')
	return render(request, 'quan_ly_phieu_bau/account/delete_account.html', {'account': account})

@login_required
def tao_cuoc_bo_phieu(request):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	if request.method == 'POST':
		title = request.POST.get('title')
		description = request.POST.get('description')
		start_time = request.POST.get('start_time')
		end_time = request.POST.get('end_time')
		counting_start_time = request.POST.get('counting_start_time')
		counting_end_time = request.POST.get('counting_end_time')
		status = request.POST.get('status')
		created_by = request.user if request.user.is_authenticated else None
		poll = Poll.objects.create(
			title=title,
			description=description,
			start_time=start_time or None,
			end_time=end_time or None,
			counting_start_time=counting_start_time or None,
			counting_end_time=counting_end_time or None,
			status=status,
			created_by=created_by
		)
		# Nếu là AJAX thì trả về JSON chứa URL chuyển hướng và message
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': poll.poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Tạo cuộc bỏ phiếu thành công!'
			})
		return redirect('poll_detail', poll_id=poll.poll_id)
	return render(request, 'quan_ly_phieu_bau/tao_cuoc_bo_phieu.html')

@login_required
def danh_sach_cuoc_bo_phieu(request):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	if request.user.role == 'admin':
		# Nếu là admin, lấy TẤT CẢ các cuộc bỏ phiếu
		polls_queryset = Poll.objects.all()
	else: 
		# Nếu là assistant, chỉ lấy các cuộc bỏ phiếu có 'created_by' là chính người dùng này
		polls_queryset = Poll.objects.filter(created_by=request.user)

	polls = polls_queryset.order_by('-start_time')
	return render(request, 'quan_ly_phieu_bau/danh_sach_cuoc_bo_phieu.html', {'polls': polls})

@login_required
def poll_detail(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	candidates = Candidate.objects.filter(poll=poll)
	ballots = Ballot.objects.filter(poll=poll)
	total_ballots = ballots.count()
	checked_ballots = ballots.filter(is_checked=True).count()
	unchecked_ballots = ballots.filter(is_checked=False).count()
	valid_ballots = ballots.filter(is_valid=True).count()
	invalid_ballots = ballots.filter(is_valid=False).count()
	# Lấy username người tạo nếu có
	created_by_username = None
	if poll.created_by:
		try:
			created_by_username = poll.created_by.username if poll.created_by else None
		except Account.DoesNotExist:
			created_by_username = poll.created_by

	return render(request, 'quan_ly_phieu_bau/poll/detail.html', {
		'poll': poll,
		'candidates': candidates,
		'total_ballots': total_ballots,
		'checked_ballots': checked_ballots,
		'unchecked_ballots': unchecked_ballots,
		'valid_ballots': valid_ballots,
		'invalid_ballots': invalid_ballots,
		'created_by_username': created_by_username,
	})

# Sửa cuộc bỏ phiếu
@login_required
def edit_poll(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	if request.method == 'POST':
		poll.title = request.POST.get('title', poll.title)
		poll.description = request.POST.get('description', poll.description)
		poll.start_time = request.POST.get('start_time') or None
		poll.end_time = request.POST.get('end_time') or None
		poll.counting_start_time = request.POST.get('counting_start_time') or None
		poll.counting_end_time = request.POST.get('counting_end_time') or None
		poll.status = request.POST.get('status', poll.status)
		poll.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': poll.poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Cập nhật cuộc bỏ phiếu thành công!'
			})
	return render(request, 'quan_ly_phieu_bau/poll/edit.html', {'poll': poll})

# Thêm nhiều ứng cử viên cho 1 cuộc bỏ phiếu
@login_required
def add_candidate(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	if request.method == 'POST':
		# Lấy tất cả các trường name_1, name_2,...
		names = [v for k, v in request.POST.items() if k.startswith('name_') and v.strip()]
		for name in names:
			Candidate.objects.create(poll=poll, name=name)
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': f'Thêm {len(names)} ứng cử viên thành công!'
			})
	return render(request, 'quan_ly_phieu_bau/candidate/add.html', {'poll': poll})

# Sửa ứng cử viên
@login_required
def edit_candidate(request, candidate_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	candidate = get_object_or_404(Candidate, candidate_id=candidate_id)
	if request.method == 'POST':
		candidate.name = request.POST.get('name', candidate.name)
		candidate.description = request.POST.get('description', candidate.description)
		candidate.image_url = request.POST.get('image_url', candidate.image_url)
		candidate.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': candidate.poll.poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Cập nhật ứng cử viên thành công!'
			})

	return render(request, 'quan_ly_phieu_bau/candidate/edit.html', {'candidate': candidate})

# Sao chép danh sách ứng cử viên từ poll khác
@login_required
def copy_candidates(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	if request.method == 'POST':
		source_poll_id = request.POST.get('source_poll_id')
		if not source_poll_id:
			messages.error(request, 'Vui lòng nhập ID cuộc bỏ phiếu nguồn.')
			return redirect('add_candidate', poll_id=poll_id)
		try:
			source_poll = Poll.objects.get(poll_id=source_poll_id)
		except Poll.DoesNotExist:
			messages.error(request, f'Không tìm thấy cuộc bỏ phiếu với ID {source_poll_id}.')
			return redirect('add_candidate', poll_id=poll_id)
		source_candidates = Candidate.objects.filter(poll=source_poll)
		count = 0
		for c in source_candidates:
			Candidate.objects.create(poll=poll, name=c.name, description=c.description, image_url=c.image_url)
			count += 1
		# Chuyển về trang detail và truyền thông báo qua query string
		return redirect(f'/poll/{poll_id}/?copied={count}')
	return redirect('add_candidate', poll_id=poll_id)

# Upload danh sách phiếu bầu cho 1 poll
@login_required
def upload_ballots(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
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
			Ballot.objects.create(poll=poll, ballot_file_path=rel_path)
			count += 1
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll_detail', kwargs={'poll_id': poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': f'Tải lên {count} phiếu bầu thành công!'
			})
	return render(request, 'quan_ly_phieu_bau/ballot/upload.html', {'poll': poll})

# Danh sách phiếu bầu cho 1 poll
@login_required
def ballot_list(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	poll = get_object_or_404(Poll, poll_id=poll_id)
	filter_type = request.GET.get('filter')
	ballots = Ballot.objects.filter(poll=poll).order_by('timestamp')
	if filter_type == 'valid':
		ballots = ballots.filter(is_valid=True)
	elif filter_type == 'invalid':
		ballots = ballots.filter(is_valid=False)

	# Add ballot_name property to each ballot
	def extract_ballot_name(ballot_file_path):
		if not ballot_file_path:
			return None
		import os
		filename = os.path.basename(ballot_file_path)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]

	for ballot in ballots:
		ballot.ballot_name = extract_ballot_name(ballot.ballot_file_path)

	return render(request, 'quan_ly_phieu_bau/ballot/list.html', {
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
	def extract_ballot_name(ballot_file_path):
		if not ballot_file_path:
			return None
		import os
		filename = os.path.basename(ballot_file_path)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]
	for ballot in ballots:
		ballot.ballot_name = extract_ballot_name(ballot.ballot_file_path)
	return render(request, 'quan_ly_phieu_bau/ballot/view.html', {
		'poll': poll,
		'ballots': ballots,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def ballot_view_detail(request, ballot_id):
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	# Add ballot_name property for display
	def extract_ballot_name(ballot_file_path):
		if not ballot_file_path:
			return None
		import os
		filename = os.path.basename(ballot_file_path)
		for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
			if filename.lower().endswith(ext):
				return filename[:-len(ext)]
		return os.path.splitext(filename)[0]
	ballot.ballot_name = extract_ballot_name(ballot.ballot_file_path)
	return render(request, 'quan_ly_phieu_bau/ballot/view_detail.html', {
		'ballot': ballot,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def ballot_list_redirect(request, poll_id):
	# Nếu là admin hoặc assistant thì vào trang quản lý, còn lại thì vào trang view
	if hasattr(request.user, 'role') and request.user.role in ['admin', 'assistant']:
		return redirect('ballot_list', poll_id=poll_id)
	else:
		return redirect('ballot_view', poll_id=poll_id)
	
def counting_stream_generator(poll_id):
	"""
	Đây là một hàm generator. Nó sẽ chạy, trả về dữ liệu với 'yield',
	tạm dừng, rồi chạy tiếp.
	"""

	poll = get_object_or_404(Poll, poll_id=poll_id)
	# Ghi nhận thời gian bắt đầu kiểm phiếu
	poll.counting_start_time = datetime.datetime.now()
	poll.save(update_fields=["counting_start_time"])

	ballots = Ballot.objects.filter(poll=poll)
	total_ballots = ballots.count()

	# --- Kiểm tra điều kiện ban đầu ---
	if not Candidate.objects.filter(poll=poll).exists():
		error_data = {'message': 'Lỗi: Chưa có danh sách ứng viên!', 'progress': -1}
		yield f"data: {json.dumps(error_data)}\n\n"
		return
	if not ballots.exists():
		error_data = {'message': 'Lỗi: Chưa có danh sách phiếu bầu!', 'progress': -1}
		yield f"data: {json.dumps(error_data)}\n\n"
		return
	if poll.status == 'counted':
		error_data = {'message': 'Lỗi: Cuộc bỏ phiếu đã được kiểm!', 'progress': -1}
		yield f"data: {json.dumps(error_data)}\n\n"
		return

	try:
		# Đường dẫn input/output
		input_dir = os.path.join(settings.MEDIA_ROOT, str(poll_id))
		output_dir = input_dir  # theo yêu cầu
		ket_qua_dir = os.path.join(input_dir, f"ket_qua_{poll_id}")

		# Xóa thư mục ket_qua cũ nếu có (nếu muốn làm sạch)
		if os.path.exists(ket_qua_dir):
			import shutil
			shutil.rmtree(ket_qua_dir)

		# Giai đoạn 1: Thông báo bắt đầu
		update_data = {'message': 'Bắt đầu quá trình kiểm phiếu...', 'progress': 5}
		yield f"data: {json.dumps(update_data)}\n\n"

		# Chạy lệnh kiểm phiếu bằng subprocess (không chờ hoàn thành)
		cmd = [
			'python',
			'-m', 'processors.trocr_yolo',
			'--input_dir', input_dir,
			'--output_dir', output_dir
		]
		# Xác định đường dẫn tuyệt đối tới ballot_processing_system
		ballot_processing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ballot_processing_system'))
		#proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ballot_processing_dir)
		proc = subprocess.Popen(cmd, cwd=ballot_processing_dir)

		print("Đã khởi chạy quá trình kiểm phiếu...")
		# Theo dõi tiến trình sinh file json mỗi 5s
		import glob
		import math
		last_count = 0
		while True:
			time.sleep(10)
			# Đếm số file json trong ket_qua_{poll_id}
			json_files = glob.glob(os.path.join(ket_qua_dir, '*.json'))
			count = len(json_files)
			if count > last_count:
				last_count = count
			print(f"Đã phát hiện {count} phiếu...")
			progress = min(99, max(5, math.floor((count / total_ballots) * 100))) if total_ballots else 99
			update_data = {
				'message': f'Đã kiểm được {count}/{total_ballots} phiếu...',
				'progress': progress
			}
			yield f"data: {json.dumps(update_data)}\n\n"
			# Nếu đã đủ số phiếu hoặc process đã kết thúc thì break
			if count >= total_ballots:
				break
			if proc.poll() is not None:
				# Nếu process đã kết thúc nhưng chưa đủ file, vẫn break để tránh lặp vô hạn
				break

		# Đợi process kết thúc hẳn (nếu chưa)
		proc.wait()

		# Thông báo đang lưu dữ liệu vào database
		update_data = {'message': 'Đang tiến hành lưu dữ liệu vào database...', 'progress': 99}
		yield f"data: {json.dumps(update_data)}\n\n"

		# Gọi hàm lưu thông tin kiểm phiếu
		luu_thong_tin_kiem_phieu(poll_id)

		# Ghi nhận thời gian kết thúc kiểm phiếu và cập nhật trạng thái
		poll.counting_end_time = datetime.datetime.now()
		poll.status = 'counted'
		poll.save(update_fields=["counting_end_time", "status"])

		# Giai đoạn cuối: Báo cáo thành công
		success_data = {'message': 'Kiểm phiếu hoàn tất!', 'progress': 100}
		yield f"data: {json.dumps(success_data)}\n\n"
	except Exception as e:
		error_data = {'message': f'Lỗi hệ thống: {str(e)}', 'progress': -1}
		yield f"data: {json.dumps(error_data)}\n\n"


@login_required
def kiem_phieu_stream(request, poll_id):
	"""
	View chính để gọi generator và trả về một StreamingHttpResponse.
	"""
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')

	# Trả về một luồng dữ liệu, với content type là text/event-stream
	response = StreamingHttpResponse(counting_stream_generator(poll_id), content_type="text/event-stream")
	# Header này giúp tránh buffering ở một số proxy
	response['X-Accel-Buffering'] = 'no'
	return response

def luu_thong_tin_kiem_phieu(poll_id):
	"""
	Hàm này sẽ lưu thông tin kiểm phiếu vào cơ sở dữ liệu.
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)

	# Lấy danh sách ballot của poll này
	ballots = Ballot.objects.filter(poll=poll)
	ballot_id_list = []
	ballot_name_list = []
	for ballot in ballots:
		ballot_id_list.append(ballot.ballot_id)
		# Lấy tên gốc từ ballot_file_path, ví dụ: '1/ballot_1.jpg' -> 'ballot_1'
		if ballot.ballot_file_path:
			base = os.path.basename(ballot.ballot_file_path)
			name, _ = os.path.splitext(base)
			ballot_name_list.append(name)
		else:
			ballot_name_list.append("")

	# Lấy danh sách Candidate, lưu (id, name viết hoa)
	candidates = Candidate.objects.filter(poll=poll)
	candidate_info_list = [(c.candidate_id, c.name.upper() if c.name else "") for c in candidates]

	# Đường dẫn kết quả kiểm phiếu
	ket_qua_dir = os.path.join('media', str(poll_id), f'ket_qua_{poll_id}')
	
	json_files = glob.glob(os.path.join(ket_qua_dir, '*.json'))

	for json_path in json_files:
		file_name = os.path.basename(json_path)
		name_no_ext, _ = os.path.splitext(file_name)
		if name_no_ext in ballot_name_list:
			idx = ballot_name_list.index(name_no_ext)
			ballot_id = ballot_id_list[idx]
			ballot = Ballot.objects.get(ballot_id=ballot_id)
			try:
				with transaction.atomic():
					with open(json_path, 'r', encoding='utf-8') as f:
						data = pyjson.load(f)
					# data là list các dict
					import difflib
					for row in data:
						# Kiểm tra hợp lệ dòng đầu tiên
						dong_y = row.get('dong_y')
						khong_dong_y = row.get('khong_dong_y')
						if dong_y is not None and khong_dong_y is not None:
							if (dong_y and khong_dong_y) or (not dong_y and not khong_dong_y):
								ballot.is_valid = False
								ballot.save(update_fields=['is_valid'])
								# Nếu không hợp lệ, rollback transaction và sang file tiếp theo
								raise Exception('Phiếu không hợp lệ do cả đồng ý và không đồng ý cùng True hoặc cùng False')
						# Nếu hợp lệ, kiểm tra trường ho_ten bằng similarity
						ho_ten = row.get('ho_ten', '').strip().upper()
						ratios = []
						for cid, cname in candidate_info_list:
							ratio = difflib.SequenceMatcher(None, ho_ten, cname).ratio()
							ratios.append((cid, ratio))
						# Chọn ứng viên có tỉ lệ similarity cao nhất
						if ratios:
							best_cid, best_ratio = max(ratios, key=lambda x: x[1])
							if best_cid and dong_y:
								Ballot_Selection.objects.create(ballot=ballot, candidate_id=best_cid)
					# Đánh dấu đã kiểm phiếu
					ballot.is_checked = True
					ballot.save(update_fields=['is_checked'])
			except Exception as e:
				# Nếu có lỗi, rollback transaction, không tạo gì cho ballot này
				ballot.is_valid = False
				ballot.save(update_fields=['is_valid'])
				continue
	# Trả về các danh sách nếu cần debug
	return ballot_id_list, ballot_name_list, candidate_info_list

@login_required
def delete_poll(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')

	# Xoá tất cả ứng viên và phiếu bầu trước khi xoá poll
	delete_all_candidates(request, poll_id)
	delete_all_ballots(request, poll_id)

	poll = get_object_or_404(Poll, poll_id=poll_id)
	poll.delete()
	return redirect('danh_sach_cuoc_bo_phieu')

@login_required
def delete_candidate(request, candidate_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	candidate = get_object_or_404(Candidate, candidate_id=candidate_id)
	poll_id = candidate.poll.poll_id
	candidate.delete()
	# Redirect with notification
	return redirect(f'/poll/{poll_id}/?deleted=1')

@login_required
def delete_all_candidates(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	count = poll.candidate_set.count()
	poll.candidate_set.all().delete()
	# Redirect with notification
	return redirect(f'/poll/{poll_id}/?deleted_all={count}')

@login_required
def delete_all_ballots(request, poll_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')

	poll = get_object_or_404(Poll, poll_id=poll_id)
	ballots = poll.ballot_set.all()
	count = ballots.count()
	for ballot in ballots:
		if ballot.ballot_file_path:
			file_path = os.path.join(settings.MEDIA_ROOT, ballot.ballot_file_path)
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
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
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
			ballot.ballot_file_path = rel_path
		ballot.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('ballot_detail', kwargs={'ballot_id': ballot.ballot_id}),
				'message': 'Cập nhật phiếu bầu thành công!'
			})
		return redirect('ballot_detail', ballot_id=ballot.ballot_id)
	return render(request, 'quan_ly_phieu_bau/ballot/detail.html', {
		'ballot': ballot,
		'MEDIA_URL': settings.MEDIA_URL,
	})

@login_required
def delete_ballot(request, ballot_id):
	# Chỉ cho phép assistant hoặc admin
	if not (request.user.role == 'assistant' or request.user.role == 'admin'):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	
	ballot = get_object_or_404(Ballot, ballot_id=ballot_id)
	poll_id = ballot.poll.poll_id
	# Xoá file đã upload nếu có
	if ballot.ballot_file_path:
		file_path = os.path.join(settings.MEDIA_ROOT, ballot.ballot_file_path)
		if os.path.exists(file_path):
			try:
				os.remove(file_path)
			except Exception:
				pass
	ballot.delete()
	return redirect('ballot_list', poll_id=poll_id)
