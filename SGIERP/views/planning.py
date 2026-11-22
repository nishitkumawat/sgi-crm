"""SGIERP Production Planning views (Single Global Plan)."""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction, models
from django.db.models import Sum, Q, Max
from django.views.decorators.http import require_POST, require_GET

from SGIERP.decorators import sgi_login_required, get_sgi_user
from SGIERP.models import ProductionPlan, ProductionPlanItem, Machine, MachineBOM, ItemProcess, Process


def _get_completed_process():
    return Process.objects.filter(is_completed_process=True).first()


def _get_single_plan():
    """Retrieve or create the single global production plan."""
    plan, _ = ProductionPlan.objects.get_or_create(
        id=1,
        defaults={
            'name': 'Production Plan',
            'description': 'Main factory production sequence',
        }
    )
    return plan


def _compute_plan_progress(plan_items, completed_process):
    """
    For each plan item (in order), compute:
      - Greedy stock consumption from row 1 downwards
      - First consumes Completed stock
      - Next consumes In-Process stock (excluding completed and rejected)
      - Subsequent rows receive remaining stock only
    """
    if not plan_items:
        return []

    machine_ids = list({entry['machine'].id for entry in plan_items})
    all_bom_map = {}
    bom_qs = MachineBOM.objects.filter(
        machine_id__in=machine_ids
    ).select_related('item').values('machine_id', 'item_id', 'quantity_required')

    for row in bom_qs:
        all_bom_map.setdefault(row['machine_id'], []).append(
            (row['item_id'], float(row['quantity_required']))
        )

    all_item_ids = {item_id for bom_list in all_bom_map.values() for item_id, _ in bom_list}
    comp_stock_map = {item_id: 0.0 for item_id in all_item_ids}
    in_proc_stock_map = {item_id: 0.0 for item_id in all_item_ids}

    if all_item_ids and completed_process:
        rows = ItemProcess.objects.filter(
            process=completed_process,
            item_id__in=all_item_ids,
        ).values('item_id').annotate(total=Sum('quantity'))
        for row in rows:
            comp_stock_map[row['item_id']] = float(row['total'] or 0)

    if all_item_ids:
        rows = ItemProcess.objects.filter(
            item_id__in=all_item_ids,
        ).exclude(
            Q(process__is_completed_process=True) | Q(process__is_rejected_process=True)
        ).values('item_id').annotate(total=Sum('quantity'))
        for row in rows:
            in_proc_stock_map[row['item_id']] = float(row['total'] or 0)

    result = []
    for entry in plan_items:
        machine = entry['machine']
        bom = all_bom_map.get(machine.id, [])
        target = entry['quantity']
        already_done = entry['completed_quantity']
        total_parts_required = sum(qty_req for _, qty_req in bom)

        unit_progress_bars = []
        for u in range(1, target + 1):
            is_marked_done = (u <= already_done)
            if is_marked_done:
                comp_parts = total_parts_required
                in_proc_parts = 0.0
                comp_pct = 100.0
                in_proc_pct = 0.0
                tot_pct = 100.0
                is_comp = True
                is_pipe = True
            elif not bom or total_parts_required <= 0:
                comp_parts = 0.0
                in_proc_parts = 0.0
                comp_pct = 0.0
                in_proc_pct = 0.0
                tot_pct = 0.0
                is_comp = False
                is_pipe = False
            else:
                comp_parts = 0.0
                in_proc_parts = 0.0
                for item_id, req_qty in bom:
                    # 1. Take from available completed stock
                    avail_c = comp_stock_map.get(item_id, 0.0)
                    used_c = min(req_qty, avail_c)
                    comp_parts += used_c
                    comp_stock_map[item_id] = max(0.0, avail_c - used_c)

                    # 2. Take remainder from available in-process stock
                    needed = req_qty - used_c
                    avail_ip = in_proc_stock_map.get(item_id, 0.0)
                    used_ip = min(needed, avail_ip)
                    in_proc_parts += used_ip
                    in_proc_stock_map[item_id] = max(0.0, avail_ip - used_ip)

                comp_pct = min(100.0, (comp_parts / total_parts_required * 100)) if total_parts_required else 0.0
                in_proc_pct = min(100.0 - comp_pct, (in_proc_parts / total_parts_required * 100)) if total_parts_required else 0.0
                tot_pct = comp_pct + in_proc_pct
                is_comp = comp_pct >= 99.99
                is_pipe = tot_pct >= 99.99

            unit_progress_bars.append({
                'unit_number': u,
                'is_marked_done': is_marked_done,
                'completed_percent': comp_pct,
                'in_process_percent': in_proc_pct,
                'total_percent': tot_pct,
                'completed_parts': comp_parts,
                'in_process_parts': in_proc_parts,
                'total_parts_required': total_parts_required,
                'is_fully_completed': is_comp,
                'is_fully_in_pipeline': is_pipe,
            })

        fully_ready_units = sum(1 for u in unit_progress_bars if u['is_fully_completed'])
        in_pipeline_units = sum(1 for u in unit_progress_bars if not u['is_fully_completed'] and u['is_fully_in_pipeline'])

        result.append({
            **entry,
            'bom': bom,
            'total_parts_required': total_parts_required,
            'unit_progress_bars': unit_progress_bars,
            'fully_ready_units': fully_ready_units,
            'in_pipeline_units': in_pipeline_units,
            'is_fully_completed': fully_ready_units >= target,
            'is_fully_in_pipeline': (fully_ready_units + in_pipeline_units) >= target,
        })
    return result


