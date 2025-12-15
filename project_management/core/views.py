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

# Import Excel export function
from .views_export import export_projects_excel

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
    except Exception as e:
        print("ERROR: board_open_count", e)
        board_open_count = 0

    # My new tasks count: tasks assigned to user and status is 'New' (or similar)
    my_new_tasks_count = 0
    try:
        cur.execute("SELECT COUNT(*) FROM TASKS")
        my_new_tasks_count = scalar_from_row(cur.fetchone(), 'c')
    except Exception as e:
        print("ERROR: my_new_tasks_count", e)
        my_new_tasks_count = 0

    # ---------------------- PLANNED TASKS (Show all pending tasks) ----------------------
    from datetime import datetime, timedelta
    import json
    planned_tasks = []
    try:
        # Show all tasks that are not completed or closed
        # This includes overdue tasks and upcoming tasks
        cur.execute("""
            SELECT id, title, status, due_date, created_at
            FROM tasks
            WHERE assigned_type='member' AND assigned_to=%s
            AND status NOT IN ('Completed', 'Closed', 'completed', 'closed')
            AND due_date IS NOT NULL
            ORDER BY due_date ASC
            LIMIT 10
        """, (member_id,))
        rows = cur.fetchall() or []
        print(f"DEBUG: planned_tasks found {len(rows)} pending tasks for member_id={member_id}")
        
        for r in rows:
            if isinstance(r, dict):
                planned_tasks.append({
                    'id': r.get('id'),
                    'title': r.get('title'),
                    'status': r.get('status'),
                    'due_date': r.get('due_date'),
                })
            else:
                planned_tasks.append({
                    'id': r[0],
                    'title': r[1],
                    'status': r[2],
                    'due_date': r[3],
                })
    except Exception as e:
        print("ERROR: planned_tasks", e)
        import traceback
        traceback.print_exc()
        planned_tasks = []

    # ---------------------- LINE CHART DATA (Tasks created/completed last 7 days) ----------------------
    line_chart_labels = []
    line_chart_created = []
    line_chart_completed = []
    try:
        today = datetime.now().date()
        # Get day names for last 7 days
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            line_chart_labels.append(day_names[day.weekday()])
            
            # Count tasks created on this day
            cur.execute("""
                SELECT COUNT(*) as cnt FROM tasks 
                WHERE assigned_type='member' AND assigned_to=%s 
                AND DATE(created_at) = %s
            """, (member_id, day))
            created_row = cur.fetchone()
            if created_row:
                if isinstance(created_row, dict):
                    line_chart_created.append(created_row.get('cnt', 0) or 0)
                else:
                    line_chart_created.append(created_row[0] or 0)
            else:
                line_chart_created.append(0)
            
            # Count tasks completed on this day
            cur.execute("""
                SELECT COUNT(*) as cnt FROM tasks 
                WHERE assigned_type='member' AND assigned_to=%s 
                AND status='Completed' AND DATE(updated_at) = %s
            """, (member_id, day))
            completed_row = cur.fetchone()
            if completed_row:
                if isinstance(completed_row, dict):
                    line_chart_completed.append(completed_row.get('cnt', 0) or 0)
                else:
                    line_chart_completed.append(completed_row[0] or 0)
            else:
                line_chart_completed.append(0)
    except Exception as e:
        print("ERROR: line_chart_data", e)
        line_chart_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        line_chart_created = [0, 0, 0, 0, 0, 0, 0]
        line_chart_completed = [0, 0, 0, 0, 0, 0, 0]

        
    



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
        'planned_tasks': planned_tasks,
        'line_chart_labels': json.dumps(line_chart_labels),
        'line_chart_created': json.dumps(line_chart_created),
        'line_chart_completed': json.dumps(line_chart_completed),
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

