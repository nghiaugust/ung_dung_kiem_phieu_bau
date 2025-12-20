from django.urls import path
from . import views

app_name = 'form'

urlpatterns = [
    path('', views.editor_view, name='editor'),
    path('<int:poll_id>/', views.editor_view, name='editor_with_poll'),
    path('compile/', views.compile_pdf, name='compile_pdf'),
    path('save/', views.save_document, name='save_document'),
    path('load/<int:doc_id>/', views.load_document, name='load_document'),
    path('ballots/<int:poll_id>/create/', views.create_ballots_ajax, name='create_ballots_ajax'),
    path('ballots/<int:poll_id>/count/', views.ballot_count_api, name='ballot_count_api'),
    path('documents/<int:poll_id>/list/', views.list_documents_api, name='list_documents_api'),
    path('candidates/<int:poll_id>/list/', views.list_candidates_api, name='list_candidates_api'),
]
