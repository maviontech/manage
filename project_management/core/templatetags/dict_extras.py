from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Safely get dictionary[key]. Works for dicts and for objects exposing get().
    Usage in template: {{ mydict|get_item:some_key }}
    """
    if dictionary is None:
        return None
    try:
        # If it's a dict-like
        return dictionary.get(key)
    except Exception:
        # Fallback for mappings that don't implement get (or key types)
        try:
            return dictionary[key]
        except Exception:
            return None
