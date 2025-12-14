import uuid
import os
from django.db import models
from account.models import Account
from poll.models import Poll, Candidate


def ballot_image_upload_path(instance, filename):
	"""
	Tạo đường dẫn upload unique cho ballot image
	Format: ballots/<poll_id>/ballot_<timestamp>_<uuid>.<ext>
	"""
	ext = filename.split('.')[-1].lower()
	from django.utils import timezone
	now = timezone.now()
	unique_id = uuid.uuid4().hex[:8]
	new_filename = f"ballot_{now.strftime('%Y%m%d_%H%M%S')}_{unique_id}.{ext}"
	
	# Tổ chức theo poll_id
	poll_id = instance.poll.poll_id if instance.poll else 'no_poll'
	return os.path.join('ballots', str(poll_id), new_filename)


class Ballot(models.Model): # phiếu bầu
	ballot_id = models.AutoField(primary_key=True)  # Mã lá phiếu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True)  # Thuộc cuộc bỏ phiếu
	
	#Không link với Voter (để bảo mật), mà link với người NHẬP LIỆU
	input_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, related_name='input_ballots')

	timestamp = models.DateTimeField(null=True)  # Thời gian bỏ phiếu
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

def form_ballot_pdf_upload_path(instance, filename):
	"""
	Tạo đường dẫn upload cho form ballot PDF
	Format: form/<poll_id>/<filename>
	"""
	poll_id = instance.poll.poll_id if instance.poll else 'no_poll'
	return os.path.join('form', str(poll_id), filename)

class FormBallot(models.Model): # Form mẫu phiếu bầu
	BALLOT_TYPE_CHOICES = [
		('mark_x', 'Đánh dấu X'),
		('mark_v', 'Đánh dấu V'),
		('cross_name', 'Gạch tên'),
	]
	
	form_id = models.AutoField(primary_key=True)  # Mã form mẫu
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='form_ballots')  # Thuộc cuộc bỏ phiếu
	ballot_type = models.CharField(max_length=20, choices=BALLOT_TYPE_CHOICES, default='mark_x')  # Loại phiếu
	form_count = models.IntegerField(default=0)  # Số thứ tự form
	quantity = models.IntegerField(default=0)  # Số lượng phiếu
	pdf_file = models.FileField(upload_to=form_ballot_pdf_upload_path, null=True, blank=True)  # File PDF form mẫu
	created_at = models.DateTimeField(auto_now_add=True)  # Thời gian tạo
	created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)  # Người tạo
	
	# Cấu hình PDF Generator - Lưu dưới dạng JSON
	title = models.CharField(max_length=255, default="PHIẾU BẦU CỬ")  # Tiêu đề phiếu bầu
	header_info = models.JSONField(null=True, blank=True)  # Thông tin header: {"Đơn vị": "...", "Kỳ bầu cử": "...", ...}
	footer_text = models.TextField(null=True, blank=True)  # Text chân trang
	
	# Cấu hình bảng dữ liệu
	table_config = models.JSONField(null=True, blank=True)  # Cấu hình bảng: {"columns": [...], "column_widths": [...]}
	
	class Meta:
		indexes = [
			models.Index(fields=['poll', 'ballot_type']),
		]
	
	def __str__(self):
		return f"Form {self.get_ballot_type_display()} - Poll: {self.poll.title}"
	
	def get_pdf_generator_config(self):
		"""
		Trả về dict config để khởi tạo BallotPDFGenerator
		
		Returns:
			dict: Config cho BallotPDFGenerator
		"""
		return {
			'title': self.title,
			'header_info': self.header_info or {},
			'footer_text': self.footer_text,
		}
	
	def get_table_config(self):
		"""
		Trả về config bảng (num_columns, num_rows, columns, column_widths, candidates)
		
		Returns:
			dict: {
				"num_columns": int,
				"num_rows": int,
				"columns": [...], 
				"column_widths": [...],
				"candidates": [...]  # Danh sách tên ứng cử viên
			}
		"""
		if self.table_config:
			return self.table_config
		
		# Default config nếu chưa set
		default_columns = ["STT", "Họ và tên", "Đồng ý", "Không đồng ý"]
		return {
			"num_columns": len(default_columns),
			"num_rows": 0,
			"columns": default_columns,
			"column_widths": None,  # None = tự động chia đều
			"candidates": []  # Danh sách ứng cử viên rỗng
		}
