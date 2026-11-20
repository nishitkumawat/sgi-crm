"""
SGIERP services — business logic for stock operations.
All stock-altering operations use atomic transactions.
"""
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, F
from django.core.exceptions import ValidationError

from .models import (
    Item, Process, ItemProcess, StockHistory,
    Machine, MachineBOM, MachineDispatch, DispatchComponent
)


# ============================================================
# PROCESS HELPERS
# ============================================================
def get_completed_process():
    """Return the special Completed process, or None."""
    return Process.objects.filter(is_completed_process=True, is_active=True).first()


def get_rejected_process():
    """Return the special Rejected process, or None."""
    return Process.objects.filter(is_rejected_process=True, is_active=True).first()


# ============================================================
# INITIAL STOCK ENTRY
# ============================================================
@transaction.atomic
def add_initial_stock(item, process, quantity, assigned_to=None, remarks='', performed_by=None, moved_at=None, price=0):
    """
    Add initial stock for an item in a given process.
    Creates or updates the ItemProcess record.
    Uses process object flags directly — no extra DB queries for terminal check.
    """
    # Use flags directly from the already-fetched process object (no extra queries)
    is_terminal_process = getattr(process, 'is_completed_process', False) or \
                          getattr(process, 'is_rejected_process', False)
    if is_terminal_process:
        assigned_to = None  # Terminal stock is not assigned to a worker

    entry, created = ItemProcess.objects.get_or_create(
        item=item,
        process=process,
        defaults={'quantity': quantity, 'assigned_to': assigned_to, 'price': price or 0}
    )
    if not created:
        entry.quantity = F('quantity') + quantity
        entry.price = price or 0
        if is_terminal_process:
            entry.assigned_to = None
            entry.assigned_at = None
        elif assigned_to:
            entry.assigned_to = assigned_to
            entry.assigned_at = timezone.now()
        entry.save(update_fields=['quantity', 'price', 'assigned_to', 'assigned_at', 'updated_at'])
        # No refresh_from_db — view redirects immediately after, return value not used

    # Record history
    StockHistory.objects.create(
        item=item,
        from_process=None,
        to_process=process,
        quantity=quantity,
        price=price or 0,
        movement_type='initial',
        from_assignee=None,
        to_assignee=assigned_to,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        unit_snapshot=item.unit,
        from_process_name='',
        to_process_name=process.name,
        from_assignee_name='',
        to_assignee_name=assigned_to.name if assigned_to else '',
        performed_by=performed_by,
        remarks=remarks,
    )

    return entry


# ============================================================
# ITEM CONVERSION
# ============================================================
@transaction.atomic
def convert_item(source_item, target_item, source_process, target_process, source_quantity, target_quantity, assigned_to=None, remarks='', performed_by=None, price=0):
    """
    Convert one item to another (e.g., 55kg die → 2 shafts).
    Uses process object flags directly — no extra queries for terminal check.
    """
    # Use flags from already-fetched process objects — no extra queries
    is_terminal_process = getattr(target_process, 'is_completed_process', False) or \
                          getattr(target_process, 'is_rejected_process', False)
    if is_terminal_process:
        assigned_to = None

    # Get or create source entry
    source_entry, _ = ItemProcess.objects.select_for_update().get_or_create(
        item=source_item,
        process=source_process,
        defaults={'quantity': 0}
    )

    # Check if enough quantity
    if source_entry.quantity < source_quantity:
        raise ValidationError(f'Insufficient quantity. Available: {source_entry.quantity} {source_item.unit}, Requested: {source_quantity} {source_item.unit}')

    # Reduce source quantity
    source_entry.quantity = F('quantity') - source_quantity
    source_entry.save(update_fields=['quantity', 'updated_at'])
    # No refresh_from_db — value not read back

    # Get or create target entry
    target_entry, _ = ItemProcess.objects.select_for_update().get_or_create(
        item=target_item,
        process=target_process,
        defaults={'quantity': 0}
    )

    # Add target quantity
    target_entry.quantity = F('quantity') + target_quantity
    target_entry.price = price or 0
    if is_terminal_process:
        target_entry.assigned_to = None
        target_entry.assigned_at = None
    elif assigned_to:
        target_entry.assigned_to = assigned_to
        target_entry.assigned_at = timezone.now()
    target_entry.save(update_fields=['quantity', 'price', 'assigned_to', 'assigned_at', 'updated_at'])
    # No refresh_from_db — view redirects after this

    # Record conversion history
    StockHistory.objects.create(
        item=source_item,
        to_item=target_item,
        from_process=source_process,
        to_process=target_process,
        quantity=source_quantity,
        price=price or 0,
        movement_type='convert',
        from_assignee=None,
        to_assignee=assigned_to,
        item_code_snapshot=source_item.code,
        item_name_snapshot=source_item.name,
        to_item_code_snapshot=target_item.code,
        to_item_name_snapshot=target_item.name,
        unit_snapshot=source_item.unit,
        from_process_name=source_process.name,
        to_process_name=target_process.name,
        from_assignee_name='',
        to_assignee_name=assigned_to.name if assigned_to else '',
        performed_by=performed_by,
        remarks=f'{source_quantity} {source_item.unit} @ {source_process.name} → {target_quantity} {target_item.unit} @ {target_process.name}. {remarks}'
    )

    return source_entry, target_entry


