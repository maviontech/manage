
import csv, io, datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.shortcuts import get_object_or_404

# helper: get connection for current tenant
from .db_helpers import get_tenant_conn, get_visible_task_user_ids
import json

# PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas


# ==============================
#  CREATE TASK  (GET / POST)
# ==============================
def create_task_view(request):
    """
    Creates a new task and saves to DB. Supports member/team polymorphic assignment.
    Requires `assigned_type` column in `tasks` table (ENUM('member','team')).
    """
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    if request.method == "POST":
        data = request.POST
        project_id = data.get("project_id") or None
        subproject_id = data.get("subproject_id") or None
        title = data.get("title")
        description = data.get("description")
        due_date = data.get("due_date") or None
        closure_date = data.get("closure_date") or None
        priority = data.get("priority") or "Normal"
        status = data.get("status") or "Open"
        work_type = data.get("work_type") or "Task"  # NEW: Get work type from form
        created_by = request.session.get("user_id")

        # --- NEW FIX ---
        assigned_raw = data.get("assigned_to") or None
        assigned_to, assigned_type = None, None
        if assigned_raw:
            if ":" in assigned_raw:
                assigned_type, assigned_to = assigned_raw.split(":", 1)
            else:
                assigned_type, assigned_to = "member", assigned_raw

        # --- INSERT ---
        cur.execute(
            """INSERT INTO tasks
               (project_id, subproject_id, title, description, status, priority,
                assigned_to, assigned_type, created_by, due_date, closure_date, work_type, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                project_id,
                subproject_id,
                title,
                description,
                status,
                priority,
                assigned_to,
                assigned_type,
                created_by,
                due_date,
                closure_date,
                work_type,
            ),
        )
        task_id = cur.lastrowid

        # Log activity
        cur.execute(
            "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
            ("task", task_id, "created", created_by),
        )

        # Create notification if task is assigned to a member
        if assigned_type == "member" and assigned_to:
            # Get creator name
            cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (created_by,))
            creator = cur.fetchone()
            creator_name = creator['name'] if creator else 'Someone'
            
            cur.execute("""
                INSERT INTO notifications (user_id, title, message, type, link)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                assigned_to,
                "New Task Assigned",
                f"{creator_name} assigned you to '{title}'",
                "task",
                f"/tasks/detail/{task_id}"
            ))
        
        # Create notification for team members if assigned to a team
        elif assigned_type == "team" and assigned_to:
            cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (created_by,))
            creator = cur.fetchone()
            creator_name = creator['name'] if creator else 'Someone'
            
            # Get all team members
            cur.execute("SELECT member_id FROM team_memberships WHERE team_id=%s", (assigned_to,))
            team_members = cur.fetchall()
            
            for member in team_members:
                cur.execute("""
                    INSERT INTO notifications (user_id, title, message, type, link)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    member['member_id'],
                    "New Team Task Assigned",
                    f"{creator_name} assigned a task to your team: '{title}'",
                    "task",
                    f"/tasks/detail/{task_id}"
                ))

        conn.commit()
        cur.close()
        return redirect("task_board")

    # --- GET ---
    cur.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cur.fetchall()
    cur.execute("SELECT id, email, first_name, last_name FROM members ORDER BY first_name")
    members = cur.fetchall()
    cur.execute("SELECT id, name FROM teams ORDER BY name")
    teams = cur.fetchall()
    
    # Get default work types (can be extended per project later)
    default_work_types = ['Task', 'Bug', 'Story', 'Defect', 'Sub Task', 'Report', 'Change Request']
    
    cur.close()

    return render(
        request,
        "core/create_task.html",
        {
            "projects": projects, 
            "members": members, 
            "teams": teams, 
            "page": "task_create",
            "work_types": default_work_types
        },
    )


# ==============================
#  MY TASKS
# ==============================
def my_tasks_view(request):

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    # Ensure user_id is set in session (should be set at login)
    user_id = request.session.get("user_id")
    if not user_id:
        # Try to resolve from email if available
        email = request.session.get("auth_email")
        if email:
            cur.execute("SELECT id FROM members WHERE email = %s", (email,))
            row = cur.fetchone()
            if row:
                user_id = row["id"]
                request.session["user_id"] = user_id
    if not user_id:
        return redirect("login")

    # Get visible task user IDs based on Alex Carter visibility rules
    visible_user_ids = get_visible_task_user_ids(conn, user_id)
    
    # Show tasks assigned to visible users (current user's tasks + Alex Carter's tasks, 
    # or all tasks if current user is Alex Carter)
    if visible_user_ids:
        placeholders = ','.join(['%s'] * len(visible_user_ids))
        cur.execute(
            f"""SELECT id, title, status, priority, due_date, closure_date
               FROM tasks
               WHERE assigned_type='member' AND assigned_to IN ({placeholders})
               ORDER BY FIELD(status,'Open','In Progress','Review','Blocked','Closed'),
                        due_date IS NULL, due_date ASC""",
            tuple(visible_user_ids),
        )
        tasks = cur.fetchall()
    else:
        tasks = []
    
    cur.close()

    today = datetime.date.today()
    return render(request, "core/tasks_my.html", {"tasks": tasks, "page": "my_tasks", "today": today})


# ==============================
#  UNASSIGNED TASKS
# ==============================
def unassigned_tasks_view(request):
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    sql = """
        SELECT 
            t.id, 
            t.title, 
            t.priority,
            t.due_date,
            t.assigned_type, 
            t.assigned_to,
            p.name AS project_name,
            sp.name AS subproject_name
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN subprojects sp ON sp.id = t.subproject_id
        WHERE t.assigned_to IS NOT NULL
        ORDER BY t.priority DESC                            
            """    
    # the change the query to fetch only unassigned tasks                              
    cur.execute(sql)
    rows = cur.fetchall()

    # also needed for modal dropdown
    cur.execute("SELECT id, email, first_name, last_name FROM members ORDER BY first_name")
    members = cur.fetchall()
    cur.execute("SELECT id, name FROM teams ORDER BY name")
    teams = cur.fetchall()
    cur.close()

    return render(
        request,
        "core/unassigned_tasks.html",
        {"tasks": rows, "members": members, "teams": teams, "page": "unassigned_tasks"},
    )


# ==============================
#  TASK BOARD PAGE + DATA
# ==============================

from django.http import JsonResponse
from math import ceil
from .db_helpers import get_tenant_conn


def board_data_api(request):
    """
    Paginated task data for the Kanban board.
    Compatible with both dict and tuple-returning cursors.
    """
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    # Get current user ID
    user_id = request.session.get("user_id")
    if not user_id:
        user_id = request.session.get("member_id")
    
    # Get visible task user IDs based on Alex Carter visibility rules
    visible_user_ids = get_visible_task_user_ids(conn, user_id) if user_id else []

    # ---- Status Filter + Assigned Filter ----
    status = request.GET.get("status")
    assigned_to = request.GET.get("assigned_to")

    # ---- Pagination ----
    try:
        page = int(request.GET.get("page", "1"))
    except:
        page = 1
    if page < 1:
        page = 1

    per_page = 20
    offset = (page - 1) * per_page

    # ---- Total Count Query ----
    count_sql = "SELECT COUNT(*) FROM tasks"
    count_params = []

    # build optional filters
    count_filters = []
    
    # Apply visibility filter for member-assigned tasks
    if visible_user_ids:
        placeholders = ','.join(['%s'] * len(visible_user_ids))
        count_filters.append(f"(assigned_type = 'member' AND assigned_to IN ({placeholders}))")
        count_params.extend(visible_user_ids)
    
    if status:
        count_filters.append("status = %s")
        count_params.append(status)
    if assigned_to:
        # Only member-assigned tasks should be considered when filtering by assigned_to
        count_filters.append("assigned_type = 'member' AND assigned_to = %s")
        count_params.append(assigned_to)

    if count_filters:
        count_sql += " WHERE " + " AND ".join(count_filters)

    cur.execute(count_sql, tuple(count_params))
    row = cur.fetchone()

    # Handle dict / tuple cursor
    if isinstance(row, dict):
        total_count = row.get("COUNT(*)", 0)
    else:
        total_count = row[0]

    # Calculate total pages
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    # ---- MAIN QUERY ----
    sql = """
        SELECT
            t.id,
            COALESCE(t.title, '(Untitled)') AS title,
            COALESCE(t.status, 'Open') AS status,
            COALESCE(t.priority, 'Normal') AS priority,
            t.due_date,

            CONCAT_WS(':', t.assigned_type, t.assigned_to) AS assigned_to,

            CASE
                WHEN t.assigned_type = 'member' THEN (
                    SELECT CONCAT(m.first_name, ' ', m.last_name)
                    FROM members m
                    WHERE m.id = t.assigned_to
                )
                WHEN t.assigned_type = 'team' THEN (
                    SELECT tm.name
                    FROM teams tm
                    WHERE tm.id = t.assigned_to
                )
                ELSE NULL
            END AS assigned_to_display

        FROM tasks t
    """

    # ---- Apply Status Filter ----
    # ---- Apply optional filters to main query ----
    params = []
    main_filters = []
    
    # Apply visibility filter for member-assigned tasks
    if visible_user_ids:
        placeholders = ','.join(['%s'] * len(visible_user_ids))
        main_filters.append(f"(t.assigned_type = 'member' AND t.assigned_to IN ({placeholders}))")
        params.extend(visible_user_ids)
    
    if status:
        main_filters.append("t.status = %s")
        params.append(status)
    if assigned_to:
        main_filters.append("t.assigned_type = 'member' AND t.assigned_to = %s")
        params.append(assigned_to)

    if main_filters:
        sql += " WHERE " + " AND ".join(main_filters)

    # ---- ORDER + Pagination ----
    sql += " ORDER BY t.id DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    cur.execute(sql, tuple(params))

    # ---- Convert rows ----
    rows = cur.fetchall()

    if not rows:
        tasks = []
    elif isinstance(rows[0], dict):
        tasks = rows
    else:
        cols = [desc[0] for desc in cur.description]
        tasks = [dict(zip(cols, r)) for r in rows]

    cur.close()

    return JsonResponse({
        "tasks": tasks,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages
    })





# ==============================
#  ASSIGN TASK (AJAX)
# ==============================
@require_POST
def assign_task_api(request):
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    task_id = request.POST.get("task_id")
    assignee = request.POST.get("assignee")  # "member:23" or "team:5"
    assigned_by = request.session.get("user_id")

    if not task_id or not assignee:
        return HttpResponseBadRequest("Missing parameters")

    assigned_type, assigned_to = None, None
    if ":" in assignee:
        assigned_type, assigned_to = assignee.split(":", 1)
    else:
        assigned_type, assigned_to = "member", assignee

    # Get task details for notification
    cur.execute("SELECT title FROM tasks WHERE id=%s", (task_id,))
    task = cur.fetchone()
    task_title = task['title'] if task else 'A task'
    
    cur.execute(
        "UPDATE tasks SET assigned_to=%s, assigned_type=%s, updated_at=NOW() WHERE id=%s",
        (assigned_to, assigned_type, task_id),
    )
    cur.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
        ("task", task_id, f"assigned_to:{assignee}", assigned_by),
    )
    
    # Create notification for assigned member/team
    if assigned_type == "member":
        # Get assigner name
        cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (assigned_by,))
        assigner = cur.fetchone()
        assigner_name = assigner['name'] if assigner else 'Someone'
        
        cur.execute("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            assigned_to,
            "Task Assigned to You",
            f"{assigner_name} assigned you to '{task_title}'",
            "task",
            f"/tasks/detail/{task_id}"
        ))
    
    elif assigned_type == "team":
        cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (assigned_by,))
        assigner = cur.fetchone()
        assigner_name = assigner['name'] if assigner else 'Someone'
        
        # Get all team members
        cur.execute("SELECT member_id FROM team_memberships WHERE team_id=%s", (assigned_to,))
        team_members = cur.fetchall()
        
        for member in team_members:
            cur.execute("""
                INSERT INTO notifications (user_id, title, message, type, link)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                member['member_id'],
                "Team Task Assignment",
                f"{assigner_name} assigned a task to your team: '{task_title}'",
                "task",
                f"/tasks/detail/{task_id}"
            ))
    
    conn.commit()
    cur.close()
    return JsonResponse({"ok": True, "task_id": task_id, "assignee": assignee})


