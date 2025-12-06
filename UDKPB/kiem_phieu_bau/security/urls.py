"""
Security App URLs
"""

from django.urls import path
from . import views

app_name = 'security'

urlpatterns = [
    # Lấy khóa công khai của cuộc bỏ phiếu
    path('poll/<int:poll_id>/public-key/', views.get_poll_public_key, name='get_poll_public_key'),
    # Xác thực phiếu bầu từ mã QR
    path('ballot/verify/', views.verify_ballot_qr, name='verify_ballot_qr'),
]
