"""SGIERP Challan views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from SGIERP.decorators import sgi_login_required, get_sgi_user
from SGIERP.models import Challan, ChallanItem, Item, Process, Assignee


@sgi_login_required
def challan_list(request):
    """List all challans."""
    user = get_sgi_user(request)
    search = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    challan_type = request.GET.get('type', '')

    challans = Challan.objects.select_related('created_by').prefetch_related('items__item')

    if search:
        challans = challans.filter(
            party_name__icontains=search
        )
    if date_from:
        challans = challans.filter(date__gte=date_from)
    if date_to:
        challans = challans.filter(date__lte=date_to)
    if challan_type:
        challans = challans.filter(challan_type=challan_type)

    challans = challans.order_by('-date', '-challan_number')

    paginator = Paginator(challans, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'challan_type': challan_type,
        'page_title': 'Challans',
    }
    return render(request, 'sgierp/challan/list.html', context)


@sgi_login_required
def challan_create(request):
    """Create a new challan."""
    user = get_sgi_user(request)
    all_items = Item.objects.filter(is_active=True).order_by('code')
    all_processes = Process.objects.filter(is_active=True).order_by('order', 'name')
    all_assignees = Assignee.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        party_name = request.POST.get('party_name', '').strip()
        party_address = request.POST.get('party_address', '').strip()
        party_contact = request.POST.get('party_contact', '').strip()
        assignee_id = request.POST.get('assignee', '').strip()
        date_str = request.POST.get('date', '').strip()
        challan_type = request.POST.get('challan_type', 'outward')
        remarks = request.POST.get('remarks', '').strip()

        # Get items
        item_ids = request.POST.getlist('item_id')
        process_ids = request.POST.getlist('process_id')
        quantities = request.POST.getlist('quantity')
        item_remarks = request.POST.getlist('item_remarks')

        errors = []
        if not party_name:
            errors.append('Party name is required.')
        if not date_str:
            errors.append('Date is required.')

        # Validate items - optimize with bulk queries
        items_data = []
        valid_item_ids = [int(i) for i in item_ids if i]
        valid_process_ids = [int(p) for p in process_ids if p]
        
        # Bulk fetch items and processes
        items_map = {item.id: item for item in Item.objects.filter(id__in=valid_item_ids)} if valid_item_ids else {}
        processes_map = {proc.id: proc for proc in Process.objects.filter(id__in=valid_process_ids)} if valid_process_ids else {}
        
        for i, item_id in enumerate(item_ids):
            if item_id:
                item = items_map.get(int(item_id))
                if not item:
                    errors.append(f'Invalid item selected.')
                    continue
                    
                qty = quantities[i] if i < len(quantities) else '0'
                if not qty or float(qty) <= 0:
                    errors.append(f'Invalid quantity for {item.code}.')
                    continue
                
                process_id = process_ids[i] if i < len(process_ids) else ''
                process = processes_map.get(int(process_id)) if process_id else None

                items_data.append({
                    'item': item,
                    'process': process,
                    'quantity': float(qty),
                    'unit': item.unit,
                    'remarks': item_remarks[i] if i < len(item_remarks) else '',
                })

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/challan/create.html', {
                'form_data': request.POST,
                'items_data': items_data,
                'all_items': all_items,
                'all_processes': all_processes,
                'all_assignees': all_assignees,
                'now': timezone.now(),
                'page_title': 'New Challan',
            })

        # Generate challan number
        year = timezone.now().year
        count = Challan.objects.filter(date__year=year).count() + 1
        challan_number = f"CH-{year}-{str(count).zfill(4)}"

        # Parse date
        try:
            date = parse_date(date_str) if date_str else timezone.now().date()
        except:
            date = timezone.now().date()

        # Get assignee - optimize
        assignee = None
        if assignee_id:
            assignee = Assignee.objects.filter(id=int(assignee_id)).first()

        # Create challan
        challan = Challan.objects.create(
            challan_number=challan_number,
            challan_type=challan_type,
            party_name=party_name,
            party_address=party_address,
            party_contact=party_contact,
            assignee=assignee,
            date=date,
            remarks=remarks,
            created_by=user
        )

        # Create challan items
        for item_data in items_data:
            ChallanItem.objects.create(
                challan=challan,
                item=item_data['item'],
                process=item_data['process'],
                quantity=item_data['quantity'],
                unit=item_data['unit'],
                remarks=item_data['remarks']
            )

        messages.success(request, f'Challan {challan_number} created successfully.')
        return redirect('sgierp:challan_detail', challan_id=challan.id)

    context = {
        'form_data': {},
        'items_data': [],
        'all_items': all_items,
        'all_processes': all_processes,
        'all_assignees': all_assignees,
        'now': timezone.now(),
        'page_title': 'New Challan',
    }
    return render(request, 'sgierp/challan/create.html', context)


@sgi_login_required
def challan_detail(request, challan_id):
    """View challan details."""
    challan = get_object_or_404(
        Challan.objects.select_related('created_by').prefetch_related('items__item'),
        id=challan_id
    )

    context = {
        'challan': challan,
        'items': challan.items.all(),
        'page_title': f'Challan {challan.challan_number}',
    }
    return render(request, 'sgierp/challan/detail.html', context)


@sgi_login_required
def challan_print(request, challan_id):
    """Print challan page."""
    challan = get_object_or_404(
        Challan.objects.select_related('created_by').prefetch_related('items__item'),
        id=challan_id
    )

    # Calculate blank rows (total 10 rows)
    items_count = challan.items.count()
    blank_rows = max(0, 10 - items_count)

    context = {
        'challan': challan,
        'items': challan.items.all(),
        'blank_rows': range(blank_rows),
        'sgi_user': get_sgi_user(request),
        'sgi_profile': get_sgi_user(request).erp_profile if get_sgi_user(request) else None,
    }
    return render(request, 'sgierp/challan/print.html', context)
