# views.py
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from .auth import identify_tenant_by_email, authenticate
from .db_connector import get_connection_from_config
from math import ceil
from django.shortcuts import render, redirect
from django.utils import timezone
from .tenant_context import get_current_tenant , set_current_tenant
from .db_helpers import get_tenant_conn
from math import ceil
from django.shortcuts import render, redirect
from django.utils import timezone

# Adjust these imports to match your project utilities (names used earlier in this project)


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

from django.shortcuts import render, redirect
from django.utils import timezone
from django.http import HttpResponseForbidden


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

    # ✅ Auth success — store user in session (keep what you already did)
    request.session['user'] = user
    print("Authenticated user:", user)
    request.session['tenant_config'] = tenant_conf
    set_current_tenant(tenant_conf)
    print("User authenticated:", email)

    # --- Determine a sensible full name for the user ---
    user_fullname = None

    # 1) If authenticate() returned a dict-like or object with full_name, use it
    try:
        # dict-like
        if isinstance(user, dict):
            user_fullname = user.get('full_name') or user.get('fullname') or user.get('name')
        else:
            # object-like
            user_fullname = getattr(user, 'full_name', None) or getattr(user, 'fullname', None) or getattr(user, 'name', None)
    except Exception:
        user_fullname = None

    # 2) If still None, try to query tenant users table for full_name
    if not user_fullname:
        try:
            # get a tenant DB connection (use your project's connector)
            conn = get_tenant_conn(request)
            cur = conn.cursor()
            # assumes the tenant 'users' table has 'email' and 'full_name'
            cur.execute("SELECT full_name FROM users WHERE email=%s LIMIT 1", (email,))
            row = cur.fetchone()
            if row:
                # row may be dict or tuple depending on cursorclass
                if isinstance(row, dict):
                    user_fullname = row.get('full_name') or row.get('fullname')
                else:
                    user_fullname = row[0]
            cur.close()
            conn.close()
        except Exception:
            user_fullname = None

    # 3) Fallback: use the email local-part
    if not user_fullname:
        user_fullname = email.split('@', 1)[0]

    # Ensure the members table has an entry and set the session member_id
    try:
        ensure_member_and_set_session(request, email, user_fullname, created_by=None)
    except Exception as ex:
        # log error (print for now) and continue — we still want to set DB connection details
        print("ensure_member_and_set_session failed:", ex)
    # prefer an explicit member identifier in session (email preferred)
    # if your 'user' object/dict contains emp_code you can prefer it, but email is simplest
    member_id = None
    if isinstance(user, dict):
        member_id = user.get('email') or user.get('emp_code') or request.session.get('ident_email')
    else:
        member_id = getattr(user, 'email', None) or getattr(user, 'emp_code', None) or request.session.get(
            'ident_email')

    member_id = str(member_id or request.session.get('ident_email') or '').strip()
    member_name = user_fullname or request.session.get('cn') or member_id

    # save canonical id and display name to session
    request.session['member_id'] = member_id
    request.session['member_name'] = member_name
    print("Login successful for user:", member_id)
    print("Login successful for user:", member_name)

    # Add explicit tenant DB credentials to session for your db_helpers
    request.session['tenant_db_name'] = tenant_conf.get('db_name')
    request.session['tenant_db_user'] = tenant_conf.get('db_user')
    request.session['tenant_db_password'] = tenant_conf.get('db_password')
    request.session['tenant_db_host'] = tenant_conf.get('db_host', '127.0.0.1')
    request.session['tenant_db_port'] = tenant_conf.get('db_port', 3306)



    return redirect('dashboard')


# inside your login view, after successful auth
# ------------------------------------------------
# ensure member record exists and set request.session['member_id']
from django.utils import timezone