# ==============================
#  UPDATE STATUS (AJAX)
# ==============================
@require_POST
def api_update_status(request):
    """Called from Kanban drag-drop to update status"""

    conn = get_tenant_conn(request)
    cur = conn.cursor()

    task_id = request.POST.get("task_id")
    new_status = request.POST.get("status")
    user_id = request.session.get("user_id")

    # 1. CHECK REQUIRED PARAMS
    if not task_id or not new_status:
        return HttpResponseBadRequest("Missing parameters")

    # 2. SET CLOSURE DATE ONLY WHEN STATUS BECOMES 'Closed'
    if new_status == "Closed":
        cur.execute("""
            UPDATE tasks
            SET status=%s,
                closure_date=NOW(),
                updated_at=NOW()
            WHERE id=%s
        """, (new_status, task_id))
    else:
        # 3. FOR ANY OTHER STATUS → remove closure date?
        cur.execute("""
            UPDATE tasks
            SET status=%s,
                closure_date=NULL,
                updated_at=NOW()
            WHERE id=%s
        """, (new_status, task_id))

    # 4. CREATE LOG ENTRY
    cur.execute("""
        INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
        VALUES (%s, %s, %s, %s)
    """, ("task", task_id, f"status_changed:{new_status}", user_id))

    # 5. CREATE NOTIFICATION WHEN TASK IS COMPLETED
    if new_status == "Closed" or new_status == "Completed":
        # Get task details and creator
        cur.execute("""
            SELECT t.title, t.created_by, t.assigned_to, t.assigned_type,
                   CONCAT(m.first_name, ' ', m.last_name) as updater_name
            FROM tasks t
            LEFT JOIN members m ON m.id = %s
            WHERE t.id = %s
        """, (user_id, task_id))
        task_info = cur.fetchone()
        
        if task_info:
            updater_name = task_info['updater_name'] or 'Someone'
            task_title = task_info['title'] or 'A task'
            
            # Notify task creator if they're not the one who completed it
            if task_info['created_by'] and str(task_info['created_by']) != str(user_id):
                cur.execute("""
                    INSERT INTO notifications (user_id, title, message, type, link)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    task_info['created_by'],
                    "Task Completed",
                    f"{updater_name} completed task '{task_title}'",
                    "success",
                    f"/tasks/detail/{task_id}"
                ))
            
            # Notify assigned member if they're not the one who completed it
            if task_info['assigned_type'] == 'member' and task_info['assigned_to'] and str(task_info['assigned_to']) != str(user_id):
                cur.execute("""
                    INSERT INTO notifications (user_id, title, message, type, link)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    task_info['assigned_to'],
                    "Task Completed",
                    f"{updater_name} marked '{task_title}' as complete",
                    "success",
                    f"/tasks/detail/{task_id}"
                ))

    # 6. SAVE CHANGES
    conn.commit()
    cur.close()

    return JsonResponse({"ok": True})


