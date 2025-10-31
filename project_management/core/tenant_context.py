# tenant_context.py
import threading

_thread_local = threading.local()

def set_current_tenant(tenant_config):
    """tenant_config: dict or None"""
    _thread_local.tenant = tenant_config

def get_current_tenant():
    return getattr(_thread_local, 'tenant', None)
