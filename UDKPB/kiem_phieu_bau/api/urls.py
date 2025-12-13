"""
API URLs cho Mobile App
"""
from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Authentication
    path('register/', views.api_register, name='register'),
    path('login/', views.api_login, name='login'),
    path('logout/', views.api_logout, name='logout'),
    path('me/', views.api_me, name='me'),
    
    # Polls
    path('polls/', views.api_poll_list, name='poll_list'),
    path('polls/join/', views.api_join_poll, name='join_poll'),
    path('polls/<int:poll_id>/', views.api_poll_detail, name='poll_detail'),
    
    # Ballots
    path('polls/<int:poll_id>/upload/', views.api_upload_ballot, name='upload_ballot'),
    path('polls/<int:poll_id>/upload-batch/', views.api_upload_ballots_batch, name='upload_ballots_batch'),
    path('polls/<int:poll_id>/ballots/', views.api_ballot_list, name='ballot_list'),
    
    # Poll Member Management
    path('polls/<int:poll_id>/request-role/', views.api_request_role_upgrade, name='request_role_upgrade'),
    path('polls/<int:poll_id>/role-requests/', views.api_get_role_requests, name='get_role_requests'),
    path('polls/<int:poll_id>/members/<int:member_id>/approve-role/', views.api_approve_role_request, name='approve_role_request'),
    path('polls/<int:poll_id>/join-requests/', views.api_get_join_requests, name='get_join_requests'),
    path('polls/<int:poll_id>/members/<int:member_id>/approve-join/', views.api_approve_join_request, name='approve_join_request'),
]
