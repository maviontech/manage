# core/templatetags/permission_tags.py
"""
Template tags for permission checking in templates.
"""
from django import template
from core.rbac import has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, permission_code, project_id=None):
    """
    Check if user has a specific permission.
    
    Usage in templates:
        {% load permission_tags %}
        {% has_perm 'projects.create' as can_create %}
        {% if can_create %}
            <button>Create Project</button>
        {% endif %}
        
        Or inline:
        {% if has_perm 'tasks.edit' task.project_id %}
            <button>Edit Task</button>
        {% endif %}
    """
    request = context.get('request')
    if not request:
        return False
    
    return has_permission(request, permission_code, project_id)


@register.filter
def has_permission_filter(request, permission_code):
    """
    Filter version for permission checking.
    
    Usage:
        {% if request|has_permission_filter:'projects.create' %}
            ...
        {% endif %}
    """
    return has_permission(request, permission_code)
