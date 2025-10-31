# urls.py
from django.urls import path
from . import views
from . import views_tenants
from . import views_passwordreset
from . import views_projects as projects

urlpatterns = [
    path('identify/', views.identify_view, name='identify'),
    path('login_password/', views.login_password_view, name='login_password'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('new_tenant/', views_tenants.new_tenant_view, name='new_tenant'),
    path("password-reset/", views_passwordreset.password_reset_request_view, name="password_reset_request"),
    path("password-reset/confirm/", views_passwordreset.password_reset_confirm_view, name="password_reset_confirm"),
    path('projects/', projects.projects_list, name='projects_list'),
    path('projects/create/', projects.project_create, name='project_create'),
    path('projects/<int:project_id>/edit/', projects.project_edit, name='project_edit'),
    path('projects/<int:project_id>/subprojects/', projects.subprojects_list, name='subprojects_list'),
    path('projects/<int:project_id>/subprojects/create/', projects.subproject_create, name='subproject_create'),
    path('projects/<int:project_id>/subprojects/<int:sub_id>/edit/', projects.subproject_edit, name='subproject_edit'),
    # ajax endpoints
    path('projects/ajax/search/', projects.projects_search_ajax, name='projects_search_ajax'),
]
