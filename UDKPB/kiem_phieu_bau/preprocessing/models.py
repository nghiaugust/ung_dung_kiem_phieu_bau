from django.db import models
from ballot.models import Ballot


class PreprocessedBallot(models.Model):
	"""
	Lưu thông tin các ảnh đã xử lý cho ballot
	Mỗi ballot sẽ có: 
	- 1 ảnh đã làm phẳng
	- 1 ảnh projection histogram (debug)
	- Nhiều ảnh ô đã cắt
	"""
	preprocessing_id = models.AutoField(primary_key=True)
	ballot = models.OneToOneField(Ballot, on_delete=models.CASCADE, related_name='preprocessed')
	
	# Ảnh đã làm phẳng
	flattened_image = models.CharField(max_length=512, null=True, blank=True)  # preprocessing/<ballot_id>.jpg
	
	# Ảnh projection histogram (debug)
	histogram_image = models.CharField(max_length=512, null=True, blank=True)  # preprocessing/<ballot_id>_projection_histogram.png
	
	# Thời gian xử lý
	processed_at = models.DateTimeField(auto_now_add=True)
	
	# Thông tin xử lý
	status = models.CharField(max_length=20, default='processing', choices=[
		('processing', 'Đang xử lý'),
		('completed', 'Hoàn thành'),
		('failed', 'Thất bại'),
	])
	error_message = models.TextField(null=True, blank=True)
	
	# Số lượng ô đã cắt
	cell_count = models.IntegerField(default=0)
	
	class Meta:
		db_table = 'preprocessed_ballot'
		verbose_name = 'Phiếu đã xử lý'
		verbose_name_plural = 'Phiếu đã xử lý'


class BallotCell(models.Model):
	"""
	Lưu thông tin từng ô đã cắt từ ballot
	"""
	cell_id = models.AutoField(primary_key=True)
	preprocessed_ballot = models.ForeignKey(PreprocessedBallot, on_delete=models.CASCADE, related_name='cells')
	
	# Vị trí ô trong grid
	row = models.IntegerField()
	col = models.IntegerField()
	
	# Đường dẫn ảnh ô đã cắt
	cell_image = models.CharField(max_length=512)  # preprocessing/<ballot_id>_<row>_<col>.jpg
	
	class Meta:
		db_table = 'ballot_cell'
		verbose_name = 'Ô phiếu'
		verbose_name_plural = 'Ô phiếu'
		unique_together = ['preprocessed_ballot', 'row', 'col']
