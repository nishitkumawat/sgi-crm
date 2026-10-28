"""
SGIERP authentication decorators.
Uses Django session with 'sgi_user_id' key (Django User.id).
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth.models import User


def sgi_login_required(view_func):
    """Requires SGIERP user to be logged in."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('sgi_user_id'):
            return redirect('sgierp:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def sgi_admin_required(view_func):
    """Requires SGIERP user to be an admin."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('sgi_user_id'):
            return redirect('sgierp:login')
        try:
            user = User.objects.get(id=request.session['sgi_user_id'], is_active=True)
            profile = user.erp_profile
            if not profile.is_erp_active or profile.role != 'admin':
                return redirect('sgierp:dashboard')
        except Exception:
            request.session.flush()
            return redirect('sgierp:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_sgi_user(request):
    """Helper to get the current SGIERP user."""
    user_id = request.session.get('sgi_user_id')
    if not user_id:
        return None
    try:
        return User.objects.select_related('erp_profile').get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return None
