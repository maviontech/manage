# core/views_projects.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
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
    # Only tenant administrators may create projects
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return redirect('login')
    # Check tenant role assignment for Admin
    conn_check, cur_check = get_tenant_conn_and_cursor(request)
    try:
        cur_check.execute("""
            SELECT 1 FROM tenant_role_assignments tra
            JOIN roles r ON r.id = tra.role_id
            WHERE tra.member_id = %s AND r.name = 'Admin' LIMIT 1
        """, (member_id,))
        has_admin = cur_check.fetchone()
    finally:
        cur_check.close(); conn_check.close()
    if not has_admin:
        return render(request, 'authorize.html')

    # Fetch employees for dropdown
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("""
            SELECT id, employee_code, first_name, last_name 
            FROM employees 
            WHERE status = 'Active' 
            ORDER BY first_name, last_name
        """)
        employees = cur.fetchall()
    finally:
        cur.close(); conn.close()
    
    # Build employee choices
    employee_choices = [('', '-- Select Employee --')] + [
        (str(emp['id']), f"{emp['first_name']} {emp['last_name'] or ''} ({emp['employee_code']})")
        for emp in employees
    ]
    
    if request.method == "POST":
        form = ProjectForm(request.POST)
        form.fields['employee_id'].choices = employee_choices
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)
            try:
                employee_id = data.get('employee_id') or None
                if employee_id == '':
                    employee_id = None
                cur.execute("""
                    INSERT INTO projects (name, description, start_date, tentative_end_date, status, employee_id, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (data['name'], data['description'], data['start_date'] or None, data['tentative_end_date'] or None,
                      data['status'], employee_id, request.session.get('user_id')))
                new_id = cur.lastrowid
                # optional activity log
                cur.execute("INSERT INTO activity_log (entity_type, entity_id, action, performed_by) VALUES (%s,%s,%s,%s)",
                            ("project", new_id, "created project", request.session.get('user_id')))
                
                # Create notification for assigned employee
                if employee_id:
                    # Get employee's member_id (assuming employees table has member_id or we use id)
                    cur.execute("SELECT first_name, last_name FROM employees WHERE id=%s", (employee_id,))
                    emp = cur.fetchone()
                    if emp:
                        # Get creator name
                        cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (request.session.get('user_id'),))
                        creator = cur.fetchone()
                        creator_name = creator['name'] if creator else 'Someone'
                        
                        # Note: We need to find the member_id for this employee
                        # If employees table has a member_id field, use it. Otherwise, match by email or name
                        cur.execute("""
                            SELECT m.id FROM members m 
                            JOIN employees e ON (m.email = e.email OR (m.first_name = e.first_name AND m.last_name = e.last_name))
                            WHERE e.id = %s LIMIT 1
                        """, (employee_id,))
                        member = cur.fetchone()
                        
                        if member:
                            cur.execute("""
                                INSERT INTO notifications (user_id, title, message, type, link)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                member['id'],
                                "Assigned to New Project",
                                f"{creator_name} assigned you to project '{data['name']}'",
                                "project",
                                f"/projects/{new_id}"
                            ))
                
                conn.commit()
            finally:
                cur.close(); conn.close()
            messages.success(request, "Project created.")
            return redirect(reverse('projects_list'))
    else:
        form = ProjectForm()
        form.fields['employee_id'].choices = employee_choices

    return render(request, "core/project_create.html", {"form": form})

from datetime import date

