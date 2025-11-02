import csv, io, datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.shortcuts import get_object_or_404

# helper: get connection for current tenant
from .db_helpers import get_tenant_conn


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
        priority = data.get("priority") or "Normal"
        status = data.get("status") or "Open"
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
                assigned_to, assigned_type, created_by, due_date, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
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
            ),
        )
        task_id = cur.lastrowid

        # Log activity
        cur.execute(
            "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
            ("task", task_id, "created", created_by),
        )

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
    cur.close()

    return render(
        request,
        "core/create_task.html",
        {"projects": projects, "members": members, "teams": teams, "page": "task_create"},
    )


# ==============================
#  MY TASKS
# ==============================
def my_tasks_view(request):
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    user_id = request.session.get("user_id")

    # Match both assigned_to and assigned_type='member'
    cur.execute(
        """SELECT id, title, status, priority, due_date
           FROM tasks
           WHERE assigned_type='member' AND assigned_to = %s
           ORDER BY FIELD(status,'Open','In Progress','Review','Blocked','Closed'),
                    due_date IS NULL, due_date ASC""",
        (user_id,),
    )
    tasks = cur.fetchall()
    cur.close()

    today = datetime.date.today()
    return render(request, "core/tasks_my.html", {"tasks": tasks, "page": "my_tasks", "today": today})


# ==============================
#  UNASSIGNED TASKS
# ==============================
def unassigned_tasks_view(request):
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    sql = """SELECT t.id, t.title, t.priority, t.due_date, p.name AS project_name, t.created_at
             FROM tasks t
             LEFT JOIN projects p ON p.id = t.project_id
             WHERE t.assigned_to IS NULL OR t.assigned_type IS NULL
             ORDER BY t.priority DESC, t.due_date IS NULL, t.due_date ASC, t.created_at DESC"""
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
def task_board_view(request):
    status_columns = ["Open", "In Progress", "Review", "Blocked", "Closed"]
    return render(
        request,
        "core/task_board.html",
        {"page": "task_board", "status_columns": status_columns},
    )


from math import ceil
from django.http import JsonResponse

def board_data_api(request):
    """
    Paginated task data for the Kanban board.
    Compatible with both dict and tuple-returning cursors.
    """
    conn = get_tenant_conn(request)
    cur = conn.cursor()

    # ---- Pagination ----
    try:
        page = int(request.GET.get("page", "1"))
    except Exception:
        page = 1
    if page < 1:
        page = 1
    per_page = 10
    offset = (page - 1) * per_page

    # ---- Total count (works for dict or tuple) ----
    cur.execute("SELECT COUNT(*) AS total FROM tasks")
    row = cur.fetchone()
    if isinstance(row, dict):
        total_count = row.get("total", 0)
    elif isinstance(row, (list, tuple)):
        total_count = row[0]
    else:
        total_count = 0
    total_pages = ceil(total_count / per_page) if total_count else 1

    # ---- Main query ----
    cur.execute(f"""
        SELECT
            t.id,
            COALESCE(t.title, '(Untitled)') AS title,
            COALESCE(t.status, 'Open') AS status,
            COALESCE(t.priority, 'Normal') AS priority,
            t.due_date,
            CONCAT_WS(':', t.assigned_type, t.assigned_to) AS assigned_to,
            CASE
                WHEN t.assigned_type='member' THEN (
                    SELECT CONCAT(m.first_name, ' ', m.last_name)
                    FROM members m WHERE m.id=t.assigned_to
                )
                WHEN t.assigned_type='team' THEN (
                    SELECT tm.name FROM teams tm WHERE tm.id=t.assigned_to
                )
                ELSE NULL
            END AS assigned_to_display
        FROM tasks t
        ORDER BY
            FIELD(t.status,'Open','In Progress','Review','Blocked','Closed'),
            FIELD(t.priority,'Critical','High','Normal','Low'),
            t.due_date IS NULL ASC, t.due_date ASC, t.created_at DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))

    # ---- Convert rows to list of dicts ----
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

    cur.execute(
        "UPDATE tasks SET assigned_to=%s, assigned_type=%s, updated_at=NOW() WHERE id=%s",
        (assigned_to, assigned_type, task_id),
    )
    cur.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
        ("task", task_id, f"assigned_to:{assignee}", assigned_by),
    )
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

    if not task_id or not new_status:
        return HttpResponseBadRequest("Missing parameters")

    cur.execute("UPDATE tasks SET status=%s, updated_at=NOW() WHERE id=%s", (new_status, task_id))
    cur.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
        ("task", task_id, f"status_changed:{new_status}", user_id),
    )
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
                errors.append({"row": i, "error": str(e)})

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
    """
    tid = request.GET.get('id') or request.GET.get('task_id')
    if not tid:
        return HttpResponseBadRequest(json.dumps({'error': 'missing id'}), content_type='application/json')

    task = get_object_or_404(Task, pk=tid)
    # adapt field names to your model
    data = {
        'id': task.id,
        'title': task.title,
        'description': task.description or '',
        'priority': task.priority or '',
        'due_date': task.due_date.isoformat() if getattr(task, 'due_date', None) else '',
        'assigned_to': getattr(task, 'assigned_to', '') or '',
        'assigned_to_display': getattr(task, 'assigned_to_display', '') or '',
        'status': task.status,
    }
    return JsonResponse(data)


@require_POST
def api_task_update(request):
    """
    Accepts form-data (task_id, title, description, priority, due_date, assigned_to_display, status)
    Returns { "ok": true } on success or { "ok": false, "error": "..." }
    """
    tid = request.POST.get('task_id')
    if not tid:
        return JsonResponse({'ok': False, 'error': 'missing task_id'}, status=400)

    task = get_object_or_404(Task, pk=tid)

    # simple permission check: only owner or staff can update (customize as needed)
    if not (request.user.is_staff or task.created_by == request.user):
        # adapt permission logic to your app
        pass

    # update fields (validate as needed)
    title = request.POST.get('title')
    description = request.POST.get('description')
    priority = request.POST.get('priority')
    due_date = request.POST.get('due_date')
    assigned_to_display = request.POST.get('assigned_to_display')
    status = request.POST.get('status')

    if title is not None: task.title = title
    if description is not None: task.description = description
    if priority is not None: task.priority = priority
    if due_date:
        try:
            from django.utils.dateparse import parse_date
            task.due_date = parse_date(due_date)
        except Exception:
            pass
    if assigned_to_display is not None:
        # adapt to your way of storing assignee (here we set a display field)
        task.assigned_to_display = assigned_to_display
    if status is not None:
        task.status = status

    task.save()
    return JsonResponse({'ok': True})
