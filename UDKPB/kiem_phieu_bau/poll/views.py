import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from account.models import Account
from .models import Poll, Candidate, PollMember, Voter
from ballot.models import Ballot, BallotSelection
from ballot.views import delete_all_ballots
from django.http import JsonResponse
import time
import json
from django.http import StreamingHttpResponse
import subprocess
from django.db import transaction
import glob
import json as pyjson
import datetime
from django.contrib import messages
from django.db.models import Count
from django.urls import reverse

# ==================== POLL MANAGEMENT ====================

@login_required
def tao_cuoc_bo_phieu(request):
	if request.method == 'POST':
		title = request.POST.get('title')
		description = request.POST.get('description')
		start_time = request.POST.get('start_time')
		end_time = request.POST.get('end_time')
		counting_start_time = request.POST.get('counting_start_time')
		counting_end_time = request.POST.get('counting_end_time')
		status = request.POST.get('status')
		created_by = request.user if request.user.is_authenticated else None
		
		# Tạo Poll trước
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
		
		# Khởi tạo HMAC secret key cho poll (mã hóa và lưu vào DB)
		from security.hmac_utils import initialize_poll_hmac_key
		initialize_poll_hmac_key(poll)
		
		# Thêm người tạo vào làm manager
		if created_by:
			PollMember.objects.create(
				poll=poll,
				account=created_by,
				role='manager',
				status='active'
			)

		# Nếu là AJAX thì trả về JSON chứa URL chuyển hướng và message:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': poll.poll_id})
			# Kiểm tra xem có tutorial mode không
			if request.POST.get('tutorial') == 'true':
				redirect_url += '?tutorial=true'
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Tạo cuộc bỏ phiếu thành công!'
			})
		# Nếu không phải AJAX, redirect bình thường
		tutorial = request.GET.get('tutorial', 'false')
		redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': poll.poll_id})
		if tutorial == 'true':
			redirect_url += '?tutorial=true'
		return redirect(redirect_url)
	
	# GET request - hiển thị form tạo cuộc bỏ phiếu
	tutorial = request.GET.get('tutorial', 'false')
	return render(request, 'poll/tao_cuoc_bo_phieu.html', {'tutorial': tutorial})

@login_required
def danh_sach_cuoc_bo_phieu(request):
	if request.user.is_superuser and request.user.is_active:
		# Nếu là admin, lấy TẤT CẢ các cuộc bỏ phiếu
		polls_queryset = Poll.objects.all()
	else: 
		# Nếu khác admin, chỉ lấy các cuộc bỏ phiếu mà user là thành viên
		polls_queryset = Poll.objects.filter(members__account=request.user)

	polls = polls_queryset.order_by('-start_time')
	return render(request, 'poll/danh_sach_cuoc_bo_phieu.html', {'polls': polls})

@login_required
def poll_detail(request, poll_id):
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
	
	# Kiểm tra xem có tutorial mode không
	tutorial = request.GET.get('tutorial', 'false')

	return render(request, 'poll/detail.html', {
		'poll': poll,
		'candidates': candidates,
		'total_ballots': total_ballots,
		'checked_ballots': checked_ballots,
		'unchecked_ballots': unchecked_ballots,
		'valid_ballots': valid_ballots,
		'invalid_ballots': invalid_ballots,
		'created_by_username': created_by_username,
		'tutorial': tutorial,
	})

# Sửa cuộc bỏ phiếu
@login_required
def edit_poll(request, poll_id):
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
			redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': poll.poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Cập nhật cuộc bỏ phiếu thành công!'
			})
	return render(request, 'poll/edit.html', {'poll': poll})

@login_required
def delete_poll(request, poll_id):
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

	# Xoá tất cả ứng viên và phiếu bầu trước khi xoá poll
	delete_all_candidates(request, poll_id)
	delete_all_ballots(request, poll_id)
	poll.delete()

# ==================== CANDIDATE MANAGEMENT ====================

