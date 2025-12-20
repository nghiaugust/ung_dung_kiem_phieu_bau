from django.urls import path
from . import views

urlpatterns = [
	path('poll/<int:poll_id>/', views.counting_form_view, name='counting_form'),
	path('poll/<int:poll_id>/process/', views.process_counting, name='process_counting'),
	path('poll/<int:poll_id>/results/', views.counting_results_view, name='counting_results'),
]
