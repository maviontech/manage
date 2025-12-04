# core/views_projects.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib import messages
from .db_helpers import get_tenant_conn_and_cursor
from .forms import ProjectForm, SubprojectForm
import math

PAGE_SIZE = 10

def projects_list(request):
    page = int(request.GET.get('page', 1))
    q = request.GET.get('q', '').strip()

    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        params = []
        where = "WHERE 1=1"
        if q:
            where += " AND (name LIKE %s OR description LIKE %s)"
            params += [f"%{q}%", f"%{q}%"]

        # count
        cur.execute(f"SELECT COUNT(*) AS c FROM projects {where};", params)
        total = cur.fetchone()['c']
        pages = max(1, math.ceil(total / PAGE_SIZE))
        offset = (page - 1) * PAGE_SIZE

        cur.execute(f"""
            SELECT p.*, u.full_name AS created_by_name
            FROM projects p
            LEFT JOIN users u ON p.created_by = u.id
            {where}
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [PAGE_SIZE, offset])
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render(request, "core/projects_list.html", {
        "projects": rows,
        "page": page,
        "pages": pages,
        "q": q,
        "total": total,
        "page_range": range(1, pages + 1),
    })


def projects_search_ajax(request):
    q = request.GET.get('q', '').strip()
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT id, name FROM projects WHERE name LIKE %s LIMIT 10", (f"%{q}%",))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return JsonResponse({"results": rows})

def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)
            try:
                cur.execute("""
                    INSERT INTO projects (name, description, start_date, tentative_end_date, status, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (data['name'], data['description'], data['start_date'] or None, data['tentative_end_date'] or None,
                      data['status'], request.session.get('user_id')))
                new_id = cur.lastrowid
                # optional activity log
                cur.execute("INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
                            ("project", new_id, "created project", request.session.get('user_id')))
            finally:
                cur.close(); conn.close()
            messages.success(request, "Project created.")
            return redirect(reverse('projects_list'))
    else:
        form = ProjectForm()

    return render(request, "core/project_create.html", {"form": form})

from datetime import date

def project_edit(request, project_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")
    finally:
        cur.close(); conn.close()

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)

            try:
                if data['status'] == 'Completed':
                    # END DATE HANDLED BY TRIGGER (NO NEED TO SET MANUALLY)
                    cur.execute("""
                        UPDATE projects
                        SET name=%s,
                            description=%s,
                            start_date=%s,
                            tentative_end_date=%s,
                            status=%s
                        WHERE id=%s
                    """, (
                        data['name'],
                        data['description'],
                        data['start_date'] or None,
                        data['tentative_end_date'] or None,
                        'Completed',
                        project_id
                    ))
                else:
                    cur.execute("""
                        UPDATE projects
                        SET name=%s,
                            description=%s,
                            start_date=%s,
                            tentative_end_date=%s,
                            status=%s,
                            end_date=NULL
                        WHERE id=%s
                    """, (
                        data['name'],
                        data['description'],
                        data['start_date'] or None,
                        data['tentative_end_date'] or None,
                        data['status'],
                        project_id
                    ))

                # Activity log
                cur.execute("""
                    INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                    VALUES (%s, %s, %s, %s)
                """, ("project", project_id, "updated project", request.session.get('user_id')))

                conn.commit()
            finally:
                cur.close()
                conn.close()

            messages.success(request, "Project updated.")
            return redirect(reverse('projects_list'))

    else:
        form = ProjectForm(initial={
            'name': project['name'],
            'description': project['description'],
            'start_date': project['start_date'],
            'tentative_end_date': project.get('tentative_end_date'),
            'status': project['status']
        })

    return render(request, "core/project_create.html", {"form": form, "editing": True, "project": project})
def subprojects_list(request, project_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")

        cur.execute("SELECT * FROM subprojects WHERE project_id=%s ORDER BY created_at DESC", (project_id,))
        subprojects = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render(request, "core/subprojects_list.html", {
        "project": project,
        "subprojects": subprojects
    })
def subproject_create(request, project_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")
    finally:
        cur.close()
        conn.close()

    if request.method == "POST":
        form = SubprojectForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)
            try:
                cur.execute("""
                    INSERT INTO subprojects (project_id, name, description, created_by)
                    VALUES (%s,%s,%s,%s)
                """, (project_id, data['name'], data['description'], request.session.get('user_id')))
                new_id = cur.lastrowid
                # optional activity log
                cur.execute("INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
                            ("subproject", new_id, "created subproject", request.session.get('user_id')))
            finally:
                cur.close(); conn.close()
            messages.success(request, "Subproject created.")
            return redirect(reverse('subprojects_list', args=[project_id]))
    else:
        form = SubprojectForm()

    return render(request, "core/subproject_create.html", {"form": form, "project": project})
def subproject_edit(request, project_id, sub_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")

        cur.execute("SELECT * FROM subprojects WHERE id=%s AND project_id=%s", (sub_id, project_id))
        subproject = cur.fetchone()
        if not subproject:
            return HttpResponseBadRequest("Subproject not found")
    finally:
        cur.close(); conn.close()

    if request.method == "POST":
        form = SubprojectForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)

            try:
                cur.execute("""
                    UPDATE subprojects
                    SET name=%s,
                        description=%s
                    WHERE id=%s AND project_id=%s
                """, (
                    data['name'],
                    data['description'],
                    sub_id,
                    project_id
                ))

                # Activity log
                cur.execute("""
                    INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                    VALUES (%s, %s, %s, %s)
                """, ("subproject", sub_id, "updated subproject", request.session.get('user_id')))

                conn.commit()
            finally:
                cur.close()
                conn.close()

            messages.success(request, "Subproject updated.")
            return redirect(reverse('subprojects_list', args=[project_id]))

    else:
        form = SubprojectForm(initial={
            'name': subproject['name'],
            'description': subproject['description']
        })

    return render(request, "core/subproject_create.html", {"form": form, "editing": True, "project": project, "subproject": subproject})