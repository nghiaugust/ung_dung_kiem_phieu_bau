"""
URL Configuration cho API app
"""
from django.urls import path
from . import views

urlpatterns = [
    path('model_vietnameocr/recognize/', views.vietnameocr_recognize, name='model_vietnameocr_recognize'),
    path('model_yolo_x/detect/', views.yolo_detect, name='model_yolo_x_detect'),

    # Legacy VietNameOCR endpoints
    path('vietnameocr/recognize/', views.vietnameocr_recognize, name='vietnameocr_recognize'),
    
    # Legacy YOLO endpoints
    path('yolo/detect/', views.yolo_detect, name='yolo_detect'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
    
    # Model info
    path('info/', views.model_info, name='model_info'),
]
