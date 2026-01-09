from django.urls import path
from . import views, auto_check_views

urlpatterns = [
	path('poll/<int:poll_id>/', views.counting_form_view, name='counting_form'),
	path('poll/<int:poll_id>/process/', views.process_counting, name='process_counting'),
	path('poll/<int:poll_id>/results/', views.counting_results_view, name='counting_results'),
	path('poll/<int:poll_id>/save-config/', views.save_config_only, name='save_config_only'),
	
	# Auto check
	path('poll/<int:poll_id>/auto-check/toggle/', auto_check_views.toggle_auto_check, name='toggle_auto_check'),
	path('poll/<int:poll_id>/auto-check/status/', auto_check_views.get_auto_check_status, name='get_auto_check_status'),
	path('scheduler/status/', auto_check_views.get_scheduler_status, name='scheduler_status'),
]
