from django.db import models
from django.contrib.auth.models import AbstractUser
# Bảng tài khoản kế thừa User của Django
class Account(AbstractUser):
	# id, username, password đã có sẵn trong AbstractUser
	role = models.CharField(max_length=16, choices=[('admin', 'Admin'), ('assistant', 'Assistant'), ('user', 'User')], default='user')  # Vai trò
	is_active = models.BooleanField(default=True)  # Trạng thái tài khoản
	created_at = models.DateTimeField(auto_now_add=True)  # Thời gian tạo
	updated_at = models.DateTimeField(auto_now=True)  # Thời gian cập nhật

	def __str__(self):
		return self.username

class Poll(models.Model): # cuộc bỏ phiếu
	poll_id = models.AutoField(primary_key=True)  # Mã cuộc bỏ phiếu
	title = models.CharField(max_length=255, null=True)  # Tiêu đề
	description = models.TextField(null=True)  # Mô tả
	start_time = models.DateTimeField(null=True)  # Thời gian bắt đầu bỏ phiếu
	end_time = models.DateTimeField(null=True)  # Thời gian kết thúc bỏ phiếu
	counting_start_time = models.DateTimeField(null=True)  # Bắt đầu kiểm phiếu
	counting_end_time = models.DateTimeField(null=True)  # Kết thúc kiểm phiếu
	created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True)  # Người tạo (id tài khoản)
	status = models.CharField(max_length=32, null=True)  # Trạng thái

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