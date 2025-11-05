# urls.py
from django.urls import path
from . import views
from . import views_tenants
from . import views_passwordreset
from . import views_projects as projects
from . import views_teams as people
from . import views_tasks as views_tasks
from  .import views_permissions as vp

urlpatterns = [
    # file: `project_management/core/urls.py`
    path('', views.identify_view, name='identify'),             # root/default page -> identify view
    path('identify/', views.identify_view, name='identify_page'),  # optional alias with a different name
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
    path("tasks/my/", views_tasks.my_tasks_view, name="my_tasks"),
    path("tasks/unassigned/", views_tasks.unassigned_tasks_view, name="unassigned_tasks"),
    path("tasks/create/", views_tasks.create_task_view, name="create_task"),
    path("tasks/bulk-import/", views_tasks.bulk_import_csv_view, name="bulk_import"),
    path("tasks/board/", views_tasks.task_board_view, name="task_board"),
    path("tasks/api/team-list/", views.api_team_list, name="api_team_list"),
    path("tasks/api/team-summary/", views.api_team_summary, name="api_team_summary"),
    # APIs
    path("tasks/api/assign/", views_tasks.assign_task_api, name="api_assign_task"),
    path("tasks/api/update-status/", views_tasks.api_update_status, name="api_update_status"),
    path("tasks/api/board-data/", views_tasks.board_data_api, name="board_data"),
    path('api/task/detail/', views_tasks.api_task_detail, name='api_task_detail'),
    path('api/task/update/', views_tasks.api_task_update, name='api_task_update'),

    path('settings/change-password/', vp.change_password_page, name='change_password'),
    path('settings/password-reset/', vp.password_reset_request, name='password_reset_request'),
    path('settings/password-reset/confirm/', vp.password_reset_confirm, name='password_reset_confirm'),

    path('settings/roles/', vp.roles_page, name='roles_page'),
    path('settings/roles/save/', vp.roles_save, name='roles_save'),
    path('settings/roles/delete/', vp.roles_delete, name='roles_delete'),

    path('settings/access-control/', vp.access_control_page, name='access_control_page'),
    path('settings/access-control/assign/', vp.assign_role, name='assign_role'),

    path('settings/password-policy/', vp.password_policy_page, name='password_policy_page'),
]
