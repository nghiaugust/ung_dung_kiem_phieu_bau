import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from account.models import Account
from .models import Poll, Candidate, PollMember, Voter
from ballot.models import Ballot
from ballot.views import delete_all_ballots
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Count, Prefetch
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
	from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
	
	if request.user.is_superuser and request.user.is_active:
		# Nếu là admin, lấy TẤT CẢ các cuộc bỏ phiếu
		polls_queryset = Poll.objects.all()
	else: 
		# Nếu khác admin, chỉ lấy các cuộc bỏ phiếu mà user là thành viên
		polls_queryset = Poll.objects.filter(members__account=request.user)

	# Tối ưu: Annotate count để tránh N+1 queries
	polls_queryset = polls_queryset.annotate(
		num_candidates=Count('candidate', distinct=True),
		num_ballots=Count('ballot', distinct=True),
		num_voters=Count('voters', distinct=True),
		num_members=Count('members', distinct=True)
	).order_by('-poll_id')
	
	# Phân trang: 10 cuộc bỏ phiếu mỗi trang
	paginator = Paginator(polls_queryset, 10)
	page = request.GET.get('page', 1)
	
	try:
		polls = paginator.page(page)
	except PageNotAnInteger:
		# Nếu page không phải số nguyên, trả về trang đầu tiên
		polls = paginator.page(1)
	except EmptyPage:
		# Nếu page vượt quá số trang, trả về trang cuối
		polls = paginator.page(paginator.num_pages)
	
	return render(request, 'poll/danh_sach_cuoc_bo_phieu.html', {'polls': polls})

@login_required
def poll_detail(request, poll_id):
	poll = get_object_or_404(Poll, poll_id=poll_id)
	candidates = Candidate.objects.filter(poll=poll)
	ballots = Ballot.objects.filter(poll=poll)
	total_ballots = ballots.count()
	checked_ballots = ballots.filter(counting_status='completed').count()
	unchecked_ballots = ballots.exclude(counting_status='completed').count()
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
	return render(request, 'poll/danh_sach_cuoc_bo_phieu.html', {'poll_id': poll_id})

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
	
	Optimized: Sử dụng prefetch_related để tải tất cả members trong 1 query
	thay vì N queries riêng lẻ (N+1 problem)
	"""
	# Chỉ admin mới có quyền truy cập
	if not (request.user.is_superuser and request.user.is_active):
		return redirect('permission_denied')
	
	# Lấy tất cả các cuộc bỏ phiếu với prefetch members
	# Sử dụng Prefetch để customize queryset của members (select_related + order_by)
	polls = Poll.objects.prefetch_related(
		Prefetch(
			'members',  # Related name của PollMember
			queryset=PollMember.objects.select_related('account', 'assigned_by').order_by('account__username')
		)
	).order_by('-poll_id')
	
	# Xây dựng poll_data từ dữ liệu đã prefetch
	poll_data = []
	for poll in polls:
		# members.all() sẽ sử dụng cache từ prefetch, không tạo query mới
		members = poll.members.all()
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
	valid_checked_ballots = Ballot.objects.filter(poll=poll, is_valid=True, counting_status='completed').count()
	return render(request, 'poll/thong_ke/detail.html', {
		'poll': poll,
		'candidate_stats': candidate_stats,
		'total_ballots': valid_checked_ballots,
	})


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

# ==================== VOTER MANAGEMENT ====================

@login_required
def manage_voters(request, poll_id):
	"""View to manage voters - only accessible by superuser and managers"""
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
		return redirect('poll:poll_detail', poll_id=poll_id)
	
	# Get all voters of this poll
	voters = Voter.objects.filter(poll=poll).select_related('check_in_by').order_by('voter_id')
	
	context = {
		'poll': poll,
		'voters': voters,
	}
	
	return render(request, 'poll/voters.html', context)

@login_required
def add_voter(request, poll_id):
	"""AJAX endpoint to add a new voter"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Invalid request method'})
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Check permission
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		return JsonResponse({'success': False, 'message': 'Bạn không có quyền thực hiện thao tác này!'})
	
	# Get form data
	full_name = request.POST.get('full_name', '').strip()
	email = request.POST.get('email', '').strip()
	code_id = request.POST.get('code_id', '').strip()
	
	# Validate required fields
	if not full_name or not code_id:
		return JsonResponse({'success': False, 'message': 'Họ tên và mã cử tri là bắt buộc!'})
	
	# Check if code_id already exists in this poll (sử dụng blind index)
	if Voter.get_by_code_id(poll, code_id):
		return JsonResponse({'success': False, 'message': f'Mã cử tri "{code_id}" đã tồn tại trong cuộc bỏ phiếu này!'})
	
	# Check if email already exists in this poll (if provided, sử dụng blind index)
	if email and Voter.get_by_email(poll, email):
		return JsonResponse({'success': False, 'message': f'Email "{email}" đã tồn tại trong cuộc bỏ phiếu này!'})
	
	# Create new voter
	try:
		voter = Voter.objects.create(
			poll=poll,
			full_name=full_name,
			email=email if email else None,
			code_id=code_id
		)
		return JsonResponse({
			'success': True, 
			'message': f'Đã thêm cử tri "{full_name}" thành công!'
		})
	except Exception as e:
		return JsonResponse({'success': False, 'message': f'Lỗi: {str(e)}'})

