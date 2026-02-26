# core/context_processors.py
"""
Context processors for making data available to all templates
"""

from .db_helpers import get_tenant_work_types
from .rbac import get_user_permissions, is_admin as check_is_admin


def tenant_work_types(request):
    """
    Add tenant-specific work types to all template contexts.
    This allows the sidebar menu to show/hide work type creation links.
    """
    try:
        if hasattr(request, 'session') and request.session:
            work_types = get_tenant_work_types(request)
            # Use RBAC system to determine admin status
            admin_status = check_is_admin(request)

            return {
                'tenant_work_types': work_types,
                'has_task': 'Task' in work_types,
                'has_bug': 'Bug' in work_types,
                'has_story': 'Story' in work_types,
                'has_defect': 'Defect' in work_types,
                'has_subtask': 'Sub Task' in work_types,
                'has_change_request': 'Change Request' in work_types,
                'has_report': 'Report' in work_types,
                'is_admin': admin_status,
            }
    except Exception:
        pass
    
    # Fallback: show all work types if there's an error
    return {
        'tenant_work_types': ['Task', 'Bug', 'Story', 'Defect', 'Sub Task', 'Report', 'Change Request'],
        'has_task': True,
        'has_bug': True,
        'has_story': True,
        'has_defect': True,
        'has_subtask': True,
        'has_change_request': True,
        'has_report': True,
        'is_admin': False,
    }


def permissions_context(request):
    """
    Add user permissions to template context.
    This makes permissions available in all templates for menu visibility control.
    """
    if not request.session.get('member_id'):
        return {
            'user_permissions': set(),
            'user_is_admin': False,
            'user_role': None,
        }
    
    try:
        permissions = get_user_permissions(request)
        admin_status = check_is_admin(request)
        
        # Get user role from session
        user_data = request.session.get('user', {})
        user_role = user_data.get('role') if isinstance(user_data, dict) else None
        
        return {
            'user_permissions': permissions,
            'user_is_admin': admin_status,
            'user_role': user_role,
        }
    except Exception:
        return {
            'user_permissions': set(),
            'user_is_admin': False,
            'user_role': None,
        }

