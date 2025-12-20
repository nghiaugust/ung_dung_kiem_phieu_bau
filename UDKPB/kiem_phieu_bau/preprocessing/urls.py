from django.urls import path
from . import views

app_name = 'preprocessing'

urlpatterns = [
	# Xử lý tất cả ballot của poll
	path('process/<int:poll_id>/', views.preprocess_poll_ballots, name='preprocess_poll'),
	
	# Lấy trạng thái xử lý
	path('status/<int:poll_id>/', views.get_preprocessed_status, name='get_status'),
]