# Thêm nhiều ứng cử viên cho 1 cuộc bỏ phiếu
@login_required
def add_candidate(request, poll_id):
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
	if request.method == 'POST':
		# Lấy tất cả các trường name_1, name_2,...
		names = [v for k, v in request.POST.items() if k.startswith('name_') and v.strip()]
		for name in names:
			Candidate.objects.create(poll=poll, name=name)
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': f'Thêm {len(names)} ứng cử viên thành công!'
			})
	return render(request, 'poll/candidate/add.html', {'poll': poll})

# Sửa ứng cử viên
@login_required
def edit_candidate(request, candidate_id):
	candidate = get_object_or_404(Candidate, candidate_id=candidate_id)
	poll = candidate.poll
	
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
		candidate.name = request.POST.get('name', candidate.name)
		candidate.description = request.POST.get('description', candidate.description)
		candidate.image_url = request.POST.get('image_url', candidate.image_url)
		candidate.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': candidate.poll.poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': 'Cập nhật ứng cử viên thành công!'
			})

	return render(request, 'poll/candidate/edit.html', {'candidate': candidate})

# Sao chép danh sách ứng cử viên từ poll khác
@login_required
def copy_candidates(request, poll_id):
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
	
	# Kiểm tra quyền: chỉ người tạo poll hoặc admin mới được copy
	if request.user.role != 'admin' and poll.created_by != request.user:
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': False,
				'message': 'Bạn không có quyền thực hiện thao tác này.'
			})
		messages.error(request, 'Bạn không có quyền thực hiện thao tác này.')
		return redirect('poll:add_candidate', poll_id=poll_id)
	
	if request.method == 'POST':
		source_poll_id = request.POST.get('source_poll_id')
		if not source_poll_id:
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': 'Vui lòng nhập ID cuộc bỏ phiếu nguồn.'
				})
			messages.error(request, 'Vui lòng nhập ID cuộc bỏ phiếu nguồn.')
			return redirect('poll:add_candidate', poll_id=poll_id)
		try:
			source_poll = Poll.objects.get(poll_id=source_poll_id)
		except Poll.DoesNotExist:
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': f'Không tìm thấy cuộc bỏ phiếu với ID {source_poll_id}.'
				})
			messages.error(request, f'Không tìm thấy cuộc bỏ phiếu với ID {source_poll_id}.')
			return redirect('poll:add_candidate', poll_id=poll_id)
		# Kiểm tra xem user hiện tại có phải là người tạo source_poll không
		# Admin được phép copy từ bất kỳ poll nào
		is_source_manager = PollMember.objects.filter(poll=source_poll, account=request.user, role='manager', status='active').exists()
		if not (request.user.is_superuser and request.user.is_active) and not is_source_manager:
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': f'Không tìm thấy cuộc bỏ phiếu với ID {source_poll_id} trong danh sách phiếu bầu của bạn.'
				})
			messages.error(request, f'Không tìm thấy cuộc bỏ phiếu với ID {source_poll_id} trong danh sách phiếu bầu của bạn.')
			return redirect('poll:add_candidate', poll_id=poll_id)
		
		source_candidates = Candidate.objects.filter(poll=source_poll)
		count = 0
		for c in source_candidates:
			Candidate.objects.create(poll=poll, name=c.name, description=c.description, image_url=c.image_url)
			count += 1
		
		# Trả về JSON nếu là AJAX request
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			redirect_url = reverse('poll:poll_detail', kwargs={'poll_id': poll_id})
			return JsonResponse({
				'success': True,
				'redirect_url': redirect_url,
				'message': f'Đã sao chép {count} ứng cử viên thành công!'
			})
		# Chuyển về trang detail và truyền thông báo qua query string
		return redirect(f'/poll/{poll_id}/?copied={count}')
	return redirect('poll:add_candidate', poll_id=poll_id)

@login_required
def delete_candidate(request, candidate_id):
	candidate = get_object_or_404(Candidate, candidate_id=candidate_id)
	poll = candidate.poll
	
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

	poll_id = candidate.poll.poll_id
	candidate.delete()
	# Redirect with notification
	return redirect(f'/poll/{poll_id}/?deleted=1')

