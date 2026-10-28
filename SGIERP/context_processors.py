"""SGIERP context processor — adds ERP user to all templates."""
from django.contrib.auth.models import User


def sgi_context(request):
    """Add SGIERP user info to all templates."""
    context = {}
    user_id = request.session.get('sgi_user_id')
    if user_id:
        try:
            user = User.objects.select_related('erp_profile').get(id=user_id, is_active=True)
            profile = user.erp_profile
            if profile.is_erp_active:
                context['sgi_user'] = user
                context['sgi_profile'] = profile
                context['is_sgi_admin'] = profile.role in ('admin', 'manager')
        except Exception:
            pass
    return context
