"""SGIERP Settings / Administration views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from SGIERP.decorators import sgi_login_required, sgi_admin_required, get_sgi_user
from SGIERP.models import Process, ERPUserProfile, Assignee


@sgi_login_required
def settings_view(request):
    """Main settings page — tabs for processes, users, etc."""
    user = get_sgi_user(request)
    processes = Process.objects.all().order_by('order', 'name')
    erp_users = User.objects.filter(
        erp_profile__isnull=False
    ).select_related('erp_profile').order_by('username')

    assignees = Assignee.objects.all().order_by('name')

    # Check which settings page is being requested
    url_name = request.resolver_match.url_name

    if url_name == 'settings_processes':
        template = 'sgierp/settings/processes.html'
        context = {
            'processes': processes,
        }
    elif url_name == 'settings_assignees':
        template = 'sgierp/settings/assignees.html'
        context = {
            'assignees': assignees,
        }
    else:
        # Landing page
        template = 'sgierp/settings/landing.html'
        context = {
            'processes': processes,
            'erp_users': erp_users,
            'assignees': assignees,
        }

    return render(request, template, context)


@sgi_login_required
def process_create_edit(request, process_id=None):
    """Create or edit a manufacturing process."""
    process = None
    if process_id:
        process = get_object_or_404(Process, id=process_id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        is_completed = request.POST.get('is_completed_process') == 'on'
        order = request.POST.get('order', 0)

        errors = []
        if not name:
            errors.append('Process name is required.')

        dup = Process.objects.filter(name__iexact=name)
        if process:
            dup = dup.exclude(id=process.id)
        if dup.exists():
            errors.append('Process name already exists.')

        if is_completed:
            existing_completed = Process.objects.filter(is_completed_process=True)
            if process:
                existing_completed = existing_completed.exclude(id=process.id)
            if existing_completed.exists():
                errors.append('Only one process can be marked as Completed.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/settings/process_form.html', {
                'process': process,
                'page_title': f'Edit {process.name}' if process else 'Add Process',
            })
        else:
            if process:
                process.name = name
                process.description = description
                process.is_active = is_active
                process.is_completed_process = is_completed
                process.order = int(order) if order else 0
                process.save()
                messages.success(request, f'Process "{name}" updated successfully.')
            else:
                user = get_sgi_user(request)
                Process.objects.create(
                    name=name,
                    description=description,
                    is_active=is_active,
                    is_completed_process=is_completed,
                    order=int(order) if order else 0,
                    created_by=user
                )
                messages.success(request, f'Process "{name}" created successfully.')
            return redirect('sgierp:settings_processes')

    context = {
        'process': process,
        'page_title': f'Edit {process.name}' if process else 'Add Process',
    }
    return render(request, 'sgierp/settings/process_form.html', context)


@sgi_login_required
def process_delete(request, process_id):
    """Delete a process with validation, cascading history."""
    process = get_object_or_404(Process, id=process_id)

    # Check if process has any active stock
    stock_count = process.item_entries.filter(quantity__gt=0).count()
    if stock_count > 0:
        messages.error(request, f'Cannot delete process "{process.name}" - it has {stock_count} active stock entries.')
        return redirect('sgierp:settings_processes')

    # Delete stock history records referencing this process
    from SGIERP.models import StockHistory
    history_qs = StockHistory.objects.filter(
        Q(from_process=process) | Q(to_process=process)
    )
    history_count = history_qs.count()
    history_qs.delete()

    process.delete()
    if history_count > 0:
        messages.success(request, f'Process "{process.name}" and {history_count} history record(s) deleted successfully.')
    else:
        messages.success(request, f'Process "{process.name}" deleted successfully.')
    return redirect('sgierp:settings_processes')


@sgi_login_required
def user_list(request):
    """ERP user management."""
    erp_users = User.objects.filter(
        erp_profile__isnull=False
    ).select_related('erp_profile').order_by('username')
    context = {
        'erp_users': erp_users,
        'page_title': 'ERP Users',
    }
    return render(request, 'sgierp/settings/user_list.html', context)


@sgi_login_required
def user_create_edit(request, user_id=None):
    """Create or edit an ERP user."""
    target_user = None
    profile = None
    if user_id:
        target_user = get_object_or_404(User, id=user_id)
        try:
            profile = target_user.erp_profile
        except ERPUserProfile.DoesNotExist:
            profile = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', 'operator')
        department = request.POST.get('department', '').strip()
        phone = request.POST.get('phone', '').strip()
        is_erp_active = request.POST.get('is_erp_active') == 'on'
        password = request.POST.get('password', '').strip()

        errors = []
        if not username:
            errors.append('Username is required.')

        dup = User.objects.filter(username=username)
        if target_user:
            dup = dup.exclude(id=target_user.id)
        if dup.exists():
            errors.append(f'Username "{username}" already exists.')

        if not target_user and not password:
            errors.append('Password is required for new users.')
        if password and len(password) < 8:
            errors.append('Password must be at least 8 characters.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/settings/user_form.html', {
                'target_user': target_user, 'profile': profile,
                'page_title': 'Edit User' if target_user else 'New User',
            })

        with transaction.atomic():
            if target_user is None:
                target_user = User.objects.create_user(
                    username=username, email=email,
                    password=password,
                    first_name=first_name, last_name=last_name,
                )
            else:
                target_user.username = username
                target_user.email = email
                target_user.first_name = first_name
                target_user.last_name = last_name
                if password:
                    target_user.set_password(password)
                target_user.save()

            if profile is None:
                profile = ERPUserProfile(user=target_user)
            profile.role = role
            profile.department = department
            profile.phone = phone
            profile.is_erp_active = is_erp_active
            profile.save()

        messages.success(request, f'User {username} saved.')
        return redirect('sgierp:settings_users')

    return render(request, 'sgierp/settings/user_form.html', {
        'target_user': target_user,
        'profile': profile,
        'roles': ERPUserProfile.ROLE_CHOICES,
        'page_title': 'Edit User' if target_user else 'New User',
    })


@sgi_login_required
def assignee_create_edit(request, assignee_id=None):
    """Create or edit an Assignee (worker / staff)."""
    assignee = None
    if assignee_id:
        assignee = get_object_or_404(Assignee, id=assignee_id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        department = request.POST.get('department', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        errors = []
        if not name:
            errors.append('Name is required.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/settings/assignee_form.html', {
                'assignee': assignee,
                'page_title': 'Edit Assignee' if assignee else 'New Assignee',
            })

        if assignee is None:
            assignee = Assignee()
        assignee.name = name
        assignee.phone = phone
        assignee.department = department
        assignee.is_active = is_active
        user = get_sgi_user(request)
        assignee.created_by = user
        assignee.save()

        messages.success(request, f'Assignee "{name}" saved.')
        return redirect('sgierp:settings_assignees')

    return render(request, 'sgierp/settings/assignee_form.html', {
        'assignee': assignee,
        'page_title': 'Edit Assignee' if assignee else 'New Assignee',
    })


@sgi_login_required
def assignee_delete(request, assignee_id):
    """Deletean assignee with validation."""
    assignee = get_object_or_404(Assignee, id=assignee_id)

    # Check if assignee has any stock assigned
    stock_count = assignee.assigned_items.filter(quantity__gt=0).count()
    if stock_count > 0:
        messages.error(request, f'Cannot delete assignee "{assignee.name}" - they have {stock_count} stock entries assigned.')
        return redirect('sgierp:settings_assignees')

    assignee.delete()
    messages.success(request, f'Assignee "{assignee.name}" deleted successfully.')
    return redirect('sgierp:settings_assignees')
