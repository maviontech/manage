"""
Suggested improvements for roles and permissions functionality
These are optional enhancements to make the system more robust

To apply these improvements:
1. Review each function
2. Copy the improved code to the appropriate file
3. Test thoroughly
"""

# ============================================================================
# IMPROVEMENT 1: Add validation to assign_role view
# File: core/views_permissions.py
# ============================================================================

@require_POST
def assign_role_improved(request):
    """Improved version with validation"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")

    project_id = request.POST.get('project_id')
    target_member_id = request.POST.get('member_id')
    role_id = request.POST.get('role_id')
    action = request.POST.get('action')  # 'add' or 'remove'

    # Validation
    if not all([project_id, target_member_id, role_id, action]):
        messages.error(request, "All fields are required")
        return redirect('access_control_page')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Validate project exists
        cur.execute("SELECT id, name FROM projects WHERE id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            messages.error(request, "Project not found")
            return redirect('access_control_page')
        
        # Validate member exists
        cur.execute("SELECT id, email FROM members WHERE id=%s", (target_member_id,))
        member = cur.fetchone()
        if not member:
            messages.error(request, "Member not found")
            return redirect('access_control_page')
        
        # Validate role exists
        cur.execute("SELECT id, name FROM roles WHERE id=%s", (role_id,))
        role = cur.fetchone()
        if not role:
            messages.error(request, "Role not found")
            return redirect('access_control_page')
        
        if action == 'add':
            # Check if assignment already exists
            cur.execute("""
                SELECT id FROM project_role_assignments 
                WHERE project_id=%s AND member_id=%s AND role_id=%s
            """, (project_id, target_member_id, role_id))
            
            if cur.fetchone():
                messages.warning(request, f"{member['email']} already has {role['name']} role on {project['name']}")
            else:
                cur.execute("""
                    INSERT INTO project_role_assignments 
                    (project_id, member_id, role_id, assigned_by) 
                    VALUES (%s,%s,%s,%s)
                """, (project_id, target_member_id, role_id, member_id))
                
                # Audit log
                cur.execute("""
                    INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                    VALUES ('role_assignment', %s, %s, %s)
                """, (cur.lastrowid, f'assigned_{role["name"]}_to_{member["email"]}_on_{project["name"]}', member_id))
                
                messages.success(request, f"Assigned {role['name']} role to {member['email']} on {project['name']}")
        else:
            result = cur.execute("""
                DELETE FROM project_role_assignments 
                WHERE project_id=%s AND member_id=%s AND role_id=%s
            """, (project_id, target_member_id, role_id))
            
            if cur.rowcount > 0:
                # Audit log
                cur.execute("""
                    INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                    VALUES ('role_assignment', NULL, %s, %s)
                """, (f'removed_{role["name"]}_from_{member["email"]}_on_{project["name"]}', member_id))
                
                messages.success(request, f"Removed {role['name']} role from {member['email']} on {project['name']}")
            else:
                messages.warning(request, "Assignment not found")
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    finally:
        cur.close()
        conn.close()
    
    return redirect('access_control_page')


# ============================================================================
# IMPROVEMENT 2: Add validation to roles_save view
# File: core/views_permissions.py
# ============================================================================

@require_POST
def roles_save_improved(request):
    """Improved version with validation and audit logging"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'roles.manage'):
        return HttpResponseForbidden("Permission denied")

    role_id = request.POST.get('role_id')  # empty for create
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    permissions = request.POST.getlist('perm')  # list of permission ids

    # Validation
    if not name:
        messages.error(request, "Role name is required")
        return redirect('roles_page')
    
    if len(name) > 100:
        messages.error(request, "Role name must be 100 characters or less")
        return redirect('roles_page')
    
    if len(description) > 255:
        messages.error(request, "Description must be 255 characters or less")
        return redirect('roles_page')

    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        if role_id:
            # Check if role exists and is not builtin
            cur.execute("SELECT name, is_builtin FROM roles WHERE id=%s", (role_id,))
            existing = cur.fetchone()
            
            if not existing:
                messages.error(request, "Role not found")
                return redirect('roles_page')
            
            if existing['is_builtin']:
                messages.error(request, "Cannot modify builtin roles")
                return redirect('roles_page')
            
            # Check for duplicate name (excluding current role)
            cur.execute("SELECT id FROM roles WHERE name=%s AND id!=%s", (name, role_id))
            if cur.fetchone():
                messages.error(request, f"Role name '{name}' already exists")
                return redirect('roles_page')
            
            # Update role
            cur.execute("UPDATE roles SET name=%s, description=%s WHERE id=%s", 
                       (name, description, role_id))
            
            # Replace permissions
            cur.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
            for pid in permissions:
                cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", 
                           (role_id, pid))
            
            # Audit log
            cur.execute("""
                INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                VALUES ('role', %s, %s, %s)
            """, (role_id, f'updated_role_{name}', member_id))
            
            messages.success(request, f"Role '{name}' updated successfully")
        else:
            # Check for duplicate name
            cur.execute("SELECT id FROM roles WHERE name=%s", (name,))
            if cur.fetchone():
                messages.error(request, f"Role name '{name}' already exists")
                return redirect('roles_page')
            
            # Create new role
            cur.execute("INSERT INTO roles (name, description, is_builtin) VALUES (%s,%s,0)", 
                       (name, description))
            new_rid = cur.lastrowid
            
            # Add permissions
            for pid in permissions:
                cur.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", 
                           (new_rid, pid))
            
            # Audit log
            cur.execute("""
                INSERT INTO activity_log (entity_type, entity_id, action, performed_by)
                VALUES ('role', %s, %s, %s)
            """, (new_rid, f'created_role_{name}', member_id))
            
            messages.success(request, f"Role '{name}' created successfully")
    
    except Exception as e:
        messages.error(request, f"Error saving role: {str(e)}")
    finally:
        cur.close()
        conn.close()
    
    return redirect('roles_page')