# ==============================
#  BULK IMPORT CSV
# ==============================
def bulk_import_csv_view(request):
    """Upload & import CSV file of tasks"""
    context = {"page": "bulk_import"}

    if request.method == "POST" and request.FILES.get("csv_file"):
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        f = request.FILES["csv_file"]
        text = f.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        inserted, errors = 0, []

        for i, row in enumerate(reader, start=1):
            try:
                # Validate required fields
                if not row.get("title"):
                    raise Exception("Missing required field: title")
                if not row.get("project_id"):
                    raise Exception("Missing required field: project_id")

                assigned_raw = row.get("assigned_to") or None
                assigned_to, assigned_type = None, None
                if assigned_raw:
                    if ":" in assigned_raw:
                        assigned_type, assigned_to = assigned_raw.split(":", 1)
                    else:
                        assigned_type, assigned_to = "member", assigned_raw

                cur.execute(
                    """INSERT INTO tasks
                       (project_id, subproject_id, title, description, status, priority,
                        assigned_to, assigned_type, created_by, due_date, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (
                        row.get("project_id") or None,
                        row.get("subproject_id") or None,
                        row["title"],
                        row.get("description"),
                        row.get("status") or "Open",
                        row.get("priority") or "Normal",
                        assigned_to,
                        assigned_type,
                        request.session.get("user_id"),
                        row.get("due_date") or None,
                    ),
                )
                inserted += 1
            except Exception as e:
                # Add row data to error for easier debugging
                errors.append({"row": i, "error": str(e), "data": dict(row)})

        conn.commit()
        cur.close()
        context.update({"inserted": inserted, "errors": errors})
        return render(request, "core/tasks_bulk_import_result.html", context)

    return render(request, "core/tasks_bulk_import.html", context)

@require_GET
def api_task_detail(request):
    """
    GET ?id=<task_id>
    Returns JSON with task fields used by the modal: id, title, description, priority, due_date, assigned_to, assigned_to_display, status
    Implemented using tenant DB queries (no Django ORM model required).
    """
    tid = request.GET.get('id') or request.GET.get('task_id')
    if not tid:
        return JsonResponse({'error': 'missing id'}, status=400)

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    try:
        # fetch task row and human-friendly assignee display name
        cur.execute("""
            SELECT
              t.id,
              COALESCE(t.title, '') AS title,
              COALESCE(t.description, '') AS description,
              COALESCE(t.priority, '') AS priority,
              t.due_date,
              t.status,
              t.project_id,
              t.subproject_id,
              t.assigned_to,
              t.assigned_type,
              CASE
                WHEN t.assigned_type = 'member' THEN (SELECT CONCAT(m.first_name, ' ', m.last_name) FROM members m WHERE m.id = t.assigned_to)
                WHEN t.assigned_type = 'team' THEN (SELECT tm.name FROM teams tm WHERE tm.id = t.assigned_to)
                ELSE NULL
              END AS assigned_to_display
            FROM tasks t
            WHERE t.id = %s
            LIMIT 1
        """, (tid,))
        row = cur.fetchone()
        if not row:
            return JsonResponse({'error': 'task not found'}, status=404)

        # map columns to dict depending on cursor return type
        if isinstance(row, dict):
            data = row
        else:
            cols = [desc[0] for desc in cur.description]
            data = dict(zip(cols, row))

        # ensure date is serialized as iso string (or empty)
        due = data.get('due_date')
        if due is None:
            data['due_date'] = ''
        else:
            # if it's a date/datetime object, convert to ISO date
            try:
                data['due_date'] = due.isoformat()
            except Exception:
                data['due_date'] = str(due)

        # normalize assigned fields to strings
        data['assigned_to'] = data.get('assigned_to') or ''
        data['assigned_to_display'] = data.get('assigned_to_display') or ''
        print("DATA:", data)
        return JsonResponse({
            'id': data.get('id'),
            'title': data.get('title', ''),
            'description': data.get('description', ''),
            'priority': data.get('priority', ''),
            'due_date': data.get('due_date', ''),
            'status': data.get('status', ''),
            'project_id': data.get('project_id'),
            'subproject_id': data.get('subproject_id'),
            'assigned_type': data.get('assigned_type'),
            'assigned_to': data.get('assigned_to', ''),
            'assigned_to_display': data.get('assigned_to_display', ''),
        })

    finally:
        cur.close()


@require_GET
def api_tasks_search(request):
    """
    Simple task search used by the global quick-search UI.
    GET params: q
    Returns: { tasks: [ { id, title, status, assigned_to_display, project_name } ] }
    """
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'tasks': []})

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    try:
        like = f"%{q}%"
        cur.execute("""
            SELECT
                t.id,
                COALESCE(t.title, '') AS title,
                COALESCE(t.status, '') AS status,
                CASE
                    WHEN t.assigned_type = 'member' THEN (SELECT CONCAT(m.first_name, ' ', m.last_name) FROM members m WHERE m.id = t.assigned_to)
                    WHEN t.assigned_type = 'team' THEN (SELECT tm.name FROM teams tm WHERE tm.id = t.assigned_to)
                    ELSE NULL
                END AS assigned_to_display,
                (SELECT p.name FROM projects p WHERE p.id = t.project_id) AS project_name
            FROM tasks t
            WHERE (t.title LIKE %s OR t.description LIKE %s)
            ORDER BY t.id DESC
            LIMIT 20
        """, (like, like))

        rows = cur.fetchall() or []
        tasks = []
        if rows:
            if isinstance(rows[0], dict):
                for r in rows:
                    tasks.append({
                        'id': r.get('id'),
                        'title': r.get('title') or '',
                        'status': r.get('status') or '',
                        'assigned_to_display': r.get('assigned_to_display') or '',
                        'project_name': r.get('project_name') or ''
                    })
            else:
                cols = [d[0] for d in cur.description]
                for r in rows:
                    d = dict(zip(cols, r))
                    tasks.append({
                        'id': d.get('id'),
                        'title': d.get('title') or '',
                        'status': d.get('status') or '',
                        'assigned_to_display': d.get('assigned_to_display') or '',
                        'project_name': d.get('project_name') or ''
                    })

        return JsonResponse({'tasks': tasks})
    finally:
        cur.close()


@require_POST
def api_task_update(request):
    """
    Accepts form-data (task_id, title, description, priority, due_date, assigned_to_display, status)
    Returns { "ok": true } on success or { "ok": false, "error": "..." }
    Implemented using SQL updates against tenant DB (no ORM).
    """
    tid = request.POST.get('task_id')
    if not tid:
        return JsonResponse({'ok': False, 'error': 'missing task_id'}, status=400)

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    try:
        # check exists
        cur.execute("SELECT id, created_by FROM tasks WHERE id = %s LIMIT 1", (tid,))
        existing = cur.fetchone()
        if not existing:
            return JsonResponse({'ok': False, 'error': 'task not found'}, status=404)

        # collect fields to update
        updates = []
        params = []

        title = request.POST.get('title')
        if title is not None:
            updates.append("title = %s")
            params.append(title)

        description = request.POST.get('description')
        if description is not None:
            updates.append("description = %s")
            params.append(description)

        priority = request.POST.get('priority')
        if priority is not None:
            updates.append("priority = %s")
            params.append(priority)

        due_date = request.POST.get('due_date')
        if due_date:
            # Accept YYYY-MM-DD (frontend uses input[type=date])
            updates.append("due_date = %s")
            params.append(due_date)
        elif due_date == '':
            # explicit empty string -> set NULL
            updates.append("due_date = NULL")

        # --- ASSIGNED TO (member:ID or team:ID) ---
        # frontend posts field name "assigned_to" (value like "member:23" or "team:5", or empty string to unassign)
        assigned_raw = request.POST.get('assigned_to')
        if assigned_raw is not None:
            # explicit empty string -> clear assignment
            if assigned_raw == '':
                updates.append("assigned_to = NULL")
                updates.append("assigned_type = NULL")
            else:
                assigned_to_val, assigned_type_val = None, None
                if ":" in assigned_raw:
                    # expected format "member:23" or "team:5"
                    assigned_type_val, assigned_to_val = assigned_raw.split(":", 1)
                else:
                    # fallback assume member id
                    assigned_type_val, assigned_to_val = "member", assigned_raw
                updates.append("assigned_to = %s")
                params.append(assigned_to_val)
                updates.append("assigned_type = %s")
                params.append(assigned_type_val)
            # remember for activity logging after update
            _assigned_change = assigned_raw
        else:
            _assigned_change = None

        # If frontend posts assigned_to_display, update a display column (you have used assigned_to_display in UI)
        assigned_to_display = request.POST.get('assigned_to_display')
        if assigned_to_display is not None:
            # Ensure your table has this column; if not, you can skip or store in a comment field
            # For compatibility with your DB schema above, store it in assigned_to (if you use member: or team:)
            # Here we just store it to a display column if it exists
            try:
                # attempt to update assigned_to_display column if present
                cur.execute("SHOW COLUMNS FROM tasks LIKE 'assigned_to_display'")
                col = cur.fetchone()
                if col:
                    updates.append("assigned_to_display = %s")
                    params.append(assigned_to_display)
                else:
                    # if column absent, optionally skip — or update assigned_to raw (not ideal)
                    pass
            except Exception:
                # ignore schema-check errors and skip
                pass

        status = request.POST.get('status')
        if status is not None:
            updates.append("status = %s")
            params.append(status)

        if not updates:
            return JsonResponse({'ok': False, 'error': 'no fields to update'}, status=400)

        # build and execute update
        set_clause = ", ".join(updates)
        params.append(tid)
        sql = f"UPDATE tasks SET {set_clause}, updated_at = NOW() WHERE id = %s"
        cur.execute(sql, tuple(params))

        # optional: log activity
        performed_by = request.session.get("user_id")
        try:
            cur.execute(
                "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
                ("task", tid, f"updated_via_api", performed_by),
            )
        except Exception:
            # don't fail entire operation if logging fails
            pass

        conn.commit()
        return JsonResponse({'ok': True})
    except Exception as e:
        # log or return reasonable error message
        conn.rollback()
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
    finally:
        cur.close()

def task_board_view(request):
    status_columns = ["Open", "In Progress", "Review", "Blocked", "Closed"]
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cur.fetchall()
    cur.execute("SELECT id, email, first_name, last_name FROM members ORDER BY first_name")
    members = cur.fetchall()
    cur.execute("SELECT id, name FROM teams ORDER BY name")
    teams = cur.fetchall()
    cur.close()
    return render(
        request,
        "core/task_board.html",
        {"page": "task_board", "status_columns": status_columns,
         "projects": projects, "members": members, "teams": teams},
    )


@require_GET
def api_get_subprojects(request):
    """
    API endpoint: GET /tasks/api/subprojects/?project_id=<id>
    Returns: { subprojects: [ {id, name}, ... ] }
    """
    project_id = request.GET.get("project_id")
    if not project_id:
        return JsonResponse({"error": "Missing project_id"}, status=400)
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM subprojects WHERE project_id = %s ORDER BY name", (project_id,))
        rows = cur.fetchall()
        # handle both dict and tuple cursor
        subprojects = []
        if rows:
            if isinstance(rows[0], dict):
                subprojects = [{"id": r["id"], "name": r["name"]} for r in rows]
            else:
                subprojects = [{"id": r[0], "name": r[1]} for r in rows]
        return JsonResponse({"subprojects": subprojects})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        cur.close()
    

def task_detail_view(request, task_id):
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    cur.execute("SELECT id, title, description, status, priority, due_date, created_at FROM tasks WHERE id=%s", (task_id,))
    print("Executing SQL for task detail:", task_id)
    task = cur.fetchone()

    # Fetch timer history for this task
    cur.execute("""
        SELECT ts.id, ts.user_id, m.first_name, m.last_name, ts.start_time, ts.end_time, ts.duration_seconds, ts.notes
        FROM timer_sessions ts
        LEFT JOIN members m ON ts.user_id = m.id
        WHERE ts.task_id = %s
        ORDER BY ts.start_time DESC
    """, (task_id,))
    timer_history = cur.fetchall()
    cur.close()

    if not task:
        return render(request, "core/404.html", status=404)

    return render(request, "core/task_detail.html", {"task": task, "timer_history": timer_history})
def edit_task_view(request, task_id):
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    if request.method == "POST":
        data = request.POST
        title = data.get("title")
        description = data.get("description")
        due_date = data.get("due_date") or None
        priority = data.get("priority") or "Normal"
        status = data.get("status") or "Open"

        cur.execute(
            """UPDATE tasks
               SET title=%s, description=%s, status=%s, priority=%s, due_date=%s, updated_at=NOW()
               WHERE id=%s""",
            (title, description, status, priority, due_date, task_id),
        )
        conn.commit()
        # Re-fetch updated task
        cur.execute("SELECT id, title, description, status, priority, due_date, created_at FROM tasks WHERE id=%s", (task_id,))
        task = cur.fetchone()
        cur.close()
        if not task:
            return render(request, "core/404.html", status=404)
        return redirect("my_tasks")

    # GET
    cur.execute("SELECT id, title, description, status, priority, due_date, created_at FROM tasks WHERE id=%s", (task_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        return render(request, "core/404.html", status=404)

    # Ensure row is a dict for template compatibility and description is not None
    if isinstance(row, dict):
        task = row
    else:
        cols = [desc[0] for desc in cur.description]
        task = dict(zip(cols, row))
    cur.close()

    # Fix: If description is None, set to empty string
    if task.get('description') is None:
        task['description'] = ''

    return render(request, "core/edit_task.html", {"task": task})

@require_POST
def delete_task_view(request, task_id): 
    """Deletes the specified task."""
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    # Check if task exists
    cur.execute("SELECT id FROM tasks WHERE id=%s", (task_id,))
    task = cur.fetchone()
    if not task:
        cur.close()
        return render(request, "core/404.html", status=404)

    # Delete the task
    cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    cur.close()

    return redirect("my_tasks")


def export_task_pdf(request, task_id):
    """
    Export task details to PDF with professional formatting
    """
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    # Fetch task details
    cur.execute("""
        SELECT 
            t.id, t.title, t.description, t.status, t.priority, 
            t.due_date, t.created_at, t.assigned_to, t.assigned_type,
            CASE
                WHEN t.assigned_type = 'member' THEN (SELECT CONCAT(m.first_name, ' ', m.last_name) FROM members m WHERE m.id = t.assigned_to)
                WHEN t.assigned_type = 'team' THEN (SELECT tm.name FROM teams tm WHERE tm.id = t.assigned_to)
                ELSE NULL
            END AS assigned_to_display,
            (SELECT p.name FROM projects p WHERE p.id = t.project_id) AS project_name
        FROM tasks t 
        WHERE t.id=%s
    """, (task_id,))
    
    task = cur.fetchone()
    
    if not task:
        cur.close()
        return HttpResponse("Task not found", status=404)
    
    # Convert to dict if tuple
    if not isinstance(task, dict):
        cols = [desc[0] for desc in cur.description]
        task = dict(zip(cols, task))
    
    # Fetch timer history
    cur.execute("""
        SELECT ts.user_id, m.first_name, m.last_name, ts.start_time, 
               ts.end_time, ts.duration_seconds, ts.notes
        FROM timer_sessions ts
        LEFT JOIN members m ON ts.user_id = m.id
        WHERE ts.task_id = %s
        ORDER BY ts.start_time DESC
    """, (task_id,))
    timer_history = cur.fetchall()
    cur.close()
    
    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="task_{task_id}_{task.get("title", "details").replace(" ", "_")}.pdf"'
    
    # Create PDF document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#3b82f6'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12
    )
    
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        fontName='Helvetica-Bold',
        spaceAfter=4
    )
    
    # Add title
    elements.append(Paragraph(f"Task: {task.get('title', 'N/A')}", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Add status badge (simulated with colored text)
    status_text = f'<para align="center" backColor="#3b82f6" textColor="white" fontSize="10" fontName="Helvetica-Bold">&nbsp;&nbsp;{task.get("status", "N/A").upper()}&nbsp;&nbsp;</para>'
    elements.append(Paragraph(status_text, normal_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Create details table
    details_data = [
        ['DESCRIPTION', task.get('description', 'No description provided.')],
        ['DUE DATE', str(task.get('due_date', 'Not set'))],
        ['CREATED AT', str(task.get('created_at', 'N/A'))],
        ['PRIORITY', task.get('priority', 'Normal')],
        ['ASSIGNED TO', task.get('assigned_to_display', 'Unassigned')],
        ['PROJECT', task.get('project_name', 'N/A')]
    ]
    
    details_table = Table(details_data, colWidths=[2*inch, 4.5*inch])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1e293b')),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(details_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Add timer history section
    if timer_history and len(timer_history) > 0:
        elements.append(Paragraph("⏱️ TIMER HISTORY", heading_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Create timer table
        timer_data = [['User', 'Start Time', 'End Time', 'Duration', 'Notes']]
        for session in timer_history:
            if isinstance(session, dict):
                user = f"{session.get('first_name', '')} {session.get('last_name', '')}".strip() or str(session.get('user_id', 'N/A'))
                timer_data.append([
                    user,
                    str(session.get('start_time', 'N/A')),
                    str(session.get('end_time', '-')),
                    f"{session.get('duration_seconds', 0)}s",
                    str(session.get('notes', '-'))
                ])
            else:
                user = f"{session[1]} {session[2]}".strip() or str(session[0])
                timer_data.append([
                    user,
                    str(session[3]),
                    str(session[4] if session[4] else '-'),
                    f"{session[5]}s",
                    str(session[6] if session[6] else '-')
                ])
        
        timer_table = Table(timer_data, colWidths=[1.2*inch, 1.5*inch, 1.5*inch, 0.8*inch, 1.5*inch])
        timer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')])
        ]))
        
        elements.append(timer_table)
    else:
        elements.append(Paragraph("⏱️ TIMER HISTORY", heading_style))
        elements.append(Paragraph("No timer history found for this task.", normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF from buffer
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response