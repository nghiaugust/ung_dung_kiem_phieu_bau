from django.urls import path
from . import views

app_name = 'poll'

urlpatterns = [
    # Poll management
    path('danh_sach/', views.danh_sach_cuoc_bo_phieu, name='danh_sach_cuoc_bo_phieu'),
    path('tao/', views.tao_cuoc_bo_phieu, name='tao_cuoc_bo_phieu'),
    path('<int:poll_id>/', views.poll_detail, name='poll_detail'),
    path('<int:poll_id>/edit/', views.edit_poll, name='edit_poll'),
    path('delete/<int:poll_id>/', views.delete_poll, name='delete_poll'),
    
    # Candidate management
    path('<int:poll_id>/add_candidate/', views.add_candidate, name='add_candidate'),
    path('<int:poll_id>/copy_candidates/', views.copy_candidates, name='copy_candidates'),
    path('candidate/<int:candidate_id>/edit/', views.edit_candidate, name='edit_candidate'),
    path('candidate/delete/<int:candidate_id>/', views.delete_candidate, name='delete_candidate'),
    path('candidate/delete_all/<int:poll_id>/', views.delete_all_candidates, name='delete_all_candidates'),
    
    # Poll member management
    path('account/manage-poll-accounts/', views.manage_poll_accounts, name='manage_poll_accounts'),
    path('<int:poll_id>/members/', views.poll_members, name='poll_members'),
    path('<int:poll_id>/members/add/', views.add_poll_member, name='add_poll_member'),
    path('poll_member/delete/<int:member_id>/', views.delete_poll_member, name='delete_poll_member'),
    
    # Statistics
    path('thong_ke/', views.thong_ke, name='thong_ke'),
    path('thong_ke/<int:poll_id>/', views.thong_ke_detail, name='thong_ke_detail'),
    
    # Counting
    path('ajax/stream-counting/<int:poll_id>/', views.kiem_phieu_stream, name='kiem_phieu_stream'),
]
