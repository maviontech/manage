# core/db_helpers.py
import pymysql
from django.conf import settings

# Replace this with your real tenant resolver: for example, get DB name/user/password from session
def resolve_tenant_credentials(request):
    """
    Resolve tenant DB credentials from session.
    """
    tenant_conf = request.session.get('tenant_config', {})

    return {
        "host": tenant_conf.get("db_host") or request.session.get("tenant_db_host", "127.0.0.1"),
        "port": int(tenant_conf.get("db_port") or request.session.get("tenant_db_port", 3306)),
        "user": tenant_conf.get("db_user") or request.session.get("tenant_db_user"),
        "password": tenant_conf.get("db_password") or request.session.get("tenant_db_password"),
        "database": tenant_conf.get("db_name") or request.session.get("tenant_db_name"),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def get_tenant_conn_and_cursor(request):
    creds = resolve_tenant_credentials(request)
    if not creds["database"] or not creds["user"]:
        raise RuntimeError("Tenant DB not resolved on request; ensure tenant middleware sets tenant_db_* on request")
    conn = pymysql.connect(host=creds["host"], port=creds["port"], user=creds["user"],
                           password=creds["password"], database=creds["database"],
                           cursorclass=creds["cursorclass"], autocommit=creds["autocommit"])
    cur = conn.cursor()
    return conn, cur
