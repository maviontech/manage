# middleware.py
from django.utils.deprecation import MiddlewareMixin
from core.tenant_context import set_current_tenant

class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        tenant_conf = request.session.get('tenant_config')
        set_current_tenant(tenant_conf)

    def process_response(self, request, response):
        # clear threadlocal to avoid leakage
        set_current_tenant(None)
        return response