def api_get_team_members(request):
    """
    Returns team members for a given team_id.
    Query: ?team_id=ID
    Response: { members: [{id, first_name, last_name, email, phone}, ...] }
    """
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated', 'members': []}, status=401)
    
    team_id = request.GET.get('team_id')
    if not team_id:
        return JsonResponse({'error': 'team_id required', 'members': []}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    members = []
    
    try:
        # Try team_members table first (preferred approach)
        cur.execute("""
            SELECT m.id, m.first_name, m.last_name, m.email, m.phone
            FROM members m
            JOIN team_members tm ON tm.member_id = m.id
            WHERE tm.team_id = %s
            ORDER BY m.first_name, m.last_name
        """, (team_id,))
        rows = cur.fetchall() or []
        
        if not rows:
            # Fallback: check if members table has team_id column
            cur.execute("""
                SELECT id, first_name, last_name, email, phone
                FROM members
                WHERE team_id = %s
                ORDER BY first_name, last_name
            """, (team_id,))
            rows = cur.fetchall() or []
        
        if rows:
            if isinstance(rows[0], dict):
                members = [{
                    'id': r['id'],
                    'first_name': r.get('first_name', ''),
                    'last_name': r.get('last_name', ''),
                    'email': r.get('email', ''),
                    'phone': r.get('phone', '')
                } for r in rows]
            else:
                members = [{
                    'id': r[0],
                    'first_name': r[1] or '',
                    'last_name': r[2] or '',
                    'email': r[3] or '',
                    'phone': r[4] or ''
                } for r in rows]
    except Exception as e:
        print(f"Error fetching team members: {e}")
        members = []
    finally:
        cur.close()
        conn.close()
    
    return JsonResponse({'members': members})

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
    social_links = {}
    try:
        cur.execute("SELECT email, first_name, last_name, phone, meta, created_at, city, dob, address, profile_photo FROM members WHERE id=%s LIMIT 1", (member_id,))
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
                    'city': row.get('city'),
                    'dob': row.get('dob'),  
                    'address': row.get('address'),
                    'profile_photo': row.get('profile_photo'),
                }
            else:
                profile = {
                    'email': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'phone': row[3],
                    'meta': row[4],
                    'created_at': row[5],
                    'city': row[6],
                    'dob': row[7],
                    'address': row[8],
                    'profile_photo': row[9] if len(row) > 9 else None,
                }
        # Fetch social links
        cur.execute("SELECT github_url, twitter_url, facebook_url, linkedin_url FROM member_social_links WHERE member_id=%s LIMIT 1", (member_id,))
        social_row = cur.fetchone()
        if social_row:
            if isinstance(social_row, dict):
                social_links = {
                    'github_url': social_row.get('github_url', ''),
                    'twitter_url': social_row.get('twitter_url', ''),
                    'facebook_url': social_row.get('facebook_url', ''),
                    'linkedin_url': social_row.get('linkedin_url', ''),
                }
            else:
                social_links = {
                    'github_url': social_row[0],
                    'twitter_url': social_row[1],
                    'facebook_url': social_row[2],
                    'linkedin_url': social_row[3],
                }
    except Exception:
        profile = {}
        social_links = {}
    finally:
        cur.close()
        conn.close()

    return render(request, 'core/profile_view.html', {'profile': profile, 'social_links': social_links})
