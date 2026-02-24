# core/rbac.py
"""
Centralized Role-Based Access Control (RBAC) System
This module provides all permission checking functionality for the application.
"""
import logging
from functools import wraps
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from .db_helpers import get_tenant_conn

logger = logging.getLogger('project_management')


def get_user_roles(conn, member_id, project_id=None):
    """
    Get all role IDs assigned to a member.
    
    Args:
        conn: Database connection
        member_id: ID of the member
        project_id: Optional project ID for project-specific roles
        
    Returns:
        List of role IDs
    """
    cur = conn.cursor()
    role_ids = set()
    
    try:
        # Get tenant-wide roles
        cur.execute(
            "SELECT role_id FROM tenant_role_assignments WHERE member_id=%s",
            (member_id,)
        )
        for row in cur.fetchall():
            role_ids.add(row['role_id'])
        
        # Get project-specific roles
        if project_id:
            # Specific project roles
            cur.execute(
                "SELECT role_id FROM project_role_assignments WHERE member_id=%s AND project_id=%s",
                (member_id, project_id)
            )
            for row in cur.fetchall():
                role_ids.add(row['role_id'])
        else:
            # If no project_id specified, get roles from ALL projects
            # This is important for actions like "create project" that don't have a project context
            cur.execute(
                "SELECT DISTINCT role_id FROM project_role_assignments WHERE member_id=%s",
                (member_id,)
            )
            for row in cur.fetchall():
                role_ids.add(row['role_id'])
    finally:
        cur.close()
    
    return list(role_ids)


def get_role_permissions(conn, role_ids):
    """
    Get all permission codes for given role IDs.
    
    Args:
        conn: Database connection
        role_ids: List of role IDs
        
    Returns:
        Set of permission codes
    """
    if not role_ids:
        return set()
    
    cur = conn.cursor()
    try:
        placeholders = ','.join(['%s'] * len(role_ids))
        query = f"""
            SELECT DISTINCT p.code 
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id IN ({placeholders})
        """
        cur.execute(query, tuple(role_ids))
        return {row['code'] for row in cur.fetchall()}
    finally:
        cur.close()


def has_permission(request, permission_code, project_id=None):
    """
    Check if the current user has a specific permission.
    
    Args:
        request: Django request object
        permission_code: Permission code to check (e.g., 'projects.create')
        project_id: Optional project ID for project-specific permission check
        
    Returns:
        Boolean indicating if user has the permission
    """
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return False
    
    conn = get_tenant_conn(request)
    try:
        role_ids = get_user_roles(conn, member_id, project_id)
        if not role_ids:
            return False
        
        permissions = get_role_permissions(conn, role_ids)
        return permission_code in permissions
    except Exception as e:
        logger.error(f"Error checking permission '{permission_code}' for member {member_id}: {e}")
        return False
    finally:
        conn.close()


def get_user_permissions(request, project_id=None):
    """
    Get all permissions for the current user.
    
    Args:
        request: Django request object
        project_id: Optional project ID for project-specific permissions
        
    Returns:
        Set of permission codes
    """
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return set()
    
    conn = get_tenant_conn(request)
    try:
        role_ids = get_user_roles(conn, member_id, project_id)
        return get_role_permissions(conn, role_ids)
    except Exception as e:
        logger.error(f"Error getting permissions for member {member_id}: {e}")
        return set()
    finally:
        conn.close()


