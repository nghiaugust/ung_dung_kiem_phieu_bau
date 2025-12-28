import os
from django.db import models
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.conf import settings
from ballot.models import Ballot


class PreprocessedBallot(models.Model):
	"""
	Lưu thông tin các ảnh đã xử lý cho ballot
	Mỗi ballot sẽ có: 
	- 1 ảnh grid detection (debug)
	- Nhiều ảnh ô đã cắt
	"""
	preprocessing_id = models.AutoField(primary_key=True)
	ballot = models.OneToOneField(Ballot, on_delete=models.CASCADE, related_name='preprocessed')
	
	# Ảnh grid detection (debug)
	detection_image = models.CharField(max_length=512, null=True, blank=True)  # preprocessing/<ballot_id>_detection.jpg
	
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


# Signals cho PreprocessedBallot
@receiver(post_delete, sender=PreprocessedBallot)
def delete_preprocessed_images_on_delete(sender, instance, **kwargs):
	"""Xóa file ảnh khi xóa PreprocessedBallot"""
	# Xóa detection_image
	if instance.detection_image:
		file_path = os.path.join(settings.MEDIA_ROOT, instance.detection_image)
		if os.path.isfile(file_path):
			os.remove(file_path)
	
	# Xóa các file debug (edges, histogram) nếu có
	ballot_id = instance.ballot.ballot_id
	ballot_dir = os.path.join(settings.MEDIA_ROOT, 'ballots')
	
	edges_file = os.path.join(ballot_dir, f"ballot_{ballot_id}_edges.jpg")
	if os.path.isfile(edges_file):
		os.remove(edges_file)
	
	histogram_file = os.path.join(ballot_dir, f"ballot_{ballot_id}_histogram.png")
	if os.path.isfile(histogram_file):
		os.remove(histogram_file)


@receiver(pre_save, sender=PreprocessedBallot)
def delete_old_preprocessed_images_on_update(sender, instance, **kwargs):
	"""Xóa file ảnh cũ khi cập nhật PreprocessedBallot"""
	if not instance.pk:
		return
	
	try:
		old_instance = PreprocessedBallot.objects.get(pk=instance.pk)
	except PreprocessedBallot.DoesNotExist:
		return
	
	# Xóa detection_image cũ nếu thay đổi
	if old_instance.detection_image and old_instance.detection_image != instance.detection_image:
		file_path = os.path.join(settings.MEDIA_ROOT, old_instance.detection_image)
		if os.path.isfile(file_path):
			os.remove(file_path)


# Signals cho BallotCell
@receiver(post_delete, sender=BallotCell)
def delete_cell_image_on_delete(sender, instance, **kwargs):
	"""Xóa file ảnh ô khi xóa BallotCell"""
	if instance.cell_image:
		file_path = os.path.join(settings.MEDIA_ROOT, instance.cell_image)
		if os.path.isfile(file_path):
			os.remove(file_path)


@receiver(pre_save, sender=BallotCell)
def delete_old_cell_image_on_update(sender, instance, **kwargs):
	"""Xóa file ảnh ô cũ khi cập nhật BallotCell"""
	if not instance.pk:
		return
	
	try:
		old_instance = BallotCell.objects.get(pk=instance.pk)
	except BallotCell.DoesNotExist:
		return
	
	# Xóa cell_image cũ nếu thay đổi
	if old_instance.cell_image and old_instance.cell_image != instance.cell_image:
		file_path = os.path.join(settings.MEDIA_ROOT, old_instance.cell_image)
		if os.path.isfile(file_path):
			os.remove(file_path)
