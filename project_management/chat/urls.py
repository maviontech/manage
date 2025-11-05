from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("members/", views.tenant_members, name="members"),
    path("history/", views.conversation_history, name="history"),
    path("send/", views.send_message, name="send"),
]