def require_permission(permission_code, project_param='project_id', json_response=False):
    """
    Decorator to require a specific permission for a view.
    
    Args:
        permission_code: Permission code required (e.g., 'projects.create')
        project_param: Name of the parameter containing project_id
        json_response: If True, return JSON error instead of HTML
        
    Usage:
        @require_permission('projects.create')
        def create_project(request):
            ...
            
        @require_permission('tasks.edit', project_param='proj_id')
        def edit_task(request, proj_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            member_id = request.session.get('member_id') or request.session.get('user_id')
            if not member_id:
                if json_response:
                    return JsonResponse({'error': 'Authentication required'}, status=401)
                return redirect('login')
            
            # Try to get project_id from various sources
            project_id = (
                kwargs.get(project_param) or
                request.POST.get(project_param) or
                request.GET.get(project_param)
            )
            
            if has_permission(request, permission_code, project_id):
                return view_func(request, *args, **kwargs)
            
            logger.warning(
                f"Permission denied: member {member_id} attempted to access "
                f"{view_func.__name__} requiring '{permission_code}'"
            )
            
            if json_response:
                return JsonResponse({'error': 'Permission denied'}, status=403)
            return HttpResponseForbidden("You don't have permission to perform this action.")
        
        return wrapper
    return decorator


def is_admin(request):
    """
    Check if the current user has admin role.
    
    Args:
        request: Django request object
        
    Returns:
        Boolean indicating if user is admin
    """
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return False
    
    conn = get_tenant_conn(request)
    try:
        cur = conn.cursor()
        
        # Check if user has Admin role (tenant-wide)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM tenant_role_assignments tra
            JOIN roles r ON tra.role_id = r.id
            WHERE tra.member_id = %s AND r.name = 'Admin'
        """, (member_id,))
        
        result = cur.fetchone()
        cur.close()
        return result['count'] > 0
    except Exception as e:
        logger.error(f"Error checking admin status for member {member_id}: {e}")
        return False
    finally:
        conn.close()


def get_accessible_projects(request):
    """
    Get list of project IDs that the current user has access to.
    
    Args:
        request: Django request object
        
    Returns:
        List of project IDs
    """
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return []
    
    conn = get_tenant_conn(request)
    try:
        cur = conn.cursor()
        
        # Get projects where user has any role assigned
        cur.execute("""
            SELECT DISTINCT project_id
            FROM project_role_assignments
            WHERE member_id = %s
        """, (member_id,))
        
        project_ids = [row['project_id'] for row in cur.fetchall()]
        cur.close()
        return project_ids
    except Exception as e:
        logger.error(f"Error getting accessible projects for member {member_id}: {e}")
        return []
    finally:
        conn.close()


def check_project_access(request, project_id):
    """
    Check if user has any access to a specific project.
    
    Args:
        request: Django request object
        project_id: ID of the project
        
    Returns:
        Boolean indicating if user has access
    """
    if is_admin(request):
        return True
    
    accessible_projects = get_accessible_projects(request)
    return int(project_id) in accessible_projects


def assign_role_to_user(request, member_id, role_id, project_id=None, assigned_by=None):
    """
    Assign a role to a user (either tenant-wide or project-specific).
    
    Args:
        request: Django request object
        member_id: ID of the member to assign role to
        role_id: ID of the role to assign
        project_id: Optional project ID for project-specific assignment
        assigned_by: ID of the member assigning the role
        
    Returns:
        Boolean indicating success
    """
    conn = get_tenant_conn(request)
    try:
        cur = conn.cursor()
        
        if project_id:
            # Project-specific role assignment
            cur.execute("""
                INSERT IGNORE INTO project_role_assignments 
                (project_id, member_id, role_id, assigned_by)
                VALUES (%s, %s, %s, %s)
            """, (project_id, member_id, role_id, assigned_by))
        else:
            # Tenant-wide role assignment
            cur.execute("""
                INSERT IGNORE INTO tenant_role_assignments 
                (member_id, role_id, assigned_by)
                VALUES (%s, %s, %s)
            """, (member_id, role_id, assigned_by))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error assigning role {role_id} to member {member_id}: {e}")
        return False
    finally:
        conn.close()


def remove_role_from_user(request, member_id, role_id, project_id=None):
    """
    Remove a role from a user.
    
    Args:
        request: Django request object
        member_id: ID of the member
        role_id: ID of the role to remove
        project_id: Optional project ID for project-specific removal
        
    Returns:
        Boolean indicating success
    """
    conn = get_tenant_conn(request)
    try:
        cur = conn.cursor()
        
        if project_id:
            cur.execute("""
                DELETE FROM project_role_assignments
                WHERE member_id = %s AND role_id = %s AND project_id = %s
            """, (member_id, role_id, project_id))
        else:
            cur.execute("""
                DELETE FROM tenant_role_assignments
                WHERE member_id = %s AND role_id = %s
            """, (member_id, role_id))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error removing role {role_id} from member {member_id}: {e}")
        return False
    finally:
        conn.close()