@login_required
def delete_all_candidates(request, poll_id):
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
	
	poll.candidate_set.all().delete()
	count = poll.candidate_set.count()
	# Redirect with notification
	return redirect(f'/poll/{poll_id}/?deleted_all={count}')

# ==================== POLL MEMBER MANAGEMENT ====================

@login_required
def manage_poll_accounts(request):
	"""
	Trang quản lý tài khoản cho tất cả các cuộc bỏ phiếu
	Hiển thị danh sách polls với nested table cho members
	"""
	# Chỉ admin mới có quyền truy cập
	if not (request.user.is_superuser and request.user.is_active):
		return redirect('permission_denied')
	
	# Lấy tất cả các cuộc bỏ phiếu
	polls = Poll.objects.all().order_by('-poll_id')
	
	# Lấy tất cả members cho các polls này
	poll_data = []
	for poll in polls:
		members = PollMember.objects.filter(poll=poll).select_related('account', 'assigned_by').order_by('account__username')
		# Tạo list các account_id đã là thành viên
		member_account_ids = [member.account.id for member in members]
		poll_data.append({
			'poll': poll,
			'members': members,
			'member_account_ids': member_account_ids,
		})
	
	# Lấy danh sách tất cả tài khoản active để thêm
	all_accounts = Account.objects.filter(is_active=True).order_by('username')
	
	return render(request, 'poll/manage_poll_accounts.html', {
		'poll_data': poll_data,
		'all_accounts': all_accounts,
	})

@login_required
def poll_members(request, poll_id):
	"""
	Hiển thị danh sách thành viên của một cuộc bỏ phiếu
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		return redirect('permission_denied')
	
	# Lấy danh sách thành viên
	members = PollMember.objects.filter(poll=poll).select_related('account', 'assigned_by').order_by('-assigned_at')
	
	return render(request, 'poll/poll_member/list.html', {
		'poll': poll,
		'members': members,
	})

@login_required
def add_poll_member(request, poll_id):
	"""
	Thêm thành viên vào cuộc bỏ phiếu
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		return redirect('permission_denied')
	
	if request.method == 'POST':
		account_id = request.POST.get('account_id')
		
		if not account_id:
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': 'Vui lòng chọn tài khoản!'
				})
			messages.error(request, 'Vui lòng chọn tài khoản!')
			return redirect('poll:add_poll_member', poll_id=poll_id)
		
		try:
			account = Account.objects.get(id=account_id)
		except Account.DoesNotExist:
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': 'Tài khoản không tồn tại!'
				})
			messages.error(request, 'Tài khoản không tồn tại!')
			return redirect('poll:add_poll_member', poll_id=poll_id)
		
		# Kiểm tra xem tài khoản đã là thành viên chưa
		if PollMember.objects.filter(poll=poll, account=account).exists():
			if request.headers.get('x-requested-with') == 'XMLHttpRequest':
				return JsonResponse({
					'success': False,
					'message': f'Tài khoản {account.username} đã là thành viên của cuộc bỏ phiếu này!'
				})
			messages.warning(request, f'Tài khoản {account.username} đã là thành viên của cuộc bỏ phiếu này!')
			return redirect('poll:add_poll_member', poll_id=poll_id)
		
		# Tạo thành viên mới
		PollMember.objects.create(
			poll=poll,
			account=account,
			assigned_by=request.user
		)
		
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('poll:poll_members', kwargs={'poll_id': poll_id}),
				'message': f'Đã thêm {account.username} vào cuộc bỏ phiếu!'
			})
		
		messages.success(request, f'Đã thêm {account.username} vào cuộc bỏ phiếu!')
		return redirect('poll:poll_members', poll_id=poll_id)
	
	# GET request - hiển thị form
	# Lấy danh sách tài khoản chưa là thành viên
	existing_member_ids = PollMember.objects.filter(poll=poll).values_list('account_id', flat=True)
	available_accounts = Account.objects.exclude(id__in=existing_member_ids).filter(is_active=True).order_by('username')
	
	return render(request, 'poll/poll_member/add.html', {
		'poll': poll,
		'accounts': available_accounts,
	})