# ============================================================================
# IMPROVEMENT 3: Add tenant-wide role management view
# File: core/views_permissions.py
# ============================================================================

def tenant_roles_page(request):
    """Manage tenant-wide role assignments (not project-specific)"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    # Fetch members
    cur.execute("SELECT id, email, first_name, last_name FROM members ORDER BY email")
    members = cur.fetchall()
    
    # Fetch roles
    cur.execute("SELECT id, name, description FROM roles ORDER BY name")
    roles = cur.fetchall()
    
    # Fetch tenant-wide assignments
    cur.execute("""
        SELECT tra.id, tra.member_id, tra.role_id, m.email, r.name as role_name
        FROM tenant_role_assignments tra
        JOIN members m ON tra.member_id = m.id
        JOIN roles r ON tra.role_id = r.id
        ORDER BY m.email, r.name
    """)
    assignments = cur.fetchall()
    
    # Build assignment map: member_id -> [role_ids]
    assign_map = {}
    for a in assignments:
        assign_map.setdefault(a['member_id'], []).append(a['role_id'])
    
    cur.close()
    conn.close()
    
    return render(request, 'core/tenant_roles.html', {
        'members': members,
        'roles': roles,
        'assignments': assignments,
        'assign_map': assign_map
    })


@require_POST
def assign_tenant_role(request):
    """Assign or remove tenant-wide role"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")
    
    target_member_id = request.POST.get('member_id')
    role_id = request.POST.get('role_id')
    action = request.POST.get('action')  # 'add' or 'remove'
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        if action == 'add':
            cur.execute("""
                INSERT IGNORE INTO tenant_role_assignments (member_id, role_id, assigned_by)
                VALUES (%s, %s, %s)
            """, (target_member_id, role_id, member_id))
            messages.success(request, "Tenant role assigned")
        else:
            cur.execute("""
                DELETE FROM tenant_role_assignments 
                WHERE member_id=%s AND role_id=%s
            """, (target_member_id, role_id))
            messages.success(request, "Tenant role removed")
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    finally:
        cur.close()
        conn.close()
    
    return redirect('tenant_roles_page')


# ============================================================================
# IMPROVEMENT 4: Add API endpoint for role permissions
# File: core/views_permissions.py
# ============================================================================

