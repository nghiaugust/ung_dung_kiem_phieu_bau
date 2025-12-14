from django.db import models
from account.models import Account

class Poll(models.Model): # cuộc bỏ phiếu
	poll_id = models.AutoField(primary_key=True)  # Mã cuộc bỏ phiếu
	access_code = models.CharField(max_length=12, unique=True, null=True, blank=True)  # Mã tham gia (tự động sinh)
	title = models.CharField(max_length=255, null=True)  # Tiêu đề
	description = models.TextField(null=True,blank=True)  # Mô tả
	start_time = models.DateTimeField(null=True)  # Thời gian bắt đầu bỏ phiếu
	end_time = models.DateTimeField(null=True)  # Thời gian kết thúc bỏ phiếu
	counting_start_time = models.DateTimeField(null=True)  # Bắt đầu kiểm phiếu
	counting_end_time = models.DateTimeField(null=True)  # Kết thúc kiểm phiếu
	total_ballots_issued = models.IntegerField(default=0) # Tổng số phiếu phát ra (dùng để đối soát)
	total_ballots_received = models.IntegerField(default=0) # Tổng số phiếu thu về (trong hòm phiếu)

	created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)  # Người tạo (id tài khoản)
	# nên để choices sau này dễ quản lý trạng thái hơn
	status = models.CharField(max_length=32, null=True)  # Trạng thái
	require_approval = models.BooleanField(default=True)  # Yêu cầu phê duyệt thành viên mới = true, không yc phê duyệt = false
	
	# Cryptographic fields for HMAC-based QR code verification
	private_key = models.TextField(null=True, blank=True)  # RSA Private Key (DEPRECATED - kept for backward compatibility)
	public_key = models.TextField(null=True, blank=True)   # RSA Public Key (DEPRECATED - kept for backward compatibility)
	hmac_secret_key = models.TextField(null=True, blank=True)  # HMAC Secret Key (encrypted with Fernet)
	key_generated_at = models.DateTimeField(null=True, blank=True)  # Thời gian tạo HMAC key
	
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
	ROLE_CHOICES = [
        ('manager', 'Trưởng ban'),
        ('operator', 'Tổ nhập liệu'),
		('checkin', 'Tổ phát phiếu'),
        ('user', 'Người xem') # Role này chỉ Read-only
    ]
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')

	member_id = models.AutoField(primary_key=True)  # Mã thành viên
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='members')  # Cuộc bỏ phiếu
	account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='poll_memberships')  # Tài khoản
	status = models.CharField(
		max_length=16, 
		choices=[
			('pending', 'Chờ duyệt'),
        	('active', 'Đang hoạt động'),
        	('rejected', 'Từ chối'),
        	('banned', 'Bị chặn')
		],
		default='pending'
	)  # Trạng thái thành viên
	requested_role_change = models.CharField(
		max_length=16,
		choices=[
			('manager', 'Trưởng ban'),
        	('operator', 'Tổ nhập liệu'),
			('checkin', 'Tổ phát phiếu'),
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
		indexes = [
            models.Index(fields=['poll', 'account']),
        ]

	def __str__(self):
		return f"{self.account.username} - {self.poll.title} - [{self.role}]"

class Candidate(models.Model): # ứng cử viên
	candidate_id = models.AutoField(primary_key=True)  # Mã ứng cử viên
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	name = models.CharField(max_length=255, null=True)  # Tên ứng cử viên/phương án
	description = models.TextField(null=True)  # Mô tả
	image_url = models.URLField(null=True)  # Ảnh

class Voter(models.Model): # cử tri
	voter_id = models.AutoField(primary_key=True)  # Mã cử tri
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='voters', null=True, blank=True) # Link vào Poll

	full_name = models.CharField(max_length=255, null=True)  # Họ tên
	email = models.EmailField(blank=True, null=True)  # Email
	code_id = models.CharField(max_length=128, null=True)  # Mã nội bộ
	# Trạng thái đi bầu (Check-in)
	has_checked_in = models.BooleanField(default=False) # Đã đến nhận phiếu chưa
	check_in_time = models.DateTimeField(null=True, blank=True)
	check_in_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True) # Ai là người phát phiếu/gạch tên
	
	class Meta:
        # Ràng buộc duy nhất theo cặp (Poll + Code) hoặc (Poll + Email)
        # Trong 1 cuộc bỏ phiếu, mã code_id này chỉ xuất hiện 1 lần.
		unique_together = [['poll', 'code_id'], ['poll', 'email']]
		indexes = [
            models.Index(fields=['poll', 'code_id']), # Index để search check-in cho nhanh
        ]
