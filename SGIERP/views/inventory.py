"""SGIERP Inventory views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db import models
from django.db.models import Sum, Q, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from PIL import Image
import io
import json
import re

from SGIERP.decorators import sgi_login_required, sgi_admin_required, sgi_delete_passcode_required, get_sgi_user
from SGIERP.models import Item, Machine, Process, ItemProcess, Assignee, StockHistory, ERPConfig
from SGIERP.services import add_initial_stock, move_stock, get_completed_process, get_rejected_process


@sgi_login_required
@require_POST
def table_pdf_export(request):
    """Render the rows currently shown in a page table as a downloadable PDF."""
    try:
        payload = json.loads(request.body or b'{}')
        if not isinstance(payload, dict):
            raise ValueError('Invalid table data.')
        headers = payload.get('headers', [])
        rows = payload.get('rows', [])
        title = str(payload.get('title') or 'Table Export')[:120]
        filename = re.sub(r'[^A-Za-z0-9_-]+', '_', str(payload.get('filename') or 'export'))[:80] or 'export'
        if not isinstance(headers, list) or not headers or len(headers) > 30:
            raise ValueError('The table has an unsupported number of columns.')
        if not isinstance(rows, list) or len(rows) > 3000:
            raise ValueError('The table has too many rows to export.')
        clean_rows = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(headers):
                continue
            clean_row = []
            for value in row:
                if isinstance(value, dict) and isinstance(value.get('image'), str) and value['image'].startswith('data:image/'):
                    clean_row.append({'text': str(value.get('text') or '')[:2000], 'image': value['image'][:700000]})
                else:
                    clean_row.append(str(value or '')[:2000])
            clean_rows.append(clean_row)
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        return JsonResponse({'error': str(error) or 'Invalid table data.'}, status=400)

    from io import BytesIO
    from xml.sax.saxutils import escape
    import base64
    from reportlab.platypus import Image as PdfImage
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, TableStyle

    page_size = landscape(A4) if len(headers) > 6 else A4
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page_size, rightMargin=14 * mm, leftMargin=14 * mm,
                            topMargin=17 * mm, bottomMargin=15 * mm, title=title)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ExportTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=15, leading=18, alignment=0, spaceAfter=4)
    header_style = ParagraphStyle('ExportHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.6, leading=9, textColor=colors.white)
    cell_style = ParagraphStyle('ExportCell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.4, leading=9, wordWrap='CJK')
    data = [[Paragraph(escape(str(value or '')) or '&nbsp;', header_style) for value in headers]]
    for row in clean_rows:
        pdf_row = []
        for value in row:
            if isinstance(value, dict) and value.get('image'):
                try:
                    image_data = base64.b64decode(value['image'].split(',', 1)[1], validate=True)
                    image = PdfImage(BytesIO(image_data), width=34, height=34)
                    image.hAlign = 'LEFT'
                    label = escape(str(value.get('text') or ''))
                    pdf_row.append([image, Paragraph(label.replace('\n', '<br/>'), cell_style)] if label else image)
                    continue
                except (ValueError, IndexError, TypeError):
                    value = value.get('text', '')
            pdf_row.append(Paragraph(escape(str(value or '')).replace('\n', '<br/>') or '&nbsp;', cell_style))
        data.append(pdf_row)
    col_width = doc.width / len(headers)
    table = LongTable(data, colWidths=[col_width] * len(headers), repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#18304F')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FC')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    doc.build([Paragraph(escape(title), title_style), table])
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    return response


def _get_default_per_page(request):
    """Return the app-configured default rows per page."""
    try:
        user = get_sgi_user(request)
        return user.erp_profile.default_per_page if user and hasattr(user, 'erp_profile') else '20'
    except Exception:
        return '20'


def compress_image(image_file, max_size_kb=500, quality=85):
    """Compress image to reduce file size while maintaining quality."""
    img = Image.open(image_file)

    # Convert to RGB if necessary (for PNG with transparency)
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # Create a BytesIO object to save the compressed image
    output = io.BytesIO()

    # Save with compression
    img.save(output, format='JPEG', quality=quality, optimize=True)

    # Check if file size is still too large and reduce quality if needed
    output.seek(0)
    while output.tell() > max_size_kb * 1024 and quality > 10:
        quality -= 5
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)

    output.seek(0)
    return output


@sgi_login_required
def item_catalog(request):
    """Item Catalog page — manage item definitions (code, name, unit, category)."""
    search = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', 'active')
    per_page = request.GET.get('per_page', _get_default_per_page(request))

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

    items_qs = items_qs.order_by('code')

    # Pagination
    per_page = request.GET.get('per_page', _get_default_per_page(request))
    if per_page == 'all':
        items = items_qs.all()
        page_obj = None
        start_index = 1
        end_index = items.count()
        total_count = items.count()
    else:
        per_page_int = int(per_page)
        paginator = Paginator(items_qs, per_page_int)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        items = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1
        end_index = min(page_obj.number * per_page_int, paginator.count)
        total_count = paginator.count

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
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
    }
    return render(request, 'sgierp/inventory/catalog.html', context)


@sgi_login_required
def item_catalog_pdf(request):
    """Download the filtered item catalog as an A4 PDF (20 cards per page)."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfgen import canvas

    search = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', 'active')
    items_qs = Item.objects.select_related('created_by').all()
    if search:
        items_qs = items_qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
    if category_filter:
        items_qs = items_qs.filter(category__icontains=category_filter)
    if status_filter == 'inactive':
        items_qs = items_qs.filter(is_active=False)
    elif status_filter:
        items_qs = items_qs.filter(is_active=True)
    items = list(items_qs.order_by('code'))

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="sgi_item_catalog.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4, pageCompression=1)
    page_width, page_height = A4
    margin = 24
    header_bottom = page_height - 55
    grid_width = page_width - 2 * margin
    grid_height = header_bottom - 22
    cell_width = grid_width / 4
    cell_height = grid_height / 5

    def printable(value, limit=None):
        text = str(value or '').encode('latin-1', 'replace').decode('latin-1')
        if limit and len(text) > limit:
            text = text[:max(0, limit - 3)].rstrip() + '...'
        return text

    page_count = max(1, (len(items) + 19) // 20)
    for page_index in range(page_count):
        page_items = items[page_index * 20:(page_index + 1) * 20]
        pdf.setFillColorRGB(.09, .16, .28)
        pdf.setFont('Helvetica-Bold', 15)
        pdf.drawString(margin, page_height - 29, 'SGI Item Catalog')
        pdf.setFillColorRGB(.36, .41, .48)
        pdf.setFont('Helvetica', 8.5)
        pdf.drawRightString(page_width - margin, page_height - 28, 'A4 | 20 items per page')
        subtitle_parts = []
        if search:
            subtitle_parts.append(f'Search: {printable(search, 40)}')
        if category_filter:
            subtitle_parts.append(f'Category: {printable(category_filter, 28)}')
        if status_filter:
            subtitle_parts.append(f'Status: {"Inactive" if status_filter == "inactive" else "Active"}')
        pdf.drawString(margin, page_height - 43, '  |  '.join(subtitle_parts) or 'Complete item catalog')

        for index, item in enumerate(page_items):
            row, column = divmod(index, 4)
            x = margin + column * cell_width
            y = header_bottom - (row + 1) * cell_height
            pdf.setStrokeColorRGB(.82, .85, .88)
            pdf.setLineWidth(.55)
            pdf.roundRect(x + 2, y + 2, cell_width - 4, cell_height - 4, 3, stroke=1, fill=0)

            image_box_w = cell_width - 14
            image_box_h = 72
            image_y = y + cell_height - 80
            image_drawn = False
            if item.image:
                try:
                    with item.image.open('rb') as image_file:
                        image_data = BytesIO(image_file.read())
                    image = ImageReader(image_data)
                    image_w, image_h = image.getSize()
                    scale = min(image_box_w / image_w, image_box_h / image_h)
                    draw_w, draw_h = image_w * scale, image_h * scale
                    pdf.drawImage(image, x + (cell_width - draw_w) / 2, image_y + (image_box_h - draw_h) / 2,
                                  width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
                    image_drawn = True
                except Exception:
                    image_drawn = False
            if not image_drawn:
                pdf.setFillColorRGB(.94, .96, .98)
                pdf.roundRect(x + 10, image_y, image_box_w, image_box_h, 3, stroke=0, fill=1)
                pdf.setFillColorRGB(.48, .53, .60)
                pdf.setFont('Helvetica', 8)
                pdf.drawCentredString(x + cell_width / 2, image_y + image_box_h / 2 - 3, 'No image')

            pdf.setFillColorRGB(.09, .16, .28)
            pdf.setFont('Helvetica-Bold', 10)
            pdf.drawCentredString(x + cell_width / 2, y + cell_height - 89, printable(item.code, 25))
            name_lines = simpleSplit(printable(item.name), 'Helvetica-Bold', 8.7, cell_width - 18)[:2]
            pdf.setFont('Helvetica-Bold', 8.7)
            for line_number, line in enumerate(name_lines):
                pdf.drawCentredString(x + cell_width / 2, y + cell_height - 100 - line_number * 9, line)

            pdf.setFillColorRGB(.30, .35, .42)
            pdf.setFont('Helvetica', 6.2)
            details = [
                f'Unit: {printable(item.get_unit_display(), 14)}  |  Min: {printable(item.min_stock_level if item.min_stock_level is not None else "-", 12)}',
            ]
            for line_number, detail in enumerate(details):
                pdf.drawCentredString(x + cell_width / 2, y + cell_height - 118 - line_number * 7.2, detail)
        pdf.setFillColorRGB(.40, .44, .50)
        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString(page_width / 2, 10, f'Page {page_index + 1} of {page_count}  |  {len(items)} items')
        pdf.showPage()
    pdf.save()
    return response


@sgi_login_required
def inventory_list(request):
    """Main inventory listing — all items with process-wise stock as separate rows."""
    user = get_sgi_user(request)

    # Filters
    search = request.GET.get('q', '').strip()
    process_filter = request.GET.get('process', '')
    status_filter = request.GET.get('status', 'active')
    process_status = request.GET.get('process_status', 'non_completed')  # Default to non-completed
    per_page = request.GET.get('per_page', _get_default_per_page(request))

    # Get all items with stock - optimize
    entries_qs = ItemProcess.objects.filter(quantity__gt=0).exclude(
        process__is_rejected_process=True
    ).select_related(
        'item', 'process', 'assigned_to'
    ).only(
        'id', 'quantity', 'price', 'assigned_at',
        'item__id', 'item__code', 'item__name', 'item__is_active', 'item__unit',
        'process__id', 'process__name', 'process__order', 'process__is_completed_process',
        'process__is_rejected_process',
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
    if process_status == 'completed':
        entries_qs = entries_qs.filter(process=completed) if completed else entries_qs.none()
    elif process_status == 'rejected':
        entries_qs = entries_qs.none()
    elif process_status == 'non_completed':
        entries_qs = entries_qs.exclude(
            Q(process__is_completed_process=True) | Q(process__is_rejected_process=True)
        )

    entries_qs = entries_qs.order_by('item__code', 'process__order', 'process__name')
    inventory_totals = entries_qs.aggregate(quantity=Sum('quantity'), price=Sum('price'))

    # Pagination
    per_page = request.GET.get('per_page', _get_default_per_page(request))
    if per_page == 'all':
        entries = entries_qs.all()
        page_obj = None
        start_index = 1
        end_index = entries.count()
        total_count = entries.count()
    else:
        per_page_int = int(per_page)
        paginator = Paginator(entries_qs, per_page_int)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        entries = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1
        end_index = min(page_obj.number * per_page_int, paginator.count)
        total_count = paginator.count

    # Get all processes for filter dropdown - optimize
    processes = Process.objects.filter(is_active=True, is_rejected_process=False).order_by('order', 'name').only('id', 'name', 'order')

    context = {
        'entries': entries,
        'processes': processes,
        'search': search,
        'process_filter': process_filter,
        'status_filter': status_filter,
        'process_status': process_status,
        'page_title': 'Inventory',
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
        'inventory_total_qty': inventory_totals['quantity'] or 0,
        'inventory_total_price': inventory_totals['price'] or 0,
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
        price_raw = request.POST.get('price', '').strip()
        remarks = request.POST.get('remarks', '')

        if not item_id or not process_id or not quantity:
            messages.error(request, 'Item, Process, and Quantity are required.')
        else:
            try:
                item = Item.objects.get(id=int(item_id))
                process = Process.objects.get(id=int(process_id))
                assignee = Assignee.objects.filter(id=int(assigned_id)).first() if assigned_id else None
                qty = float(quantity)
                price = float(price_raw) if price_raw else 0

                if qty <= 0 or price < 0:
                    messages.error(request, 'Quantity must be greater than zero.')
                else:
                    add_initial_stock(
                        item=item,
                        process=process,
                        quantity=qty,
                        assigned_to=assignee,
                        remarks=remarks,
                        performed_by=user,
                        moved_at=timezone.now(),
                        price=price,
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
                # Validate and compress image
                if 'image' in request.FILES:
                    image_file = request.FILES['image']
                    if image_file.size > 2.5 * 1024 * 1024:  # 2.5MB
                        messages.error(request, 'Image size must be less than 2.5MB.')
                        context = {'page_title': 'Add Item to Catalog', 'form_data': request.POST}
                        return render(request, 'sgierp/inventory/item_form.html', context)

                # Check if code already exists
                if Item.objects.filter(code__iexact=code).exists() or Machine.objects.filter(code__iexact=code).exists():
                    messages.error(request, f'Code "{code}" is already used by an item or product.')
                else:
                    item = Item.objects.create(
                        code=code,
                        name=name,
                        unit=unit,
                        category=category,
                        min_stock_level=float(min_stock_level) if min_stock_level else None,
                        is_active=is_active,
                        created_by=user,
                    )
                    if 'image' in request.FILES:
                        # Compress image before saving
                        compressed_image = compress_image(request.FILES['image'])
                        from django.core.files.uploadedfile import SimpleUploadedFile
                        item.image = SimpleUploadedFile(
                            request.FILES['image'].name,
                            compressed_image.read(),
                            content_type='image/jpeg'
                        )
                        item.save()
                    messages.success(request, f'Item "{code} - {name}" created successfully.')
                    return redirect('sgierp:item_catalog')
            except ValueError:
                messages.error(request, 'Invalid value for minimum stock level.')

    context = {
        'page_title': 'Add Item to Catalog',
    }
    return render(request, 'sgierp/inventory/item_form.html', context)


@sgi_login_required
@require_POST
@sgi_delete_passcode_required
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
@require_POST
@sgi_delete_passcode_required
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
    return render(request, 'sgierp/inventory/groups.html', context)


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
                # Validate and compress image
                if 'image' in request.FILES:
                    image_file = request.FILES['image']
                    if image_file.size > 2.5 * 1024 * 1024:  # 2.5MB
                        messages.error(request, 'Image size must be less than 2.5MB.')
                        context = {'item': item, 'page_title': f'Edit {item.code}', 'form_data': request.POST}
                        return render(request, 'sgierp/inventory/item_form.html', context)

                item.name = name
                item.unit = unit
                item.category = category
                item.min_stock_level = float(min_stock_level) if min_stock_level else None
                item.is_active = is_active
                if 'image' in request.FILES:
                    # Compress image before saving
                    compressed_image = compress_image(request.FILES['image'])
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    item.image = SimpleUploadedFile(
                        request.FILES['image'].name,
                        compressed_image.read(),
                        content_type='image/jpeg'
                    )
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
    per_page = request.GET.get('per_page', _get_default_per_page(request))

    # Process-wise stock summary for this item
    process_stock = []
    for entry in item.process_entries.filter(quantity__gt=0).exclude(
        process__is_rejected_process=True
    ).select_related('process', 'assigned_to'):
        process_stock.append({
            'process_id': entry.process.id,
            'process_name': entry.process.name,
            'total': entry.quantity,
            'price': entry.price,
            'is_completed_process': entry.process.is_completed_process,
            'is_rejected_process': entry.process.is_rejected_process,
            'assigned_to': entry.assigned_to.name if entry.assigned_to else None,
            'assigned_at': entry.assigned_at,
        })

    # Item-specific stock history with pagination
    item_history_qs = StockHistory.objects.filter(
        item=item
    ).select_related('from_process', 'to_process', 'to_item', 'performed_by').order_by('-created_at')
    item_history_filters = {key: request.GET.get(key, '') for key in ('date_from', 'date_to', 'from_process', 'to_process', 'from_assignee', 'to_assignee')}
    for key, lookup in [('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte'), ('from_process', 'from_process_id'), ('to_process', 'to_process_id'), ('from_assignee', 'from_assignee_id'), ('to_assignee', 'to_assignee_id')]:
        if item_history_filters[key]: item_history_qs = item_history_qs.filter(**{lookup: item_history_filters[key]})
    item_history_totals = item_history_qs.aggregate(quantity=Sum('quantity'), price=Sum('price'))
    process_stock_total = sum((row['total'] for row in process_stock), 0)
    process_stock_price_total = sum((row['price'] for row in process_stock), 0)

    if per_page == 'all':
        item_history = item_history_qs.all()
        page_obj = None
        start_index = 1
        end_index = item_history.count()
        total_count = item_history.count()
    else:
        per_page_int = int(per_page)
        paginator = Paginator(item_history_qs, per_page_int)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        item_history = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1
        end_index = min(page_obj.number * per_page_int, paginator.count)
        total_count = paginator.count

    context = {
        'item': item,
        'process_stock': process_stock,
        'item_history': item_history,
        'item_history_totals': item_history_totals,
        'history_filters': item_history_filters,
        'processes': Process.objects.filter(is_active=True).order_by('order', 'name'),
        'assignees': Assignee.objects.filter(is_active=True).order_by('name'),
        'process_stock_total': process_stock_total,
        'process_stock_price_total': process_stock_price_total,
        'completed_process': completed,
        'page_title': f'{item.code} - {item.name}',
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
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
            # Default to the first available stock entry; completed/rejected stock can be moved back too.
            stock_entry = selected_item.process_entries.filter(
                quantity__gt=0
            ).select_related('process').first()
            if stock_entry:
                selected_stock_entry = stock_entry
                selected_source_process = stock_entry.process
        except (ValueError, Item.DoesNotExist):
            pass

    if process_id:
        try:
            selected_source_process = Process.objects.get(id=int(process_id))
            if selected_item:
                selected_stock_entry = selected_item.process_entries.filter(
                    process=selected_source_process,
                    quantity__gt=0,
                ).select_related('process', 'assigned_to').first()
        except (ValueError, Process.DoesNotExist):
            pass

    # Include all process stages so completed and rejected stock can be reprocessed.
    items_with_stock = []
    for item in items:
        stock_entries = item.process_entries.filter(
            quantity__gt=0
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
        price_raw = request.POST.get('price', '').strip()

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
            price = float(price_raw) if price_raw else 0
            if qty <= 0 or price < 0:
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
                    performed_by=user,
                    price=price,
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
                    performed_by=user,
                    price=price,
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
def process_wise_stock(request):
    """Process-wise stock view — shows stock by process in tabs."""
    processes = Process.objects.filter(is_active=True, is_rejected_process=False).order_by('order')
    search = request.GET.get('q', '').strip()
    selected_process_id = request.GET.get('process', '').strip()

    # Get all entries with stock
    entries_qs = ItemProcess.objects.filter(
        quantity__gt=0
    ).exclude(process__is_rejected_process=True).select_related('item', 'process', 'assigned_to')

    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    if selected_process_id:
        entries_qs = entries_qs.filter(process_id=int(selected_process_id))

    # Group by process
    from collections import defaultdict
    process_map = defaultdict(lambda: {'process': None, 'entries': [], 'total': 0, 'price_total': 0})
    for entry in entries_qs:
        key = entry.process_id
        process_map[key]['process'] = entry.process
        process_map[key]['entries'].append(entry)
        process_map[key]['total'] += entry.quantity
        process_map[key]['price_total'] += entry.price

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
    assignee_map = defaultdict(lambda: {'assignee': None, 'entries': [], 'total': 0, 'price_total': 0})
    for entry in entries_qs:
        key = entry.assigned_to_id
        assignee_map[key]['assignee'] = entry.assigned_to
        assignee_map[key]['entries'].append(entry)
        assignee_map[key]['total'] += entry.quantity
        assignee_map[key]['price_total'] += entry.price

    assignee_data = sorted(assignee_map.values(), key=lambda x: x['assignee'].name if x['assignee'] else '')

    return render(request, 'sgierp/inventory/assignee_wise.html', {
        'assignee_data': assignee_data,
        'assignees': assignees,
        'selected_assignee_id': int(selected_assignee_id) if selected_assignee_id else None,
        'page_title': 'Stock by Assignee',
    })


def _render_entity_history(request, history_qs, entity_name, entity_type):
    search = request.GET.get('q', '').strip()
    filters = {key: request.GET.get(key, '') for key in ('date_from', 'date_to', 'from_process', 'to_process', 'from_assignee', 'to_assignee')}
    for key, lookup in [('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte'), ('from_process', 'from_process_id'), ('to_process', 'to_process_id'), ('from_assignee', 'from_assignee_id'), ('to_assignee', 'to_assignee_id')]:
        if filters[key]: history_qs = history_qs.filter(**{lookup: filters[key]})
    per_page = request.GET.get('per_page', _get_default_per_page(request))
    if search:
        history_qs = history_qs.filter(
            Q(item_code_snapshot__icontains=search) |
            Q(item_name_snapshot__icontains=search) |
            Q(remarks__icontains=search)
        )
    history_totals = history_qs.aggregate(quantity=Sum('quantity'), price=Sum('price'))
    history_qs = history_qs.select_related(
        'item', 'from_process', 'to_process', 'from_assignee', 'to_assignee', 'performed_by'
    ).order_by('-created_at', '-id')

    if per_page == 'all':
        history = history_qs
        page_obj = None
        total_count = history_qs.count()
        start_index = 1 if total_count else 0
        end_index = total_count
    else:
        per_page_int = int(per_page)
        paginator = Paginator(history_qs, per_page_int)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        history = page_obj.object_list
        total_count = paginator.count
        start_index = (page_obj.number - 1) * per_page_int + 1 if total_count else 0
        end_index = min(page_obj.number * per_page_int, total_count)

    return render(request, 'sgierp/inventory/entity_history.html', {
        'history': history,
        'entity_name': entity_name,
        'entity_type': entity_type,
        'search': search,
        'history_filters': filters,
        'history_totals': history_totals,
        'processes': Process.objects.filter(is_active=True).order_by('order', 'name'),
        'assignees': Assignee.objects.filter(is_active=True).order_by('name'),
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
        'page_title': f'{entity_type} History — {entity_name}',
    })


@sgi_login_required
def process_history(request, process_id):
    """Show stock history where a process appears as either source or destination."""
    process = get_object_or_404(Process, id=process_id)
    history_qs = StockHistory.objects.filter(
        Q(from_process=process) | Q(to_process=process) |
        Q(from_process_name__iexact=process.name) | Q(to_process_name__iexact=process.name)
    )
    return _render_entity_history(request, history_qs, process.name, 'Process')


@sgi_login_required
def assignee_history(request, assignee_id):
    """Show stock history where an assignee appears as either source or destination."""
    assignee = get_object_or_404(Assignee, id=assignee_id)
    history_qs = StockHistory.objects.filter(
        Q(from_assignee=assignee) | Q(to_assignee=assignee) |
        Q(from_assignee_name__iexact=assignee.name) | Q(to_assignee_name__iexact=assignee.name)
    )
    return _render_entity_history(request, history_qs, assignee.name, 'Assignee')


@sgi_login_required
def completed_stock(request):
    """Show paginated stock totals in the Completed process."""
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
        items_map[key]['price'] = entry.price

    all_completed_items = sorted(items_map.values(), key=lambda x: x['item'].code)
    total_items = len(all_completed_items)
    total_qty = sum(entry['total'] for entry in all_completed_items)
    total_price = sum(entry['price'] for entry in all_completed_items)

    per_page = request.GET.get('per_page', _get_default_per_page(request))
    if per_page == 'all':
        completed_items = all_completed_items
        page_obj = None
        start_index = 1 if total_items else 0
        end_index = total_items
        total_count = total_items
    else:
        per_page_int = int(per_page)
        paginator = Paginator(all_completed_items, per_page_int)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        completed_items = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1 if total_items else 0
        end_index = min(page_obj.number * per_page_int, total_items)
        total_count = total_items

    return render(request, 'sgierp/inventory/completed.html', {
        'completed_process': completed,
        'completed_items': completed_items,
        'total_items': total_items,
        'total_qty': total_qty,
        'total_price': total_price,
        'search': search,
        'page_title': 'Completed Stock',
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
    })


@sgi_login_required
def rejected_stock(request):
    """Show paginated stock totals in the special Rejected process."""
    rejected = get_rejected_process()
    search = request.GET.get('q', '').strip()
    entries_qs = ItemProcess.objects.filter(
        process=rejected, quantity__gt=0
    ).select_related('item')
    if search:
        entries_qs = entries_qs.filter(
            Q(item__code__icontains=search) | Q(item__name__icontains=search)
        )

    from collections import defaultdict
    items_map = defaultdict(lambda: {'item': None, 'entries': [], 'total': 0})
    for entry in entries_qs:
        items_map[entry.item_id]['item'] = entry.item
        items_map[entry.item_id]['entries'].append(entry)
        items_map[entry.item_id]['total'] += entry.quantity
        items_map[entry.item_id]['price'] = entry.price

    all_rejected_items = sorted(items_map.values(), key=lambda row: row['item'].code)
    total_items = len(all_rejected_items)
    total_qty = sum(row['total'] for row in all_rejected_items)
    total_price = sum(row['price'] for row in all_rejected_items)
    per_page = request.GET.get('per_page', _get_default_per_page(request))
    if per_page == 'all':
        rejected_items = all_rejected_items
        page_obj = None
        start_index = 1 if total_items else 0
        end_index = total_items
        total_count = total_items
    else:
        per_page_int = int(per_page)
        paginator = Paginator(all_rejected_items, per_page_int)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        rejected_items = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1 if total_items else 0
        end_index = min(page_obj.number * per_page_int, total_items)
        total_count = total_items

    return render(request, 'sgierp/inventory/rejected.html', {
        'rejected_process': rejected,
        'rejected_items': rejected_items,
        'total_items': total_items,
        'total_qty': total_qty,
        'total_price': total_price,
        'search': search,
        'page_title': 'Rejected Stock',
        'page_obj': page_obj,
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
    })


@sgi_login_required
@sgi_login_required
def stock_history(request):
    """Stock History page — all stock movements and assignments."""
    search = request.GET.get('q', '').strip()
    movement_type = request.GET.get('type', '')
    history_filters = {
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'from_process': request.GET.getlist('from_process'),
        'to_process': request.GET.getlist('to_process'),
        'from_assignee': request.GET.getlist('from_assignee'),
        'to_assignee': request.GET.getlist('to_assignee'),
    }
    per_page = request.GET.get('per_page', _get_default_per_page(request))

    history_qs = StockHistory.objects.select_related(
        'item', 'from_process', 'to_process', 'performed_by'
    ).order_by('-created_at')

    if search:
        history_qs = history_qs.filter(
            Q(item_code_snapshot__icontains=search) |
            Q(item_name_snapshot__icontains=search) |
            Q(to_item_code_snapshot__icontains=search) |
            Q(to_item_name_snapshot__icontains=search) |
            Q(from_process_name__icontains=search) |
            Q(to_process_name__icontains=search) |
            Q(from_assignee_name__icontains=search) |
            Q(to_assignee_name__icontains=search) |
            Q(movement_type__icontains=search) |
            Q(remarks__icontains=search) |
            Q(unit_snapshot__icontains=search) |
            Q(quantity__icontains=search) |
            Q(performed_by__username__icontains=search) |
            Q(performed_by__first_name__icontains=search) |
            Q(performed_by__last_name__icontains=search)
        )

    if movement_type:
        history_qs = history_qs.filter(movement_type=movement_type)
    for key, lookup in [('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')]:
        if history_filters[key]: history_qs = history_qs.filter(**{lookup: history_filters[key]})
    for key, lookup in [('from_process', 'from_process_id__in'), ('to_process', 'to_process_id__in'), ('from_assignee', 'from_assignee_id__in'), ('to_assignee', 'to_assignee_id__in')]:
        selected_ids = [value for value in history_filters[key] if value.isdigit()]
        if selected_ids: history_qs = history_qs.filter(**{lookup: selected_ids})
    history_totals = history_qs.aggregate(quantity=Sum('quantity'), price=Sum('price'))

    # Pagination
    if per_page == 'all':
        history = history_qs.all()
        page_obj = None
        start_index = 1
        end_index = history.count()
        total_count = history.count()
    else:
        per_page_int = int(per_page)
        paginator = Paginator(history_qs, per_page_int)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        history = page_obj.object_list
        start_index = (page_obj.number - 1) * per_page_int + 1
        end_index = min(page_obj.number * per_page_int, paginator.count)
        total_count = paginator.count

    context = {
        'history': history,
        'page_obj': page_obj,
        'search': search,
        'movement_type': movement_type,
        'filter_active': bool(movement_type or history_filters['date_from'] or history_filters['date_to'] or any(history_filters[key] for key in ('from_process', 'to_process', 'from_assignee', 'to_assignee'))),
        'history_filters': history_filters,
        'history_totals': history_totals,
        'processes': Process.objects.filter(is_active=True).order_by('order', 'name'),
        'assignees': Assignee.objects.filter(is_active=True).order_by('name'),
        'page_title': 'Stock History',
        'per_page': per_page,
        'start_index': start_index,
        'end_index': end_index,
        'total_count': total_count,
    }
    return render(request, 'sgierp/inventory/history.html', context)

