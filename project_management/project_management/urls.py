# project_management/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.views.generic import RedirectView

def favicon_view(request):
    """Return empty response for favicon to prevent 404 errors"""
    return HttpResponse(status=204)  # No Content

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('chat/', include('chat.urls', namespace='chat')),
    path('favicon.ico', favicon_view),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
