"""SGIERP Machine Dispatch views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.utils import timezone

from SGIERP.decorators import sgi_login_required, get_sgi_user
from SGIERP.models import Machine, MachineDispatch, MachineBOM, ItemProcess
from SGIERP.services import dispatch_machine, get_completed_process


@sgi_login_required
def dispatch_list(request):
    """Dispatch history page."""
    user = get_sgi_user(request)

    search = request.GET.get('q', '').strip()
    machine_filter = request.GET.get('machine', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    dispatches = MachineDispatch.objects.select_related(
        'machine', 'dispatched_by'
    ).prefetch_related('components__item')

    if search:
        dispatches = dispatches.filter(
            Q(machine__name__icontains=search) |
            Q(customer_name__icontains=search) |
            Q(invoice_reference__icontains=search)
        )
    if machine_filter:
        dispatches = dispatches.filter(machine_id=machine_filter)
    if date_from:
        dispatches = dispatches.filter(dispatch_date__date__gte=date_from)
    if date_to:
        dispatches = dispatches.filter(dispatch_date__date__lte=date_to)

    dispatches = dispatches.order_by('-dispatch_date')

    paginator = Paginator(dispatches, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    machines = Machine.objects.filter(is_active=True).order_by('code')

    context = {
        'page_obj': page_obj,
        'machines': machines,
        'search': search,
        'machine_filter': machine_filter,
        'date_from': date_from,
        'date_to': date_to,
        'page_title': 'Dispatch History',
    }
    return render(request, 'sgierp/dispatch/list.html', context)


@sgi_login_required
def dispatch_create(request):
    """Create a new machine dispatch."""
    user = get_sgi_user(request)
    machines = Machine.objects.filter(is_active=True).order_by('code')
    completed = get_completed_process()

    selected_machine = None
    bom_preview = []

    machine_id = request.GET.get('machine') or request.POST.get('machine_id')
    machine_count_str = request.GET.get('count', '1') or request.POST.get('machine_count', '1')

    try:
        machine_count = int(machine_count_str)
    except (ValueError, TypeError):
        machine_count = 1

    if machine_id:
        try:
            selected_machine = Machine.objects.prefetch_related('bom_items__item').get(
                id=machine_id, is_active=True
            )
            for entry in selected_machine.bom_items.all():
                avail = 0
                if completed:
                    result = entry.item.process_entries.filter(
                        process=completed, quantity__gt=0
                    ).aggregate(total=Sum('quantity'))
                    avail = result['total'] or 0
                required = entry.quantity_required * machine_count
                bom_preview.append({
                    'item': entry.item,
                    'quantity_required_per_machine': entry.quantity_required,
                    'total_required': required,
                    'available': avail,
                    'sufficient': avail >= required,
                })
        except Machine.DoesNotExist:
            pass

    if request.method == 'POST':
        mid = request.POST.get('machine_id', '').strip()
        mcount_str = request.POST.get('machine_count', '1').strip()
        customer = request.POST.get('customer_name', '').strip()
        dispatch_date_str = request.POST.get('dispatch_date', '').strip()
        invoice = request.POST.get('invoice_reference', '').strip()
        remarks = request.POST.get('remarks', '').strip()

        errors = []
        if not mid:
            errors.append('Please select a machine.')

        try:
            mcount = int(mcount_str)
            if mcount < 1:
                errors.append('Machine count must be at least 1.')
        except ValueError:
            mcount = 1
            errors.append('Invalid machine count.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/dispatch/create.html', {
                'machines': machines, 'selected_machine': selected_machine,
                'bom_preview': bom_preview, 'machine_count': machine_count,
                'form_data': request.POST, 'page_title': 'New Dispatch',
            })

        dispatch_date = None
        if dispatch_date_str:
            try:
                from django.utils.dateparse import parse_datetime
                dispatch_date = parse_datetime(dispatch_date_str)
            except Exception:
                pass

        try:
            dispatch = dispatch_machine(
                machine_id=int(mid),
                machine_count=mcount,
                customer_name=customer,
                dispatch_date=dispatch_date,
                invoice_reference=invoice,
                remarks=remarks,
                dispatched_by=user,
            )
            messages.success(
                request,
                f'Dispatch #{dispatch.id} created: {mcount}× {dispatch.machine.name}.'
            )
            return redirect('sgierp:dispatch_detail', dispatch_id=dispatch.id)
        except ValidationError as e:
            messages.error(request, str(e.message))
        except Exception as e:
            messages.error(request, f'Dispatch failed: {e}')

    context = {
        'machines': machines,
        'selected_machine': selected_machine,
        'bom_preview': bom_preview,
        'machine_count': machine_count,
        'form_data': request.GET,
        'now': timezone.now(),
        'page_title': 'New Dispatch',
    }
    return render(request, 'sgierp/dispatch/create.html', context)


@sgi_login_required
def dispatch_detail(request, dispatch_id):
    """Dispatch detail page."""
    dispatch = get_object_or_404(
        MachineDispatch.objects.select_related('machine', 'dispatched_by')
        .prefetch_related('components__item', 'components__source_entry'),
        id=dispatch_id
    )
    user = get_sgi_user(request)

    # Calculate blank rows for challan (total 10 rows)
    components_count = dispatch.components.count()
    blank_rows = max(0, 10 - components_count)

    context = {
        'dispatch': dispatch,
        'components': dispatch.components.all(),
        'blank_rows': range(blank_rows),
        'page_title': f'Dispatch #{dispatch.id}',
    }
    return render(request, 'sgierp/dispatch/detail.html', context)


@sgi_login_required
def dispatch_challan(request, dispatch_id):
    """Delivery challan page for printing."""
    dispatch = get_object_or_404(
        MachineDispatch.objects.select_related('machine', 'dispatched_by')
        .prefetch_related('components__item', 'components__source_entry'),
        id=dispatch_id
    )

    # Calculate blank rows for challan (total 10 rows)
    components_count = dispatch.components.count()
    blank_rows = max(0, 10 - components_count)

    context = {
        'dispatch': dispatch,
        'components': dispatch.components.all(),
        'blank_rows': range(blank_rows),
        'sgi_user': get_sgi_user(request),
        'sgi_profile': get_sgi_user(request).erp_profile if get_sgi_user(request) else None,
    }
    return render(request, 'sgierp/dispatch/challan.html', context)