@sgi_login_required
def planning_view(request):
    """Single global production planning page."""
    plan = _get_single_plan()
    completed_process = _get_completed_process()

    plan_items_qs = plan.items.select_related('machine').order_by('order', 'id')
    raw_items = [
        {
            'id': item.id,
            'machine': item.machine,
            'quantity': item.quantity,
            'completed_quantity': item.completed_quantity,
            'order': item.order,
        }
        for item in plan_items_qs
    ]

    enriched_items = _compute_plan_progress(raw_items, completed_process)

    # Active machines available to add
    machines = list(Machine.objects.filter(is_active=True).order_by('code').values('id', 'code', 'name'))

    # Summary metrics
    total_items = len(enriched_items)
    total_units_target = sum(item['quantity'] for item in raw_items)
    total_units_ready = sum(item['fully_ready_units'] for item in enriched_items)
    total_units_in_pipeline = sum(item['in_pipeline_units'] for item in enriched_items)

    context = {
        'plan': plan,
        'enriched_items': enriched_items,
        'machines': machines,
        'completed_process': completed_process,
        'total_items': total_items,
        'total_units_target': total_units_target,
        'total_units_ready': total_units_ready,
        'total_units_in_pipeline': total_units_in_pipeline,
        'page_title': 'Production Planning',
    }
    return render(request, 'sgierp/planning/detail.html', context)


@sgi_login_required
@require_POST
def planning_add_item(request):
    """Add a product to the single production plan."""
    plan = _get_single_plan()
    machine_id = request.POST.get('machine_id')
    qty_raw = request.POST.get('quantity', '1')

    try:
        qty = max(1, int(qty_raw))
    except (ValueError, TypeError):
        qty = 1

    if not machine_id:
        messages.error(request, 'Please select a product.')
        return redirect('sgierp:planning_list')

    machine = get_object_or_404(Machine, id=machine_id)
    max_order = plan.items.aggregate(m=Max('order'))['m']
    next_order = 0 if max_order is None else max_order + 1

    ProductionPlanItem.objects.create(
        plan=plan,
        machine=machine,
        quantity=qty,
        order=next_order,
        completed_quantity=0,
    )
    messages.success(request, f'Added {machine.code} ({qty} unit{"s" if qty > 1 else ""}) to planning queue.')
    return redirect('sgierp:planning_list')


@sgi_login_required
@require_POST
def planning_delete_item(request, item_id):
    """Remove a product from the single plan."""
    plan = _get_single_plan()
    item = get_object_or_404(ProductionPlanItem, id=item_id, plan=plan)
    code = item.machine.code
    item.delete()
    messages.success(request, f'Removed {code} from plan.')
    return redirect('sgierp:planning_list')


@sgi_login_required
@require_POST
def planning_mark_done(request, item_id):
    """Increment or decrement completed units of a plan item."""
    plan = _get_single_plan()
    item = get_object_or_404(ProductionPlanItem, id=item_id, plan=plan)

    try:
        data = json.loads(request.body)
        delta = int(data.get('delta', 1))
    except Exception:
        delta = 1

    item.completed_quantity = min(item.quantity, max(0, item.completed_quantity + delta))
    item.save(update_fields=['completed_quantity'])
    return JsonResponse({'ok': True, 'completed_quantity': item.completed_quantity})


@sgi_login_required
@require_POST
def planning_update_qty(request, item_id):
    """Update target quantity of a plan item."""
    plan = _get_single_plan()
    item = get_object_or_404(ProductionPlanItem, id=item_id, plan=plan)
    try:
        qty = max(1, int(request.POST.get('quantity', 1)))
        item.quantity = qty
        if item.completed_quantity > qty:
            item.completed_quantity = qty
        item.save(update_fields=['quantity', 'completed_quantity'])
        messages.success(request, f'Updated {item.machine.code} quantity to {qty}.')
    except (ValueError, TypeError):
        messages.error(request, 'Invalid quantity.')
    return redirect('sgierp:planning_list')


@sgi_login_required
@require_POST
def planning_reorder(request):
    """AJAX: save new item order after drag-and-drop."""
    plan = _get_single_plan()
    try:
        data = json.loads(request.body)
        order_list = data.get('order', [])
    except Exception:
        return JsonResponse({'error': 'Invalid data'}, status=400)

    items = {item.id: item for item in plan.items.all()}
    with transaction.atomic():
        for idx, item_id in enumerate(order_list):
            if item_id in items:
                items[item_id].order = idx
                items[item_id].save(update_fields=['order'])

    return JsonResponse({'ok': True})


# Aliases & redirects for backward compatibility
planning_list = planning_view

@sgi_login_required
def planning_detail(request, plan_id=None):
    return redirect('sgierp:planning_list')

@sgi_login_required
def planning_create(request):
    return redirect('sgierp:planning_list')

@sgi_login_required
def planning_edit(request, plan_id=None):
    return redirect('sgierp:planning_list')

@sgi_login_required
def planning_delete(request, plan_id=None):
    plan = _get_single_plan()
    plan.items.all().delete()
    messages.success(request, 'Cleared all items from planning queue.')
    return redirect('sgierp:planning_list')
