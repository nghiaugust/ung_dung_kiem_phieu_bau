from django.db import models
from django.contrib.auth.models import AbstractUser
# Bảng tài khoản kế thừa User của Django
class Account(AbstractUser):
	# id, username, password đã có sẵn trong AbstractUser
	role = models.CharField(max_length=16, choices=[('admin', 'Admin'), ('assistant', 'Assistant'), ('operator', 'Operator'), ('user', 'User')], default='user')  # Vai trò
	is_active = models.BooleanField(default=True)  # Trạng thái tài khoản
	created_at = models.DateTimeField(auto_now_add=True)  # Thời gian tạo
	updated_at = models.DateTimeField(auto_now=True)  # Thời gian cập nhật

	def __str__(self):
		return self.username

class Poll(models.Model): # cuộc bỏ phiếu
	poll_id = models.AutoField(primary_key=True)  # Mã cuộc bỏ phiếu
	access_code = models.CharField(max_length=12, unique=True, null=True, blank=True)  # Mã tham gia (tự động sinh)
	title = models.CharField(max_length=255, null=True)  # Tiêu đề
	description = models.TextField(null=True)  # Mô tả
	start_time = models.DateTimeField(null=True)  # Thời gian bắt đầu bỏ phiếu
	end_time = models.DateTimeField(null=True)  # Thời gian kết thúc bỏ phiếu
	counting_start_time = models.DateTimeField(null=True)  # Bắt đầu kiểm phiếu
	counting_end_time = models.DateTimeField(null=True)  # Kết thúc kiểm phiếu
	created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)  # Người tạo (id tài khoản)
	status = models.CharField(max_length=32, null=True)  # Trạng thái
	require_approval = models.BooleanField(default=True)  # Yêu cầu phê duyệt thành viên mới = true, không yc phê duyệt = false
	
	def save(self, *args, **kwargs):
		# Tự động sinh mã tham gia nếu chưa có
		if not self.access_code:
			self.access_code = self.generate_access_code()
		super().save(*args, **kwargs)
	
	def generate_access_code(self):
		"""Sinh mã tham gia ngẫu nhiên dạng xxx-xxx-xxx (9 ký tự + 2 dấu gạch ngang)"""
		import random
		import string
		while True:
			# Sinh mã gồm 3 nhóm, mỗi nhóm 3 ký tự chữ và số
			part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
			part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
			part3 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
			code = f"{part1}-{part2}-{part3}"
			
			# Kiểm tra xem mã đã tồn tại chưa
			if not Poll.objects.filter(access_code=code).exists():
				return code

class PollMember(models.Model): # Thành viên của cuộc bỏ phiếu (phân quyền)
	member_id = models.AutoField(primary_key=True)  # Mã thành viên
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='members')  # Cuộc bỏ phiếu
	account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='poll_memberships')  # Tài khoản
	status = models.CharField(
		max_length=16, 
		choices=[
			('pending', 'Chờ duyệt'),
			('approved', 'Đã duyệt'),
			('rejected', 'Từ chối')
		],
		default='approved'
	)  # Trạng thái thành viên
	requested_role_change = models.CharField(
		max_length=16,
		choices=[
			('assistant', 'Assistant'),
			('operator', 'Operator')
		],
		null=True,
		blank=True
	)  # Role mà user xin nâng cấp (chỉ dùng khi status='pending' cho yêu cầu thay đổi role)
	assigned_at = models.DateTimeField(auto_now_add=True)  # Thời gian thêm vào cuộc bỏ phiếu
	assigned_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_members')  # Người thêm vào (null nếu tự xin vào)
	approved_at = models.DateTimeField(null=True, blank=True)  # Thời gian duyệt
	approved_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_members')  # Người duyệt

	class Meta:
		unique_together = ('poll', 'account')  # Mỗi tài khoản chỉ thuộc 1 lần trong 1 cuộc bỏ phiếu
		verbose_name = 'Thành viên cuộc bỏ phiếu'
		verbose_name_plural = 'Thành viên cuộc bỏ phiếu'

	def __str__(self):
		return f"{self.account.username} - {self.poll.title} ({self.get_status_display()})"

class Candidate(models.Model): # ứng cử viên
	candidate_id = models.AutoField(primary_key=True)  # Mã ứng cử viên
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	name = models.CharField(max_length=255, null=True)  # Tên ứng cử viên/phương án
	description = models.TextField(null=True)  # Mô tả
	image_url = models.URLField(null=True)  # Ảnh

class Voter(models.Model): # cử tri
	voter_id = models.AutoField(primary_key=True)  # Mã cử tri
	full_name = models.CharField(max_length=255, null=True)  # Họ tên
	email = models.EmailField(unique=True, null=True)  # Email
	external_id = models.CharField(max_length=128, null=True)  # Mã nội bộ
	has_voted = models.BooleanField(null=True)  # Đã bỏ phiếu chưa


class Ballot(models.Model): # phiếu bầu
	ballot_id = models.AutoField(primary_key=True)  # Mã lá phiếu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	voter = models.ForeignKey(Voter, on_delete=models.SET_NULL, null=True, blank=True)  # Ai bỏ phiếu
	timestamp = models.DateTimeField(null=True)  # Thời gian bỏ phiếu
	is_checked = models.BooleanField(default=False)  # Đã kiểm phiếu chưa
	is_valid = models.BooleanField(default=True)  # Hợp lệ không
	ballot_file_path = models.CharField(max_length=512, null=True)  # Đường dẫn đến file lá phiếu
	metadata = models.JSONField(null=True)  # Thông tin mở rộng

# Bảng lưu lựa chọn của từng phiếu bầu
class Ballot_Selection(models.Model):
	selection_id = models.AutoField(primary_key=True)  # Mã lựa chọn
	ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, null=True)  # Phiếu bầu
	candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, null=True)  # Ứng cử viên được chọn