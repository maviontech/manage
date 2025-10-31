# urls.py
from django.urls import path
from . import views
from . import views_tenants
from . import views_passwordreset

urlpatterns = [
    path('identify/', views.identify_view, name='identify'),
    path('login_password/', views.login_password_view, name='login_password'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('new_tenant/', views_tenants.new_tenant_view, name='new_tenant'),
    path("password-reset/", views_passwordreset.password_reset_request_view, name="password_reset_request"),
    path("password-reset/confirm/", views_passwordreset.password_reset_confirm_view, name="password_reset_confirm"),
]
