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


# ============================================================
# INITIAL STOCK ENTRY
# ============================================================
@transaction.atomic
def add_initial_stock(item, process, quantity, assigned_to=None, remarks='', performed_by=None, moved_at=None):
    """
    Add initial stock for an item in a given process.
    Creates or updates the ItemProcess record.
    """
    completed = get_completed_process()
    if completed and process.id == completed.id:
        assigned_to = None  # No assignment for completed process

    entry, created = ItemProcess.objects.get_or_create(
        item=item,
        process=process,
        defaults={'quantity': quantity, 'assigned_to': assigned_to}
    )
    if not created:
        entry.quantity = F('quantity') + quantity
        if assigned_to:
            entry.assigned_to = assigned_to
            entry.assigned_at = timezone.now()
        entry.save(update_fields=['quantity', 'assigned_to', 'assigned_at', 'updated_at'])
        entry.refresh_from_db()
    
    # Record history
    StockHistory.objects.create(
        item=item,
        from_process=None,  # No source for initial stock
        to_process=process,
        quantity=quantity,
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
def convert_item(source_item, target_item, source_process, target_process, source_quantity, target_quantity, assigned_to=None, remarks='', performed_by=None):
    """
    Convert one item to another (e.g., 55kg die → 2 shafts).
    Reduces source item quantity and adds target item quantity (optionally in a different process).
    """
    completed = get_completed_process()
    if completed and target_process.id == completed.id:
        assigned_to = None  # No assignment for completed process

    # Get or create source entry
    source_entry, _ = ItemProcess.objects.get_or_create(
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
    source_entry.refresh_from_db()
    
    # Get or create target entry
    target_entry, _ = ItemProcess.objects.get_or_create(
        item=target_item,
        process=target_process,
        defaults={'quantity': 0}
    )
    
    # Add target quantity
    target_entry.quantity = F('quantity') + target_quantity
    if assigned_to:
        target_entry.assigned_to = assigned_to
        target_entry.assigned_at = timezone.now()
    target_entry.save(update_fields=['quantity', 'assigned_to', 'assigned_at', 'updated_at'])
    target_entry.refresh_from_db()
    
    # Record conversion history
    StockHistory.objects.create(
        item=source_item,
        to_item=target_item,
        from_process=source_process,
        to_process=target_process,
        quantity=source_quantity,
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
               remarks='', performed_by=None):
    """
    Move `quantity` units from source_process to destination_process for an item.

    - Reduces quantity in source process.
    - Increases quantity in destination process.
    - Validates quantity and stock availability.

    Returns the updated source and destination ItemProcess records.
    """
    item = Item.objects.get(id=item_id)
    source_process = Process.objects.get(id=source_process_id, is_active=True)
    dest_process = Process.objects.get(id=destination_process_id, is_active=True)
    completed = get_completed_process()

    # Validations
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    if source_process_id == destination_process_id:
        raise ValidationError("Source and destination processes cannot be the same.")

    # If moving to Completed, clear assignment
    if completed and dest_process.id == completed.id:
        assigned_to = None

    # Get or create source entry
    source_entry, _ = ItemProcess.objects.get_or_create(
        item=item,
        process=source_process,
        defaults={'quantity': 0}
    )
    source_entry.refresh_from_db()

    if source_entry.quantity < quantity:
        raise ValidationError(
            f"Insufficient stock. Available: {source_entry.quantity}, "
            f"Requested: {quantity}"
        )

    # Capture source assignee before movement
    source_assignee = source_entry.assigned_to

    # Deduct from source
    source_entry.quantity = F('quantity') - quantity
    source_entry.save(update_fields=['quantity', 'updated_at'])
    source_entry.refresh_from_db()

    # Add to destination
    dest_entry, _ = ItemProcess.objects.get_or_create(
        item=item,
        process=dest_process,
        defaults={'quantity': 0, 'assigned_to': assigned_to}
    )
    dest_entry.quantity = F('quantity') + quantity
    if assigned_to:
        dest_entry.assigned_to = assigned_to
        dest_entry.assigned_at = timezone.now()
    dest_entry.save(update_fields=['quantity', 'assigned_to', 'assigned_at', 'updated_at'])
    dest_entry.refresh_from_db()

    # Record history
    StockHistory.objects.create(
        item=item,
        from_process=source_process,
        to_process=dest_process,
        quantity=quantity,
        movement_type='move',
        from_assignee=source_assignee,
        to_assignee=assigned_to,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        unit_snapshot=item.unit,
        from_process_name=source_process.name,
        to_process_name=dest_process.name,
        from_assignee_name=source_assignee.name if source_assignee else '',
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


# ============================================================
# DASHBOARD AGGREGATES
# ============================================================
def get_dashboard_stats():
    """Compute summary statistics for the dashboard."""
    from django.db.models import Count
    from django.utils import timezone

    today = timezone.now().date()
    completed = get_completed_process()
    process_entries_qs = ItemProcess.objects.filter(quantity__gt=0)

    total_items = Item.objects.filter(is_active=True).count()
    active_entries = process_entries_qs.count()

    # Quantities by process
    process_totals = list(
        process_entries_qs.values(
            'process__name', 'process__id', 'process__is_completed_process'
        ).annotate(total=Sum('quantity')).order_by('process__order')
    )

    in_production = sum(
        p['total'] for p in process_totals
        if not p['process__is_completed_process']
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
