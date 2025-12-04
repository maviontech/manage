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
    member_id = None
    member_name = user_fullname
    try:
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        # Find or create member row
        cur.execute("SELECT id, first_name, last_name FROM members WHERE email=%s LIMIT 1", (email,))
        r = cur.fetchone()
        if r:
            # Dict or tuple
            if isinstance(r, dict):
                member_id = int(r['id'])
                member_name = (r.get('first_name', '') + ' ' + r.get('last_name', '')).strip() or user_fullname
            else:
                member_id = int(r[0])
                member_name = (r[1] + ' ' + r[2]).strip() or user_fullname
        else:
            # Create member row
            first_name = user_fullname.split()[0] if user_fullname else email.split('@')[0]
            last_name = user_fullname.split()[-1] if user_fullname and len(user_fullname.split()) > 1 else ''
            cur.execute("""
                INSERT INTO members (email, first_name, last_name, phone, meta, created_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (email, first_name, last_name, None, None, None, timezone.now()))
            member_id = cur.lastrowid
            member_name = (first_name + ' ' + last_name).strip()
        cur.close()
        conn.close()
    except Exception as ex:
        print("ensure_member_and_set_session failed:", ex)
        member_id = None

    # save canonical id and display name to session
    request.session['member_id'] = member_id
    request.session['member_name'] = member_name
    request.session['user_id'] = member_id  # Ensure user_id is set for task views
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


    # Use member_id from session for all queries
    member_id = request.session.get('member_id')
    if not member_id:
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

    def scalar_from_row(row, key_alias='c'):
        if row is None:
            return 0
        if isinstance(row, dict):
            return int(row.get(key_alias) or next(iter(row.values()), 0))
        if isinstance(row, (list, tuple)):
            return int(row[0]) if len(row) > 0 and row[0] is not None else 0
        return 0

    assigned_count = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to = %s", (member_id,))
        assigned_count = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        assigned_count = 0

    active_projects = 0
    try:
        cur.execute("""
            SELECT COUNT(*) AS c
            FROM projects
            WHERE status = 'Active'
        """)
        active_projects = scalar_from_row(cur.fetchone(), 'c')
    except Exception as e:
        print("ERROR active_projects:", e)
        active_projects = 0

    projects_completed = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM projects WHERE status='Completed' AND (owner_id=%s OR members LIKE CONCAT('%', %s, '%'))", (member_id, member_id))
        projects_completed = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        projects_completed = 0

    tasks_completed = 0
    try:
        cur.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND status = 'Closed'",
            (member_id,))
        tasks_completed = scalar_from_row(cur.fetchone(), 'c')
    except Exception:
        tasks_completed = 0

    tasks_pending = 0
    try:
        cur.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND NOT (status = 'Closed')",
            (member_id,))
        tasks_pending = scalar_from_row(cur.fetchone(), 'c')
    except Exception as e:
        print("ERROR tasks_pending:", e)
        tasks_pending = 0

    progress_completed = progress_inprogress = progress_pending = 0
    try:
        cur.execute("""
            SELECT status, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            GROUP BY status
        """, (member_id,))
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

    priority_buckets = {'Critical': 0, 'High': 0, 'Normal': 0, 'Low': 0}
    try:
        cur.execute("""
            SELECT COALESCE(priority,'Normal') AS p, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            GROUP BY p
        """, (member_id,))
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

    pri_keys = ['Critical', 'High', 'Normal', 'Low']
    pri_open = {k: 0 for k in pri_keys}
    pri_closed = {k: 0 for k in pri_keys}
    try:
        cur.execute("""
            SELECT COALESCE(priority,'Normal') AS p, status, COUNT(*) AS c
            FROM tasks
            WHERE assigned_type='member' AND assigned_to = %s
            GROUP BY p, status
        """, (member_id,))
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
        pass

    is_team_lead = False
    try:
        cur.execute("SELECT 1 FROM teams WHERE lead_id = %s LIMIT 1", (member_id,))
        row = cur.fetchone()
        if row:
            is_team_lead = True
    except Exception:
        is_team_lead = False

    # Board open count: tasks assigned to user and not closed (for board view)
    board_open_count = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND NOT (status = 'Closed')", (member_id,))
        board_open_count = scalar_from_row(cur.fetchone(), 'c')
        print("DEBUG: board_open_count =", board_open_count)
    except Exception as e:
        print("ERROR: board_open_count", e)
        board_open_count = 0

    # My new tasks count: tasks assigned to user and status is 'New' (or similar)
    my_new_tasks_count = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_type='member' AND assigned_to=%s AND status = 'New'", (member_id,))
        my_new_tasks_count = scalar_from_row(cur.fetchone(), 'c')
        print("DEBUG: my_new_tasks_count =", my_new_tasks_count)
    except Exception as e:
        print("ERROR: my_new_tasks_count", e)
        my_new_tasks_count = 0

    cur.close()
    conn.close()

    ctx = {
        'user': request.session.get('user'),
        'assigned_count': assigned_count,
        'active_projects': active_projects,
        'projects_completed': projects_completed,
        'tasks_completed': tasks_completed,
        'tasks_pending': tasks_pending,
        'progress_completed': progress_completed,
        'progress_inprogress': progress_inprogress,
        'progress_pending': progress_pending,
        'pri_critical': priority_buckets.get('Critical', 0),
        'pri_high': priority_buckets.get('High', 0),
        'pri_normal': priority_buckets.get('Normal', 0),
        'pri_low': priority_buckets.get('Low', 0),
        'pri_critical_open': pri_open.get('Critical', 0),
        'pri_high_open': pri_open.get('High', 0),
        'pri_normal_open': pri_open.get('Normal', 0),
        'pri_low_open': pri_open.get('Low', 0),
        'pri_critical_closed': pri_closed.get('Critical', 0),
        'pri_high_closed': pri_closed.get('High', 0),
        'pri_normal_closed': pri_closed.get('Normal', 0),
        'pri_low_closed': pri_closed.get('Low', 0),
        'is_team_lead': is_team_lead,
        'board_open_count': board_open_count,
        'my_new_tasks_count': my_new_tasks_count,
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

def profile_view(request):
    """
    Display the profile of the logged-in user.
    """
    user = request.session.get('user')
    if not user:
        return redirect('login_password')

    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    profile = {}
    try:
        cur.execute("SELECT email, first_name, last_name, phone, meta, created_at FROM members WHERE id=%s LIMIT 1", (member_id,))
        row = cur.fetchone()
        if row:
            if isinstance(row, dict):
                profile = {
                    'email': row.get('email'),
                    'first_name': row.get('first_name'),
                    'last_name': row.get('last_name'),
                    'phone': row.get('phone'),
                    'meta': row.get('meta'),
                    'created_at': row.get('created_at'),
                }
            else:
                profile = {
                    'email': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'phone': row[3],
                    'meta': row[4],
                    'created_at': row[5],
                }
    except Exception:
        profile = {}
    finally:
        cur.close()
        conn.close()

    return render(request, 'core/profile_view.html', {'profile': profile})
def profile_edit_view(request):
    """Display the profile edit form and handle profile updates."""
    user = request.session.get('user')
    member_id = request.session.get('member_id')

    if not user or not member_id:
        return redirect('login_password')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    error_msg = None

    # ---------------------- POST: Save Updates ----------------------
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        meta = request.POST.get('meta', '').strip()

        try:
            cur.execute("""
                UPDATE members
                SET first_name=%s, last_name=%s, phone=%s, meta=%s
                WHERE id=%s
            """, (first_name, last_name, phone, meta, member_id))
            conn.commit()

            return redirect('profile_view')

        except Exception as e:
            conn.rollback()
            error_msg = f"Update failed: {str(e)}"

    # ---------------------- GET: Fetch Profile Data ----------------------
    profile = {}
    try:
        cur.execute("""
            SELECT email, first_name, last_name, phone, meta
            FROM members
            WHERE id=%s
            LIMIT 1
        """, (member_id,))
        row = cur.fetchone()

        if row:
            # If row is a dict-like cursor result
            if isinstance(row, dict):
                profile = {
                    'email': row.get('email'),
                    'first_name': row.get('first_name'),
                    'last_name': row.get('last_name'),
                    'phone': row.get('phone'),
                    'meta': row.get('meta'),
                }
            else:
                # Row is a tuple
                profile = {
                    'email': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'phone': row[3],
                    'meta': row[4],
                }

    except Exception as e:
        error_msg = f"Error loading profile: {str(e)}"

    finally:
        cur.close()
        conn.close()

    # ---------------------- RENDER PAGE ----------------------
    return render(request, 'core/profile_edit.html', {
        'profile': profile,
        'error': error_msg
    })

def profile_change_password_view(request):
    """ Allow the user to change their password. """
    user = request.session.get('user')
    if not user:
        return redirect('login_password')

    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if new_password != confirm_password:
            error_msg = "New password and confirmation do not match."
        else:
            # Verify current password
            email = user.get('email')
            tenant_conf = request.session.get('tenant_config')
            try:
                auth_user = authenticate(email, current_password, tenant_conf)
                if not auth_user:
                    error_msg = "Current password is incorrect."
                else:
                    # Update password in the users table
                    conn = get_tenant_conn(request)
                    cur = conn.cursor()
                    try:
                        cur.execute("UPDATE users SET password=%s WHERE email=%s", (new_password, email))
                        conn.commit()
                        return redirect('profile_view')
                    except Exception as e:
                        conn.rollback()
                        error_msg = "Failed to update password: " + str(e)
                    finally:
                        cur.close()
                        conn.close()
            except Exception as e:
                error_msg = "Authentication error: " + str(e)
    else:
        error_msg = None

    return render(request, 'core/profile_change_password.html', {'error': error_msg})