def project_edit(request, project_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")
        
        # Fetch employees for dropdown
        cur.execute("""
            SELECT id, employee_code, first_name, last_name 
            FROM employees 
            WHERE status = 'Active' 
            ORDER BY first_name, last_name
        """)
        employees = cur.fetchall()
    finally:
        cur.close(); conn.close()
    
    # Build employee choices
    employee_choices = [('', '-- Select Employee --')] + [
        (str(emp['id']), f"{emp['first_name']} {emp['last_name'] or ''} ({emp['employee_code']})")
        for emp in employees
    ]

    if request.method == "POST":
        form = ProjectForm(request.POST)
        form.fields['employee_id'].choices = employee_choices
        if form.is_valid():
            data = form.cleaned_data
            conn, cur = get_tenant_conn_and_cursor(request)

            try:
                employee_id = data.get('employee_id') or None
                if employee_id == '':
                    employee_id = None
                    
                if data['status'] == 'Completed':
                    # END DATE HANDLED BY TRIGGER (NO NEED TO SET MANUALLY)
                    cur.execute("""
                        UPDATE projects
                        SET name=%s,
                            description=%s,
                            start_date=%s,
                            tentative_end_date=%s,
                            status=%s,
                            employee_id=%s
                        WHERE id=%s
                    """, (
                        data['name'],
                        data['description'],
                        data['start_date'] or None,
                        data['tentative_end_date'] or None,
                        'Completed',
                        employee_id,
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
                            employee_id=%s,
                            end_date=NULL
                        WHERE id=%s
                    """, (
                        data['name'],
                        data['description'],
                        data['start_date'] or None,
                        data['tentative_end_date'] or None,
                        data['status'],
                        employee_id,
                        project_id
                    ))

                # Activity log
                cur.execute("""
                    INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                    VALUES (%s, %s, %s, %s)
                """, ("project", project_id, "updated project", request.session.get('user_id')))

                # Create notification if employee assignment changed
                if employee_id and str(employee_id) != str(project.get('employee_id')):
                    # Get updater name
                    cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (request.session.get('user_id'),))
                    updater = cur.fetchone()
                    updater_name = updater['name'] if updater else 'Someone'
                    
                    # Find member_id for the employee
                    cur.execute("""
                        SELECT m.id FROM members m 
                        JOIN employees e ON (m.email = e.email OR (m.first_name = e.first_name AND m.last_name = e.last_name))
                        WHERE e.id = %s LIMIT 1
                    """, (employee_id,))
                    member = cur.fetchone()
                    
                    if member:
                        cur.execute("""
                            INSERT INTO notifications (user_id, title, message, type, link)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            member['id'],
                            "Assigned to Project",
                            f"{updater_name} assigned you to project '{data['name']}'",
                            "project",
                            f"/projects/{project_id}"
                        ))
                
                # Notify if project is completed
                if data['status'] == 'Completed' and project.get('status') != 'Completed':
                    # Get updater name
                    cur.execute("SELECT CONCAT(first_name, ' ', last_name) as name FROM members WHERE id=%s", (request.session.get('user_id'),))
                    updater = cur.fetchone()
                    updater_name = updater['name'] if updater else 'Someone'
                    
                    # Notify project creator if different from updater
                    if project.get('created_by') and str(project.get('created_by')) != str(request.session.get('user_id')):
                        cur.execute("""
                            INSERT INTO notifications (user_id, title, message, type, link)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            project['created_by'],
                            "Project Completed",
                            f"{updater_name} marked project '{data['name']}' as completed",
                            "success",
                            f"/projects/{project_id}"
                        ))
                    
                    # Notify assigned employee
                    if employee_id:
                        cur.execute("""
                            SELECT m.id FROM members m 
                            JOIN employees e ON (m.email = e.email OR (m.first_name = e.first_name AND m.last_name = e.last_name))
                            WHERE e.id = %s LIMIT 1
                        """, (employee_id,))
                        member = cur.fetchone()
                        
                        if member and str(member['id']) != str(request.session.get('user_id')):
                            cur.execute("""
                                INSERT INTO notifications (user_id, title, message, type, link)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                member['id'],
                                "Project Completed",
                                f"Project '{data['name']}' has been completed",
                                "success",
                                f"/projects/{project_id}"
                            ))

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
            'status': project['status'],
            'employee_id': str(project.get('employee_id')) if project.get('employee_id') else ''
        })
        form.fields['employee_id'].choices = employee_choices

    return render(request, "core/project_create.html", {"form": form, "editing": True, "project": project})
def subprojects_list(request, project_id):
    conn, cur = get_tenant_conn_and_cursor(request)
    try:
        cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return HttpResponseBadRequest("Project not found")

        # Search functionality
        q = request.GET.get('q', '').strip()

        if q:
            search_pattern = f"%{q}%"
            cur.execute("""
                SELECT *
                FROM subprojects
                WHERE project_id = %s
                AND (
                    name LIKE %s
                    OR description LIKE %s
                )
                ORDER BY created_at DESC
            """, (project_id, search_pattern, search_pattern))
        else:
            cur.execute("""
                SELECT *
                FROM subprojects
                WHERE project_id = %s
                ORDER BY created_at DESC
            """, (project_id,))

        subprojects = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render(request, "core/subprojects_list.html", {
        "project": project,
        "subprojects": subprojects,
        "q": q if q else ""
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

    return render(request, "core/subproject_create.html", {
        "form": form, 
        "project": project,
        "project_id": project_id
    })
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

    return render(request, "core/subproject_create.html", {
        "form": form, 
        "editing": True, 
        "project": project, 
        "subproject": subproject,
        "project_id": project_id
    })