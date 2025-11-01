# views.py
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from core.auth import identify_tenant_by_email, authenticate
from core.tenant_context import set_current_tenant, get_current_tenant
from core.db_connector import get_connection_from_config

def identify_view(request):
    if request.method == 'GET':
        return render(request, 'core/identify.html', {})
    email = request.POST.get('email','').strip()
    if not email or '@' not in email:
        return render(request, 'core/identify.html', {'error': 'Enter a valid email.'})
    tenant = identify_tenant_by_email(email)
    if not tenant:
        return render(request, 'core/identify.html', {'error': 'No tenant found for this email domain.'})
    # store tenant row (dict) in session
    request.session['tenant_config'] = {
        'db_engine': tenant.get('db_engine', 'mysql'),
        'db_name': tenant.get('db_name'),
        'db_host': tenant.get('db_host') or '127.0.0.1',
        'db_port': tenant.get('db_port') or 3306,
        'db_user': tenant.get('db_user'),
        'db_password': tenant.get('db_password'),
        'domain_postfix': tenant.get('domain_postfix')
    }
    request.session['ident_email'] = email
    return redirect('login_password')

def login_password_view(request):
    if request.method == 'GET':
        if not request.session.get('tenant_config') or not request.session.get('ident_email'):
            return redirect('identify')
        return render(request, 'core/login.html', {
            'email': request.session.get('ident_email'),
            'domain': request.session['tenant_config'].get('domain_postfix')
        })

    email = request.session.get('ident_email')
    tenant_conf = request.session.get('tenant_config')
    password = request.POST.get('password', '')

    if not email or not tenant_conf:
        return redirect('identify')

    try:
        user = authenticate(email, password, tenant_conf)
    except Exception as e:
        return render(request, 'core/login.html', {'email': email, 'error': 'Auth error: ' + str(e)})

    if not user:
        return render(request, 'core/login.html', {'email': email, 'error': 'Invalid credentials'})

    # ✅ Auth success
    request.session['user'] = user

    # ✅ Ensure tenant_config present
    request.session['tenant_config'] = tenant_conf
    set_current_tenant(tenant_conf)

    # ✅ Add explicit tenant connection info for db_helpers.py
    request.session['tenant_db_name'] = tenant_conf.get('db_name')
    request.session['tenant_db_user'] = tenant_conf.get('db_user')
    request.session['tenant_db_password'] = tenant_conf.get('db_password')
    request.session['tenant_db_host'] = tenant_conf.get('db_host', '127.0.0.1')
    request.session['tenant_db_port'] = tenant_conf.get('db_port', 3306)

    return redirect('dashboard')


def logout_view(request):
    request.session.flush()
    return redirect('identify')

from math import ceil
from django.shortcuts import render, redirect
from django.utils import timezone
from core.tenant_context import get_current_tenant
from core.db_connector import get_connection_from_config

def dashboard_view(request):
    """
    Dashboard for logged-in user (tenant-aware).
    Computes top metrics and chart data for the logged-in user.
    """
    tenant = get_current_tenant() or request.session.get('tenant_config')
    if not tenant:
        return redirect('identify')

    user = request.session.get('user')
    if not user:
        return redirect('login_password')

    # Open DB connection for current tenant
    conn = get_connection_from_config({
        'db_engine': tenant.get('db_engine','mysql'),
        'db_name': tenant.get('db_name'),
        'db_host': tenant.get('db_host'),
        'db_port': tenant.get('db_port'),
        'db_user': tenant.get('db_user'),
        'db_password': tenant.get('db_password')
    })
    cur = conn.cursor()

    # Helper to read scalar counts safely from dict or tuple rows
    def scalar_from_row(row, key_alias='c'):
        if row is None:
            return 0
        if isinstance(row, dict):
            # try both 'c' and first key
            return int(row.get(key_alias) or next(iter(row.values()), 0))
        if isinstance(row, (list, tuple)):
            return int(row[0]) if len(row) > 0 and row[0] is not None else 0
        return 0

    # 1) Total tasks assigned to this user
    assigned_count = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to = %s", (user['id'],))
        assigned_count = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        assigned_count = 0

    # 2) Active projects (start <= today AND (end IS NULL OR end >= today))
    active_projects = 0
    try:
        cur.execute("""
            SELECT COUNT(*) AS c FROM projects
            WHERE (start_date IS NULL OR start_date <= CURDATE())
              AND (end_date IS NULL OR end_date >= CURDATE())
        """)
        active_projects = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        active_projects = 0

    # 3) Tasks completed (for this user)
    tasks_completed = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND status = 'Closed'", (user['id'],))
        tasks_completed = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        tasks_completed = 0

    # 4) Tasks pending (for this user) -> any not Closed
    tasks_pending = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND NOT (status = 'Closed')", (user['id'],))
        tasks_pending = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        tasks_pending = 0

    # Chart #1: task distribution by logical groups (Completed, In Progress, Pending)
    # Map statuses to the 3 groups:
    # - Completed: status='Closed'
    # - In Progress: status IN ('In Progress','Review')
    # - Pending: status IN ('Open','Blocked') and others
    progress_completed = progress_inprogress = progress_pending = 0
    try:
        cur.execute("""
            SELECT status, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            GROUP BY status
        """, (user['id'],))
        rows = cur.fetchall() or []
        # rows may be dicts or tuples
        if rows:
            # unify iteration
            if isinstance(rows[0], dict):
                items = [(r.get('status'), int(r.get('c') or 0)) for r in rows]
            else:
                # assume tuple (status, c)
                items = [(r[0], int(r[1] or 0)) for r in rows]
            for status, cnt in items:
                s = (status or '').lower()
                if s == 'closed':
                    progress_completed += cnt
                elif s in ('in progress', 'review', 'in-progress'):
                    progress_inprogress += cnt
                else:
                    # Open, Blocked, or other
                    progress_pending += cnt
    except Exception:
        progress_completed = progress_inprogress = progress_pending = 0

    # Chart #2: tasks by priority (Critical, High, Normal, Low)
    priority_buckets = {'Critical': 0, 'High': 0, 'Normal': 0, 'Low': 0}
    try:
        cur.execute("""
            SELECT COALESCE(priority,'Normal') AS p, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            GROUP BY p
        """, (user['id'],))
        rows = cur.fetchall() or []
        if rows:
            if isinstance(rows[0], dict):
                items = [(r.get('p'), int(r.get('c') or 0)) for r in rows]
            else:
                items = [(r[0], int(r[1] or 0)) for r in rows]
            for p, cnt in items:
                key = (p or 'Normal').title()
                if key not in priority_buckets:
                    priority_buckets[key] = cnt
                else:
                    priority_buckets[key] = cnt
    except Exception:
        pass

    # Close DB
    cur.close()
    conn.close()

    # Prepare context for template
    ctx = {
        'user': user,
        'assigned_count': assigned_count,
        'active_projects': active_projects,
        'tasks_completed': tasks_completed,
        'tasks_pending': tasks_pending,
        # donut chart values
        'progress_completed': progress_completed,
        'progress_inprogress': progress_inprogress,
        'progress_pending': progress_pending,
        # priority bars
        'pri_critical': priority_buckets.get('Critical', 0),
        'pri_high': priority_buckets.get('High', 0),
        'pri_normal': priority_buckets.get('Normal', 0),
        'pri_low': priority_buckets.get('Low', 0),
    }

    return render(request, 'core/dashboard.html', ctx)

