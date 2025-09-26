from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    
    path('tai_khoan/', views.tai_khoan, name='tai_khoan'),
    
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('account/profile/', views.account_profile, name='account_profile'),
    path('account/list/', views.account_list, name='account_list'),
    path('account/add/', views.add_account, name='add_account'),
    path('account/edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('account/edit_user/<int:account_id>/', views.edit_account_user, name='edit_account_user'),
    path('account/edit_redirect/<int:account_id>/', views.edit_account_redirect, name='edit_account_redirect'),
    path('account/delete/<int:account_id>/', views.delete_account, name='delete_account'),
    
    path('danh_sach_cuoc_bo_phieu/', views.danh_sach_cuoc_bo_phieu, name='danh_sach_cuoc_bo_phieu'),
    path('tao_cuoc_bo_phieu/', views.tao_cuoc_bo_phieu, name='tao_cuoc_bo_phieu'),
    path('poll/<int:poll_id>/', views.poll_detail, name='poll_detail'),
    path('poll/<int:poll_id>/ballots/redirect/', views.ballot_list_redirect, name='ballot_list_redirect'),
    path('poll/<int:poll_id>/add_candidate/', views.add_candidate, name='add_candidate'),
    path('poll/<int:poll_id>/copy_candidates/', views.copy_candidates, name='copy_candidates'),
    path('poll/<int:poll_id>/edit/', views.edit_poll, name='edit_poll'),
    path('poll/<int:poll_id>/upload_ballots/', views.upload_ballots, name='upload_ballots'),
    path('poll/<int:poll_id>/ballots/', views.ballot_list, name='ballot_list'),
    path('poll/<int:poll_id>/ballots/view/', views.ballot_view, name='ballot_view'),
    path('poll/delete/<int:poll_id>/', views.delete_poll, name='delete_poll'),
    
    path('ajax/stream-counting/<int:poll_id>/', views.kiem_phieu_stream, name='kiem_phieu_stream'),
    
    path('candidate/<int:candidate_id>/edit/', views.edit_candidate, name='edit_candidate'),
    path('candidate/delete/<int:candidate_id>/', views.delete_candidate, name='delete_candidate'),
    path('candidate/delete_all/<int:poll_id>/', views.delete_all_candidates, name='delete_all_candidates'),
    
    path('ballot/delete_all/<int:poll_id>/', views.delete_all_ballots, name='delete_all_ballots'),
    path('ballot/detail/<int:ballot_id>/', views.ballot_detail, name='ballot_detail'),
    path('ballot/delete/<int:ballot_id>/', views.delete_ballot, name='delete_ballot'),
    path('ballot/view_detail/<int:ballot_id>/', views.ballot_view_detail, name='ballot_view_detail'),
    
    path('thong_ke/', views.thong_ke, name='thong_ke'),
    path('thong_ke/<int:poll_id>/', views.thong_ke_detail, name='thong_ke_detail'),
    
    path('permission_denied/', views.permission_denied, name='permission_denied'),
]
