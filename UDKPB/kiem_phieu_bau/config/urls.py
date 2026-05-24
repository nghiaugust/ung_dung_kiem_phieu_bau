from django.urls import path

from . import views


app_name = "config"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("<str:component_id>/start/", views.start_component, name="start_component"),
    path("<str:component_id>/stop/", views.stop_component, name="stop_component"),
    path("<str:component_id>/restart/", views.restart_component, name="restart_component"),
]

