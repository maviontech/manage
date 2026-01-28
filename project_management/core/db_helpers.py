# core/db_helpers.py
"""
Multi-tenant DB helpers for tenant-per-database architecture.

Usage (existing code compatibility):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT ...", (param,))
        rows = cur.fetchall()
    finally:
        cur.close()   # keep connection cached, close cursor
    # Do NOT close conn unless you explicitly want to remove it from cache.

Recommended (context-managed):
    conn = get_tenant_conn(request)
    with conn.cursor() as cur:
        cur.execute(...)
        rows = cur.fetchall()

Notes:
 - This tries to resolve tenant credentials from request.session first (same keys your older code uses).
 - If session does not contain the DB info, it attempts to resolve by host or from the central clients_master table using the Django default DB.
 - Caches connections per-thread to reduce overhead. If you run in async or green-thread environment, adapt caching strategy.
"""

import threading
import time
import pymysql
import pymysql.cursors
from django.conf import settings
from django.db import connection as default_connection
from django.http import HttpRequest
import contextlib
import logging
from typing import Optional, List, Dict, Any, Union
from django.db import connections, connection as default_connection

logger = logging.getLogger('utility')

# Thread-local cache for tenant connections
_tlocal = threading.local()
# default max age for cached connections (seconds)
_CONN_MAX_AGE = getattr(settings, "TENANT_CONN_MAX_AGE", 300)  # 5 minutes


