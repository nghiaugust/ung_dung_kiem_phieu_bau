from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('permission_denied/', views.permission_denied, name='permission_denied'),
]
