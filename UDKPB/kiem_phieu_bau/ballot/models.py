import os
from django.db import models
from account.models import Account
from poll.models import Poll, Candidate


def ballot_image_upload_path(instance, filename):
	"""
	Tạo đường dẫn upload cho ballot image
	Format: ballots/ballot_<ballot_id>.<ext>
	"""
	ext = filename.split('.')[-1].lower()
	new_filename = f"ballot_{instance.ballot_id}.{ext}"
	return os.path.join('ballots', new_filename)


class Ballot(models.Model): # phiếu bầu
	ballot_id = models.AutoField(primary_key=True)  # Mã lá phiếu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	
	#Không link với Voter (để bảo mật), mà link với người NHẬP LIỆU
	input_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, related_name='input_ballots')

	timestamp = models.DateTimeField(auto_now_add=True)  # Thời gian tạo phiếu (chỉ set khi tạo, không thay đổi sau đó)
	is_checked = models.BooleanField(default=False)  # Đã kiểm phiếu chưa
	is_valid = models.BooleanField(default=True)  # Hợp lệ không
	ballot_image = models.ImageField(upload_to=ballot_image_upload_path, null=True, blank=True)
	# ballot_file_path = models.CharField(max_length=512, null=True)  # Đường dẫn đến file lá phiếu
	metadata = models.JSONField(null=True)  # Thông tin mở rộng
	
	# QR Code HMAC fields
	qr_hmac = models.CharField(max_length=64, null=True, blank=True)  # HMAC signature (hex string)
	qr_generated_at = models.DateTimeField(null=True, blank=True)  # Thời gian tạo QR HMAC
	# Legacy fields (kept for backward compatibility)
	qr_signature = models.CharField(max_length=1024, null=True, blank=True)  # RSA Signature (DEPRECATED)
	qr_payload = models.JSONField(null=True, blank=True)  # RSA Payload (DEPRECATED)

# Bảng lưu lựa chọn của từng phiếu bầu
class BallotSelection(models.Model):
	selection_id = models.AutoField(primary_key=True)  # Mã lựa chọn
	ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, null=True)  # Phiếu bầu
	candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, null=True)  # Ứng cử viên được chọn
