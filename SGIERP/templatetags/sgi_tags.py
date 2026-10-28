"""SGIERP custom template tags and filters."""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get a dictionary value by key — usage: {{ dict|get_item:key }}"""
    return dictionary.get(key, '')


@register.filter
def mul(value, arg):
    """Multiply two values."""
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def div(value, arg):
    """Divide two values safely."""
    try:
        divisor = float(arg)
        if divisor == 0:
            return 0
        return float(value) / divisor
    except (TypeError, ValueError):
        return 0


@register.filter
def percentage(value, total):
    """Return (value / total) * 100 as a float."""
    try:
        t = float(total)
        if t == 0:
            return 0
        return round(float(value) / t * 100, 1)
    except (TypeError, ValueError):
        return 0


@register.simple_tag
def url_replace(request, field, value):
    """Replace a single GET parameter, keeping the rest."""
    d = request.GET.copy()
    d[field] = value
    return d.urlencode()
