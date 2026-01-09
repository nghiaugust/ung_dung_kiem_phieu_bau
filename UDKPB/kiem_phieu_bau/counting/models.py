from django.db import models
from poll.models import Poll


class AIModelResult(models.Model):
	"""
	Lưu kết quả từ các AI models (TrOCR, YOLO, etc.)
	result_model chứa cả thông tin cấu hình và kết quả:
	{
		'config': {'type': 'config1' hoặc 'config2', ...},
		'results': [...]
	}
	"""
	result_id = models.AutoField(primary_key=True)
	poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='ai_results')
	
	# Kết quả JSON từ model (chứa cả config và results)
	result_model = models.JSONField()
	
	# Tự động kiểm phiếu
	auto_check_enabled = models.BooleanField(default=False, help_text='Bật/tắt tự động kiểm phiếu')
	auto_check_max_ballots = models.IntegerField(null=True, blank=True, help_text='Số lượng phiếu tối đa cần kiểm (None = tất cả)')
	auto_check_processed = models.IntegerField(default=0, help_text='Số phiếu đã kiểm tự động')
	
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
			models.Index(fields=['poll']),
			models.Index(fields=['created_at']),
		]
	
	def __str__(self):
		config_type = self.result_model.get('config', {}).get('type', 'unknown')
		return f"{config_type} - Poll {self.poll_id} - {self.status}"
