from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from .models import Account

def tai_khoan(request):
	# Chỉ cho phép admin
	if not (request.user.is_superuser and request.user.is_active):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	return render(request, 'account/tai_khoan.html')

# Danh sách tài khoản
@login_required
def account_list(request):
	# Chỉ cho phép admin
	if not (request.user.is_superuser and request.user.is_active):
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('permission_denied'),
				'message': 'Bạn không có quyền truy cập chức năng này!'
			})
		return redirect('permission_denied')
	users = Account.objects.all().order_by('-date_joined')
	return render(request, 'account/list.html', {'users': users})

# View đăng ký
def register_view(request):
	if request.method == 'POST':
		username = request.POST.get('username')
		password = request.POST.get('password')
		password_confirm = request.POST.get('password_confirm')
		email = request.POST.get('email')
		last_name = request.POST.get('last_name')
		
		# Validate
		errors = {}
		if not username or not password or not password_confirm:
			errors['general'] = 'Vui lòng điền đầy đủ thông tin bắt buộc.'
		elif password != password_confirm:
			errors['password'] = 'Mật khẩu xác nhận không khớp.'
		elif Account.objects.filter(username=username).exists():
			errors['username'] = 'Tên đăng nhập đã tồn tại.'
		elif len(password) < 6:
			errors['password'] = 'Mật khẩu phải có ít nhất 6 ký tự.'
		
		if not errors:
			# Tạo tài khoản mới
			Account.objects.create(
				username=username,
				password=make_password(password),
				email=email or '',
				last_name=last_name or '',
				is_active=True
			)
			messages.success(request, 'Đăng ký thành công! Vui lòng đăng nhập.')
			return redirect('account:login')
		else:
			return render(request, 'account/register.html', {'errors': errors, 'form_data': request.POST})
	
	return render(request, 'account/register.html')

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
	return render(request, 'account/login.html', {'form': {'errors': error}})

# View đăng xuất
def logout_view(request):
	logout(request)
	# Xoá session/account info nếu có lưu thêm
	return redirect('account:login')

@login_required
def account_profile(request):
	return render(request, 'account/profile.html', {'user': request.user})

# Thêm tài khoản
@login_required
def add_account(request):
	# Chỉ cho phép admin
	if not (request.user.is_superuser and request.user.is_active):
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
		is_active = bool(request.POST.get('is_active', True))
		account = Account.objects.create(
			username=username,
			last_name=name,
			email=email,
			password=make_password(password),
			is_active=is_active
		)
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('account:account_list'),
				'message': 'Thêm tài khoản thành công!'
			})
		return redirect('account:account_list')
	return render(request, 'account/add_account.html')

# Sửa tài khoản
@login_required
def edit_account(request, account_id):
	# Chỉ cho phép admin
	if not (request.user.is_superuser and request.user.is_active):
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
		is_active_val = request.POST.get('is_active', '1')
		account.is_active = (is_active_val == '1')
		account.save()
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({
				'success': True,
				'redirect_url': reverse('account:account_list'),
				'message': 'Cập nhật tài khoản thành công!'
			})
		return redirect('account:account_list')
	return render(request, 'account/edit_account.html', {'account': account})

@login_required
def edit_account_user(request, account_id):
	account = get_object_or_404(Account, id=account_id)
	if request.method == 'POST':
		account.last_name = request.POST.get('last_name', account.last_name)
		account.email = request.POST.get('email', account.email)
		password = request.POST.get('password')
		if password:
			account.password = make_password(password)
		account.save()
		# Nếu là AJAX thì trả về JSON
		if request.headers.get('x-requested-with') == 'XMLHttpRequest':
			return JsonResponse({'success': True, 'message': 'Cập nhật thành công!'})
	return render(request, 'account/edit_account_user.html', {'account': account})

@login_required
def edit_account_redirect(request, account_id):
	# Nếu là admin thì vào trang quản lý, còn lại thì vào trang view
	if request.user.is_superuser and request.user.is_active:
		return redirect('account:edit_account', account_id=account_id)
	else:
		return redirect('account:edit_account_user', account_id=account_id)
	
# Xoá tài khoản
@login_required
def delete_account(request, account_id):
	# Chỉ cho phép admin
	if not (request.user.is_superuser and request.user.is_active):
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
				'redirect_url': reverse('account:account_list'),
				'message': 'Xoá tài khoản thành công!'
			})
		return redirect('account:account_list')
	return render(request, 'account/delete_account.html', {'account': account})