# ============================================================
# STOCK MOVEMENT (Process Transfer)
# ============================================================
@transaction.atomic
def move_stock(item_id, source_process_id, destination_process_id, quantity, assigned_to=None,
               remarks='', performed_by=None, price=0):
    """
    Move `quantity` units from source_process to destination_process for an item.
    Optimised: fetches item + both processes in a single query each, eliminates
    redundant refresh_from_db calls (saves 3 round-trips on remote DB).
    """
    # Single query per lookup — batch item + processes together
    try:
        item = Item.objects.only('id', 'code', 'name', 'unit').get(id=item_id)
    except Item.DoesNotExist:
        raise ValidationError("Item not found.")

    # Fetch both processes in one query
    processes = {
        p.id: p for p in Process.objects.filter(
            id__in=[source_process_id, destination_process_id]
        )
    }
    source_process = processes.get(source_process_id)
    dest_process   = processes.get(destination_process_id)
    if not source_process or not dest_process:
        raise ValidationError("Process not found.")

    # Use flags from already-fetched process objects — no extra queries
    is_terminal_destination = getattr(dest_process, 'is_completed_process', False) or \
                              getattr(dest_process, 'is_rejected_process', False)

    # Validations
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    if source_process_id == destination_process_id:
        raise ValidationError("Source and destination processes cannot be the same.")

    if is_terminal_destination:
        assigned_to = None

    # Get or create source entry with assignee pre-fetched — single query, no lazy load later
    source_entry, _ = ItemProcess.objects.select_related('assigned_to').select_for_update().get_or_create(
        item=item,
        process=source_process,
        defaults={'quantity': 0}
    )

    if source_entry.quantity < quantity:
        raise ValidationError(
            f"Insufficient stock. Available: {source_entry.quantity}, Requested: {quantity}"
        )

    # Capture assignee name now while it's cached — no extra query
    from_assignee_obj  = source_entry.assigned_to
    from_assignee_name = from_assignee_obj.name if from_assignee_obj else ''

    # Deduct from source
    source_entry.quantity = F('quantity') - quantity
    source_entry.save(update_fields=['quantity', 'updated_at'])
    # No refresh_from_db — we don't read the value back

    # Add to destination — single query
    dest_entry, _ = ItemProcess.objects.select_for_update().get_or_create(
        item=item,
        process=dest_process,
        defaults={'quantity': 0, 'assigned_to': assigned_to, 'price': price or 0}
    )
    dest_entry.quantity = F('quantity') + quantity
    dest_entry.price = price or 0
    if is_terminal_destination:
        dest_entry.assigned_to = None
        dest_entry.assigned_at = None
    elif assigned_to:
        dest_entry.assigned_to = assigned_to
        dest_entry.assigned_at = timezone.now()
    dest_entry.save(update_fields=['quantity', 'price', 'assigned_to', 'assigned_at', 'updated_at'])
    # No refresh_from_db — view redirects after this

    # Record history
    StockHistory.objects.create(
        item=item,
        from_process=source_process,
        to_process=dest_process,
        quantity=quantity,
        price=price or 0,
        movement_type='move',
        from_assignee=from_assignee_obj,
        to_assignee=assigned_to,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        unit_snapshot=item.unit,
        from_process_name=source_process.name,
        to_process_name=dest_process.name,
        from_assignee_name=from_assignee_name,
        to_assignee_name=assigned_to.name if assigned_to else '',
        performed_by=performed_by,
        remarks=remarks,
    )

    return source_entry, dest_entry


