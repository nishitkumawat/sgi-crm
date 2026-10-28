"""SGIERP Inventory views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from django.db.models import Sum, Q, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ValidationError

from SGIERP.decorators import sgi_login_required, sgi_admin_required, get_sgi_user
from SGIERP.models import Item, Process, ItemProcess, Assignee, StockHistory
from SGIERP.services import add_initial_stock, move_stock, get_completed_process


@sgi_login_required
def item_catalog(request):
    """Item Catalog page — manage item definitions (code, name, unit, category)."""
    search = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', 'active')

    items_qs = Item.objects.all()

    if search:
        items_qs = items_qs.filter(
            Q(code__icontains=search) | Q(name__icontains=search)
        )
    if category_filter:
        items_qs = items_qs.filter(category__icontains=category_filter)
    if status_filter == 'inactive':
        items_qs = items_qs.filter(is_active=False)
    elif status_filter:
        items_qs = items_qs.filter(is_active=True)

    items = items_qs.order_by('code')

    # Get unique categories for filter - optimize
    categories = Item.objects.filter(is_active=True).values_list('category', flat=True).distinct()
    categories = sorted([c for c in categories if c])

    context = {
        'items': items,
        'categories': categories,
        'search': search,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'page_title': 'Item Catalog',
    }
    return render(request, 'sgierp/inventory/catalog.html', context)


@sgi_login_required
def inventory_list(request):
    """Main inventory listing — all items with process-wise stock as separate rows."""
    user = get_sgi_user(request)

    # Filters
    search = request.GET.get('q', '').strip()
    process_filter = request.GET.get('process', '')
    status_filter = request.GET.get('status', 'active')
    process_status = request.GET.get('process_status', 'non_completed')  # Default to non-completed

    # Get all items with stock - optimize
    entries_qs = ItemProcess.objects.filter(quantity__gt=0).select_related(
        'item', 'process', 'assigned_to'
    ).only(
        'id', 'quantity', 'assigned_at',
        'item__id', 'item__code', 'item__name', 'item__is_active', 'item__unit',
        'process__id', 'process__name', 'process__order', 'process__is_completed_process',
        'assigned_to__id', 'assigned_to__name'
    )

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )
    if process_filter:
        entries_qs = entries_qs.filter(process_id=int(process_filter))
    if status_filter == 'inactive':
        entries_qs = entries_qs.filter(item__is_active=False)
    elif status_filter:
        entries_qs = entries_qs.filter(item__is_active=True)
    
    # Filter by process status (completed/non-completed)
    completed = get_completed_process()
    if process_status == 'completed' and completed:
        entries_qs = entries_qs.filter(process=completed)
    elif process_status == 'non_completed' and completed:
        entries_qs = entries_qs.exclude(process=completed)

    entries = entries_qs.order_by('item__code', 'process__order', 'process__name')

    # Get all processes for filter dropdown - optimize
    processes = Process.objects.filter(is_active=True).order_by('order', 'name').only('id', 'name', 'order')

    context = {
        'entries': entries,
        'processes': processes,
        'search': search,
        'process_filter': process_filter,
        'status_filter': status_filter,
        'process_status': process_status,
        'page_title': 'Inventory',
    }
    return render(request, 'sgierp/inventory/list.html', context)


@sgi_login_required
def add_stock(request):
    """Add initial stock to an existing catalog item."""
    user = get_sgi_user(request)
    items = Item.objects.filter(is_active=True).order_by('code')
    processes = Process.objects.filter(is_active=True).order_by('order', 'name')
    assignees = Assignee.objects.filter(is_active=True).order_by('name')
    completed = get_completed_process()

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        process_id = request.POST.get('process_id')
        quantity = request.POST.get('quantity')
        assigned_id = request.POST.get('assigned_id')
        remarks = request.POST.get('remarks', '')

        if not item_id or not process_id or not quantity:
            messages.error(request, 'Item, Process, and Quantity are required.')
        else:
            try:
                item = Item.objects.get(id=int(item_id))
                process = Process.objects.get(id=int(process_id))
                assignee = Assignee.objects.filter(id=int(assigned_id)).first() if assigned_id else None
                qty = float(quantity)

                if qty <= 0:
                    messages.error(request, 'Quantity must be greater than zero.')
                else:
                    add_initial_stock(
                        item=item,
                        process=process,
                        quantity=qty,
                        assigned_to=assignee,
                        remarks=remarks,
                        performed_by=user,
                        moved_at=timezone.now()
                    )
                    messages.success(request, f'Stock added successfully: {qty} {item.unit} of {item.code} in {process.name}.')
                    return redirect('sgierp:inventory')
            except (ValueError, Item.DoesNotExist, Process.DoesNotExist) as e:
                messages.error(request, f'Error: {str(e)}')

    # Get selected item from query params
    selected_item_id = request.GET.get('item')
    selected_item = None
    if selected_item_id:
        try:
            selected_item = Item.objects.get(id=int(selected_item_id))
        except (ValueError, Item.DoesNotExist):
            pass

    context = {
        'items': items,
        'processes': processes,
        'assignees': assignees,
        'selected_item': selected_item,
        'completed_process': completed,
        'page_title': 'Add Stock',
    }
    return render(request, 'sgierp/inventory/add_stock.html', context)


@sgi_login_required
def item_create(request):
    """Create a new item master record in the catalog."""
    user = get_sgi_user(request)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        unit = request.POST.get('unit', 'pcs')
        category = request.POST.get('category', '').strip()
        min_stock_level = request.POST.get('min_stock_level', '')
        is_active = request.POST.get('is_active') == 'on'

        if not code or not name:
            messages.error(request, 'Code and Name are required.')
        else:
            try:
                # Check if code already exists
                if Item.objects.filter(code=code).exists():
                    messages.error(request, f'Item code "{code}" already exists.')
                else:
                    item = Item.objects.create(
                        code=code,
                        name=name,
                        unit=unit,
                        category=category,
                        min_stock_level=float(min_stock_level) if min_stock_level else None,
                        is_active=is_active,
                        created_by=request.user if request.user.is_authenticated else None
                    )
                    messages.success(request, f'Item "{code} - {name}" created successfully.')
                    return redirect('sgierp:item_catalog')
            except ValueError:
                messages.error(request, 'Invalid value for minimum stock level.')

    context = {
        'page_title': 'Add Item to Catalog',
    }
    return render(request, 'sgierp/inventory/item_form.html', context)


@sgi_login_required
def item_delete(request, item_id):
    """Delete an item, cascading all dependent records."""
    item = get_object_or_404(Item, id=item_id)

    # Block if item is used in BOM
    from SGIERP.models import MachineBOM, DispatchComponent
    bom_count = MachineBOM.objects.filter(item=item).count()
    if bom_count > 0:
        messages.error(request, f'Cannot delete item "{item.code}" - it is used in {bom_count} machine BOMs.')
        return redirect('sgierp:item_catalog')

    # Cascade: delete stock history records
    history_count = StockHistory.objects.filter(item=item).count()
    StockHistory.objects.filter(item=item).delete()
    StockHistory.objects.filter(to_item=item).delete()

    # Cascade: delete dispatch components referencing this item
    DispatchComponent.objects.filter(item=item).delete()

    # Cascade: delete all item-process entries
    item.process_entries.all().delete()

    item.delete()
    if history_count > 0:
        messages.success(request, f'Item "{item.code}" and its {history_count} history record(s) deleted successfully.')
    else:
        messages.success(request, f'Item "{item.code}" deleted successfully.')
    return redirect('sgierp:item_catalog')


@sgi_login_required
def inventory_entry_delete(request, entry_id):
    """Delete an inventory entry (ItemProcess), cascading any related stock history."""
    entry = get_object_or_404(ItemProcess, id=entry_id)
    item = entry.item
    process = entry.process

    # Delete history records tied to this item+process combination
    history_qs = StockHistory.objects.filter(
        item=item
    ).filter(
        models.Q(from_process=process) | models.Q(to_process=process)
    )
    history_count = history_qs.count()
    history_qs.delete()

    entry.delete()
    if history_count > 0:
        messages.success(request, f'Inventory entry deleted along with {history_count} related history record(s).')
    else:
        messages.success(request, 'Inventory entry deleted successfully.')
    return redirect('sgierp:inventory')


@sgi_login_required
def item_groups(request):
    """View items grouped by name with total quantities."""
    user = get_sgi_user(request)
    search = request.GET.get('q', '').strip()

    # Group items by name
    items_qs = Item.objects.filter(is_active=True)
    if search:
        items_qs = items_qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
    
    items = items_qs.order_by('name', 'code')

    # Build groups
    groups = {}
    for item in items:
        if item.name not in groups:
            groups[item.name] = {
                'name': item.name,
                'items': [],
                'total_quantity': 0,
            }
        
        # Calculate total quantity for this item
        total_qty = item.process_entries.aggregate(total=Sum('quantity'))['total'] or 0
        groups[item.name]['items'].append({
            'item': item,
            'total_quantity': total_qty,
        })
        groups[item.name]['total_quantity'] += total_qty

    # Convert to list and sort by total quantity
    group_list = sorted(groups.values(), key=lambda x: x['total_quantity'], reverse=True)

    context = {
        'groups': group_list,
        'search': search,
        'page_title': 'Item Groups',
    }
    return render(request, 'sgierp/inventory/item_groups.html', context)


@sgi_login_required
def item_edit(request, item_id):
    """Edit an existing item master record."""
    user = get_sgi_user(request)
    item = get_object_or_404(Item, id=item_id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        unit = request.POST.get('unit', 'pcs')
        category = request.POST.get('category', '').strip()
        min_stock_level = request.POST.get('min_stock_level', '')
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, 'Name is required.')
        else:
            try:
                item.name = name
                item.unit = unit
                item.category = category
                item.min_stock_level = float(min_stock_level) if min_stock_level else None
                item.is_active = is_active
                item.save()
                messages.success(request, f'Item "{item.code}" updated successfully.')
                return redirect('sgierp:item_catalog')
            except ValueError:
                messages.error(request, 'Invalid value for minimum stock level.')

    context = {
        'item': item,
        'page_title': f'Edit {item.code}',
    }
    return render(request, 'sgierp/inventory/item_form.html', context)


@sgi_login_required
def item_detail(request, item_id):
    """Item master detail with all process entries and history."""
    item = get_object_or_404(Item, id=item_id)
    user = get_sgi_user(request)
    completed = get_completed_process()

    # Process-wise stock summary for this item
    process_stock = []
    for entry in item.process_entries.filter(quantity__gt=0).select_related('process', 'assigned_to'):
        process_stock.append({
            'process_id': entry.process.id,
            'process_name': entry.process.name,
            'total': entry.quantity,
            'is_completed_process': entry.process.is_completed_process,
            'assigned_to': entry.assigned_to.name if entry.assigned_to else None,
            'assigned_at': entry.assigned_at,
        })

    # Item-specific stock history
    item_history = StockHistory.objects.filter(
        item=item
    ).select_related('from_process', 'to_process', 'to_item', 'performed_by').order_by('-created_at')[:50]

    context = {
        'item': item,
        'process_stock': process_stock,
        'item_history': item_history,
        'completed_process': completed,
        'page_title': f'{item.code} - {item.name}',
    }
    return render(request, 'sgierp/inventory/item_detail.html', context)


@sgi_login_required
def stock_move_view(request):
    """Move stock from one process to another."""
    user = get_sgi_user(request)
    items = Item.objects.filter(is_active=True).order_by('code')
    # Get all processes including Completed, regardless of active status
    processes = list(Process.objects.all().order_by('order', 'name'))
    assignees = Assignee.objects.filter(is_active=True).order_by('name')
    completed = get_completed_process()

    selected_item = None
    selected_source_process = None
    selected_stock_entry = None

    # Get selected item and process from query params
    item_id = request.GET.get('item')
    process_id = request.GET.get('process')

    if item_id:
        try:
            selected_item = Item.objects.get(id=int(item_id))
            # Get the first stock entry for this item (excluding completed process)
            stock_entry = selected_item.process_entries.filter(
                quantity__gt=0
            ).exclude(
                process__is_completed_process=True
            ).select_related('process').first()
            if stock_entry:
                selected_stock_entry = stock_entry
                selected_source_process = stock_entry.process
        except (ValueError, Item.DoesNotExist):
            pass

    if process_id:
        try:
            selected_source_process = Process.objects.get(id=int(process_id))
        except (ValueError, Process.DoesNotExist):
            pass

    # Build items with stock info for dropdown (exclude completed process)
    items_with_stock = []
    for item in items:
        stock_entries = item.process_entries.filter(
            quantity__gt=0
        ).exclude(
            process__is_completed_process=True
        ).select_related('process', 'assigned_to')
        items_with_stock.append({
            'item': item,
            'stock_entries': stock_entries,
        })

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        source_process_id = request.POST.get('source_process_id')  # Hidden field from item selection
        to_process_id = request.POST.get('to_process_id')
        quantity = request.POST.get('quantity', '').strip()
        to_assigned_id = request.POST.get('to_assigned', '').strip()
        notes = request.POST.get('notes', '').strip()
        change_unit = request.POST.get('change_unit') == 'on'
        target_item_id = request.POST.get('target_item_id', '').strip()
        target_quantity = request.POST.get('target_quantity', '').strip()

        errors = []
        if not item_id:
            errors.append('Item is required.')
        if not source_process_id:
            errors.append('Source process is required.')
        if not quantity:
            errors.append('Quantity is required.')
        if not to_process_id:
            errors.append('Destination process is required.')
        
        if change_unit:
            if not target_item_id:
                errors.append('Target item is required for conversion.')
            if not target_quantity:
                errors.append('Target quantity is required for conversion.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/inventory/stock_move.html', {
                'items': items_with_stock,
                'processes': processes,
                'assignees': assignees,
                'selected_item': selected_item,
                'selected_source_process': selected_source_process,
                'selected_stock_entry': selected_stock_entry,
                'page_title': 'Stock Movement',
            })

        try:
            qty = float(quantity)
            if qty <= 0:
                raise ValueError("Quantity must be positive")
        except ValueError:
            messages.error(request, 'Invalid quantity. Must be a positive number.')
            return render(request, 'sgierp/inventory/stock_move.html', {
                'items': items_with_stock,
                'processes': processes,
                'assignees': assignees,
                'selected_item': selected_item,
                'selected_source_process': selected_source_process,
                'selected_stock_entry': selected_stock_entry,
                'page_title': 'Stock Movement',
            })

        try:
            target_qty = float(target_quantity) if target_quantity else qty
        except ValueError:
            messages.error(request, 'Invalid target quantity. Must be a positive number.')
            return render(request, 'sgierp/inventory/stock_move.html', {
                'items': items_with_stock,
                'processes': processes,
                'assignees': assignees,
                'selected_item': selected_item,
                'selected_source_process': selected_source_process,
                'selected_stock_entry': selected_stock_entry,
                'page_title': 'Stock Movement',
            })

        try:
            if change_unit:
                # Conversion mode - optimize with bulk queries
                from SGIERP.services import convert_item
                
                required_ids = [int(item_id), int(target_item_id), int(source_process_id), int(to_process_id)]
                items = Item.objects.filter(id__in=[int(item_id), int(target_item_id)])
                processes = Process.objects.filter(id__in=[int(source_process_id), int(to_process_id)])
                
                items_map = {item.id: item for item in items}
                processes_map = {proc.id: proc for proc in processes}
                
                source_item = items_map.get(int(item_id))
                target_item = items_map.get(int(target_item_id))
                source_process = processes_map.get(int(source_process_id))
                target_process = processes_map.get(int(to_process_id))
                to_assigned = Assignee.objects.filter(id=int(to_assigned_id)).first() if to_assigned_id else None
                
                if not all([source_item, target_item, source_process, target_process]):
                    messages.error(request, 'Invalid selection. Please check your inputs.')
                    return redirect('sgierp:stock_move')
                
                convert_item(
                    source_item=source_item,
                    target_item=target_item,
                    source_process=source_process,
                    target_process=target_process,
                    source_quantity=qty,
                    target_quantity=target_qty,
                    assigned_to=to_assigned,
                    remarks=notes,
                    performed_by=user
                )
                messages.success(request, f'Converted {qty} {source_item.unit} of {source_item.code} @ {source_process.name} to {target_qty} {target_item.unit} of {target_item.code} @ {target_process.name}.')
            else:
                # Normal move mode
                to_assigned = Assignee.objects.filter(id=int(to_assigned_id)).first() if to_assigned_id else None
                move_stock(
                    item_id=int(item_id),
                    source_process_id=int(source_process_id),
                    destination_process_id=int(to_process_id),
                    quantity=qty,
                    assigned_to=to_assigned,
                    remarks=notes,
                    performed_by=user
                )
                messages.success(request, f'Stock moved successfully.')
            
            return redirect('sgierp:inventory')
        except (ValueError, Item.DoesNotExist, Process.DoesNotExist, ValidationError) as e:
            messages.error(request, f'Error: {str(e)}')
        except Exception as e:
            messages.error(request, f'Unexpected error: {str(e)}')

    return render(request, 'sgierp/inventory/stock_move.html', {
        'items': items_with_stock,
        'processes': processes,
        'assignees': assignees,
        'selected_item': selected_item,
        'selected_source_process': selected_source_process,
        'selected_stock_entry': selected_stock_entry,
        'completed_process': completed,
        'page_title': 'Stock Movement',
    })


@sgi_login_required
def completed_stock(request):
    """Completed Stock page — all items with stock in the Completed process."""
    completed = get_completed_process()
    search = request.GET.get('q', '').strip()

    entries_qs = ItemProcess.objects.filter(
        process=completed, quantity__gt=0
    ).select_related('item')

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    # Aggregate by item
    from collections import defaultdict
    items_map = defaultdict(lambda: {'item': None, 'entries': [], 'total': 0})
    for entry in entries_qs:
        key = entry.item_id
        items_map[key]['item'] = entry.item
        items_map[key]['entries'].append(entry)
        items_map[key]['total'] += entry.quantity

    completed_items = sorted(items_map.values(), key=lambda x: x['item'].code)
    total_qty = sum(v['total'] for v in completed_items)


@sgi_login_required
def process_wise_stock(request):
    """Process-wise stock view — shows stock by process in tabs."""
    processes = Process.objects.filter(is_active=True).order_by('order')
    search = request.GET.get('q', '').strip()
    selected_process_id = request.GET.get('process', '').strip()

    # Get all entries with stock
    entries_qs = ItemProcess.objects.filter(
        quantity__gt=0
    ).select_related('item', 'process', 'assigned_to')

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    if selected_process_id:
        entries_qs = entries_qs.filter(process_id=int(selected_process_id))

    # Group by process
    from collections import defaultdict
    process_map = defaultdict(lambda: {'process': None, 'entries': [], 'total': 0})
    for entry in entries_qs:
        key = entry.process_id
        process_map[key]['process'] = entry.process
        process_map[key]['entries'].append(entry)
        process_map[key]['total'] += entry.quantity

    process_data = sorted(process_map.values(), key=lambda x: x['process'].order if x['process'] else 999)

    return render(request, 'sgierp/inventory/process_wise.html', {
        'process_data': process_data,
        'processes': processes,
        'selected_process_id': int(selected_process_id) if selected_process_id else None,
        'page_title': 'Stock by Process',
    })


@sgi_login_required
def assignee_wise_stock(request):
    """Assignee-wise stock view — shows stock by assignee in tabs."""
    assignees = Assignee.objects.filter(is_active=True).order_by('name')
    search = request.GET.get('q', '').strip()
    selected_assignee_id = request.GET.get('assignee', '').strip()

    # Get all entries with stock and assignments
    entries_qs = ItemProcess.objects.filter(
        quantity__gt=0,
        assigned_to__isnull=False
    ).select_related('item', 'process', 'assigned_to')

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    if selected_assignee_id:
        entries_qs = entries_qs.filter(assigned_to_id=int(selected_assignee_id))

    # Group by assignee
    from collections import defaultdict
    assignee_map = defaultdict(lambda: {'assignee': None, 'entries': [], 'total': 0})
    for entry in entries_qs:
        key = entry.assigned_to_id
        assignee_map[key]['assignee'] = entry.assigned_to
        assignee_map[key]['entries'].append(entry)
        assignee_map[key]['total'] += entry.quantity

    assignee_data = sorted(assignee_map.values(), key=lambda x: x['assignee'].name if x['assignee'] else '')

    return render(request, 'sgierp/inventory/assignee_wise.html', {
        'assignee_data': assignee_data,
        'assignees': assignees,
        'selected_assignee_id': int(selected_assignee_id) if selected_assignee_id else None,
        'page_title': 'Stock by Assignee',
    })


@sgi_login_required
def completed_stock(request):
    """Completed Stock page — all items with stock in the Completed process."""
    completed = get_completed_process()
    search = request.GET.get('q', '').strip()

    entries_qs = ItemProcess.objects.filter(
        process=completed, quantity__gt=0
    ).select_related('item')

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    # Aggregate by item
    from collections import defaultdict
    items_map = defaultdict(lambda: {'item': None, 'entries': [], 'total': 0})
    for entry in entries_qs:
        key = entry.item_id
        items_map[key]['item'] = entry.item
        items_map[key]['entries'].append(entry)
        items_map[key]['total'] += entry.quantity

    completed_items = sorted(items_map.values(), key=lambda x: x['item'].code)
    total_qty = sum(v['total'] for v in completed_items)

    return render(request, 'sgierp/inventory/completed.html', {
        'completed_process': completed,
        'completed_items': completed_items,
        'total_items': len(completed_items),
        'total_qty': total_qty,
        'search': search,
        'page_title': 'Completed Stock',
    })


@sgi_login_required
def stock_history(request):
    """Stock History page — all stock movements and assignments."""
    search = request.GET.get('q', '').strip()
    movement_type = request.GET.get('type', '')
    page = request.GET.get('page', 1)

    history_qs = StockHistory.objects.select_related(
        'item', 'from_process', 'to_process', 'performed_by'
    ).order_by('-created_at')

    if search:
        history_qs = history_qs.filter(
            Q(item_code_snapshot__icontains=search) |
            Q(item_name_snapshot__icontains=search)
        )

    if movement_type:
        history_qs = history_qs.filter(movement_type=movement_type)

    paginator = Paginator(history_qs, 50)
    history_page = paginator.get_page(page)

    context = {
        'history': history_page,
        'search': search,
        'movement_type': movement_type,
        'page_title': 'Stock History',
    }
    return render(request, 'sgierp/inventory/history.html', context)

