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


@register.filter
def short_timesince(value):
    """Return compact relative time: 'just now', '5m ago', '2h ago', '2d ago'."""
    if not value:
        return ''
    from django.utils import timezone
    from datetime import datetime
    try:
        now = timezone.now() if timezone.is_aware(value) else datetime.now()
        diff = now - value
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return 'just now'
        if seconds < 60:
            return 'just now'
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days == 1:
            return '1d ago'
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        return f"{days // 365}y ago"
    except Exception:
        return ''