# ============================================================
# MACHINE DISPATCH (Atomic)
# ============================================================
@transaction.atomic
def dispatch_machine(machine_id, machine_count, customer_name='', dispatch_date=None,
                     invoice_reference='', remarks='', dispatched_by=None):
    """
    Dispatch `machine_count` units of a machine.
    Deducts required components from Completed stock.

    Raises ValidationError if:
    - Any component has insufficient Completed stock.
    - machine_count <= 0.

    Returns the MachineDispatch object.
    """
    if machine_count <= 0:
        raise ValidationError("Machine count must be at least 1.")

    machine = Machine.objects.get(id=machine_id, is_active=True)
    bom_items = machine.bom_items.select_related('item').all()
    completed = get_completed_process()

    if not completed:
        raise ValidationError("No Completed process configured. Cannot dispatch.")

    if not bom_items.exists():
        raise ValidationError("Machine has no BOM. Cannot dispatch.")

    dispatch_date = dispatch_date or timezone.now()

    # ---- Phase 1: Validate all components ----
    consumption_plan = []  # list of (item, needed_qty, process_entry)

    for bom_entry in bom_items:
        item = bom_entry.item
        needed = bom_entry.quantity_required * machine_count

        # Lock completed process entry
        process_entry = ItemProcess.objects.select_for_update().filter(
            item=item,
            process=completed,
        ).first()

        available = process_entry.quantity if process_entry else 0
        if available < needed:
            raise ValidationError(
                f"Insufficient completed stock for {item.code} - {item.name}. "
                f"Required: {needed}, Available: {available}"
            )

        consumption_plan.append((item, needed, process_entry))

    # ---- Phase 2: Create dispatch record ----
    dispatch = MachineDispatch.objects.create(
        machine=machine,
        machine_count=machine_count,
        customer_name=customer_name,
        dispatch_date=dispatch_date,
        invoice_reference=invoice_reference,
        dispatched_by=dispatched_by,
        remarks=remarks,
    )

    # ---- Phase 3: Consume stock ----
    for item, needed, process_entry in consumption_plan:
        # Capture assignee before consumption
        source_assignee = process_entry.assigned_to if process_entry else None
        
        # Create dispatch component record
        DispatchComponent.objects.create(
            dispatch=dispatch,
            item=item,
            source_entry=process_entry,
            quantity_consumed=needed,
            item_code_snapshot=item.code,
            item_name_snapshot=item.name,
            unit_snapshot=item.unit,
        )

        # Deduct from process entry
        process_entry.quantity = F('quantity') - needed
        process_entry.save(update_fields=['quantity', 'updated_at'])
        process_entry.refresh_from_db()
        
        # Record history for dispatch consumption
        StockHistory.objects.create(
            item=item,
            from_process=completed,
            to_process=completed,  # Dispatch is consumption within completed
            quantity=needed,
            movement_type='dispatch',
            from_assignee=source_assignee,
            to_assignee=None,
            item_code_snapshot=item.code,
            item_name_snapshot=item.name,
            unit_snapshot=item.unit,
            from_process_name=completed.name,
            to_process_name='Dispatched',
            from_assignee_name=source_assignee.name if source_assignee else '',
            to_assignee_name='',
            performed_by=dispatched_by,
            remarks=f'Dispatched for {machine.code} - {machine.name}',
        )

    return dispatch


@transaction.atomic
def dispatch_item(item_id, quantity, customer_name='', dispatch_date=None,
                  invoice_reference='', remarks='', dispatched_by=None):
    """Dispatch a catalog item directly from Completed stock."""
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero.")
    item = Item.objects.get(id=item_id, is_active=True)
    completed = get_completed_process()
    if not completed:
        raise ValidationError("No Completed process configured. Cannot dispatch.")
    entry = ItemProcess.objects.select_for_update().filter(item=item, process=completed).first()
    available = entry.quantity if entry else 0
    if available < quantity:
        raise ValidationError(f"Insufficient completed stock for {item.code} - {item.name}. Required: {quantity}, Available: {available}")
    dispatch = MachineDispatch.objects.create(
        machine=None, machine_count=1, customer_name=customer_name,
        dispatch_date=dispatch_date or timezone.now(), invoice_reference=invoice_reference,
        dispatched_by=dispatched_by, remarks=remarks,
    )
    source_assignee = entry.assigned_to
    DispatchComponent.objects.create(dispatch=dispatch, item=item, source_entry=entry,
        quantity_consumed=quantity, item_code_snapshot=item.code,
        item_name_snapshot=item.name, unit_snapshot=item.unit)
    entry.quantity = F('quantity') - quantity
    entry.save(update_fields=['quantity', 'updated_at'])
    entry.refresh_from_db()
    StockHistory.objects.create(item=item, from_process=completed, to_process=completed,
        quantity=quantity, movement_type='dispatch', from_assignee=source_assignee,
        item_code_snapshot=item.code, item_name_snapshot=item.name, unit_snapshot=item.unit,
        from_process_name=completed.name, to_process_name='Dispatched',
        from_assignee_name=source_assignee.name if source_assignee else '', performed_by=dispatched_by,
        remarks='Direct item dispatch')
    return dispatch


