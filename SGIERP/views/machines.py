"""SGIERP Machine views."""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum

from SGIERP.decorators import sgi_login_required, get_sgi_user
from SGIERP.models import Machine, MachineBOM, Item, MachineDispatch, ItemProcess
from SGIERP.services import get_completed_process


@sgi_login_required
def machine_list(request):
    """List all machines."""
    user = get_sgi_user(request)
    search = request.GET.get('q', '').strip()

    machines = Machine.objects.prefetch_related('bom_items__item')
    if search:
        machines = machines.filter(
            __import__('django.db.models', fromlist=['Q']).Q(code__icontains=search) |
            __import__('django.db.models', fromlist=['Q']).Q(name__icontains=search)
        )
    machines = machines.order_by('code')

    dispatch_counts = {}
    for m in machines:
        dispatch_counts[m.id] = MachineDispatch.objects.filter(machine=m).count()

    context = {
        'machines': machines,
        'dispatch_counts': dispatch_counts,
        'search': search,
        'page_title': 'Machines',
    }
    return render(request, 'sgierp/machines/list.html', context)


@sgi_login_required
def machine_create(request):
    """Create a new machine with BOM."""
    user = get_sgi_user(request)
    items = Item.objects.filter(is_active=True).order_by('code')

    if request.method == 'POST':
        return _save_machine(request, None)

    return render(request, 'sgierp/machines/form.html', {
        'machine': None, 'items': items, 'form_data': {},
        'page_title': 'Create Machine', 'bom_json': '[]',
    })


@sgi_login_required
def machine_edit(request, machine_id):
    """Edit existing machine and BOM."""
    machine = get_object_or_404(Machine, id=machine_id)
    user = get_sgi_user(request)
    items = Item.objects.filter(is_active=True).order_by('code')

    if request.method == 'POST':
        return _save_machine(request, machine)

    existing_bom = [
        {'item_id': b.item_id, 'item_code': b.item.code,
         'item_name': b.item.name, 'quantity': float(b.quantity_required)}
        for b in machine.bom_items.select_related('item').all()
    ]

    return render(request, 'sgierp/machines/form.html', {
        'machine': machine, 'items': items,
        'page_title': f'Edit {machine.code}',
        'bom_json': json.dumps(existing_bom),
    })


def _save_machine(request, machine=None):
    """Shared save logic for create/edit."""
    code = request.POST.get('code', '').strip().upper()
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    is_active = request.POST.get('is_active') == 'on'
    bom_data_raw = request.POST.get('bom_data', '[]')

    errors = []
    if not code:
        errors.append('Machine code is required.')
    if not name:
        errors.append('Machine name is required.')

    dup_check = Machine.objects.filter(code=code)
    if machine:
        dup_check = dup_check.exclude(id=machine.id)
    if dup_check.exists():
        errors.append(f'Machine code "{code}" already exists.')

    try:
        bom_data = json.loads(bom_data_raw)
    except (json.JSONDecodeError, ValueError):
        bom_data = []
        errors.append('Invalid BOM data.')

    # Validate BOM
    seen_items = set()
    for entry in bom_data:
        item_id = entry.get('item_id')
        qty = entry.get('quantity', 0)
        if not item_id:
            errors.append('BOM entry missing item.')
        if item_id in seen_items:
            errors.append(f'Duplicate item in BOM.')
        seen_items.add(item_id)
        if not qty or float(qty) <= 0:
            errors.append('BOM quantities must be positive.')

    if errors:
        items = Item.objects.filter(is_active=True).order_by('code')
        for e in errors:
            messages.error(request, e)
        return render(request, 'sgierp/machines/form.html', {
            'machine': machine, 'items': items,
            'form_data': request.POST,
            'page_title': f'Edit {machine.code}' if machine else 'Create Machine',
            'bom_json': bom_data_raw,
        })

    with transaction.atomic():
        if machine is None:
            machine = Machine(
                created_by=request.user if request.user.is_authenticated else None
            )
        machine.code = code
        machine.name = name
        machine.description = description
        machine.is_active = is_active
        if 'image' in request.FILES:
            machine.image = request.FILES['image']
        machine.save()

        # Replace BOM
        machine.bom_items.all().delete()
        for entry in bom_data:
            MachineBOM.objects.create(
                machine=machine,
                item_id=entry['item_id'],
                quantity_required=entry['quantity'],
            )

    messages.success(request, f'Machine {code} saved successfully.')
    return redirect('sgierp:machine_detail', machine_id=machine.id)


@sgi_login_required
def machine_detail(request, machine_id):
    """Machine detail with BOM and dispatch history."""
    machine = get_object_or_404(Machine, id=machine_id)
    user = get_sgi_user(request)
    completed = get_completed_process()

    bom_items = machine.bom_items.select_related('item').all()
    dispatches = machine.dispatches.select_related('dispatched_by').order_by('-dispatch_date')[:20]

    # Enrich BOM with available completed stock
    enriched_bom = []
    for entry in bom_items:
        avail = 0
        if completed:
            from django.db.models import Sum
            result = entry.item.process_entries.filter(
                process=completed
            ).aggregate(total=Sum('quantity'))
            avail = result['total'] or 0
        enriched_bom.append({
            'item': entry.item,
            'quantity_required': entry.quantity_required,
            'available_completed': avail,
        })

    context = {
        'machine': machine,
        'enriched_bom': enriched_bom,
        'dispatches': dispatches,
        'page_title': f'{machine.code} - {machine.name}',
    }
    return render(request, 'sgierp/machines/detail.html', context)
