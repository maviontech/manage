# core/views_permissions.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden, JsonResponse
import pymysql
from . import tenant_permissions as tp
from .auth import hash_password, check_password  # your existing auth helpers
from django.utils import timezone
from datetime import timedelta

# Helper: tenant connection (replace with your actual function if different)
from .db_helpers import get_tenant_conn  # your existing helper (adapt import path)

# --- Change Password (user) ---
def change_password_page(request):
    import logging
    logger = logging.getLogger('project_management')

    # local import of auth helpers (adjust if your package layout differs)
    try:
        from .auth import check_password, hash_password
    except Exception:
        # fallback if views_permissions is not a package module
        from core.auth import check_password, hash_password

    if request.method == 'POST':
        cur_pw = request.POST.get('current_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        if new_pw != confirm:
            messages.error(request, "New passwords do not match.")
            return redirect('change_password')

        member_id = request.session.get('member_id')
        if not member_id:
            return redirect('login')

        # fetch stored hash
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        try:
            cur.execute("SELECT password_hash FROM users WHERE id=%s", (member_id,))
            row = cur.fetchone()
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        if not row:
            messages.error(request, "User not found.")
            return redirect('change_password')

        stored_hash = row.get('password_hash') if isinstance(row, dict) else row[0]

        # robust password check: check_password returns (ok, needs_rehash)
        try:
            ok, needs_rehash = check_password(cur_pw, stored_hash)
        except TypeError:
            # if legacy check_password signature (bool only), handle gracefully
            try:
                ok_bool = check_password(cur_pw, stored_hash)
                ok, needs_rehash = bool(ok_bool), False
            except Exception as e:
                logger.exception("Unexpected error while checking password: %s", e)
                messages.error(request, "An internal error occurred.")
                return redirect('change_password')
        except Exception as e:
            logger.exception("Error during password verification: %s", e)
            messages.error(request, "An internal error occurred.")
            return redirect('change_password')

        if not ok:
            messages.error(request, "Current password is incorrect.")
            return redirect('change_password')

        # If the stored hash validated but was not bcrypt, re-hash current password to bcrypt and persist.
        if needs_rehash:
            try:
                new_bcrypt = hash_password(cur_pw)
                conn_up = get_tenant_conn(request)
                cur_up = conn_up.cursor()
                try:
                    cur_up.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_bcrypt, member_id))
                    conn_up.commit()
                finally:
                    try:
                        cur_up.close()
                    except Exception:
                        pass
                    try:
                        conn_up.close()
                    except Exception:
                        pass
            except Exception as e:
                # log warning but do not block password change flow
                logger.warning("Rehash-to-bcrypt failed for user %s: %s", member_id, e)

        # optional: enforce password policy
        conn2 = get_tenant_conn(request)
        c2 = conn2.cursor()
        try:
            c2.execute("SELECT * FROM password_policies LIMIT 1")
            policy = c2.fetchone()
        finally:
            try:
                c2.close()
            except Exception:
                pass
            try:
                conn2.close()
            except Exception:
                pass

        if policy:
            # minimal checks (ensure keys exist in policy dict if using dict row)
            min_len = policy.get('min_length') if isinstance(policy, dict) else policy['min_length']
            require_number = policy.get('require_number') if isinstance(policy, dict) else policy['require_number']
            require_upper = policy.get('require_upper') if isinstance(policy, dict) else policy['require_upper']
            require_lower = policy.get('require_lower') if isinstance(policy, dict) else policy['require_lower']
            require_symbol = policy.get('require_symbol') if isinstance(policy, dict) else policy['require_symbol']

            if min_len and len(new_pw) < int(min_len):
                messages.error(request, f"Password must be at least {min_len} characters.")
                return redirect('change_password')
            if require_number and not any(ch.isdigit() for ch in new_pw):
                messages.error(request, "Password must contain a number.")
                return redirect('change_password')
            if require_upper and not any(ch.isupper() for ch in new_pw):
                messages.error(request, "Password must contain an uppercase letter.")
                return redirect('change_password')
            if require_lower and not any(ch.islower() for ch in new_pw):
                messages.error(request, "Password must contain a lowercase letter.")
                return redirect('change_password')
            if require_symbol and not any(not ch.isalnum() for ch in new_pw):
                messages.error(request, "Password must contain a symbol.")
                return redirect('change_password')

        # update with new bcrypt hash
        try:
            new_hash = hash_password(new_pw)
            conn3 = get_tenant_conn(request)
            cur3 = conn3.cursor()
            try:
                cur3.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, member_id))
                conn3.commit()
            finally:
                try:
                    cur3.close()
                except Exception:
                    pass
                try:
                    conn3.close()
                except Exception:
                    pass
        except Exception as e:
            logger.exception("Failed to update password for user %s: %s", member_id, e)
            messages.error(request, "Could not update password due to an internal error.")
            return redirect('change_password')

        messages.success(request, "Your password has been changed.")
        return redirect('change_password')

    return render(request, 'core/change_password.html', {})