def profile_edit_view(request):
    """Display the profile edit form and handle profile updates."""
    import os
    from django.conf import settings
    
    user = request.session.get('user')
    member_id = request.session.get('member_id')

    if not user or not member_id:
        return redirect('login_password')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    error_msg = None

    # ---------------------- POST: Save Updates ----------------------
    import json
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        meta = json.dumps(request.POST.get('meta', '').strip())
        city = request.POST.get('city', '').strip()
        dob = request.POST.get('dob', '').strip() or None
        address = request.POST.get('address', '').strip()
        github_url = request.POST.get('github_url', '').strip()
        twitter_url = request.POST.get('twitter_url', '').strip()
        facebook_url = request.POST.get('facebook_url', '').strip()
        linkedin_url = request.POST.get('linkedin_url', '').strip()
        
        # Handle profile photo upload
        profile_photo_path = None
        if 'profile_photo' in request.FILES:
            photo = request.FILES['profile_photo']
            # Create directory if it doesn't exist
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'profile_photos')
            os.makedirs(upload_dir, exist_ok=True)
            # Generate unique filename
            file_ext = os.path.splitext(photo.name)[1]
            filename = f"member_{member_id}{file_ext}"
            file_path = os.path.join(upload_dir, filename)
            # Save file
            with open(file_path, 'wb+') as destination:
                for chunk in photo.chunks():
                    destination.write(chunk)
            profile_photo_path = f"profile_photos/{filename}"

        try:
            # Update member info
            if profile_photo_path:
                cur.execute("""
                    UPDATE members
                    SET first_name=%s, last_name=%s, phone=%s, meta=%s, city=%s, dob=%s, address=%s, profile_photo=%s
                    WHERE id=%s
                """, (first_name, last_name, phone, meta, city, dob, address, profile_photo_path, member_id))
            else:
                cur.execute("""
                    UPDATE members
                    SET first_name=%s, last_name=%s, phone=%s, meta=%s, city=%s, dob=%s, address=%s
                    WHERE id=%s
                """, (first_name, last_name, phone, meta, city, dob, address, member_id))
            # Upsert social links
            cur.execute("""
                INSERT INTO member_social_links (member_id, github_url, twitter_url, facebook_url, linkedin_url)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    github_url=VALUES(github_url),
                    twitter_url=VALUES(twitter_url),
                    facebook_url=VALUES(facebook_url),
                    linkedin_url=VALUES(linkedin_url)
            """, (member_id, github_url, twitter_url, facebook_url, linkedin_url))
            conn.commit()
            return redirect('profile')
        except Exception as e:
            conn.rollback()
            print("Profile update failed:", e)  # Debug print
            error_msg = f"Update failed: {str(e)}"

    # ---------------------- GET: Fetch Profile Data ----------------------
    profile = {}
    social_links = {}
    try:
        cur.execute("""
            SELECT email, first_name, last_name, phone, meta, city, dob, address, profile_photo
            FROM members
            WHERE id=%s
            LIMIT 1
        """, (member_id,))
        row = cur.fetchone()

        def parse_meta(val):
            import json
            try:
                return json.loads(val) if val else ''
            except Exception:
                return val or ''

        if row:
            if isinstance(row, dict):
                profile = {
                    'email': row.get('email'),
                    'first_name': row.get('first_name'),
                    'last_name': row.get('last_name'),
                    'phone': row.get('phone'),
                    'meta': parse_meta(row.get('meta')),
                    'city': row.get('city'),
                    'dob': row.get('dob'),
                    'address': row.get('address'),
                    'profile_photo': row.get('profile_photo'),
                }
            else:
                profile = {
                    'email': row[0],
                    'first_name': row[1],
                    'last_name': row[2],
                    'phone': row[3],
                    'meta': parse_meta(row[4]),
                    'city': row[5],
                    'dob': row[6],
                    'address': row[7],
                    'profile_photo': row[8] if len(row) > 8 else None,
                }
        # Fetch social links
        cur.execute("SELECT github_url, twitter_url, facebook_url, linkedin_url FROM member_social_links WHERE member_id=%s LIMIT 1", (member_id,))
        social_row = cur.fetchone()
        if social_row:
            if isinstance(social_row, dict):
                social_links = {
                    'github_url': social_row.get('github_url', ''),
                    'twitter_url': social_row.get('twitter_url', ''),
                    'facebook_url': social_row.get('facebook_url', ''),
                    'linkedin_url': social_row.get('linkedin_url', ''),
                }
            else:
                social_links = {
                    'github_url': social_row[0],
                    'twitter_url': social_row[1],
                    'facebook_url': social_row[2],
                    'linkedin_url': social_row[3],
                }
    except Exception as e:
        error_msg = f"Error loading profile: {str(e)}"
        social_links = {}
    finally:
        cur.close()
        conn.close()

    # ---------------------- RENDER PAGE ----------------------
    return render(request, 'core/profile_edit.html', {
        'profile': profile,
        'social_links': social_links,
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
                        return redirect('profile')
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

def projects_report_view(request):
    """
    Display a comprehensive report of projects with task statistics, employee info, and live tracking data.
    """
    user = request.session.get('user')
    if not user:
        return redirect('login_password')

    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')

    conn = get_tenant_conn(request)
    projects = []
    tasks_list = []
    summary = {}
    
    try:
        # Fetch comprehensive project data with employee info and task statistics
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                p.id,
                p.name,
                p.description,
                p.status,
                p.start_date,
                p.tentative_end_date,
                p.end_date,
                p.created_at,
                p.employee_id,
                e.employee_code,
                e.first_name AS emp_first_name,
                e.last_name AS emp_last_name,
                e.email AS emp_email,
                e.department,
                e.designation,
                e.status AS employee_status,
                u.full_name AS created_by_name,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) AS total_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status = 'Completed') AS completed_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status IN ('New', 'In Progress', 'Pending')) AS pending_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND status = 'In Progress') AS inprogress_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND priority = 'Critical') AS critical_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND priority = 'High') AS high_tasks,
                (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND due_date < CURDATE() AND status != 'Completed') AS overdue_tasks
            FROM projects p
            LEFT JOIN employees e ON p.employee_id = e.id
            LEFT JOIN users u ON p.created_by = u.id
            ORDER BY p.created_at DESC
        """)
        rows = cur.fetchall()
        
        for r in rows:
            # Calculate progress percentage
            total = r['total_tasks'] or 0
            completed = r['completed_tasks'] or 0
            progress = round((completed / total * 100) if total > 0 else 0, 1)
            
            # Calculate timeline status
            timeline_status = 'On Track'
            if r['status'] == 'Completed':
                timeline_status = 'Completed'
            elif r['tentative_end_date']:
                from datetime import datetime, date
                today = date.today()
                end_date = r['tentative_end_date']
                if isinstance(end_date, str):
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                if end_date < today and r['status'] != 'Completed':
                    timeline_status = 'Overdue'
                elif (end_date - today).days <= 7 and r['status'] != 'Completed':
                    timeline_status = 'At Risk'
            
            # Employee full name
            employee_name = ''
            if r['emp_first_name']:
                employee_name = f"{r['emp_first_name']} {r['emp_last_name'] or ''}".strip()
            
            projects.append({
                'id': r['id'],
                'name': r['name'],
                'description': r['description'] or '',
                'status': r['status'],
                'start_date': r['start_date'],
                'tentative_end_date': r['tentative_end_date'],
                'end_date': r['end_date'],
                'created_at': r['created_at'],
                'created_by_name': r['created_by_name'] or 'Unknown',
                'employee_code': r['employee_code'] or 'N/A',
                'employee_name': employee_name or 'Not Assigned',
                'employee_email': r['emp_email'] or '',
                'department': r['department'] or 'N/A',
                'designation': r['designation'] or 'N/A',
                'employee_status': r['employee_status'] or 'Unknown',
                'total_tasks': total,
                'completed_tasks': completed,
                'pending_tasks': r['pending_tasks'] or 0,
                'inprogress_tasks': r['inprogress_tasks'] or 0,
                'critical_tasks': r['critical_tasks'] or 0,
                'high_tasks': r['high_tasks'] or 0,
                'overdue_tasks': r['overdue_tasks'] or 0,
                'progress': progress,
                'timeline_status': timeline_status
            })
        
        # Calculate summary statistics
        total_projects = len(projects)
        active_projects = len([p for p in projects if p['status'] == 'Active'])
        completed_projects = len([p for p in projects if p['status'] == 'Completed'])
        planned_projects = len([p for p in projects if p['status'] == 'Planned'])
        onhold_projects = len([p for p in projects if p['status'] == 'On Hold'])
        total_all_tasks = sum(p['total_tasks'] for p in projects)
        total_completed_tasks = sum(p['completed_tasks'] for p in projects)
        total_pending_tasks = sum(p['pending_tasks'] for p in projects)
        total_overdue_tasks = sum(p['overdue_tasks'] for p in projects)
        
        # Calculate employee counts by status - get distinct employees from employees table
        cur.execute("SELECT COUNT(*) as count FROM employees WHERE status = 'Active'")
        active_employees = cur.fetchone()['count'] or 0
        
        cur.execute("SELECT COUNT(*) as count FROM employees WHERE status = 'Inactive'")
        inactive_employees = cur.fetchone()['count'] or 0
        
        cur.execute("SELECT COUNT(*) as count FROM employees WHERE status = 'Terminated'")
        terminated_employees = cur.fetchone()['count'] or 0
        
        cur.execute("SELECT COUNT(*) as count FROM employees WHERE status = 'On Leave'")
        onleave_employees = cur.fetchone()['count'] or 0
        
        summary = {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'planned_projects': planned_projects,
            'onhold_projects': onhold_projects,
            'total_tasks': total_all_tasks,
            'completed_tasks': total_completed_tasks,
            'pending_tasks': total_pending_tasks,
            'overdue_tasks': total_overdue_tasks,
            'active_employees': active_employees,
            'inactive_employees': inactive_employees,
            'terminated_employees': terminated_employees,
            'onleave_employees': onleave_employees,
            'overall_progress': round((total_completed_tasks / total_all_tasks * 100) if total_all_tasks > 0 else 0, 1)
        }
        
    except Exception as e:
        print(f"Error in projects_report_view: {e}")
        projects = []
        summary = {
            'total_projects': 0,
            'active_projects': 0,
            'completed_projects': 0,
            'planned_projects': 0,
            'onhold_projects': 0,
            'active_employees': 0,
            'inactive_employees': 0,
            'terminated_employees': 0,
            'onleave_employees': 0,
            'total_tasks': 0,
            'completed_tasks': 0,
            'pending_tasks': 0,
            'overdue_tasks': 0,
            'overall_progress': 0
        }
    
    # Fetch all tasks with project and assignee information (reuse same connection)
    try:
        cur = conn.cursor()
        print("Fetching tasks...")
        cur.execute("""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.status,
                t.priority,
                t.due_date,
                t.created_at,
                t.assigned_type,
                t.assigned_to,
                p.name AS project_name,
                p.id AS project_id,
                m.first_name AS member_first_name,
                m.last_name AS member_last_name,
                tm.name AS assigned_team_name,
                creator.full_name AS created_by_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN members m ON t.assigned_type = 'member' AND t.assigned_to = m.id
            LEFT JOIN teams tm ON t.assigned_type = 'team' AND t.assigned_to = tm.id
            LEFT JOIN users creator ON t.created_by = creator.id
            ORDER BY t.created_at DESC
        """)
        rows = cur.fetchall()
        print(f"Found {len(rows)} tasks")
        
        for r in rows:
            # Determine assigned name
            assigned_name = 'Unassigned'
            if r['assigned_type'] == 'member' and r['member_first_name']:
                assigned_name = f"{r['member_first_name']} {r['member_last_name'] or ''}".strip()
            elif r['assigned_type'] == 'team' and r['assigned_team_name']:
                assigned_name = f"Team: {r['assigned_team_name']}"
            
            tasks_list.append({
                'id': r['id'],
                'title': r['title'],
                'description': r['description'] or '',
                'status': r['status'],
                'priority': r['priority'],
                'due_date': r['due_date'],
                'created_at': r['created_at'],
                'project_name': r['project_name'] or 'No Project',
                'project_id': r['project_id'],
                'assigned_name': assigned_name,
                'assigned_type': r['assigned_type'],
                'created_by_name': r['created_by_name'] or 'Unknown'
            })
        print(f"Tasks list prepared: {len(tasks_list)} tasks")
    except Exception as e:
        print(f"Error fetching tasks: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close connection after all queries are complete
        if conn:
            conn.close()

    # Fetch all teams for filter dropdown
    teams = []
    try:
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM teams ORDER BY name")
        teams = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching teams: {e}")
        teams = []

    print(f"Rendering template with {len(projects)} projects, {len(tasks_list)} tasks, and {len(teams)} teams")
    return render(request, 'core/projects_report.html', {
        'projects': projects,
        'tasks': tasks_list,
        'summary': summary,
        'teams': teams,
        'page': 'reports'
    })


# ======================== EMPLOYEES VIEWS ========================

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

def employees_page(request):
    """Display the employees management page."""
    user = request.session.get('user')
    if not user:
        return redirect('identify')

    return render(request, 'core/employees.html', {'page': 'employees'})


def api_employees_list(request):
    """Return a list of all employees."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    employees = []
    try:
        cur.execute("""
            SELECT id, employee_code, email, first_name, last_name, phone, 
                   department, designation, date_of_joining, status, salary,
                   created_at
            FROM employees
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        employees = [{
            'id': r['id'],
            'employee_code': r['employee_code'],
            'email': r['email'],
            'first_name': r['first_name'],
            'last_name': r['last_name'],
            'full_name': f"{r['first_name']} {r['last_name'] or ''}".strip(),
            'phone': r['phone'] or '',
            'department': r['department'] or '',
            'designation': r['designation'] or '',
            'date_of_joining': r['date_of_joining'].strftime('%Y-%m-%d') if r['date_of_joining'] else '',
            'status': r['status'],
            'salary': float(r['salary']) if r['salary'] else 0,
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else ''
        } for r in rows]
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()

    return JsonResponse({'employees': employees})


@require_http_methods(["POST"])
def api_create_employee(request):
    """Create a new employee."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    import json
    data = json.loads(request.body)
    
    employee_code = data.get('employee_code', '').strip()
    email = data.get('email', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    phone = data.get('phone', '').strip()
    department = data.get('department', '').strip()
    designation = data.get('designation', '').strip()
    date_of_joining = data.get('date_of_joining', '').strip()
    date_of_birth = data.get('date_of_birth', '').strip()
    address = data.get('address', '').strip()
    city = data.get('city', '').strip()
    state = data.get('state', '').strip()
    country = data.get('country', '').strip()
    postal_code = data.get('postal_code', '').strip()
    emergency_contact_name = data.get('emergency_contact_name', '').strip()
    emergency_contact_phone = data.get('emergency_contact_phone', '').strip()
    status = data.get('status', 'Active')
    salary = data.get('salary', None)

    if not employee_code or not email or not first_name:
        return JsonResponse({'error': 'Employee code, email, and first name are required'}, status=400)

    member_id = request.session.get('member_id')
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO employees (
                employee_code, email, first_name, last_name, phone,
                department, designation, date_of_joining, date_of_birth,
                address, city, state, country, postal_code,
                emergency_contact_name, emergency_contact_phone,
                status, salary, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            employee_code, email, first_name, last_name, phone,
            department, designation, date_of_joining or None, date_of_birth or None,
            address, city, state, country, postal_code,
            emergency_contact_name, emergency_contact_phone,
            status, salary, member_id
        ))
        conn.commit()
        employee_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()

    return JsonResponse({'success': True, 'employee_id': employee_id})


@require_http_methods(["POST"])
def api_update_employee(request):
    """Update an existing employee."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    import json
    data = json.loads(request.body)
    
    employee_id = data.get('id')
    if not employee_id:
        return JsonResponse({'error': 'Employee ID is required'}, status=400)

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    try:
        # Build dynamic update query
        fields = []
        values = []
        
        for field in ['employee_code', 'email', 'first_name', 'last_name', 'phone',
                      'department', 'designation', 'date_of_joining', 'date_of_birth',
                      'address', 'city', 'state', 'country', 'postal_code',
                      'emergency_contact_name', 'emergency_contact_phone', 'status', 'salary']:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field] if data[field] else None)
        
        if not fields:
            return JsonResponse({'error': 'No fields to update'}, status=400)
        
        values.append(employee_id)
        query = f"UPDATE employees SET {', '.join(fields)} WHERE id = %s"
        
        cur.execute(query, values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()

    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def api_delete_employee(request):
    """Delete an employee."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    import json
    data = json.loads(request.body)
    
    employee_id = data.get('id')
    if not employee_id:
        return JsonResponse({'error': 'Employee ID is required'}, status=400)

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()

    return JsonResponse({'success': True})


def api_employee_detail(request):
    """Get details of a specific employee."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    employee_id = request.GET.get('id')
    if not employee_id:
        return JsonResponse({'error': 'Employee ID is required'}, status=400)

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, employee_code, email, first_name, last_name, phone,
                   department, designation, date_of_joining, date_of_birth,
                   address, city, state, country, postal_code,
                   emergency_contact_name, emergency_contact_phone,
                   status, salary, created_at, updated_at
            FROM employees
            WHERE id = %s
        """, (employee_id,))
        row = cur.fetchone()
        
        if not row:
            return JsonResponse({'error': 'Employee not found'}, status=404)
        
        employee = {
            'id': row['id'],
            'employee_code': row['employee_code'],
            'email': row['email'],
            'first_name': row['first_name'],
            'last_name': row['last_name'] or '',
            'phone': row['phone'] or '',
            'department': row['department'] or '',
            'designation': row['designation'] or '',
            'date_of_joining': row['date_of_joining'].strftime('%Y-%m-%d') if row['date_of_joining'] else '',
            'date_of_birth': row['date_of_birth'].strftime('%Y-%m-%d') if row['date_of_birth'] else '',
            'address': row['address'] or '',
            'city': row['city'] or '',
            'state': row['state'] or '',
            'country': row['country'] or '',
            'postal_code': row['postal_code'] or '',
            'emergency_contact_name': row['emergency_contact_name'] or '',
            'emergency_contact_phone': row['emergency_contact_phone'] or '',
            'status': row['status'],
            'salary': float(row['salary']) if row['salary'] else 0,
            'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else '',
            'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row['updated_at'] else ''
        }
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()

    return JsonResponse({'employee': employee})