@login_required
def update_voter(request, poll_id, voter_id):
	"""AJAX endpoint to update voter information"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Invalid request method'})
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	voter = get_object_or_404(Voter, voter_id=voter_id, poll=poll)
	
	# Check permission
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		return JsonResponse({'success': False, 'message': 'Bạn không có quyền thực hiện thao tác này!'})
	
	# Get form data
	full_name = request.POST.get('full_name', '').strip()
	email = request.POST.get('email', '').strip()
	code_id = request.POST.get('code_id', '').strip()
	
	# Validate required fields
	if not full_name or not code_id:
		return JsonResponse({'success': False, 'message': 'Họ tên và mã cử tri là bắt buộc!'})
	
	# Check if code_id already exists in this poll (excluding current voter, sử dụng blind index)
	existing_voter = Voter.get_by_code_id(poll, code_id)
	if existing_voter and existing_voter.voter_id != voter_id:
		return JsonResponse({'success': False, 'message': f'Mã cử tri "{code_id}" đã tồn tại trong cuộc bỏ phiếu này!'})
	
	# Check if email already exists in this poll (excluding current voter, if provided, sử dụng blind index)
	if email:
		existing_voter = Voter.get_by_email(poll, email)
		if existing_voter and existing_voter.voter_id != voter_id:
			return JsonResponse({'success': False, 'message': f'Email "{email}" đã tồn tại trong cuộc bỏ phiếu này!'})
	
	# Update voter
	try:
		voter.full_name = full_name
		voter.email = email if email else None
		voter.code_id = code_id
		voter.save()
		
		return JsonResponse({
			'success': True, 
			'message': f'Đã cập nhật thông tin cử tri "{full_name}"'
		})
	except Exception as e:
		return JsonResponse({'success': False, 'message': f'Lỗi: {str(e)}'})

@login_required
def remove_voter(request, poll_id, voter_id):
	"""AJAX endpoint to remove a voter"""
	if request.method != 'POST':
		return JsonResponse({'success': False, 'message': 'Invalid request method'})
	
	poll = get_object_or_404(Poll, poll_id=poll_id)
	voter = get_object_or_404(Voter, voter_id=voter_id, poll=poll)
	
	# Check permission
	is_manager = PollMember.objects.filter(
		poll=poll, 
		account=request.user, 
		role='manager', 
		status='active'
	).exists()
	
	if not (request.user.is_superuser or is_manager):
		return JsonResponse({'success': False, 'message': 'Bạn không có quyền thực hiện thao tác này!'})
	
	full_name = voter.full_name
	voter.delete()
	
	return JsonResponse({
		'success': True, 
		'message': f'Đã xóa cử tri "{full_name}" khỏi cuộc bỏ phiếu'
	})
