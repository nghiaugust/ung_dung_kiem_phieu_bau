from django.db import models
from account.models import Account
from poll.models import Poll, Candidate

class Ballot(models.Model): # phiếu bầu
	ballot_id = models.AutoField(primary_key=True)  # Mã lá phiếu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	
	#Không link với Voter (để bảo mật), mà link với người NHẬP LIỆU
	input_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, related_name='input_ballots')

	timestamp = models.DateTimeField(null=True)  # Thời gian bỏ phiếu
	is_checked = models.BooleanField(default=False)  # Đã kiểm phiếu chưa
	is_valid = models.BooleanField(default=True)  # Hợp lệ không
	ballot_image = models.ImageField(upload_to='ballots/%Y/%m/%d/', null=True, blank=True)
	# ballot_file_path = models.CharField(max_length=512, null=True)  # Đường dẫn đến file lá phiếu
	metadata = models.JSONField(null=True)  # Thông tin mở rộng
	
	# QR Code cryptographic fields
	qr_signature = models.CharField(max_length=1024, null=True, blank=True)  # RSA Signature (Base64 encoded)
	qr_generated_at = models.DateTimeField(null=True, blank=True)  # Thời gian tạo QR signature
	qr_payload = models.JSONField(null=True, blank=True)  # Payload gốc đã sign (để verify)

# Bảng lưu lựa chọn của từng phiếu bầu
class BallotSelection(models.Model):
	selection_id = models.AutoField(primary_key=True)  # Mã lựa chọn
	ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, null=True)  # Phiếu bầu
	candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, null=True)  # Ứng cử viên được chọn
