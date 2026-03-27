import time

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from core.tenant_context import set_current_tenant


class SessionTimeoutMiddleware:
    """
    Enforce inactivity timeout for the app's custom session-based auth flow.
    """

    EXEMPT_PATH_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = int(getattr(settings, 'SESSION_COOKIE_AGE', 1800))

    def __call__(self, request):
        if self._should_skip(request):
            return self.get_response(request)

        if self._is_authenticated(request):
            current_time = time.time()
            last_activity = float(request.session.get('last_activity', current_time))

            if current_time - last_activity > self.timeout:
                return self._handle_timeout(request)

            request.session['last_activity'] = current_time

        return self.get_response(request)

    def _should_skip(self, request):
        return any(request.path.startswith(prefix) for prefix in self.EXEMPT_PATH_PREFIXES)

    def _is_authenticated(self, request):
        return bool(
            request.session.get('user')
            or request.session.get('member_id')
            or request.session.get('user_id')
            or request.session.get('multi_tenant_admin')
        )

    def _is_api_request(self, request):
        accept = (request.headers.get('Accept') or '').lower()
        content_type = (request.headers.get('Content-Type') or '').lower()
        requested_with = (request.headers.get('X-Requested-With') or '').lower()

        return (
            request.path.startswith('/api/')
            or request.path.startswith('/tasks/api/')
            or request.path.startswith('/chat/')
            or requested_with == 'xmlhttprequest'
            or 'application/json' in accept
            or 'application/json' in content_type
        )

    def _clear_authenticated_session(self, request):
        preserved = {
            'tenant_config': request.session.get('tenant_config'),
            'ident_email': request.session.get('ident_email'),
        }

        request.session.flush()

        for key, value in preserved.items():
            if value is not None:
                request.session[key] = value

    def _handle_timeout(self, request):
        expired_admin = bool(request.session.get('multi_tenant_admin'))
        self._clear_authenticated_session(request)

        if expired_admin:
            request.session['multi_tenant_error'] = 'Your session has expired. Please log in again.'
            if self._is_api_request(request):
                return JsonResponse({'error': 'Session expired'}, status=401)
            return redirect('multi_tenant_login')

        request.session['session_expired_message'] = 'Your session has expired. Please log in again.'
        if self._is_api_request(request):
            return JsonResponse({'error': 'Session expired'}, status=401)
        return redirect('login_password')


class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        tenant_conf = request.session.get('tenant_config')
        set_current_tenant(tenant_conf)

    def process_response(self, request, response):
        # clear threadlocal to avoid leakage
        set_current_tenant(None)
        return response
