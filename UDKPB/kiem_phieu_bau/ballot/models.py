import os
from django.db import models
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from account.models import Account
from poll.models import Poll, Candidate
from security.fields import EncryptedImageField


def ballot_image_upload_path(instance, filename):
	"""
	Tạo đường dẫn upload cho ballot image
	Format: ballots/ballot_<ballot_id>.<ext>
	"""
	ext = filename.split('.')[-1].lower()
	new_filename = f"ballot_{instance.ballot_id}.{ext}"
	return os.path.join('ballots', new_filename)


class Ballot(models.Model): # phiếu bầu
	"""
	Model phiếu bầu với mã hóa AES-256-GCM cho đường dẫn ảnh
	File path được mã hóa trong database để bảo vệ thông tin vị trí file
	"""
	ballot_id = models.AutoField(primary_key=True)  # Mã lá phiếu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	
	#Không link với Voter (để bảo mật), mà link với người NHẬP LIỆU
	input_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, related_name='input_ballots')

	timestamp = models.DateTimeField(auto_now_add=True)  # Thời gian tạo phiếu (chỉ set khi tạo, không thay đổi sau đó)
	
	is_uploaded = models.BooleanField(default=False)  # Đã tải lên chưa
	is_checked = models.BooleanField(default=False)  # Đã kiểm phiếu chưa
	is_post_checked = models.BooleanField(default=False)  # Đã hậu kiểm chưa
	is_valid = models.BooleanField(default=True)  # Hợp lệ không
	ballot_image = EncryptedImageField(upload_to=ballot_image_upload_path, null=True, blank=True)  # Đường dẫn ảnh được mã hóa
	# ballot_file_path = models.CharField(max_length=512, null=True)  # Đường dẫn đến file lá phiếu
	
	# Thông tin mở rộng
	# Cấu trúc metadata:
	# {
	#     "qr_code_raw": str,                    # Dữ liệu QR code thô từ phiếu
	#     "processed_at": str,                   # Thời gian xử lý (ISO format)
	#     "horizontal_lines": [                  # Tọa độ các đường kẻ ngang
	#         {"y": int, "x1": int, "x2": int},  # y: tọa độ Y, x1: điểm bắt đầu, x2: điểm kết thúc
	#         ...
	#     ],
	#     "vertical_lines": [                    # Tọa độ các đường kẻ dọc
	#         {"x": int, "y1": int, "y2": int},  # x: tọa độ X, y1: điểm bắt đầu, y2: điểm kết thúc
	#         ...
	#     ]
	# }
	metadata = models.JSONField(null=True)
	
	# Trạng thái xử lý asynchronous - UPLOAD PROCESS
	PROCESSING_STATUS = (
		('pending', 'Chờ xử lý'),
		('processing', 'Đang xử lý'),
		('completed', 'Hoàn thành'),
		('failed', 'Lỗi'),
	)
	process_status = models.CharField(max_length=20, choices=PROCESSING_STATUS, default='pending')
	process_error = models.TextField(null=True, blank=True)  # Lưu lỗi nếu có
	
	# Trạng thái kiểm phiếu asynchronous - COUNTING PROCESS (riêng biệt với upload)
	COUNTING_STATUS = (
		('pending', 'Chờ kiểm'),
		('processing', 'Đang kiểm'),
		('completed', 'Đã kiểm'),
		('failed', 'Lỗi kiểm'),
	)
	counting_status = models.CharField(max_length=20, choices=COUNTING_STATUS, default='pending')
	counting_error = models.TextField(null=True, blank=True)  # Lưu lỗi kiểm phiếu nếu có
	
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


# Signal để tự động xóa file ballot_image khi xóa Ballot
@receiver(post_delete, sender=Ballot)
def delete_ballot_image_on_delete(sender, instance, **kwargs):
	"""Xóa file ballot_image khi xóa Ballot"""
	if instance.ballot_image:
		if os.path.isfile(instance.ballot_image.path):
			os.remove(instance.ballot_image.path)


# Signal để xóa file ballot_image cũ khi cập nhật
@receiver(pre_save, sender=Ballot)
def delete_old_ballot_image_on_update(sender, instance, **kwargs):
	"""Xóa file ballot_image cũ khi cập nhật với file mới"""
	if not instance.pk:
		return  # Nếu là instance mới, không làm gì
	
	try:
		old_file = Ballot.objects.get(pk=instance.pk).ballot_image
	except Ballot.DoesNotExist:
		return
	
	# Nếu file mới khác file cũ, xóa file cũ
	new_file = instance.ballot_image
	if old_file and old_file != new_file:
		if os.path.isfile(old_file.path):
			os.remove(old_file.path)