def ensure_member_and_set_session(request, user_email, user_fullname=None, created_by=None):
    """
    Ensure a row exists in members for this user_email, create if missing, and set session['member_id'].
    Uses raw SQL and your tenant DB connection.
    """
    conn = get_tenant_conn(request)   # <-- use your project's tenant connector
    cur = conn.cursor()
    try:
        # 1) find existing member
        cur.execute("SELECT id FROM members WHERE email=%s LIMIT 1", (user_email,))
        r = cur.fetchone()
        if r and r.get('id'):
            member_id = int(r['id'])
        else:
            # 2) create members row using full name split if provided
            first_name = None
            last_name = None
            if user_fullname:
                # basic split (first token / last token)
                parts = user_fullname.strip().split()
                first_name = parts[0] if parts else user_fullname
                last_name = parts[-1] if len(parts) > 1 else ''
            else:
                first_name = user_email.split('@')[0]
                last_name = ''

            cur.execute("""
                INSERT INTO members (email, first_name, last_name, phone, meta, created_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (user_email, first_name, last_name, None, None, created_by, timezone.now()))
            member_id = cur.lastrowid

        # 3) set session
        request.session['member_id'] = int(member_id)

        # Optionally set a human display name (`cn`) used across your templates
        if user_fullname:
            request.session['cn'] = user_fullname
        else:
            # fallback to members table name
            cur.execute("SELECT CONCAT(COALESCE(first_name,''), ' ', COALESCE(last_name,'')) AS cn FROM members WHERE id=%s", (member_id,))
            rr = cur.fetchone()
            if rr and rr.get('cn'):
                request.session['cn'] = rr['cn']

    finally:
        cur.close()
        conn.close()


def logout_view(request):
    request.session.flush()
    return redirect('identify')



# If your project uses get_tenant_conn(request) instead, swap usage accordingly.

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

    # Open DB connection for current tenant (adapt function name if needed)
    conn = get_connection_from_config({
        'db_engine': tenant.get('db_engine', 'mysql'),
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
        cur.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND status = 'Closed'",
            (user['id'],))
        tasks_completed = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        tasks_completed = 0

    # 4) Tasks pending (for this user) -> any not Closed
    tasks_pending = 0
    try:
        cur.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND NOT (status = 'Closed')",
            (user['id'],))
        tasks_pending = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        tasks_pending = 0

    # Chart #1: task distribution by logical groups (Completed, In Progress, Pending)
    progress_completed = progress_inprogress = progress_pending = 0
    try:
        cur.execute("""
            SELECT status, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            GROUP BY status
        """, (user['id'],))
        rows = cur.fetchall() or []
        if rows:
            if isinstance(rows[0], dict):
                items = [(r.get('status'), int(r.get('c') or 0)) for r in rows]
            else:
                items = [(r[0], int(r[1] or 0)) for r in rows]
            for status, cnt in items:
                s = (status or '').lower()
                if s == 'closed':
                    progress_completed += cnt
                elif s in ('in progress', 'review', 'in-progress'):
                    progress_inprogress += cnt
                else:
                    progress_pending += cnt
    except Exception:
        progress_completed = progress_inprogress = progress_pending = 0

    # Chart #2: tasks by priority (flat counts)
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
                priority_buckets[key] = cnt
    except Exception:
        pass

    # --- NEW: compute per-priority open vs closed (for stacked bars) ---
    pri_keys = ['Critical', 'High', 'Normal', 'Low']
    pri_open = {k: 0 for k in pri_keys}
    pri_closed = {k: 0 for k in pri_keys}
    try:
        cur.execute("""
            SELECT COALESCE(priority,'Normal') AS p, status, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to = %s
            GROUP BY p, status
        """, (user['id'],))
        rows = cur.fetchall() or []
        if rows:
            if isinstance(rows[0], dict):
                for r in rows:
                    p = (r.get('p') or 'Normal').title()
                    st = (r.get('status') or '').lower()
                    cnt = int(r.get('c') or 0)
                    if st == 'closed':
                        pri_closed[p] = pri_closed.get(p, 0) + cnt
                    else:
                        pri_open[p] = pri_open.get(p, 0) + cnt
            else:
                for r in rows:
                    p = (r[0] or 'Normal').title()
                    st = (r[1] or '').lower()
                    cnt = int(r[2] or 0)
                    if st == 'closed':
                        pri_closed[p] = pri_closed.get(p, 0) + cnt
                    else:
                        pri_open[p] = pri_open.get(p, 0) + cnt
    except Exception:
        # keep defaults
        pass

    # ---- determine if logged-in user is a team lead (so UI can show Team View) ----
    is_team_lead = False
    try:
        cur.execute("SELECT 1 FROM teams WHERE lead_id = %s LIMIT 1", (user['id'],))
        row = cur.fetchone()
        if row:
            is_team_lead = True
    except Exception:
        is_team_lead = False

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
        # priority flat counts
        'pri_critical': priority_buckets.get('Critical', 0),
        'pri_high': priority_buckets.get('High', 0),
        'pri_normal': priority_buckets.get('Normal', 0),
        'pri_low': priority_buckets.get('Low', 0),
        # priority open/closed for stacked chart
        'pri_critical_open': pri_open.get('Critical', 0),
        'pri_high_open': pri_open.get('High', 0),
        'pri_normal_open': pri_open.get('Normal', 0),
        'pri_low_open': pri_open.get('Low', 0),
        'pri_critical_closed': pri_closed.get('Critical', 0),
        'pri_high_closed': pri_closed.get('High', 0),
        'pri_normal_closed': pri_closed.get('Normal', 0),
        'pri_low_closed': pri_closed.get('Low', 0),
        # team lead flag
        'is_team_lead': is_team_lead,
    }

    return render(request, 'core/dashboard.html', ctx)


from django.http import JsonResponse, HttpResponseBadRequest
from math import ceil

def _scalar_from_row(row, alias=None):
    if row is None:
        return 0
    if isinstance(row, dict):
        if alias and alias in row:
            return int(row.get(alias) or 0)
        # fallback: first value
        return int(next(iter(row.values()), 0) or 0)
    if isinstance(row, (list, tuple)):
        return int(row[0] or 0)
    return 0

def api_team_list(request):
    """
    Return teams the logged-in user leads (or belongs to).
    Response: { teams: [{id, name}, ...] }
    """
    user = request.session.get('user')
    if not user:
        return JsonResponse({'teams': []})
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    teams = []
    try:
        # Try: a common pattern where teams have a 'lead_id' column
        cur.execute("SELECT id, name FROM teams WHERE lead_id = %s", (user['id'],))
        rows = cur.fetchall() or []
        if rows:
            if isinstance(rows[0], dict):
                teams = [{'id': r['id'], 'name': r.get('name')} for r in rows]
            else:
                teams = [{'id': r[0], 'name': r[1]} for r in rows]
        else:
            # fallback: teams where user is member (team_members table)
            cur.execute("""
                SELECT t.id, t.name
                FROM teams t
                JOIN team_members tm ON tm.team_id = t.id
                WHERE tm.member_id = %s
            """, (user['id'],))
            rows = cur.fetchall() or []
            if rows:
                if isinstance(rows[0], dict):
                    teams = [{'id': r['id'], 'name': r.get('name')} for r in rows]
                else:
                    teams = [{'id': r[0], 'name': r[1]} for r in rows]
    except Exception:
        teams = []
    finally:
        cur.close()
        conn.close()
    return JsonResponse({'teams': teams})


def api_team_summary(request):
    """
    Returns team summary for the given team_id.
    Query: ?team_id=ID
    Response:
    {
      members: [{ id, name, assigned_count, completed, pending, priorities: {Critical,High,Normal,Low} }, ...],
      totals: { completed, inprogress, pending, priorities: {Critical_open, Critical_closed, ... } }
    }
    """
    team_id = request.GET.get('team_id')
    if not team_id:
        return HttpResponseBadRequest("team_id required")

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    # First: try to fetch members for the given team
    members = []
    try:
        # Preferred: a team_members table
        cur.execute("SELECT m.id, CONCAT(m.first_name, ' ', m.last_name) AS name, m.email FROM members m JOIN team_members tm ON tm.member_id = m.id WHERE tm.team_id = %s", (team_id,))
        rows = cur.fetchall() or []
        if rows:
            if isinstance(rows[0], dict):
                members = [{'id': r['id'], 'name': r.get('name') or r.get('email')} for r in rows]
            else:
                members = [{'id': r[0], 'name': r[1] or r[2]} for r in rows]
        else:
            # fallback: members.team_id
            cur.execute("SELECT id, CONCAT(first_name,' ',last_name) AS name, email FROM members WHERE team_id = %s", (team_id,))
            rows = cur.fetchall() or []
            if rows:
                if isinstance(rows[0], dict):
                    members = [{'id': r['id'], 'name': r.get('name') or r.get('email')} for r in rows]
                else:
                    members = [{'id': r[0], 'name': r[1] or r[2]} for r in rows]
    except Exception:
        members = []
    # If still empty: return early
    if not members:
        cur.close()
        conn.close()
        return JsonResponse({'members': [], 'totals': {}})

    # For each member, compute assigned_count, completed, pending and priority buckets
    member_summaries = []
    # accumulate team totals
    totals = {'completed': 0, 'inprogress': 0, 'pending': 0, 'priorities': {}}
    # prepare priority totals open/closed buckets
    pri_keys = ['Critical','High','Normal','Low']
    for pk in pri_keys:
        totals['priorities'][f'{pk}_open'] = 0
        totals['priorities'][f'{pk}_closed'] = 0

    for m in members:
        mid = m['id']
        # counts: assigned total, completed, pending
        try:
            cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to = %s", (mid,))
            assigned = _scalar_from_row(cur.fetchone(), 'c')
            cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to = %s AND status = 'Closed'", (mid,))
            completed = _scalar_from_row(cur.fetchone(), 'c')
            cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to = %s AND NOT (status = 'Closed')", (mid,))
            pending = _scalar_from_row(cur.fetchone(), 'c')
        except Exception:
            assigned = completed = pending = 0

        # priorities per member (flat counts)
        try:
            cur.execute("""
                SELECT COALESCE(priority,'Normal') AS p, status, COUNT(*) AS c
                FROM tasks
                WHERE assigned_type='member' AND assigned_to = %s
                GROUP BY p, status
            """, (mid,))
            rows = cur.fetchall() or []
            # build dict priorities
            pmap = {'Critical':0,'High':0,'Normal':0,'Low':0}
            if rows:
                if isinstance(rows[0], dict):
                    for r in rows:
                        p = (r.get('p') or 'Normal').title()
                        st = (r.get('status') or '').lower()
                        cnt = int(r.get('c') or 0)
                        if p not in pmap: pmap[p] = 0
                        pmap[p] += cnt
                        # update totals open/closed
                        if st == 'closed':
                            totals['priorities'].setdefault(f'{p}_closed',0)
                            totals['priorities'][f'{p}_closed'] += cnt
                        else:
                            totals['priorities'].setdefault(f'{p}_open',0)
                            totals['priorities'][f'{p}_open'] += cnt
                else:
                    for r in rows:
                        p = (r[0] or 'Normal').title()
                        st = (r[1] or '').lower()
                        cnt = int(r[2] or 0)
                        if p not in pmap: pmap[p] = 0
                        pmap[p] += cnt
                        if st == 'closed':
                            totals['priorities'].setdefault(f'{p}_closed',0)
                            totals['priorities'][f'{p}_closed'] += cnt
                        else:
                            totals['priorities'].setdefault(f'{p}_open',0)
                            totals['priorities'][f'{p}_open'] += cnt
        except Exception:
            pmap = {'Critical':0,'High':0,'Normal':0,'Low':0}

        member_summaries.append({
            'id': mid,
            'name': m.get('name'),
            'assigned_count': assigned,
            'completed': completed,
            'pending': pending,
            'priorities': pmap
        })

        totals['completed'] += completed
        totals['inprogress'] += 0  # inprogress can be calculated if you want more granularity
        totals['pending'] += pending

    # If totals priorities not filled for any key, ensure keys exist
    for pk in pri_keys:
        totals['priorities'].setdefault(f'{pk}_open', 0)
        totals['priorities'].setdefault(f'{pk}_closed', 0)

    cur.close()
    conn.close()
    return JsonResponse({'members': member_summaries, 'totals': totals})