@login_required
def delete_poll_member(request, member_id):
	"""
	Xóa thành viên khỏi cuộc bỏ phiếu
	"""
	member = get_object_or_404(PollMember, member_id=member_id)
	poll = member.poll
	poll_id = poll.poll_id
	account_username = member.account.username
	
	# Check permission
	is_manager = PollMember.objects.filter(poll=poll, account=request.user, role='manager', status='active').exists()
	if not (request.user.is_superuser and request.user.is_active) and not is_manager:
		return redirect('permission_denied')
	
	if request.method == 'POST':
		member.delete()
		
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('poll:poll_members', kwargs={'poll_id': poll_id}),
				'message': f'Đã xóa {account_username} khỏi cuộc bỏ phiếu!'
			})
		
		messages.success(request, f'Đã xóa {account_username} khỏi cuộc bỏ phiếu!')
		return redirect('poll:poll_members', poll_id=poll_id)
	
	return render(request, 'poll/poll_member/delete.html', {
		'member': member,
	})

# ==================== STATISTICS ====================

@login_required
def thong_ke(request):
	# Lấy các cuộc bỏ phiếu dựa trên role
	if request.user.is_superuser and request.user.is_active:
		# Admin xem được tất cả các cuộc bỏ phiếu
		polls = Poll.objects.all()
	else:
		# User khác chỉ xem được các cuộc bỏ phiếu mà họ là thành viên
		polls = Poll.objects.filter(members__account=request.user)
	
	thong_ke_data = []
	for poll in polls:
		# Annotate số lượt chọn cho từng ứng viên thuộc poll này
		candidates = Candidate.objects.filter(poll=poll).annotate(
			num_selected=Count('ballotselection')
		)
		# Tìm ứng viên được chọn nhiều nhất
		top_candidate = candidates.order_by('-num_selected', 'name').first()
		
		# Lấy ID của ballot đầu tiên trong poll này để dùng cho nút Hậu kiểm
		first_ballot = Ballot.objects.filter(poll=poll).order_by('ballot_id').first()
		first_ballot_id = first_ballot.ballot_id if first_ballot else None
		
		thong_ke_data.append({
			'poll_id': poll.poll_id,
			'poll_title': poll.title,
			'top_candidate': top_candidate.name if top_candidate else '-',
			'top_count': top_candidate.num_selected if top_candidate else 0,
			'status': poll.status or '-',
			'first_ballot_id': first_ballot_id,
		})
	return render(request, 'poll/thong_ke/thong_ke.html', {'thong_ke_data': thong_ke_data})

