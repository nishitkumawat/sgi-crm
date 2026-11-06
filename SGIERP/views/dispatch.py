"""SGIERP Machine Dispatch views."""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.views.decorators.http import require_POST
from django.utils import timezone

from SGIERP.decorators import sgi_login_required, sgi_delete_passcode_required, get_sgi_user
from SGIERP.models import Machine, MachineDispatch, MachineBOM, ItemProcess, Item, ERPConfig
from SGIERP.services import dispatch_machine, dispatch_item, delete_dispatch, get_completed_process


def _get_default_per_page():
    try:
        return ERPConfig.get_solo().default_per_page
    except Exception:
        return '20'


@sgi_login_required
def dispatch_list(request):
    """Dispatch history page."""
    user = get_sgi_user(request)

    search = request.GET.get('q', '').strip()
    machine_filter = request.GET.get('machine', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    per_page = request.GET.get('per_page', _get_default_per_page())

    dispatches_qs = MachineDispatch.objects.select_related(
        'machine', 'dispatched_by'
    ).prefetch_related('components__item')

    if search:
        dispatches_qs = dispatches_qs.filter(
            Q(machine__name__icontains=search) |
            Q(customer_name__icontains=search) |
            Q(invoice_reference__icontains=search)
        )
    if machine_filter:
        dispatches_qs = dispatches_qs.filter(machine_id=machine_filter)
    if date_from:
        dispatches_qs = dispatches_qs.filter(dispatch_date__date__gte=date_from)
    if date_to:
        dispatches_qs = dispatches_qs.filter(dispatch_date__date__lte=date_to)

    dispatches_qs = dispatches_qs.order_by('-dispatch_date')

    # Pagination
    if per_page == 'all':
        dispatches = dispatches_qs.all()
        page_obj = None
        start_index = 1
        end_index = dispatches.count()
        total_count = dispatches.count()
    else:
        per_page_int = int(per_page)
        paginator = Paginator(dispatches_qs, per_page_int)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        dispatches = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1
        end_index = min(page_obj.number * per_page_int, paginator.count)
        total_count = paginator.count

    machines = Machine.objects.filter(is_active=True).order_by('code')
    units_total = sum(
        d.machine_count if d.machine_id else sum((component.quantity_consumed for component in d.components.all()), 0)
        for d in dispatches
    )

    context = {
        'dispatches': dispatches,
        'units_total': units_total,
        'page_obj': page_obj,
        'machines': machines,
        'search': search,
        'machine_filter': machine_filter,
        'date_from': date_from,
        'date_to': date_to,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
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
    selected_item = None
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
    bom_preview_totals = {
        'per_machine': sum((row['quantity_required_per_machine'] for row in bom_preview), 0),
        'required': sum((row['total_required'] for row in bom_preview), 0),
        'available': sum((row['available'] for row in bom_preview), 0),
    }
    item_id = request.GET.get('item') or request.POST.get('item_id')
    if item_id:
        selected_item = Item.objects.filter(id=item_id, is_active=True).first()

    completed_items = Item.objects.filter(is_active=True, process_entries__process=completed,
        process_entries__quantity__gt=0).distinct().annotate(
            total_completed=Sum('process_entries__quantity', filter=Q(process_entries__process=completed))
        ) if completed else Item.objects.none()

    if request.method == 'POST':
        mid = request.POST.get('machine_id', '').strip()
        mcount_str = request.POST.get('machine_count', '1').strip()
        customer = request.POST.get('customer_name', '').strip()
        dispatch_date_str = request.POST.get('dispatch_date', '').strip()
        invoice = request.POST.get('invoice_reference', '').strip()
        remarks = request.POST.get('remarks', '').strip()

        errors = []
        item_id = request.POST.get('item_id', '').strip()
        direct_item = request.POST.get('dispatch_mode') == 'single_item'
        if direct_item and not item_id:
            errors.append('Please select an item from the lookup list.')
        elif not direct_item and not mid:
            errors.append('Please select a product.')

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
                'completed_items': completed_items, 'selected_item': selected_item,
                'bom_preview': bom_preview, 'machine_count': machine_count,
                'bom_preview_totals': bom_preview_totals,
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
            if direct_item:
                quantity = Decimal(request.POST.get('item_quantity', '0'))
                dispatch = dispatch_item(int(item_id), quantity, customer, dispatch_date, invoice, remarks, user)
            else:
                dispatch = dispatch_machine(int(mid), mcount, customer, dispatch_date, invoice, remarks, user)
            messages.success(
                request,
                f'Dispatch #{dispatch.id} created.'
            )
            return redirect('sgierp:dispatch_detail', dispatch_id=dispatch.id)
        except ValidationError as e:
            messages.error(request, str(e.message))
        except Exception as e:
            messages.error(request, f'Dispatch failed: {e}')

    context = {
        'machines': machines,
        'completed_items': completed_items,
        'selected_item': selected_item,
        'selected_machine': selected_machine,
        'bom_preview': bom_preview,
        'bom_preview_totals': bom_preview_totals,
        'machine_count': machine_count,
        'form_data': request.POST if request.method == 'POST' else request.GET,
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
        'components_quantity_total': dispatch.components.aggregate(total=Sum('quantity_consumed'))['total'] or 0,
        'blank_rows': range(blank_rows),
        'page_title': f'Dispatch #{dispatch.id}',
    }
    return render(request, 'sgierp/dispatch/detail.html', context)


@sgi_login_required
@require_POST
@sgi_delete_passcode_required
def dispatch_delete(request, dispatch_id):
    """Delete a dispatch and restore the stock it consumed."""
    dispatch = get_object_or_404(MachineDispatch, id=dispatch_id)
    try:
        delete_dispatch(dispatch.id, deleted_by=get_sgi_user(request))
    except ValidationError as error:
        messages.error(request, error.messages[0] if error.messages else str(error))
        return redirect('sgierp:dispatch_detail', dispatch_id=dispatch.id)
    messages.success(request, f'Dispatch #{dispatch.id} deleted and stock restored.')
    return redirect('sgierp:dispatch_list')


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
