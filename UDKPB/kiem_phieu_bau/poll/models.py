from django.db import models
from account.models import Account
import hashlib
from security.fields import EncryptedCharField

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

	is_counting_started = models.BooleanField(default=False) # cờ kiểm tự động
	is_checking_started = models.BooleanField(default=False) # cờ hậu kiểm
	total_ballots_count = models.IntegerField(default=0) # Tổng số phiếu sẽ kiểm

	created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)  # Người tạo (id tài khoản)
	# nên để choices sau này dễ quản lý trạng thái hơn
	status = models.CharField(max_length=32, null=True)  # Trạng thái
	require_approval = models.BooleanField(default=True)  # Yêu cầu phê duyệt thành viên mới = true, không yc phê duyệt = false
	
	# Cryptographic fields for HMAC-based QR code verification
	private_key = models.TextField(null=True, blank=True)  # RSA Private Key (DEPRECATED - kept for backward compatibility)
	public_key = models.TextField(null=True, blank=True)   # RSA Public Key (DEPRECATED - kept for backward compatibility)
	hmac_secret_key = models.TextField(null=True, blank=True)  # HMAC Secret Key (encrypted with Fernet)
	key_generated_at = models.DateTimeField(null=True, blank=True)  # Thời gian tạo HMAC key
	
	# Cấu hình kiểm phiếu
	config_number = models.IntegerField(null=True, blank=True, choices=[
		(1, 'Cau hinh 1: VietNameOCR + YOLO-X'),
		(2, 'Cau hinh 2: Theo thu tu + YOLO-X'),
		(3, 'Cau hinh 3: Phieu gach ten + ResNet18 crossed'),
	], help_text='Cấu hình AI model đã sử dụng để kiểm phiếu')
	
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
	"""
	Model cử tri với mã hóa AES-256-GCM cho dữ liệu nhạy cảm
	Sử dụng SHA-256 blind index để hỗ trợ tìm kiếm
	"""
	voter_id = models.AutoField(primary_key=True)  # Mã cử tri
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='voters', null=True, blank=True) # Link vào Poll

	# Dữ liệu
	full_name = models.CharField(max_length=255, null=True, db_index=True)  # Họ tên
	email = EncryptedCharField(max_length=512, blank=True, null=True)  # Email (encrypted)
	code_id = EncryptedCharField(max_length=256, null=True)  # Mã nội bộ (encrypted)
	
	# Blind Index (SHA-256 hash) để tìm kiếm
	email_hash = models.CharField(max_length=64, db_index=True, null=True, blank=True)
	code_id_hash = models.CharField(max_length=64, db_index=True, null=True, blank=True)
	
	# Trạng thái đi bầu (Check-in)
	has_checked_in = models.BooleanField(default=False) # Đã đến nhận phiếu chưa
	check_in_time = models.DateTimeField(null=True, blank=True)
	check_in_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True) # Ai là người phát phiếu/gạch tên
	
	class Meta:
        # Ràng buộc duy nhất theo cặp (Poll + Hash) thay vì plaintext
        # Trong 1 cuộc bỏ phiếu, mã code_id này chỉ xuất hiện 1 lần.
		unique_together = [['poll', 'code_id_hash'], ['poll', 'email_hash']]
	
	@staticmethod
	def hash_value(value: str) -> str:
		"""Tạo SHA-256 hash của giá trị cho blind index"""
		if not value:
			return None
		return hashlib.sha256(value.encode('utf-8')).hexdigest()
	
	def save(self, *args, **kwargs):
		"""Tự động tạo hash khi save()"""
		# Tạo hash nếu có giá trị plaintext và chưa có hash
		if self.email and not self.email_hash:
			self.email_hash = self.hash_value(self.email)
		if self.code_id and not self.code_id_hash:
			self.code_id_hash = self.hash_value(self.code_id)
		super().save(*args, **kwargs)
	
	@classmethod
	def get_by_code_id(cls, poll, plaintext_code_id):
		"""Tìm voter theo code_id sử dụng blind index"""
		if not plaintext_code_id:
			return None
		code_hash = cls.hash_value(plaintext_code_id)
		try:
			voter = cls.objects.get(poll=poll, code_id_hash=code_hash)
			# Verify plaintext matches (double-check security)
			if voter.code_id == plaintext_code_id:
				return voter
		except cls.DoesNotExist:
			pass
		return None
	
	@classmethod
	def get_by_email(cls, poll, plaintext_email):
		"""Tìm voter theo email sử dụng blind index"""
		if not plaintext_email:
			return None
		email_hash = cls.hash_value(plaintext_email)
		try:
			voter = cls.objects.get(poll=poll, email_hash=email_hash)
			# Verify plaintext matches
			if voter.email == plaintext_email:
				return voter
		except cls.DoesNotExist:
			pass
		return None
	
	@classmethod
	def search_by_fields(cls, poll, search_text):
		"""Tìm kiếm voter theo full_name, email, hoặc code_id"""
		if not search_text:
			return cls.objects.filter(poll=poll)
		
		# Tạo hash của search text cho email và code_id
		search_hash = cls.hash_value(search_text)
		
		# Tìm theo full_name (plaintext) và hash của email/code_id
		from django.db.models import Q
		voters = cls.objects.filter(
			poll=poll
		).filter(
			Q(full_name__icontains=search_text) |
			Q(email_hash=search_hash) |
			Q(code_id_hash=search_hash)
		)
		
		# Verify plaintext matches cho encrypted fields (vì hash collision có thể xảy ra)
		matched_voters = []
		for voter in voters:
			if (voter.full_name and search_text.lower() in voter.full_name.lower()) or \
			   (voter.email and search_text.lower() in voter.email.lower()) or \
			   (voter.code_id and search_text.lower() in voter.code_id.lower()):
				matched_voters.append(voter.voter_id)
		
		# Trả về queryset với các voter_id matched
		if matched_voters:
			return cls.objects.filter(voter_id__in=matched_voters)
		return cls.objects.none()
