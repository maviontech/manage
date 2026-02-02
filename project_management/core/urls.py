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
    path('multi-tenant-login/', views_tenants.multi_tenant_login_view, name='multi_tenant_login'),
    path('tenant-dashboard/', views_tenants.tenant_dashboard_view, name='tenant_dashboard'),
    path('add-admin/', views_tenants.add_tenant_admin_view, name='add_tenant_admin'),
    path('tenant/<int:tenant_id>/add-admin/', views_tenants.add_tenant_admin_view, name='add_tenant_admin_specific'),
    path('login_password/', views.login_password_view, name='login_password'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('new_tenant/', views_tenants.new_tenant_view, name='new_tenant'),
    path("password-reset/", views_passwordreset.password_reset_request_view, name="password_reset_request"),
    path("password-reset/confirm/", views_passwordreset.password_reset_confirm_view, name="password_reset_confirm"),
    path('projects/', projects.projects_list, name='projects_list'),
    path('projects/create/', projects.project_create, name='project_create'),
    path('projects/<int:project_id>/configure/', projects.project_configure, name='project_configure'),
    path('projects/<int:project_id>/edit/', projects.project_edit, name='project_edit'),
    path('report/', views.projects_report_view, name='projects_report'),
    path('report/export-excel/', views.export_projects_excel, name='export_projects_excel'),
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
    path("tasks/create/bug/", views_tasks.create_bug_view, name="create_bug"),
    path("tasks/create/story/", views_tasks.create_story_view, name="create_story"),
    path("tasks/create/defect/", views_tasks.create_defect_view, name="create_defect"),
    path("tasks/create/subtask/", views_tasks.create_subtask_view, name="create_subtask"),
    path("tasks/create/report/", views_tasks.create_report_view, name="create_report"),
    path("tasks/create/change-request/", views_tasks.create_change_request_view, name="create_change_request"),
    path("tasks/bulk-import/", views_tasks.bulk_import_csv_view, name="bulk_import"),
    path("tasks/board/", views_tasks.task_board_view, name="task_board"),
    path("tasks/analytics/", views_tasks.task_analytics_view, name="task_analytics"),
    path("tasks/api/team-list/", views.api_team_list, name="api_team_list"),
    path("tasks/api/team-summary/", views.api_team_summary, name="api_team_summary"),
    path("api/team-members/", views.api_get_team_members, name="api_get_team_members"),
    path("tasks/api/subprojects/", views_tasks.api_get_subprojects, name="api_get_subprojects"),
    path("tasks/<int:task_id>/", views_tasks.task_detail_view, name="task_detail"),
    path("tasks/<int:task_id>/view/", views_tasks.task_page_view, name="task_page_view"),
    path("tasks/<int:task_id>/edit/", views_tasks.edit_task_view, name="edit_task"),
    path("tasks/<int:task_id>/delete/", views_tasks.delete_task_view, name="delete_task"),
    path("tasks/<int:task_id>/export-pdf/", views_tasks.export_task_pdf, name="export_task_pdf"),
    path("tasks/<int:task_id>/update-status/", views_tasks.update_task_status, name="update_task_status"),
    path("tasks/<int:task_id>/update-priority/", views_tasks.update_task_priority, name="update_task_priority"),
    path("tasks/<int:task_id>/add-comment/", views_tasks.add_task_comment, name="add_task_comment"),

    # APIs
    path("tasks/api/assign/", views_tasks.assign_task_api, name="api_assign_task"),
    path("tasks/api/update-status/", views_tasks.api_update_status, name="api_update_status"),
    path("tasks/api/board-data/", views_tasks.board_data_api, name="board_data"),
    path('api/task/detail/', views_tasks.api_task_detail, name='api_task_detail'),
    path('api/task/update/', views_tasks.api_task_update, name='api_task_update'),
    path('tasks/api/search/', views_tasks.api_tasks_search, name='api_tasks_search'),
    path('tasks/api/project-work-types/', views_tasks.api_get_project_work_types, name='api_project_work_types'),

    path('settings/change-password/', vp.change_password_page, name='change_password'),
    path('settings/password-reset/', vp.password_reset_request, name='password_reset_request'),
    path('settings/password-reset/confirm/', vp.password_reset_confirm, name='password_reset_confirm'),

    path('settings/roles/', vp.roles_page, name='roles_page'),
    path('settings/roles/save/', vp.roles_save, name='roles_save'),
    path('settings/roles/delete/', vp.roles_delete, name='roles_delete'),

    path('settings/access-control/', vp.access_control_page, name='access_control_page'),
    path('settings/access-control/assign/', vp.assign_role, name='assign_role'),

    path('settings/password-policy/', vp.password_policy_page, name='password_policy_page'),
    
    # Employees
    path('employees/', views.employees_page, name='employees_page'),
    path('api/employees/list', views.api_employees_list, name='api_employees_list'),
    path('api/employees/create', views.api_create_employee, name='api_create_employee'),
    path('api/employees/update', views.api_update_employee, name='api_update_employee'),
    path('api/employees/delete', views.api_delete_employee, name='api_delete_employee'),
    path('api/employees/detail', views.api_employee_detail, name='api_employee_detail'),
    
    # Notifications
    path('notifications/', views.notifications_page, name='notifications_page'),
    path('notifications/test/', views.test_notifications_page, name='test_notifications_page'),
    path('api/notifications/list', views.api_notifications_list, name='api_notifications_list'),
    path('api/notifications/mark-read', views.api_notifications_mark_read, name='api_notifications_mark_read'),
    path('api/notifications/delete', views.api_notifications_delete, name='api_notifications_delete'),
    path('api/notifications/unread-count', views.api_notifications_unread_count, name='api_notifications_unread_count'),
    
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/change-password/', views.profile_change_password_view, name='profile_change_password'),
    
    # Timer
    path('timer/', views.timer_page, name='timer_page'),
    path('api/timer/start', views.api_timer_start, name='api_timer_start'),
    path('api/timer/stop', views.api_timer_stop, name='api_timer_stop'),
    path('api/timer/pause', views.api_timer_pause, name='api_timer_pause'),
    path('api/timer/resume', views.api_timer_resume, name='api_timer_resume'),
    path('api/timer/current', views.api_timer_current, name='api_timer_current'),
    path('api/timer/history', views.api_timer_history, name='api_timer_history'),
    # Time Entries
    path('time-entries/', views.time_entries_page, name='time_entries_page'),
    path('api/time-entries/list', views.api_time_entries_list, name='api_time_entries_list'),
    path('api/time-entries/create', views.api_time_entries_create, name='api_time_entries_create'),
    path('api/time-entries/update', views.api_time_entries_update, name='api_time_entries_update'),
    path('api/time-entries/delete', views.api_time_entries_delete, name='api_time_entries_delete'),
    path('api/time-entries/approve', views.api_time_entries_approve, name='api_time_entries_approve'),
    path('api/time-entries/reject', views.api_time_entries_reject, name='api_time_entries_reject'),

    
]

