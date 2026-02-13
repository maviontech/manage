# core/context_processors.py
"""
Context processors for making data available to all templates
"""

from .db_helpers import get_tenant_work_types


def tenant_work_types(request):
    """
    Add tenant-specific work types to all template contexts.
    This allows the sidebar menu to show/hide work type creation links.
    """
    try:
        if hasattr(request, 'session') and request.session:
            work_types = get_tenant_work_types(request)
            # determine admin role from session user if present
            is_admin = False
            try:
                user = request.session.get('user')
                role = user.get('role') if isinstance(user, dict) else getattr(user, 'role', None)
                if role and 'admin' in str(role).lower():
                    is_admin = True
            except Exception:
                is_admin = False

            return {
                'tenant_work_types': work_types,
                'has_task': 'Task' in work_types,
                'has_bug': 'Bug' in work_types,
                'has_story': 'Story' in work_types,
                'has_defect': 'Defect' in work_types,
                'has_subtask': 'Sub Task' in work_types,
                'has_change_request': 'Change Request' in work_types,
                'has_report': 'Report' in work_types,
                'is_admin': is_admin,
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
