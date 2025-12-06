from django.db import models
from django.contrib.auth.models import AbstractUser

# Bảng tài khoản kế thừa User của Django
class Account(AbstractUser):
	# Các trường username, password, email, first_name, last_name, 
    # is_superuser, is_staff, is_active, date_joined... ĐÃ CÓ SẴN.

	phone_number = models.CharField(max_length=15, null=True, blank=True)  # Số điện thoại
	avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)  # Ảnh đại diện
	updated_at = models.DateTimeField(auto_now=True)  # Thời gian cập nhật

	def __str__(self):
		return self.username
