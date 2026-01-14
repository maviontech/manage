# chat/routing.py
from django.urls import re_path
from .consumers import ChatConsumer, NotificationConsumer, TypingIndicatorConsumer

websocket_urlpatterns = [
    re_path(r"^ws/chat/$", ChatConsumer.as_asgi()),
    re_path(r"^ws/presence/$", NotificationConsumer.as_asgi()),
    re_path(r"^ws/notifications/$", NotificationConsumer.as_asgi()),
    re_path(r"^ws/is_typing/$", TypingIndicatorConsumer.as_asgi()),
]
