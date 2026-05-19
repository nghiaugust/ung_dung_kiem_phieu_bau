"""
URL Configuration cho API app
"""
from django.urls import path
from . import views

urlpatterns = [
    path('model_vietnameocr/recognize/', views.vietnameocr_recognize, name='vietnameocr_recognize'),
    path('model_yolo_x/detect/', views.yolo_x_detect, name='yolo_x_detect'),
    path('model_resnet18_crossed/detect/', views.resnet18_crossed_detect, name='resnet18_crossed_detect'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
    
    # Model info
    path('info/', views.model_info, name='model_info'),
]