# --- Password Reset Request ---
def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        row = cur.fetchone()
        if not row:
            # Don't reveal whether user exists
            messages.success(request, "If that email exists, we sent a reset link.")
            return redirect('password_reset_request')
        user_id = row['id']

        # create token
        token = tp.generate_token()
        expires_at = timezone.now() + timedelta(hours=1)
        cur.execute("INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s,%s,%s)", (user_id, token, expires_at))
        # TODO: send email with link - put tenant's domain/url
        reset_link = request.build_absolute_uri(reverse('password_reset_confirm') + f"?token={token}")
        # Use your email send function, for now print/log
        print("[reset] Password reset link for", email, reset_link)
        cur.close()
        conn.close()
        messages.success(request, "If that email exists, we sent a reset link (check logs).")
        return redirect('password_reset_request')
    return render(request, 'core/password_reset_request.html', {})

# --- Password Reset Confirm (via token) ---
def password_reset_confirm(request):
    token = request.GET.get('token') or request.POST.get('token')
    if request.method == 'POST':
        token = request.POST.get('token')
        new_pw = request.POST.get('new_password')
        confirm = request.POST.get('confirm_password')
        if new_pw != confirm:
            messages.error(request, "Passwords mismatch.")
            return redirect(request.path + f"?token={token}")
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, expires_at, used FROM password_reset_tokens WHERE token=%s", (token,))
        row = cur.fetchone()
        if not row:
            messages.error(request, "Invalid token.")
            return redirect('password_reset_request')
        if row['used']:
            messages.error(request, "Token already used.")
            return redirect('password_reset_request')
        if row['expires_at'] < timezone.now():
            messages.error(request, "Token expired.")
            return redirect('password_reset_request')

        # update password
        new_hash = hash_password(new_pw)
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, row['user_id']))
        cur.execute("UPDATE password_reset_tokens SET used=1 WHERE id=%s", (row['id'],))
        cur.close()
        conn.close()
        messages.success(request, "Password reset successful. Please login.")
        return redirect('login')

    # GET: show form if token valid (optional: don't expose)
    return render(request, 'core/password_reset_confirm.html', {'token': token})


# --- Roles & Permissions page (list & edit) ---
def roles_page(request):
    # require 'roles.manage' permission for tenant-level role editing (we treat project_id None)
    member_id = request.session.get('member_id')
    print("Roles page access by member:", member_id)
    if not tp.user_has_permission(request, member_id, None, 'roles.manage'):
        return HttpResponseForbidden("Permission denied")

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    # fetch roles
    cur.execute("SELECT id,name,description,is_builtin,created_at FROM roles ORDER BY is_builtin DESC, name ASC")
    roles = cur.fetchall()
    # fetch permissions grouped
    cur.execute("SELECT id,code,description FROM permissions ORDER BY code")
    permissions = cur.fetchall()
    # fetch role->perm map
    cur.execute("SELECT role_id, permission_id FROM role_permissions")
    rp = cur.fetchall()
    cur.close()
    conn.close()

    rp_map = {}
    for r in rp:
        rp_map.setdefault(r['role_id'], set()).add(r['permission_id'])

    return render(request, 'core/roles_page.html', {
        'roles': roles,
        'permissions': permissions,
        'rp_map': rp_map
    })


@require_POST
def roles_save(request):
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'roles.manage'):
        return HttpResponseForbidden("Permission denied")

    role_id = request.POST.get('role_id')  # empty for create
    name = request.POST.get('name')
    description = request.POST.get('description','')
    permissions = request.POST.getlist('perm')  # list of permission ids

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    if role_id:
        cur.execute("UPDATE roles SET name=%s, description=%s WHERE id=%s", (name, description, role_id))
        # replace mappings
        cur.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
        for pid in permissions:
            cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", (role_id, pid))
        messages.success(request, "Role updated.")
    else:
        cur.execute("INSERT INTO roles (name, description, is_builtin) VALUES (%s,%s,0)", (name, description))
        new_rid = cur.lastrowid
        for pid in permissions:
            cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", (new_rid, pid))
        messages.success(request, "Role created.")
    cur.close()
    conn.close()
    return redirect('roles_page')


