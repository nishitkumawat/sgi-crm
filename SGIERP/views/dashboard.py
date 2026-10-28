"""SGIERP Dashboard view."""
from django.shortcuts import render
from django.db.models import Sum, Count
from django.utils import timezone

from SGIERP.decorators import sgi_login_required, get_sgi_user
from SGIERP.models import Item, Process, ItemProcess, Machine, MachineDispatch
from SGIERP.services import get_dashboard_stats


@sgi_login_required
def dashboard(request):
    """Main SGIERP dashboard."""
    user = get_sgi_user(request)
    stats = get_dashboard_stats()

    # Recent entries
    recent_entries = ItemProcess.objects.select_related(
        'item', 'process', 'assigned_to'
    ).filter(quantity__gt=0).order_by('-updated_at')[:8]

    # Process-wise stock summary
    process_stock_raw = (
        ItemProcess.objects.filter(quantity__gt=0)
        .values('process__name', 'process__is_completed_process')
        .annotate(total=Sum('quantity'))
        .order_by('process__order')
    )
    process_stock = [
        {
            'process_name': r['process__name'],
            'total': r['total'] or 0,
            'is_completed': r['process__is_completed_process'],
        }
        for r in process_stock_raw if r['total']
    ]

    # Max total for progress bar width
    total_stock = sum(ps['total'] for ps in process_stock) or 1

    context = {
        'stats': stats,
        'recent_entries': recent_entries,
        'process_stock': process_stock,
        'total_stock': total_stock,
        'page_title': 'Dashboard',
    }
    return render(request, 'sgierp/dashboard/index.html', context)
