from django.urls import path
from . import views

urlpatterns = [
	path('', views.counting_config_list, name='counting_config_list'),
	path('poll/<int:poll_id>/', views.counting_form_view, name='counting_form'),
	path('poll/<int:poll_id>/process/', views.process_counting, name='process_counting'),
	path('poll/<int:poll_id>/results/', views.counting_results_view, name='counting_results'),
	path('poll/<int:poll_id>/save-config/', views.save_configuration, name='save_configuration'),
	path('poll/<int:poll_id>/auto/', views.auto_counting_view, name='auto_counting'),
	path('poll/<int:poll_id>/toggle-auto', views.toggle_auto_counting),
	path('poll/<int:poll_id>/toggle-auto/', views.toggle_auto_counting, name='toggle_auto_counting'),
	path('poll/<int:poll_id>/stats/', views.get_counting_stats, name='counting_stats'),
]
