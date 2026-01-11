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
    path('refresh-token/', views.api_refresh_token, name='refresh_token'),
    path('logout/', views.api_logout, name='logout'),
    path('me/', views.api_me, name='me'),
    
    # Polls
    path('polls/', views.api_poll_list, name='poll_list'),
    path('polls-no-pool/', views.api_poll_list_no_pool, name='poll_list_no_pool'),  # Benchmark endpoint
    path('my-poll-memberships/', views.api_my_poll_memberships, name='my_poll_memberships'),
    path('polls/join/', views.api_join_poll, name='join_poll'),
    path('polls/<int:poll_id>/', views.api_poll_detail, name='poll_detail'),
    
    # Ballots
    path('polls/<int:poll_id>/upload/', views.api_upload_ballot, name='upload_ballot'),
    path('polls/<int:poll_id>/upload-batch/', views.api_upload_ballots_batch, name='upload_ballots_batch'),
    path('polls/<int:poll_id>/ballots/', views.api_ballot_list, name='ballot_list'),
    path('polls/<int:poll_id>/ballots/<int:ballot_id>/verify-hmac/', views.api_verify_ballot_hmac, name='verify_ballot_hmac'),
    
    # Ballot Status (Async Upload)
    path('ballots/<int:ballot_id>/status/', views.api_ballot_status, name='ballot_status'),
    path('ballots/status-batch/', views.api_ballot_status_batch, name='ballot_status_batch'),
    
    # Poll Member Management
    path('polls/<int:poll_id>/request-role/', views.api_request_role_upgrade, name='request_role_upgrade'),
    path('polls/<int:poll_id>/role-requests/', views.api_get_role_requests, name='get_role_requests'),
    path('polls/<int:poll_id>/members/<int:member_id>/approve-role/', views.api_approve_role_request, name='approve_role_request'),
    path('polls/<int:poll_id>/join-requests/', views.api_get_join_requests, name='get_join_requests'),
    path('polls/<int:poll_id>/members/<int:member_id>/approve-join/', views.api_approve_join_request, name='approve_join_request'),
    
    # Statistics
    path('statistics/', views.api_statistics, name='statistics'),
    path('polls/<int:poll_id>/statistics/', views.api_statistics_detail, name='statistics_detail'),
    
    # Voter Management
    path('polls/<int:poll_id>/voters/', views.api_voter_list, name='voter_list'),
    path('polls/<int:poll_id>/voters/all/', views.api_voter_list_no_limit, name='voter_list_no_limit'),
    path('polls/<int:poll_id>/voters/create/', views.api_voter_create, name='voter_create'),
    path('polls/<int:poll_id>/voters/<int:voter_id>/', views.api_voter_update, name='voter_update'),
    path('polls/<int:poll_id>/voters/<int:voter_id>/delete/', views.api_voter_delete, name='voter_delete'),
    path('polls/<int:poll_id>/voters/<int:voter_id>/checkin/', views.api_voter_checkin, name='voter_checkin'),
    path('polls/<int:poll_id>/voters/<int:voter_id>/undo-checkin/', views.api_voter_undo_checkin, name='voter_undo_checkin'),
    
]
