# core/tenant_permissions.py
import pymysql
from functools import wraps
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.conf import settings
from django.utils import timezone
import secrets, string

# If you already have a tenant connector (get_tenant_conn), import it.
# from core.db import get_tenant_conn

# Fallback helper: adapt as necessary to your get_tenant_conn pattern
def get_tenant_conn_from_request(request):
    # This assumes you have stored tenant DB credentials in session or can derive a db_name from session
    # Replace with your project's actual tenant-connection helper.
    from .db_helpers import get_tenant_conn
    return get_tenant_conn(request)

def get_user_project_role_ids(conn, member_id, project_id):
    """
    Return role_ids assigned to member for this project (if project_id provided) OR tenant-wide (tenant_role_assignments).
    Returns a list of unique role_id ints.
    Assumes 'conn' is a pymysql connection with DictCursor.
    """
    cur = conn.cursor()
    role_ids = set()

    # 1) tenant-wide roles
    try:
        cur.execute("SELECT role_id FROM tenant_role_assignments WHERE member_id=%s", (member_id,))
        rows = cur.fetchall()
        for r in rows:
            role_ids.add(int(r['role_id']))
    except Exception:
        # If tenant_role_assignments does not exist for some reason, ignore and continue
        pass

    # 2) project-scoped roles (if project_id provided)
    if project_id is not None:
        try:
            cur.execute(
                "SELECT role_id FROM project_role_assignments WHERE member_id=%s AND project_id=%s",
                (member_id, project_id)
            )
            prow = cur.fetchall()
            for r in prow:
                role_ids.add(int(r['role_id']))
        except Exception:
            # If querying project_role_assignments fails for some reason, ignore (we don't want to break permission flow)
            pass

    cur.close()
    return list(role_ids)



def get_permissions_for_role_ids(conn, role_ids):
    if not role_ids:
        return []
    q = "SELECT p.code FROM permissions p JOIN role_permissions rp ON p.id=rp.permission_id WHERE rp.role_id IN ({})".format(
        ",".join(["%s"]*len(role_ids))
    )
    cur = conn.cursor()
    cur.execute(q, tuple(role_ids))
    rows = cur.fetchall()
    cur.close()
    return [r['code'] for r in rows]

def user_has_permission(request, member_id, project_id, permission_code):
    conn = get_tenant_conn_from_request(request)
    try:
        role_ids = get_user_project_role_ids(conn, member_id, project_id)
        if not role_ids:
            return False
        perms = get_permissions_for_role_ids(conn, role_ids)
        return permission_code in perms
    finally:
        conn.close()

def require_permission(permission_code, project_param='project_id'):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            member_id = request.session.get('member_id') or getattr(request.user, 'id', None)
            project_id = kwargs.get(project_param) or request.POST.get(project_param) or request.GET.get(project_param)
            if not member_id:
                return redirect('login')
            if not project_id:
                # for tenant-level operations, project_id might be None; require special perms like roles.manage
                if user_has_permission(request, member_id, None, permission_code):
                    return view_func(request, *args, **kwargs)
                return HttpResponseForbidden("Permission denied")
            if user_has_permission(request, member_id, project_id, permission_code):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Permission denied")
        return _wrapped
    return decorator

# Utility: fetch effective permissions for a member on a project
def get_effective_permissions(request, member_id, project_id):
    conn = get_tenant_conn_from_request(request)
    try:
        role_ids = get_user_project_role_ids(conn, member_id, project_id)
        if not role_ids:
            return []
        return get_permissions_for_role_ids(conn, role_ids)
    finally:
        conn.close()

# Utility: create a secure random token
def generate_token(length=48):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