# Thống kê chi tiết cho 1 cuộc bỏ phiếu
@login_required
def thong_ke_detail(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	# Lấy danh sách ứng cử viên và số lượt được chọn
	candidate_stats = Candidate.objects.filter(poll=poll).annotate(
		count=Count('ballotselection')
	).values('name', 'count').order_by('-count', 'name')
	valid_checked_ballots = Ballot.objects.filter(poll=poll, is_valid=True, is_checked=True).count()
	return render(request, 'poll/thong_ke/detail.html', {
		'poll': poll,
		'candidate_stats': candidate_stats,
		'total_ballots': valid_checked_ballots,
	})

# ==================== COUNTING FUNCTIONS ====================

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
		# Thư mục gốc chứa các thư mục con theo ngày tháng
		base_dir = os.path.join(settings.MEDIA_ROOT, 'ballots', str(poll_id))
		
		# Tìm tất cả file ảnh trong các thư mục con (theo cấu trúc yyyy/mm/dd/)
		image_files = []
		for root, dirs, files in os.walk(base_dir):
			for file in files:
				if file.lower().endswith(('.jpg', '.jpeg', '.png')):
					# Bỏ qua file trong thư mục ket_qua
					if 'ket_qua' not in root:
						image_files.append(os.path.join(root, file))
		
		if not image_files:
			error_data = {'message': f'Lỗi: Không tìm thấy ảnh nào trong {base_dir}!', 'progress': -1}
			yield f"data: {json.dumps(error_data)}\n\n"
			return
		
		print(f"Tìm thấy {len(image_files)} ảnh phiếu bầu")
		
		# Đường dẫn output và kết quả
		output_dir = base_dir  # lưu kết quả vào cùng thư mục gốc
		ket_qua_dir = os.path.join(base_dir, f"ket_qua_{poll_id}")

		# Xóa thư mục ket_qua cũ nếu có (nếu muốn làm sạch)
		if os.path.exists(ket_qua_dir):
			import shutil
			shutil.rmtree(ket_qua_dir)

		# Giai đoạn 1: Thông báo bắt đầu
		update_data = {'message': 'Bắt đầu quá trình kiểm phiếu...', 'progress': 5}
		yield f"data: {json.dumps(update_data)}\n\n"

		# Chạy lệnh kiểm phiếu bằng subprocess (không chờ hoàn thành)
		# Truyền base_dir để script tìm tất cả file trong thư mục con
		cmd = [
			'python',
			'-m', 'processors.trocr_yolo',
			'--input_dir', base_dir,
			'--output_dir', output_dir
		]
		# Xác định đường dẫn tuyệt đối tới ballot_processing_system
		ballot_processing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ballot_processing_system'))
		#proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ballot_processing_dir)
		proc = subprocess.Popen(cmd, cwd=ballot_processing_dir)

		print("Đã khởi chạy quá trình kiểm phiếu...")
		# Theo dõi tiến trình sinh file json mỗi 5s
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

		# Chạy lệnh kiểm phiếu bằng subprocess (không chờ hoàn thành)
		cmd = [
			'python',
			'-m', 'processors.yolo_detection',
			'--input_dir', base_dir,
			'--output_dir', base_dir
		]
		# Xác định đường dẫn tuyệt đối tới ballot_processing_system
		ballot_processing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ballot_processing_system'))
		#proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ballot_processing_dir)
		proc = subprocess.Popen(cmd, cwd=ballot_processing_dir)

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
		# Lấy tên gốc từ ballot_image
		# Ví dụ: 'ballots/1/ballot_20251213_170754_2b35f357.jpg' -> 'ballot_20251213_170754_2b35f357'
		if ballot.ballot_image:
			# Lấy tên file từ đường dẫn đầy đủ
			base = os.path.basename(str(ballot.ballot_image))
			name, _ = os.path.splitext(base)
			ballot_name_list.append(name)
		else:
			ballot_name_list.append("")

	# Lấy danh sách Candidate, lưu (id, name viết hoa)
	candidates = Candidate.objects.filter(poll=poll)
	candidate_info_list = [(c.candidate_id, c.name.upper() if c.name else "") for c in candidates]

	# Đường dẫn kết quả kiểm phiếu
	ket_qua_dir = os.path.join(settings.MEDIA_ROOT, 'ballots', str(poll_id), f'ket_qua_{poll_id}')
	
	# Kiểm tra xem thư mục có tồn tại không
	if not os.path.exists(ket_qua_dir):
		print(f"Thư mục kết quả không tồn tại: {ket_qua_dir}")
		return ballot_id_list, ballot_name_list, candidate_info_list
	
	json_files = glob.glob(os.path.join(ket_qua_dir, '*.json'))
	print(f"Tìm thấy {len(json_files)} file JSON trong {ket_qua_dir}")

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
								BallotSelection.objects.create(ballot=ballot, candidate_id=best_cid)
					# Đánh dấu đã kiểm phiếu
					ballot.is_checked = True
					ballot.is_valid = True
					ballot.save(update_fields=['is_checked', 'is_valid'])
			except Exception as e:
				# Nếu có lỗi, rollback transaction, không tạo gì cho ballot này
				print(f"Lỗi khi xử lý phiếu {ballot_id}: {str(e)}")
				ballot.is_valid = False
				ballot.is_checked = True
				ballot.save(update_fields=['is_valid', 'is_checked'])
				continue
		else:
			print(f"Không tìm thấy ballot tương ứng cho file: {name_no_ext}")
	# Trả về các danh sách nếu cần debug
	return ballot_id_list, ballot_name_list, candidate_info_list

# ==================== MEMBER MANAGEMENT ====================

@login_required
def manage_members(request, poll_id):
	"""View to manage poll members - only accessible by superuser and managers"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission: only superuser or manager can access
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		messages.error(request, 'Bạn không có quyền truy cập chức năng này!')
		return redirect('poll:detail', poll_id=poll_id)
	
	# Get filter parameters from request
	filter_type = request.GET.get('filter', 'all')  # all, pending, requested
	
	# Start with all members of this poll
	members = PollMember.objects.filter(poll=poll).select_related('account')
	
	# Apply filters
	if filter_type == 'pending':
		members = members.filter(status='pending')
	elif filter_type == 'requested':
		members = members.exclude(requested_role_change__isnull=True).exclude(requested_role_change='')
	# else: filter_type == 'all', no additional filter needed
	
	# Order by assigned_at
	members = members.order_by('-assigned_at')
	
	context = {
		'poll': poll,
		'members': members,
		'filter_type': filter_type,
		'total_count': PollMember.objects.filter(poll=poll).count(),
		'pending_count': PollMember.objects.filter(poll=poll, status='pending').count(),
		'requested_count': PollMember.objects.filter(poll=poll).exclude(requested_role_change__isnull=True).exclude(requested_role_change='').count(),
	}
	
	return render(request, 'poll/members.html', context)

@login_required
def update_member(request, poll_id, member_id):
	"""AJAX endpoint to update member role and status"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Invalid request method'})
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	member = get_object_or_404(PollMember, member_id=member_id, poll=poll)
	
	# Check permission
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		return JsonResponse({'success': False, 'message': 'Bạn không có quyền thực hiện thao tác này!'})
	
	# Don't allow editing superuser accounts
	if member.account.is_superuser:
		return JsonResponse({'success': False, 'message': 'Không thể chỉnh sửa tài khoản superuser!'})
	
	# Update role and status
	new_role = request.POST.get('role')
	new_status = request.POST.get('status')
	
	if new_role and new_role in ['manager', 'operator', 'checkin', 'user']:
		member.role = new_role
	
	if new_status and new_status in ['pending', 'active', 'rejected', 'banned']:
		member.status = new_status
	
	member.save()
	
	return JsonResponse({
		'success': True, 
		'message': f'Đã cập nhật thông tin thành viên {member.account.username}'
	})

@login_required
def remove_member(request, poll_id, member_id):
	"""AJAX endpoint to remove a member from poll"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Invalid request method'})
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	member = get_object_or_404(PollMember, member_id=member_id, poll=poll)
	
	# Check permission
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		return JsonResponse({'success': False, 'message': 'Bạn không có quyền thực hiện thao tác này!'})
	
	# Don't allow removing superuser accounts
	if member.account.is_superuser:
		return JsonResponse({'success': False, 'message': 'Không thể xóa tài khoản superuser!'})
	
	# Don't allow removing yourself if you're the only manager
	if member.account == request.user and member.role == 'manager':
		manager_count = PollMember.objects.filter(
			poll=poll, 
			role='manager', 
			status='active'
		).count()
		if manager_count <= 1:
			return JsonResponse({
				'success': False, 
				'message': 'Không thể xóa chính mình khi bạn là manager duy nhất!'
			})
	
	username = member.account.username
	member.delete()
	
	return JsonResponse({
		'success': True, 
		'message': f'Đã xóa thành viên {username} khỏi cuộc bỏ phiếu'
	})
