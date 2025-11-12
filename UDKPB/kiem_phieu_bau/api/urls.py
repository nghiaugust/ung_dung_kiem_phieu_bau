"""
API URLs cho Mobile App
"""
from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Authentication
    path('login/', views.api_login, name='login'),
    path('logout/', views.api_logout, name='logout'),
    path('me/', views.api_me, name='me'),
    
    # Polls
    path('polls/', views.api_poll_list, name='poll_list'),
    path('polls/<int:poll_id>/', views.api_poll_detail, name='poll_detail'),
    
    # Ballots
    path('polls/<int:poll_id>/upload/', views.api_upload_ballot, name='upload_ballot'),
    path('polls/<int:poll_id>/ballots/', views.api_ballot_list, name='ballot_list'),
]
