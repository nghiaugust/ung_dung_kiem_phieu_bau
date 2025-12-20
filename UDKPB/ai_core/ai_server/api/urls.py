"""
URL Configuration cho API app
"""
from django.urls import path
from . import views

urlpatterns = [
    # TrOCR endpoints
    path('trocr/recognize/', views.trocr_recognize, name='trocr_recognize'),
    
    # YOLO endpoints
    path('yolo/detect/', views.yolo_detect, name='yolo_detect'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
    
    # Model info
    path('info/', views.model_info, name='model_info'),
]