@require_POST
def roles_delete(request):
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'roles.manage'):
        return HttpResponseForbidden("Permission denied")

    role_id = request.POST.get('role_id')
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    # prevent deleting builtin
    cur.execute("SELECT is_builtin FROM roles WHERE id=%s", (role_id,))
    r = cur.fetchone()
    if not r:
        messages.error(request, "Role not found.")
    elif r['is_builtin']:
        messages.error(request, "Cannot delete builtin role.")
    else:
        cur.execute("DELETE FROM roles WHERE id=%s", (role_id,))
        messages.success(request, "Role deleted.")
    cur.close()
    conn.close()
    return redirect('roles_page')


# --- Access Control page (assign role to project-member) ---
def access_control_page(request):
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    # fetch projects & members & roles & current assignments
    cur.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cur.fetchall()
    cur.execute("SELECT id, email, first_name, last_name FROM members ORDER BY email")
    members = cur.fetchall()
    cur.execute("SELECT id, name FROM roles ORDER BY name")
    roles = cur.fetchall()



    # inside access_control_page view (replace existing assignment map construction)
    cur.execute("SELECT project_id, member_id, role_id FROM project_role_assignments")
    assign_rows = cur.fetchall()
    cur.close()
    conn.close()
    # Build a string-keyed map: "projectid,memberid" -> [role_id, ...]
    assign_map = {}
    for a in assign_rows:
        # normalize values to strings (in case cursor returns ints)
        proj = str(a['project_id'])
        mem = str(a['member_id'])
        key = proj + ',' + mem
        assign_map.setdefault(key, []).append(a['role_id'])

    return render(request, 'core/access_control.html', {
        'projects': projects,
        'members': members,
        'roles': roles,
        'assign_map': assign_map
    })


@require_POST
def assign_role(request):
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")

    project_id = request.POST.get('project_id')
    target_member_id = request.POST.get('member_id')
    role_id = request.POST.get('role_id')
    action = request.POST.get('action')  # 'add' or 'remove'

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    if action == 'add':
        cur.execute("INSERT IGNORE INTO project_role_assignments (project_id, member_id, role_id, assigned_by) VALUES (%s,%s,%s,%s)",
                    (project_id, target_member_id, role_id, member_id))
        messages.success(request, "Role assigned.")
    else:
        cur.execute("DELETE FROM project_role_assignments WHERE project_id=%s AND member_id=%s AND role_id=%s",
                    (project_id, target_member_id, role_id))
        messages.success(request, "Role removed.")
    cur.close()
    conn.close()
    return redirect('access_control_page')


# --- Password Policy page (tenant-level edit) ---
def password_policy_page(request):
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'settings.edit'):
        return render(request, 'core/Permission_denied.html')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    if request.method == 'POST':
        min_length = int(request.POST.get('min_length',8))
        require_upper = 1 if request.POST.get('require_upper')=='on' else 0
        require_lower = 1 if request.POST.get('require_lower')=='on' else 0
        require_number = 1 if request.POST.get('require_number')=='on' else 0
        require_symbol = 1 if request.POST.get('require_symbol')=='on' else 0

        cur.execute("SELECT COUNT(*) AS c FROM password_policies")
        if cur.fetchone()['c'] == 0:
            cur.execute("INSERT INTO password_policies (min_length, require_upper, require_lower, require_number, require_symbol) VALUES (%s,%s,%s,%s,%s)",
                        (min_length, require_upper, require_lower, require_number, require_symbol))
        else:
            cur.execute("UPDATE password_policies SET min_length=%s, require_upper=%s, require_lower=%s, require_number=%s, require_symbol=%s",
                        (min_length, require_upper, require_lower, require_number, require_symbol))
        messages.success(request, "Password policy updated.")
        cur.close()
        conn.close()
        return redirect('password_policy_page')

    cur.execute("SELECT * FROM password_policies LIMIT 1")
    policy = cur.fetchone()
    cur.close()
    conn.close()
    return render(request, 'core/password_policy.html', {'policy': policy})
