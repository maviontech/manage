import csv, io, datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.utils import timezone

# helper: get connection for current tenant
from core.db_helpers import get_tenant_conn


# ==============================
#  CREATE TASK  (GET / POST)
# ==============================
def create_task_view(request):
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
        assigned_to = data.get("assigned_to") or None
        status = data.get("status") or "Open"
        created_by = request.session.get("user_id")

        cur.execute(
            """INSERT INTO tasks
               (project_id, subproject_id, title, description, status, priority,
                assigned_to, created_by, due_date, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (project_id, subproject_id, title, description, status,
             priority, assigned_to, created_by, due_date)
        )
        task_id = cur.lastrowid

        # log activity
        cur.execute(
            "INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
            ("task", task_id, "created", created_by)
        )
        conn.commit()
        cur.close()

        # redirect to board or my tasks
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

    cur.execute(
        """SELECT id, title, status, priority, due_date
           FROM tasks
           WHERE assigned_to = %s
           ORDER BY FIELD(status,'Open','In Progress','Review','Blocked','Closed'),
                    due_date IS NULL, due_date ASC""",
        (user_id,),
    )
    tasks = cur.fetchall()
    cur.close()

    return render(request, "core/tasks_my.html", {"tasks": tasks, "page": "my_tasks"})


# ==============================
#  UNASSIGNED TASKS
# ==============================
def unassigned_tasks_view(request):
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    sql = """SELECT t.id, t.title, t.priority, t.due_date, p.name AS project_name, t.created_at
             FROM tasks t
             LEFT JOIN projects p ON p.id = t.project_id
             WHERE t.assigned_to IS NULL
             ORDER BY t.priority DESC, t.due_date IS NULL, t.due_date ASC, t.created_at DESC"""
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()

    return render(request, "core/unassigned_tasks.html", {"tasks": rows, "page": "unassigned_tasks"})


# ==============================
#  TASK BOARD PAGE + DATA
# ==============================
def task_board_view(request):
    status_columns = ["Open", "In Progress", "Review", "Blocked", "Closed"]
    return render(request, "core/task_board.html", {"page": "task_board", "status_columns": status_columns})



def board_data_api(request):
    """Return JSON payload for Kanban board"""
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, title, status, priority, assigned_to, due_date
           FROM tasks
           ORDER BY FIELD(status,'Open','In Progress','Review','Blocked','Closed'),
                    priority DESC, due_date IS NULL, due_date ASC"""
    )
    tasks = cur.fetchall()
    cur.close()
    return JsonResponse({"tasks": tasks})


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

    cur.execute("UPDATE tasks SET assigned_to=%s, updated_at=NOW() WHERE id=%s", (assignee, task_id))
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
        inserted = 0
        errors = []

        for i, row in enumerate(reader, start=1):
            try:
                cur.execute(
                    """INSERT INTO tasks
                       (project_id, subproject_id, title, description, status, priority,
                        assigned_to, created_by, due_date, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (
                        row.get("project_id") or None,
                        row.get("subproject_id") or None,
                        row["title"],
                        row.get("description"),
                        row.get("status") or "Open",
                        row.get("priority") or "Normal",
                        row.get("assigned_to") or None,
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