# ======================== NOTIFICATIONS ========================

def notifications_page(request):
    """Display notifications page."""
    user = request.session.get('user')
    if not user:
        return redirect('identify')
    
    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('identify')
    
    return render(request, 'core/notifications.html', {'page': 'notifications'})


def api_notifications_list(request):
    """Get user notifications."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    if not member_id:
        return JsonResponse({'error': 'Member ID not found'}, status=401)
    
    try:
        conn = get_tenant_conn(request)
        if not conn:
            return JsonResponse({'error': 'Database connection failed'}, status=500)
            
        cur = conn.cursor()
        
        # Check if notifications table exists
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = 'notifications'
        """)
        table_exists = cur.fetchone()['count'] > 0
        
        if not table_exists:
            # Table doesn't exist yet, return empty
            cur.close()
            conn.close()
            return JsonResponse({
                'notifications': [],
                'unread_count': 0,
                'message': 'Notifications table not found. Run migration script.'
            })
        
        # Get all notifications for user
        cur.execute("""
            SELECT id, title, message, type, is_read, link, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (member_id,))
        notifications = cur.fetchall()
        notifications_list = []
        
        for r in notifications:
            notifications_list.append({
                'id': r['id'],
                'title': r['title'],
                'message': r['message'],
                'type': r['type'],
                'is_read': bool(r['is_read']),
                'link': r['link'],
                'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else '',
                'read_at': None
            })
        
        # Get unread count
        cur.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0", (member_id,))
        unread_count = cur.fetchone()['count']
        
        cur.close()
        conn.close()
        
        return JsonResponse({
            'notifications': notifications,
            'unread_count': unread_count
        })
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Notification API Error: {error_detail}")
        return JsonResponse({
            'error': str(e),
            'notifications': [],
            'unread_count': 0
        }, status=500)


def api_notifications_mark_read(request):
    """Mark notification(s) as read."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    data = json.loads(request.body)
    notification_id = data.get('id')
    mark_all = data.get('mark_all', False)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        if mark_all:
            cur.execute("""
                UPDATE notifications 
                SET is_read = 1
                WHERE user_id = %s AND is_read = 0
            """, (member_id,))
        elif notification_id:
            cur.execute("""
                UPDATE notifications 
                SET is_read = 1
                WHERE id = %s AND user_id = %s
            """, (notification_id, member_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()
    
    return JsonResponse({'success': True})


def api_notifications_delete(request):
    """Delete notification."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    data = json.loads(request.body)
    notification_id = data.get('id')
    
    if not notification_id:
        return JsonResponse({'error': 'Notification ID required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM notifications WHERE id = %s AND user_id = %s", (notification_id, member_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()
    
    return JsonResponse({'success': True})


def api_notifications_unread_count(request):
    """Get unread notifications count."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'count': 0})
    
    member_id = request.session.get('member_id')
    if not member_id:
        return JsonResponse({'count': 0})
    
    try:
        conn = get_tenant_conn(request)
        if not conn:
            return JsonResponse({'count': 0})
            
        cur = conn.cursor()
        
        # Check if notifications table exists
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = 'notifications'
        """)
        table_exists = cur.fetchone()['count'] > 0
        
        if not table_exists:
            cur.close()
            conn.close()
            return JsonResponse({'count': 0})
        
        cur.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0", (member_id,))
        result = cur.fetchone()
        count = result['count'] if result else 0
        
        cur.close()
        conn.close()
        
        return JsonResponse({'count': count})
        
    except Exception as e:
        print(f"Error getting unread count: {e}")
        return JsonResponse({'count': 0})


# ============================================================================
# TIMER VIEWS
# ============================================================================

def timer_page(request):
    """Timer page for tracking time on tasks."""
    if not request.session.get('user'):
        return redirect('identify')
    
    return render(request, 'core/timer.html', {'page': 'timer'})


def api_timer_start(request):
    """Start a new timer session."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    from datetime import datetime
    data = json.loads(request.body)
    task_id = data.get('task_id')
    notes = data.get('notes', '')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Check if there's already a running timer for this user
        cur.execute("""
            SELECT id FROM timer_sessions 
            WHERE user_id = %s AND is_running = 1
        """, (member_id,))
        existing = cur.fetchone()
        
        if existing:
            return JsonResponse({'error': 'A timer is already running. Please stop it first.'}, status=400)
        
        # Create new timer session
        now = datetime.now()
        cur.execute("""
            INSERT INTO timer_sessions (user_id, task_id, start_time, notes, is_running)
            VALUES (%s, %s, %s, %s, 1)
        """, (member_id, task_id, now, notes))
        
        session_id = cur.lastrowid
        conn.commit()
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'start_time': now.isoformat()
        })
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_timer_stop(request):
    """Stop the current running timer."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    from datetime import datetime
    data = json.loads(request.body)
    session_id = data.get('session_id')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Get the running timer
        if session_id:
            cur.execute("""
                SELECT id, start_time FROM timer_sessions 
                WHERE id = %s AND user_id = %s AND is_running = 1
            """, (session_id, member_id))
        else:
            cur.execute("""
                SELECT id, start_time FROM timer_sessions 
                WHERE user_id = %s AND is_running = 1
                ORDER BY start_time DESC LIMIT 1
            """, (member_id,))
        
        timer = cur.fetchone()
        
        if not timer:
            return JsonResponse({'error': 'No running timer found'}, status=404)
        
        # Calculate duration
        now = datetime.now()
        start_time = timer['start_time']
        duration = int((now - start_time).total_seconds())
        
        # Update timer session
        cur.execute("""
            UPDATE timer_sessions 
            SET end_time = %s, duration_seconds = %s, is_running = 0
            WHERE id = %s
        """, (now, duration, timer['id']))
        
        conn.commit()
        
        return JsonResponse({
            'success': True,
            'session_id': timer['id'],
            'duration_seconds': duration,
            'end_time': now.isoformat()
        })
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_timer_current(request):
    """Get the current running timer for the user."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT ts.*, t.title as task_title
            FROM timer_sessions ts
            LEFT JOIN tasks t ON ts.task_id = t.id
            WHERE ts.user_id = %s AND ts.is_running = 1
            ORDER BY ts.start_time DESC LIMIT 1
        """, (member_id,))
        
        timer = cur.fetchone()
        
        if timer:
            from datetime import datetime
            start_time = timer['start_time']
            elapsed = int((datetime.now() - start_time).total_seconds())
            
            return JsonResponse({
                'running': True,
                'session_id': timer['id'],
                'task_id': timer['task_id'],
                'task_title': timer['task_title'],
                'start_time': start_time.isoformat(),
                'elapsed_seconds': elapsed,
                'notes': timer['notes']
            })
        else:
            return JsonResponse({'running': False})
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_timer_history(request):
    """Get timer history for the user."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    limit = int(request.GET.get('limit', 50))
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT ts.*, t.title as task_title, t.status as task_status
            FROM timer_sessions ts
            LEFT JOIN tasks t ON ts.task_id = t.id
            WHERE ts.user_id = %s
            ORDER BY ts.start_time DESC
            LIMIT %s
        """, (member_id, limit))
        
        sessions = cur.fetchall()
        
        # Convert datetime objects to strings
        for session in sessions:
            if session['start_time']:
                session['start_time'] = session['start_time'].isoformat()
            if session['end_time']:
                session['end_time'] = session['end_time'].isoformat()
            if session['created_at']:
                session['created_at'] = session['created_at'].isoformat()
            if session['updated_at']:
                session['updated_at'] = session['updated_at'].isoformat()
        
        return JsonResponse({'sessions': sessions})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


# ============================================================================
# TIME ENTRIES VIEWS
# ============================================================================

def time_entries_page(request):
    """Time entries page for logging and approving time."""
    if not request.session.get('user'):
        return redirect('identify')
    
    return render(request, 'core/time_entries.html', {'page': 'time_entries'})


def api_time_entries_list(request):
    """Get time entries list with filtering options."""
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    # Get filter parameters
    filter_type = request.GET.get('filter', 'my')  # 'my', 'team', 'pending', 'all'
    status_filter = request.GET.get('status', '')  # 'pending', 'approved', 'rejected'
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Base query
        query = """
            SELECT 
                te.*,
                m.first_name, m.last_name, m.email,
                t.title as task_title, t.status as task_status,
                p.name as project_name,
                approver.first_name as approver_first_name,
                approver.last_name as approver_last_name
            FROM time_entries te
            LEFT JOIN members m ON te.user_id = m.id
            LEFT JOIN tasks t ON te.task_id = t.id
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN members approver ON te.approved_by = approver.id
            WHERE 1=1
        """
        params = []
        
        # Apply filters
        if filter_type == 'my':
            query += " AND te.user_id = %s"
            params.append(member_id)
        elif filter_type == 'pending':
            query += " AND te.status = 'pending'"
        
        if status_filter:
            query += " AND te.status = %s"
            params.append(status_filter)
        
        if start_date:
            query += " AND te.date >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND te.date <= %s"
            params.append(end_date)
        
        query += " ORDER BY te.date DESC, te.created_at DESC LIMIT 100"
        
        cur.execute(query, params)
        entries = cur.fetchall()
        
        # Convert datetime objects to strings
        for entry in entries:
            if entry.get('date'):
                entry['date'] = entry['date'].isoformat()
            if entry.get('created_at'):
                entry['created_at'] = entry['created_at'].isoformat()
            if entry.get('updated_at'):
                entry['updated_at'] = entry['updated_at'].isoformat()
            if entry.get('approved_at'):
                entry['approved_at'] = entry['approved_at'].isoformat()
        
        return JsonResponse({'entries': entries})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_time_entries_create(request):
    """Create a new time entry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    data = json.loads(request.body)
    task_id = data.get('task_id')
    hours = data.get('hours')
    date = data.get('date')
    description = data.get('description', '')
    
    if not all([hours, date]):
        return JsonResponse({'error': 'Hours and date are required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO time_entries (user_id, task_id, hours, date, description, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (member_id, task_id, hours, date, description))
        
        entry_id = cur.lastrowid
        conn.commit()
        
        return JsonResponse({'success': True, 'entry_id': entry_id})
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_time_entries_update(request):
    """Update an existing time entry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    data = json.loads(request.body)
    entry_id = data.get('id')
    task_id = data.get('task_id')
    hours = data.get('hours')
    date = data.get('date')
    description = data.get('description', '')
    
    if not entry_id:
        return JsonResponse({'error': 'Entry ID required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Check ownership
        cur.execute("SELECT user_id, status FROM time_entries WHERE id = %s", (entry_id,))
        entry = cur.fetchone()
        
        if not entry:
            return JsonResponse({'error': 'Entry not found'}, status=404)
        
        if entry['user_id'] != member_id:
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        if entry['status'] != 'pending':
            return JsonResponse({'error': 'Cannot edit approved/rejected entries'}, status=400)
        
        # Update entry
        updates = []
        params = []
        
        if task_id is not None:
            updates.append("task_id = %s")
            params.append(task_id)
        
        if hours is not None:
            updates.append("hours = %s")
            params.append(hours)
        
        if date is not None:
            updates.append("date = %s")
            params.append(date)
        
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        
        if updates:
            params.append(entry_id)
            cur.execute(f"UPDATE time_entries SET {', '.join(updates)} WHERE id = %s", params)
            conn.commit()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_time_entries_delete(request):
    """Delete a time entry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    data = json.loads(request.body)
    entry_id = data.get('id')
    
    if not entry_id:
        return JsonResponse({'error': 'Entry ID required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Check ownership
        cur.execute("SELECT user_id, status FROM time_entries WHERE id = %s", (entry_id,))
        entry = cur.fetchone()
        
        if not entry:
            return JsonResponse({'error': 'Entry not found'}, status=404)
        
        if entry['user_id'] != member_id:
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        if entry['status'] != 'pending':
            return JsonResponse({'error': 'Cannot delete approved/rejected entries'}, status=400)
        
        cur.execute("DELETE FROM time_entries WHERE id = %s", (entry_id,))
        conn.commit()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_time_entries_approve(request):
    """Approve a time entry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    from datetime import datetime
    data = json.loads(request.body)
    entry_id = data.get('id')
    
    if not entry_id:
        return JsonResponse({'error': 'Entry ID required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Check if entry exists
        cur.execute("SELECT id, status FROM time_entries WHERE id = %s", (entry_id,))
        entry = cur.fetchone()
        
        if not entry:
            return JsonResponse({'error': 'Entry not found'}, status=404)
        
        if entry['status'] != 'pending':
            return JsonResponse({'error': 'Entry already processed'}, status=400)
        
        # Approve entry
        now = datetime.now()
        cur.execute("""
            UPDATE time_entries 
            SET status = 'approved', approved_by = %s, approved_at = %s
            WHERE id = %s
        """, (member_id, now, entry_id))
        
        conn.commit()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


def api_time_entries_reject(request):
    """Reject a time entry."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    user = request.session.get('user')
    if not user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    member_id = request.session.get('member_id')
    
    import json
    from datetime import datetime
    data = json.loads(request.body)
    entry_id = data.get('id')
    
    if not entry_id:
        return JsonResponse({'error': 'Entry ID required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Check if entry exists
        cur.execute("SELECT id, status FROM time_entries WHERE id = %s", (entry_id,))
        entry = cur.fetchone()
        
        if not entry:
            return JsonResponse({'error': 'Entry not found'}, status=404)
        
        if entry['status'] != 'pending':
            return JsonResponse({'error': 'Entry already processed'}, status=400)
        
        # Reject entry
        now = datetime.now()
        cur.execute("""
            UPDATE time_entries 
            SET status = 'rejected', approved_by = %s, approved_at = %s
            WHERE id = %s
        """, (member_id, now, entry_id))
        
        conn.commit()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        conn.rollback()
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()