def api_role_permissions(request):
    """API endpoint to get permissions for a role"""
    role_id = request.GET.get('role_id')
    
    if not role_id:
        return JsonResponse({'error': 'role_id required'}, status=400)
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    try:
        # Get role info
        cur.execute("SELECT id, name, description FROM roles WHERE id=%s", (role_id,))
        role = cur.fetchone()
        
        if not role:
            return JsonResponse({'error': 'Role not found'}, status=404)
        
        # Get permissions
        cur.execute("""
            SELECT p.id, p.code, p.description
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = %s
            ORDER BY p.code
        """, (role_id,))
        permissions = cur.fetchall()
        
        return JsonResponse({
            'role': role,
            'permissions': permissions
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        cur.close()
        conn.close()


# ============================================================================
# IMPROVEMENT 5: Add bulk role assignment
# File: core/views_permissions.py
# ============================================================================

@require_POST
def bulk_assign_roles(request):
    """Assign same role to multiple members on a project"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'members.manage_roles'):
        return HttpResponseForbidden("Permission denied")
    
    project_id = request.POST.get('project_id')
    member_ids = request.POST.getlist('member_ids')  # list of member IDs
    role_id = request.POST.get('role_id')
    
    if not all([project_id, member_ids, role_id]):
        messages.error(request, "All fields are required")
        return redirect('access_control_page')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    success_count = 0
    error_count = 0
    
    try:
        for target_member_id in member_ids:
            try:
                cur.execute("""
                    INSERT IGNORE INTO project_role_assignments 
                    (project_id, member_id, role_id, assigned_by)
                    VALUES (%s, %s, %s, %s)
                """, (project_id, target_member_id, role_id, member_id))
                
                if cur.rowcount > 0:
                    success_count += 1
            except Exception:
                error_count += 1
        
        if success_count > 0:
            messages.success(request, f"Assigned role to {success_count} member(s)")
        if error_count > 0:
            messages.warning(request, f"Failed to assign role to {error_count} member(s)")
    
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    finally:
        cur.close()
        conn.close()
    
    return redirect('access_control_page')


# ============================================================================
# IMPROVEMENT 6: Add role usage statistics
# File: core/views_permissions.py
# ============================================================================

def role_statistics(request):
    """Show statistics about role usage"""
    member_id = request.session.get('member_id')
    if not tp.user_has_permission(request, member_id, None, 'roles.manage'):
        return HttpResponseForbidden("Permission denied")
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    # Get role usage counts
    cur.execute("""
        SELECT r.id, r.name, 
               COUNT(DISTINCT pra.member_id) as project_assignments,
               COUNT(DISTINCT tra.member_id) as tenant_assignments
        FROM roles r
        LEFT JOIN project_role_assignments pra ON r.id = pra.role_id
        LEFT JOIN tenant_role_assignments tra ON r.id = tra.role_id
        GROUP BY r.id, r.name
        ORDER BY r.name
    """)
    stats = cur.fetchall()
    
    # Get permission usage
    cur.execute("""
        SELECT p.code, COUNT(DISTINCT rp.role_id) as role_count
        FROM permissions p
        LEFT JOIN role_permissions rp ON p.id = rp.permission_id
        GROUP BY p.id, p.code
        ORDER BY role_count DESC, p.code
    """)
    perm_stats = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render(request, 'core/role_statistics.html', {
        'role_stats': stats,
        'perm_stats': perm_stats
    })


# ============================================================================
# URL ADDITIONS
# Add these to core/urls.py
# ============================================================================

"""
# In core/urls.py, add these paths:

path('settings/tenant-roles/', vp.tenant_roles_page, name='tenant_roles_page'),
path('settings/tenant-roles/assign/', vp.assign_tenant_role, name='assign_tenant_role'),
path('api/role-permissions/', vp.api_role_permissions, name='api_role_permissions'),
path('settings/roles/bulk-assign/', vp.bulk_assign_roles, name='bulk_assign_roles'),
path('settings/roles/statistics/', vp.role_statistics, name='role_statistics'),
"""


# ============================================================================
# TEMPLATE IMPROVEMENT: Enhanced error handling in access_control.html
# ============================================================================

"""
Add this JavaScript to access_control.html for better error handling:

<script>
// Enhanced assignment map rendering with error handling
(function(){
  try {
    const assignMap = {{ assign_map|default:"null"|safe }};
    const projects = {{ projects|default:"[]"|safe }};
    const members = {{ members|default:"[]"|safe }};
    const roles = {{ roles|default:"[]"|safe }};
    
    if (!assignMap || !projects || !members || !roles) {
      console.warn('Missing data for assignment map rendering');
      return;
    }
    
    const tbody = document.getElementById('assignments-tbody');
    if (!tbody) {
      console.error('assignments-tbody element not found');
      return;
    }
    
    // Clear existing rows
    tbody.innerHTML = '';
    
    // Build role lookup
    const roleById = {};
    roles.forEach(r => roleById[String(r.id)] = r.name);
    
    // Render assignments
    let rowCount = 0;
    Object.entries(assignMap).forEach(([key, roleIds]) => {
      const [pid, mid] = key.split(',');
      const proj = projects.find(p => String(p.id) === String(pid));
      const mem = members.find(m => String(m.id) === String(mid));
      
      if (proj && mem && roleIds && roleIds.length) {
        const tr = document.createElement('tr');
        const roleChips = roleIds.map(id => 
          `<span class="chip">${roleById[String(id)] || id}</span>`
        ).join(' ');
        
        tr.innerHTML = `
          <td>${proj.name}</td>
          <td>${mem.email}</td>
          <td><div class="chips">${roleChips}</div></td>
        `;
        tbody.appendChild(tr);
        rowCount++;
      }
    });
    
    if (rowCount === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-note">No role assignments found</td></tr>';
    }
    
    console.log(`Rendered ${rowCount} role assignments`);
    
  } catch (err) {
    console.error('Error rendering assignment map:', err);
    const tbody = document.getElementById('assignments-tbody');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-note">Error loading assignments</td></tr>';
    }
  }
})();
</script>
"""
