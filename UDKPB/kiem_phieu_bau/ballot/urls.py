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
    
    # Form ballot management
    path('form/create/<int:poll_id>/', views.create_form_ballot, name='create_form_ballot'),
    path('form/list/<int:poll_id>/', views.list_form_ballot, name='list_form_ballot'),
    path('form/detail/<int:form_id>/', views.detail_form_ballot, name='detail_form_ballot'),
    path('form/apply/<int:form_id>/', views.apply_form_ballot, name='apply_form_ballot'),
    path('form/delete/<int:form_id>/', views.delete_form_ballot, name='delete_form_ballot'),
    path('form/export-pdf/<int:form_id>/', views.export_form_ballot_pdf, name='export_form_ballot_pdf'),
]
