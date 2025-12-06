from django.urls import path
from . import views

app_name = 'ballot'

urlpatterns = [
    path('upload/<int:poll_id>/', views.upload_ballots, name='upload_ballots'),
    path('list/<int:poll_id>/', views.ballot_list, name='ballot_list'),
    path('view/<int:poll_id>/', views.ballot_view, name='ballot_view'),
    path('list/redirect/<int:poll_id>/', views.ballot_list_redirect, name='ballot_list_redirect'),
    
    path('delete_all/<int:poll_id>/', views.delete_all_ballots, name='delete_all_ballots'),
    path('detail/<int:ballot_id>/', views.ballot_detail, name='ballot_detail'),
    path('delete/<int:ballot_id>/', views.delete_ballot, name='delete_ballot'),
    path('view_detail/<int:ballot_id>/', views.ballot_view_detail, name='ballot_view_detail'),
    path('download-sample-ballots/', views.download_sample_ballots, name='download_sample_ballots'),
    path('hau-kiem/<int:ballot_id>/', views.hau_kiem_ballot, name='hau_kiem_ballot'),
    path('hau-kiem/<int:ballot_id>/save/', views.save_hau_kiem, name='save_hau_kiem'),
]