@transaction.atomic
def delete_dispatch(dispatch_id, deleted_by=None):
    """Remove a dispatch and restore its consumed stock, recording the reversal."""
    dispatch = MachineDispatch.objects.select_for_update().get(id=dispatch_id)
    completed = get_completed_process()
    components = list(dispatch.components.select_related('item', 'source_entry__process').all())

    for component in components:
        source_entry = component.source_entry
        if source_entry:
            source_entry = ItemProcess.objects.select_for_update().get(id=source_entry.id)
            process = source_entry.process
            assignee = source_entry.assigned_to
        else:
            if not completed:
                raise ValidationError('No Completed process configured; dispatch stock cannot be restored.')
            process = completed
            source_entry, _ = ItemProcess.objects.select_for_update().get_or_create(
                item=component.item, process=process, defaults={'quantity': 0}
            )
            assignee = source_entry.assigned_to

        source_entry.quantity += component.quantity_consumed
        source_entry.save(update_fields=['quantity', 'updated_at'])
        StockHistory.objects.create(
            item=component.item,
            from_process=None,
            to_process=process,
            quantity=component.quantity_consumed,
            movement_type='adjustment',
            to_assignee=assignee,
            item_code_snapshot=component.item_code_snapshot,
            item_name_snapshot=component.item_name_snapshot,
            unit_snapshot=component.unit_snapshot,
            from_process_name='Dispatch Cancelled',
            to_process_name=process.name,
            to_assignee_name=assignee.name if assignee else '',
            performed_by=deleted_by,
            remarks=f'Stock restored after deleting dispatch #{dispatch.id}.',
        )

    dispatch.delete()


