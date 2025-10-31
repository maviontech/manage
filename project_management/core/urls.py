# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('identify/', views.identify_view, name='identify'),
    path('login_password/', views.login_password_view, name='login_password'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
]
