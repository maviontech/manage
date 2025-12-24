from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.team_chat_page, name="team_chat"),
    path("dm/<int:peer_id>/", views.team_chat_page, name="dm_chat"),
    path("peer/<int:peer_id>/", views.team_chat_page, name="peer_chat"),
    path("members/", views.tenant_members, name="members"),
    path("history/", views.conversation_history, name="history"),
    path("send/", views.send_message, name="send"),
    # Group (threads) endpoints
    path("groups/", views.groups_list, name="groups"),
    path("groups/create/", views.create_group, name="groups_create"),
    path("group/history/", views.group_history, name="group_history"),
    path("group/send/", views.group_send, name="group_send"),
    path("group/mark_read/", views.mark_group_read, name="group_mark_read"),
    path("group/update/", views.group_update, name="group_update"),
    path("mark_all_read/", views.mark_all_read, name="mark_all_read"),
    path("unread/", views.unread_counts, name="unread"),
    path("mark_read/", views.mark_read, name="mark_read"),
]