def get_alex_carter_id(conn):
    """
    Get the member ID for Alex Carter.
    Returns None if not found.
    """
    cur = conn.cursor()
    try:
        # Try to find Alex Carter by name or email
        cur.execute("""
            SELECT id FROM members 
            WHERE (first_name = 'Alex' AND last_name = 'Carter') 
               OR email LIKE '%alex.carter%'
               OR email LIKE '%alexcarter%'
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return row['id'] if isinstance(row, dict) else row[0]
        return None
    except Exception as e:
        logger.error(f"Error getting Alex Carter ID: {e}")
        return None
    finally:
        cur.close()


def get_visible_task_user_ids(conn, current_user_id):
    """
    Get list of user IDs whose tasks should be visible to the current user.
    
    Rules:
    - All users can see all users' tasks (full visibility for everyone)
    
    Returns: list of user IDs
    """
    # Return all user IDs - everyone can see everyone's tasks
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM members")
        rows = cur.fetchall()
        return [row['id'] if isinstance(row, dict) else row[0] for row in rows]
    finally:
        cur.close()

# Session keys / fallback keys your existing code uses
_SESSION_TENANT_KEYS = (
    "tenant_config",          # dict with full creds (preferred)
    "tenant_db_name",         # explicit db name
    "tenant_db_user",
    "tenant_db_password",
    "tenant_db_host",
    "tenant_db_port",
    "tenant",                 # generic tenant key
    "client",                 # alternative session key
)


def _get_thread_cache():
    if not hasattr(_tlocal, "tenant_cache"):
        _tlocal.tenant_cache = {}
    return _tlocal.tenant_cache


def _get_tenant_row_from_master(tenant_key):
    """
    Query central clients_master table on default Django DB for tenant credential row.
    Adjust the SELECT columns if your clients_master uses different names.

    Expected columns: db_name, db_host, db_user, db_password, db_port (optional), domain_postfix or client_name
    """
    if not tenant_key:
        return None

    # Try several matching columns: domain_postfix, db_name, client_name
    q = """
        SELECT id, client_name, domain_postfix, db_name, db_host, db_user, db_password
        FROM clients_master
        WHERE domain_postfix = %s OR db_name = %s OR client_name = %s
        LIMIT 1
    """
    with default_connection.cursor() as cur:
        cur.execute(q, [tenant_key, tenant_key, tenant_key])
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        result = dict(zip(cols, row))
        # Add default port if not present
        result['db_port'] = 3306
        return result


def resolve_tenant_key_from_request(request: HttpRequest):
    """
    Resolve a tenant key (string) from request/session/host. This key is used to look up clients_master.
    Order:
      1) session['tenant'] or session['client'] or other session keys
      2) host header (full host, e.g. tenant.example.com or example.com)
      3) settings.DEFAULT_TENANT_KEY fallback
    """
    # 1) session explicit keys
    if request is not None:
        for k in ("tenant", "client", "tenant_db_name", "tenant_config"):
            v = request.session.get(k)
            if v:
                # If tenant_config is present and has db_name, return that db_name
                if k == "tenant_config" and isinstance(v, dict):
                    # prefer db_name if available
                    dbn = v.get("db_name")
                    if dbn:
                        return dbn
                    # else try domain_postfix inside tenant_config
                    dp = v.get("domain_postfix")
                    if dp:
                        return dp
                else:
                    return v

        # 2) host header (use whole host)
        host = (request.get_host() or "").split(":")[0].lower()
        if host:
            return host

    # 3) fallback
    return getattr(settings, "DEFAULT_TENANT_KEY", None)


def resolve_tenant_credentials(request: HttpRequest = None, tenant_key: str = None):
    """
    Resolve tenant DB credentials as a dict for pymysql.connect.
    Priority:
      1) request.session['tenant_config'] (a dict containing db_*)
      2) explicit session keys tenant_db_* used by older code
      3) if tenant_key or host derived, try clients_master lookup
      4) settings.DEFAULT_TENANT_CREDENTIALS (optional)
    Returns dict with keys: host, port, user, password, database, cursorclass, autocommit
    """
    # 1) if tenant_config present in session, use it
    if request is not None:
        tc = request.session.get("tenant_config")
        if isinstance(tc, dict) and tc.get("db_name"):
            return {
                "host": tc.get("db_host", "127.0.0.1"),
                "port": int(tc.get("db_port", 3306)),
                "user": tc.get("db_user"),
                "password": tc.get("db_password"),
                "database": tc.get("db_name"),
                "cursorclass": pymysql.cursors.DictCursor,
                "autocommit": True,
            }

        # 2) older session keys fallback
        dbname = request.session.get("tenant_db_name") or request.session.get("tenant")
        dbuser = request.session.get("tenant_db_user")
        dbpass = request.session.get("tenant_db_password")
        dbhost = request.session.get("tenant_db_host") or "127.0.0.1"
        dbport = int(request.session.get("tenant_db_port") or 3306)
        if dbname and dbuser:
            return {
                "host": dbhost,
                "port": dbport,
                "user": dbuser,
                "password": dbpass,
                "database": dbname,
                "cursorclass": pymysql.cursors.DictCursor,
                "autocommit": True,
            }

    # 3) if tenant_key provided or resolvable from request, try clients_master
    if tenant_key is None and request is not None:
        tenant_key = resolve_tenant_key_from_request(request)

    if tenant_key:
        tenant_row = _get_tenant_row_from_master(tenant_key)
        if tenant_row:
            return {
                "host": tenant_row.get("db_host") or "127.0.0.1",
                "port": int(tenant_row.get("db_port") or 3306),
                "user": tenant_row.get("db_user"),
                "password": tenant_row.get("db_password"),
                "database": tenant_row.get("db_name"),
                "cursorclass": pymysql.cursors.DictCursor,
                "autocommit": True,
            }

    # 4) application-level default credentials (optional)
    fallback = getattr(settings, "DEFAULT_TENANT_CREDENTIALS", None)
    if isinstance(fallback, dict) and fallback.get("database"):
        # ensure port is int and cursorclass present
        return {
            "host": fallback.get("host", "127.0.0.1"),
            "port": int(fallback.get("port", 3306)),
            "user": fallback.get("user"),
            "password": fallback.get("password"),
            "database": fallback.get("database"),
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": fallback.get("autocommit", True),
        }

    # nothing found
    return {
        "host": None, "port": None, "user": None, "password": None, "database": None,
        "cursorclass": pymysql.cursors.DictCursor, "autocommit": True
    }


def _open_tenant_connection(creds):
    """
    Create a pymysql connection from credentials dict.
    """
    return pymysql.connect(
        host=creds["host"],
        port=int(creds.get("port") or 3306),
        user=creds["user"],
        password=creds.get("password") or "",
        database=creds["database"],
        charset="utf8mb4",
        cursorclass=creds.get("cursorclass", pymysql.cursors.DictCursor),
        autocommit=creds.get("autocommit", True),
        connect_timeout=5,
    )


def get_tenant_conn(request: HttpRequest = None, tenant_key: str = None):
    """
    Return a pymysql.Connection for the tenant. Cached per-thread.

    Use get_tenant_conn_and_cursor(request) if you want conn, cursor pair.
    """
    if tenant_key is None and request is not None:
        tenant_key = resolve_tenant_key_from_request(request)

    if not tenant_key:
        raise RuntimeError("Could not resolve tenant key from request and no tenant_key provided.")

    cache = _get_thread_cache()
    now = time.time()

    cached = cache.get(tenant_key)
    if cached:
        conn = cached.get("conn")
        opened_at = cached.get("opened_at", 0)
        age = now - opened_at
        try:
            if conn and conn.open and age < _CONN_MAX_AGE:
                # ping to ensure it's alive; reconnect if needed
                conn.ping(reconnect=True)
                return conn
        except Exception:
            # connection dead or ping failed; close and remove
            try:
                conn.close()
            except Exception:
                pass
            cache.pop(tenant_key, None)

    # Not cached or stale: open new connection
    creds = resolve_tenant_credentials(request=request, tenant_key=tenant_key)
    if not creds["database"] or not creds["user"]:
        raise RuntimeError("Tenant DB credentials could not be resolved. Ensure session or clients_master is set.")

    conn = _open_tenant_connection(creds)
    cache[tenant_key] = {"conn": conn, "opened_at": now}
    return conn


def get_tenant_conn_and_cursor(request: HttpRequest = None, tenant_key: str = None):
    """
    Backwards-compatible helper: returns (conn, cursor) matching old code signature.

    Example:
        conn, cur = get_tenant_conn_and_cursor(request)
        cur.execute(...)
        rows = cur.fetchall()
        cur.close()   # keep conn cached
    """
    conn = get_tenant_conn(request=request, tenant_key=tenant_key)
    cur = conn.cursor()
    return conn, cur


def close_all_thread_conns():
    """
    Close and clear all cached tenant connections for this thread.
    Call this in management commands or on worker shutdown if desired.
    """
    cache = _get_thread_cache()
    for k, v in list(cache.items()):
        try:
            v["conn"].close()
        except Exception:
            pass
        cache.pop(k, None)


# core/db_helpers.py


def _cursor_from_conn(conn):
    """
    Normalize a 'conn' into a Django-like connection that has .cursor().
    Accepts:
      - None -> uses default Django connection
      - Django connection object (has .cursor)
      - string DB alias -> connections[alias]
      - a wrapper that exposes .cursor()
    """
    if conn is None:
        return default_connection
    if isinstance(conn, str):
        return connections[conn]
    if hasattr(conn, "cursor"):
        return conn
    raise ValueError("Unsupported connection object passed to exec_sql")

def exec_sql(conn: Optional[Union[str, object]],
             query: str,
             params: Optional[List[Any]] = None,
             fetch: bool = True,
             commit: bool = False,
             many: bool = False) -> Union[List[Dict[str, Any]], int, None]:
    """
    Execute raw SQL and return results.

    - If fetch=True: returns list of dict rows (column -> value).
    - If fetch=False: returns lastrowid (if available) or rowcount.
    """
    params = params or []
    db = _cursor_from_conn(conn)

    with contextlib.closing(db.cursor()) as cur:
        try:
            if many:
                cur.executemany(query, params)
            else:
                cur.execute(query, params)
        except Exception:
            logger.exception("exec_sql failed executing query: %s", query)
            raise

        # commit if requested (note: Django typically autocommits)
        if commit and hasattr(db, "commit"):
            try:
                db.commit()
            except Exception:
                logger.exception("exec_sql commit failed")

        if fetch:
            # if cursor.description is falsy, no rows to fetch
            if not cur.description:
                return []

            cols = [col[0] for col in cur.description]

            rows = cur.fetchall()

            result = []
            for row in rows:
                # Case 1: row is a mapping (dict-like)
                try:
                    # Many DB connectors return dict-like rows (e.g. DictCursor)
                    if hasattr(row, "keys"):
                        # mapping: use column names to fetch values
                        # Some mapping-like rows implement __getitem__ with column names
                        row_dict = {}
                        for c in cols:
                            # prefer direct key access; fallback to .get or attribute
                            if c in row:
                                row_dict[c] = row[c]
                            else:
                                # Some row objects require access by index
                                try:
                                    # get index of c
                                    idx = cols.index(c)
                                    row_dict[c] = row[idx]
                                except Exception:
                                    # last resort: None
                                    row_dict[c] = None
                        result.append(row_dict)
                        continue
                except Exception:
                    # fall through to sequence handling
                    pass

                # Case 2: row is sequence/tuple-like
                try:
                    row_seq = list(row)
                    row_dict = {cols[i]: row_seq[i] for i in range(len(cols))}
                    result.append(row_dict)
                except Exception:
                    # Case 3: object with attributes
                    row_dict = {}
                    for i, c in enumerate(cols):
                        row_dict[c] = getattr(row, c, None)
                    result.append(row_dict)

            return result
        else:
            # non-fetch: try lastrowid then rowcount
            lastrowid = getattr(cur, "lastrowid", None)
            if lastrowid:
                return lastrowid
            try:
                return cur.rowcount
            except Exception:
                return None


def get_tenant_work_types(request):
    """
    Get enabled work types for the current tenant.
    Returns a list of work type names that are enabled for the tenant.
    If no configuration exists, returns default work types.
    
    Args:
        request: Django HttpRequest object with session data
        
    Returns:
        list: List of enabled work type names (e.g., ['Task', 'Bug', 'Defect'])
    """
    default_work_types = ['Task', 'Bug', 'Story', 'Defect', 'Sub Task', 'Report', 'Change Request']
    
    try:
        # Get tenant configuration from session
        tenant_config = request.session.get("tenant_config")
        if not tenant_config or not isinstance(tenant_config, dict):
            return default_work_types
        
        tenant_id = tenant_config.get("tenant_id")
        if not tenant_id:
            return default_work_types
        
        # Connect to master_db to get work types configuration
        from django.conf import settings
        
        admin_conf = {
            'host': getattr(settings, 'MYSQL_ADMIN_HOST', '127.0.0.1'),
            'port': int(getattr(settings, 'MYSQL_ADMIN_PORT', 3306)),
            'user': getattr(settings, 'MYSQL_ADMIN_USER', 'root'),
            'password': getattr(settings, 'MYSQL_ADMIN_PWD', 'root'),
            'cursorclass': pymysql.cursors.DictCursor,
            'autocommit': True
        }
        
        admin_conn = pymysql.connect(**admin_conf)
        cur = admin_conn.cursor()
        
        # Query tenant_work_types table
        cur.execute("""
            SELECT work_type 
            FROM master_db.tenant_work_types 
            WHERE tenant_id = %s AND is_enabled = TRUE
            ORDER BY work_type
        """, (tenant_id,))
        
        rows = cur.fetchall()
        cur.close()
        admin_conn.close()
        
        if rows:
            # Return only enabled work types
            enabled_work_types = [row['work_type'] for row in rows]
            return enabled_work_types
        else:
            # No configuration found, return defaults
            return default_work_types
            
    except Exception as e:
        logger.error(f"Error getting tenant work types: {e}")
        # On error, return default work types
        return default_work_types
