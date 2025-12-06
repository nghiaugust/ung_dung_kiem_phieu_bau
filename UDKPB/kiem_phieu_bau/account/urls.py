from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    path('tai_khoan/', views.tai_khoan, name='tai_khoan'),
    
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('profile/', views.account_profile, name='account_profile'),
    path('list/', views.account_list, name='account_list'),
    path('add/', views.add_account, name='add_account'),
    path('edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('edit_user/<int:account_id>/', views.edit_account_user, name='edit_account_user'),
    path('edit_redirect/<int:account_id>/', views.edit_account_redirect, name='edit_account_redirect'),
    path('delete/<int:account_id>/', views.delete_account, name='delete_account'),
]
