"""SGIERP context processor — adds ERP user and config to all templates."""
from django.contrib.auth.models import User


def sgi_context(request):
    """Add SGIERP user info and app config to all templates."""
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

    # Inject app-wide config (default rows per page, etc.)
    try:
        from SGIERP.models import ERPConfig
        config = ERPConfig.get_solo()
        context['erp_config'] = config
        context['default_per_page'] = config.default_per_page
    except Exception:
        context['default_per_page'] = '20'

    return context
