"""SGIERP Machine Dispatch views."""
import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.utils import timezone

from SGIERP.decorators import sgi_login_required, sgi_delete_passcode_required, get_sgi_user
from SGIERP.models import Machine, MachineDispatch, MachineBOM, ItemProcess, Item, ERPConfig
from SGIERP.services import dispatch_machine, dispatch_item, dispatch_mixed, delete_dispatch, get_completed_process


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
    """Create a new dispatch — supports a multi-item cart (machines + items)."""
    user = get_sgi_user(request)
    machines = Machine.objects.filter(is_active=True).order_by('code')
    completed = get_completed_process()

    completed_items = Item.objects.none()
    if completed:
        completed_items = (
            Item.objects.filter(
                is_active=True,
                process_entries__process=completed,
                process_entries__quantity__gt=0,
            )
            .distinct()
            .annotate(total_completed=Sum(
                'process_entries__quantity',
                filter=Q(process_entries__process=completed)
            ))
        )

    if request.method == 'POST':
        customer      = request.POST.get('customer_name', '').strip()
        dispatch_date_str = request.POST.get('dispatch_date', '').strip()
        invoice       = request.POST.get('invoice_reference', '').strip()
        remarks       = request.POST.get('remarks', '').strip()
        cart_json     = request.POST.get('cart_json', '').strip()

        dispatch_date = None
        if dispatch_date_str:
            try:
                from django.utils.dateparse import parse_datetime
                dispatch_date = parse_datetime(dispatch_date_str)
            except Exception:
                pass

        try:
            cart = json.loads(cart_json) if cart_json else []
        except (json.JSONDecodeError, TypeError):
            cart = []

        if not cart:
            messages.error(request, 'Cart is empty. Add at least one product or item.')
        else:
            # Build typed cart entries
            cart_entries = []
            errors = []
            for row in cart:
                rtype = row.get('type')
                if rtype == 'machine':
                    try:
                        cart_entries.append({
                            'type': 'machine',
                            'machine_id': int(row['machine_id']),
                            'count': int(row.get('count', 1)),
                        })
                    except (KeyError, ValueError, TypeError) as e:
                        errors.append(f'Invalid machine entry: {e}')
                elif rtype == 'item':
                    try:
                        cart_entries.append({
                            'type': 'item',
                            'item_id': int(row['item_id']),
                            'quantity': Decimal(str(row['quantity'])),
                        })
                    except (KeyError, ValueError, TypeError, InvalidOperation) as e:
                        errors.append(f'Invalid item entry: {e}')
                else:
                    errors.append(f'Unknown cart entry type: {rtype}')

            if errors:
                for e in errors:
                    messages.error(request, e)
            else:
                try:
                    dispatch = dispatch_mixed(
                        cart_entries=cart_entries,
                        customer_name=customer,
                        dispatch_date=dispatch_date,
                        invoice_reference=invoice,
                        remarks=remarks,
                        dispatched_by=user,
                    )
                    messages.success(request, f'Dispatch #{dispatch.id} created successfully.')
                    return redirect('sgierp:dispatch_detail', dispatch_id=dispatch.id)
                except ValidationError as e:
                    messages.error(request, str(e.message))
                except Exception as e:
                    messages.error(request, f'Dispatch failed: {e}')

    context = {
        'machines': machines,
        'completed_items': completed_items,
        'now': timezone.now(),
        'page_title': 'New Dispatch',
        'preselect_machine_id': request.GET.get('machine', ''),
    }
    return render(request, 'sgierp/dispatch/create.html', context)


@sgi_login_required
@require_GET
def dispatch_bom_preview(request):
    """AJAX: return BOM stock check for a machine + count. Optimised: 3 queries total."""
    machine_id = request.GET.get('machine_id')
    count_str  = request.GET.get('count', '1')

    try:
        mid   = int(machine_id)
        count = max(1, int(count_str))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Machine not found'}, status=404)

    # Query 1: completed process
    completed = get_completed_process()

    # Query 2: machine + all BOM entries + items in one shot
    try:
        machine = Machine.objects.prefetch_related(
            'bom_items__item'
        ).get(id=mid, is_active=True)
    except Machine.DoesNotExist:
        return JsonResponse({'error': 'Machine not found'}, status=404)

    bom_entries = list(machine.bom_items.all())  # already prefetched
    if not bom_entries:
        return JsonResponse({
            'machine_code': machine.code, 'machine_name': machine.name,
            'count': count, 'rows': [], 'all_ok': True, 'has_bom': False,
        })

    # Query 3: get ALL completed stock for ALL BOM items in one bulk query
    item_ids = [e.item_id for e in bom_entries]
    if completed:
        stock_qs = (
            ItemProcess.objects
            .filter(item_id__in=item_ids, process=completed)
            .values('item_id')
            .annotate(total=Sum('quantity'))
        )
        stock_map = {row['item_id']: float(row['total'] or 0) for row in stock_qs}
    else:
        stock_map = {}

    rows = []
    all_ok = True
    for entry in bom_entries:
        item     = entry.item
        avail    = stock_map.get(item.id, 0.0)
        required = float(entry.quantity_required * count)
        ok       = avail >= required
        if not ok:
            all_ok = False
        rows.append({
            'code': item.code,
            'name': item.name,
            'unit': item.unit,
            'per_machine': float(entry.quantity_required),
            'required': required,
            'available': avail,
            'ok': ok,
        })

    return JsonResponse({
        'machine_code': machine.code,
        'machine_name': machine.name,
        'count': count,
        'rows': rows,
        'all_ok': all_ok,
        'has_bom': True,
    })


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
