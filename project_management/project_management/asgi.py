# project_management/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project_management.settings")

# Standard Django ASGI app for HTTP handling
django_asgi_app = get_asgi_application()

# Import Channels classes here (after settings are configured)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import chat.routing  # keep this import light — chat.routing should only define websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        # Handles traditional HTTP requests by Django ASGI application
        "http": django_asgi_app,
        # Handles WebSocket connections with session/auth middleware
        "websocket": AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns)),
    }
)