@transaction.atomic
def dispatch_mixed(cart_entries, customer_name='', dispatch_date=None,
                   invoice_reference='', remarks='', dispatched_by=None):
    """
    Dispatch a mixed cart of products (machines) and/or standalone items
    in a single atomic transaction.

    cart_entries: list of dicts, each either:
        {'type': 'machine', 'machine_id': int, 'count': int}
        {'type': 'item',    'item_id':    int, 'quantity': Decimal}

    Returns the MachineDispatch object (machine=None for mixed/item-only dispatches,
    or the single machine if only one machine with no items).
    """
    if not cart_entries:
        raise ValidationError("Cart is empty. Add at least one product or item.")

    completed = get_completed_process()
    if not completed:
        raise ValidationError("No Completed process configured. Cannot dispatch.")

    dispatch_date = dispatch_date or timezone.now()

    # ---- Phase 1: Validate entire cart, build consumption plan ----
    consumption_plan = []  # list of (item, needed, process_entry, group_label)
    single_machine = None   # set if exactly one machine entry and no items
    machine_count_for_single = 1

    machine_entries = [e for e in cart_entries if e['type'] == 'machine']
    item_entries    = [e for e in cart_entries if e['type'] == 'item']

    if len(machine_entries) == 1 and not item_entries:
        single_machine_entry = machine_entries[0]
        single_machine = Machine.objects.get(id=single_machine_entry['machine_id'], is_active=True)
        machine_count_for_single = single_machine_entry['count']

    for entry in cart_entries:
        if entry['type'] == 'machine':
            machine_id = entry['machine_id']
            count = entry['count']
            if count < 1:
                raise ValidationError("Machine count must be at least 1.")
            machine = Machine.objects.get(id=machine_id, is_active=True)
            bom_items = machine.bom_items.select_related('item').all()
            if not bom_items.exists():
                raise ValidationError(f"Machine {machine.code} has no BOM. Cannot dispatch.")
            group_label = f"Machine: {machine.code} — {machine.name} ({count}×)"
            for bom_entry in bom_items:
                item = bom_entry.item
                needed = bom_entry.quantity_required * count
                process_entry = ItemProcess.objects.select_for_update().filter(
                    item=item, process=completed,
                ).first()
                available = process_entry.quantity if process_entry else 0
                if available < needed:
                    raise ValidationError(
                        f"Insufficient completed stock for {item.code} - {item.name} "
                        f"(needed for {machine.code}). Required: {needed}, Available: {available}"
                    )
                consumption_plan.append((item, needed, process_entry, group_label))

        elif entry['type'] == 'item':
            item_id = entry['item_id']
            quantity = entry['quantity']
            if quantity <= 0:
                raise ValidationError("Item quantity must be greater than zero.")
            item = Item.objects.get(id=item_id, is_active=True)
            group_label = f"Item: {item.code} — {item.name}"
            process_entry = ItemProcess.objects.select_for_update().filter(
                item=item, process=completed,
            ).first()
            available = process_entry.quantity if process_entry else 0
            if available < quantity:
                raise ValidationError(
                    f"Insufficient completed stock for {item.code} - {item.name}. "
                    f"Required: {quantity}, Available: {available}"
                )
            consumption_plan.append((item, quantity, process_entry, group_label))

    # ---- Phase 2: Create dispatch header ----
    dispatch = MachineDispatch.objects.create(
        machine=single_machine,
        machine_count=machine_count_for_single if single_machine else 1,
        customer_name=customer_name,
        dispatch_date=dispatch_date,
        invoice_reference=invoice_reference,
        dispatched_by=dispatched_by,
        remarks=remarks,
    )

    # ---- Phase 3: Consume stock ----
    for item, needed, process_entry, group_label in consumption_plan:
        source_assignee = process_entry.assigned_to if process_entry else None
        DispatchComponent.objects.create(
            dispatch=dispatch,
            item=item,
            source_entry=process_entry,
            quantity_consumed=needed,
            item_code_snapshot=item.code,
            item_name_snapshot=item.name,
            unit_snapshot=item.unit,
            group_label=group_label,
        )
        process_entry.quantity = F('quantity') - needed
        process_entry.save(update_fields=['quantity', 'updated_at'])
        process_entry.refresh_from_db()

        StockHistory.objects.create(
            item=item,
            from_process=completed,
            to_process=completed,
            quantity=needed,
            movement_type='dispatch',
            from_assignee=source_assignee,
            to_assignee=None,
            item_code_snapshot=item.code,
            item_name_snapshot=item.name,
            unit_snapshot=item.unit,
            from_process_name=completed.name,
            to_process_name='Dispatched',
            from_assignee_name=source_assignee.name if source_assignee else '',
            to_assignee_name='',
            performed_by=dispatched_by,
            remarks=f'Dispatched — {group_label}',
        )

    return dispatch


# ============================================================
# DASHBOARD AGGREGATES
# ============================================================
def get_dashboard_stats():
    """Compute summary statistics for the dashboard."""
    from django.db.models import Count
    from django.utils import timezone

    today = timezone.now().date()
    completed = get_completed_process()
    process_entries_qs = ItemProcess.objects.filter(quantity__gt=0).exclude(
        process__is_rejected_process=True
    )

    total_items = Item.objects.filter(is_active=True).count()
    active_entries = process_entries_qs.count()

    # Quantities by process
    process_totals = list(
        process_entries_qs.values(
            'process__name', 'process__id', 'process__is_completed_process', 'process__is_rejected_process'
        ).annotate(total=Sum('quantity')).order_by('process__order')
    )

    in_production = sum(
        p['total'] for p in process_totals
        if not p['process__is_completed_process'] and not p['process__is_rejected_process']
    ) or 0
    completed_stock = sum(
        p['total'] for p in process_totals
        if p['process__is_completed_process']
    ) or 0
    total_machines = Machine.objects.filter(is_active=True).count()
    dispatches_today = MachineDispatch.objects.filter(dispatch_date__date=today).count()

    # Low stock items
    low_stock_items = []
    for item in Item.objects.filter(is_active=True, min_stock_level__isnull=False):
        total_qty = item.total_quantity()
        if total_qty < item.min_stock_level:
            low_stock_items.append({
                'item': item,
                'total_qty': total_qty,
                'min_level': item.min_stock_level,
            })

    return {
        'total_items': total_items,
        'active_entries': active_entries,
        'completed_stock': completed_stock,
        'in_production': in_production,
        'process_totals': process_totals,
        'total_machines': total_machines,
        'dispatches_today': dispatches_today,
        'low_stock_items': low_stock_items,
    }
