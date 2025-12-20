from django.db import models
from poll.models import Poll


class AIModelResult(models.Model):
	"""
	Lưu kết quả từ các AI models (TrOCR, YOLO, etc.)
	"""
	result_id = models.AutoField(primary_key=True)
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='ai_results')
	
	# ID/tên của model (VD: 'trocr', 'yolo', 'trocr-v2', etc.)
	model_id = models.CharField(max_length=100, db_index=True)
	
	# Kết quả JSON từ model
	result_model = models.JSONField()
	
	# Metadata
	created_at = models.DateTimeField(auto_now_add=True)
	processing_time = models.FloatField(null=True, blank=True, help_text='Thời gian xử lý (giây)')
	
	# Trạng thái
	status = models.CharField(max_length=20, default='success', choices=[
		('success', 'Thành công'),
		('failed', 'Thất bại'),
		('partial', 'Một phần thành công'),
	])
	error_message = models.TextField(null=True, blank=True)
	
	class Meta:
		db_table = 'ai_model_result'
		verbose_name = 'Kết quả AI Model'
		verbose_name_plural = 'Kết quả AI Models'
		indexes = [
			models.Index(fields=['poll', 'model_id']),
			models.Index(fields=['created_at']),
		]
	
	def __str__(self):
		return f"{self.model_id} - Poll {self.poll_id} - {self.status}"
