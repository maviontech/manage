from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("members/", views.tenant_members, name="members"),
    path("history/", views.conversation_history, name="history"),
    path("send/", views.send_message, name="send"),
    path("unread/", views.unread_counts, name="unread"),
    path("mark_read/", views.mark_read, name="mark_read"),
]
