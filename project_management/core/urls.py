# urls.py
from django.urls import path
from . import views
from . import views_tenants
from . import views_passwordreset
from . import views_projects as projects
from . import views_teams as people

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
    # People
    path('people/', people.people_page, name='people_page'),           # render UI
    path('api/people/list', people.api_people_list, name='api_people_list'),
    path('api/people/create', people.api_create_member, name='api_create_member'),

    # Teams
    path('teams/', people.teams_page, name='teams_page'),
    path('api/teams/list', people.api_teams_list, name='api_teams_list'),
    path('api/teams/create', people.api_create_team, name='api_create_team'),
    path('api/teams/<int:team_id>/members', people.api_team_members, name='api_team_members'),
    path('api/teams/<int:team_id>/add_member', people.api_team_add_member, name='api_team_add_member'),
    path('api/teams/<int:team_id>/remove_member', people.api_team_remove_member, name='api_team_remove_member'),
    path('api/teams/<int:team_id>/set_lead', people.api_team_set_lead, name='api_team_set_lead'),
]
