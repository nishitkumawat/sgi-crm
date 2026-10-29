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
        profile = context.get('sgi_profile')
        context['erp_config'] = profile or config
        context['default_per_page'] = profile.default_per_page if profile else '20'
        themes = {
            'orange': ('#E65100', '#FF6D00', '#BF360C', '#FFF3E0'),
            'blue': ('#1565C0', '#1E88E5', '#0D47A1', '#E3F2FD'),
            'green': ('#2E7D32', '#43A047', '#1B5E20', '#E8F5E9'),
            'purple': ('#6A1B9A', '#8E24AA', '#4A148C', '#F3E5F5'),
            'red': ('#C62828', '#E53935', '#8E0000', '#FFEBEE'),
        }
        selected_theme = profile.primary_theme if profile else 'orange'
        theme = themes.get(selected_theme, themes['orange'])
        context['primary_theme'] = selected_theme
        context['primary_theme_css'] = f'--sgi-primary:{theme[0]};--sgi-primary-light:{theme[1]};--sgi-primary-dark:{theme[2]};--sgi-primary-bg:{theme[3]};'
    except Exception:
        context['default_per_page'] = '20'

    return context
