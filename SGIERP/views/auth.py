"""SGIERP Auth views: login, logout, forgot password with OTP."""
import re
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from SGIERP.models import OTPToken, ERPUserProfile
from SGIERP.decorators import get_sgi_user


def login_view(request):
    """Login with username + password."""
    if request.session.get('sgi_user_id'):
        return redirect('sgierp:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        if not username or not password:
            messages.error(request, 'Please enter username and password.')
            return render(request, 'sgierp/auth/login.html')

        try:
            user = User.objects.select_related('erp_profile').get(
                username=username, is_active=True
            )
        except User.DoesNotExist:
            messages.error(request, 'Invalid username or password.')
            return render(request, 'sgierp/auth/login.html')

        if not user.check_password(password):
            messages.error(request, 'Invalid username or password.')
            return render(request, 'sgierp/auth/login.html')

        try:
            profile = user.erp_profile
            if not profile.is_erp_active:
                messages.error(request, 'Your account has been deactivated. Contact administrator.')
                return render(request, 'sgierp/auth/login.html')
        except ERPUserProfile.DoesNotExist:
            messages.error(request, 'Your account does not have ERP access. Contact administrator.')
            return render(request, 'sgierp/auth/login.html')

        request.session['sgi_user_id'] = user.id
        request.session.set_expiry(86400 * 30)  # 30 days
        return redirect('sgierp:dashboard')

    return render(request, 'sgierp/auth/login.html')


def logout_view(request):
    """Logout — clear SGI session."""
    request.session.pop('sgi_user_id', None)
    messages.success(request, 'You have been logged out.')
    return redirect('sgierp:login')


def forgot_password_view(request):
    """Step 1: Enter username, receive OTP on registered email."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        # Generic response to avoid revealing account existence
        success_msg = (
            'If this username has a registered email, an OTP has been sent. '
            'Please check your inbox.'
        )
        try:
            user = User.objects.select_related('erp_profile').get(username=username, is_active=True)
            if user.email:
                token = OTPToken.generate_for_user(user)
                try:
                    send_mail(
                        subject='SGIERP Password Reset OTP',
                        message=(
                            f'Your OTP for SGIERP password reset is: {token.otp}\n\n'
                            f'This OTP expires in 5 minutes. Do not share it with anyone.'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
                # Store username in session for OTP verification step
                request.session['sgi_pw_reset_user'] = user.id
        except User.DoesNotExist:
            pass

        messages.info(request, success_msg)
        return redirect('sgierp:verify_otp')

    return render(request, 'sgierp/auth/forgot_password.html')


def verify_otp_view(request):
    """Step 2: Enter OTP to verify identity."""
    user_id = request.session.get('sgi_pw_reset_user')
    if not user_id:
        return redirect('sgierp:forgot_password')

    if request.method == 'POST':
        otp_input = request.POST.get('otp', '').strip()

        try:
            user = User.objects.get(id=user_id, is_active=True)
            token = OTPToken.objects.filter(
                user=user, is_used=False
            ).order_by('-created_at').first()

            if not token:
                messages.error(request, 'No active OTP found. Please request a new one.')
                return render(request, 'sgierp/auth/verify_otp.html')

            token.attempt_count += 1
            token.save(update_fields=['attempt_count'])

            if not token.is_valid():
                messages.error(request, 'OTP has expired or exceeded maximum attempts. Please request a new one.')
                return redirect('sgierp:forgot_password')

            if token.otp != otp_input:
                messages.error(request, f'Invalid OTP. {5 - token.attempt_count} attempts remaining.')
                return render(request, 'sgierp/auth/verify_otp.html')

            # OTP correct — mark used and allow password reset
            token.is_used = True
            token.save(update_fields=['is_used'])
            request.session['sgi_pw_verified_user'] = user_id
            del request.session['sgi_pw_reset_user']
            return redirect('sgierp:reset_password')

        except User.DoesNotExist:
            messages.error(request, 'Session expired. Please try again.')
            return redirect('sgierp:forgot_password')

    return render(request, 'sgierp/auth/verify_otp.html')


def reset_password_view(request):
    """Step 3: Set new password after OTP verification."""
    user_id = request.session.get('sgi_pw_verified_user')
    if not user_id:
        return redirect('sgierp:forgot_password')

    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        confirm = request.POST.get('confirm_password', '').strip()

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'sgierp/auth/reset_password.html')

        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'sgierp/auth/reset_password.html')

        try:
            user = User.objects.get(id=user_id, is_active=True)
            user.set_password(password)
            user.save()
            del request.session['sgi_pw_verified_user']
            messages.success(request, 'Password reset successfully! Please login.')
            return redirect('sgierp:login')
        except User.DoesNotExist:
            messages.error(request, 'Session expired.')
            return redirect('sgierp:forgot_password')

    return render(request, 'sgierp/auth/reset_password.html')


def signup_view(request):
    """
    Self-registration page.
    Creates a Django User + ERPUserProfile (operator role).
    Admin can later change role / deactivate via Settings > Users.
    """
    if request.session.get('sgi_user_id'):
        return redirect('sgierp:dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        username   = request.POST.get('username', '').strip()
        email      = request.POST.get('email', '').strip()
        department = request.POST.get('department', '').strip()
        phone      = request.POST.get('phone', '').strip()
        password   = request.POST.get('password', '').strip()
        confirm    = request.POST.get('confirm_password', '').strip()

        errors = []

        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append(f'Username "{username}" is already taken.')

        if not password:
            errors.append('Password is required.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        elif password != confirm:
            errors.append('Passwords do not match.')

        if email and User.objects.filter(email=email).exclude(username=username).exists():
            errors.append('An account with this email already exists.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'sgierp/auth/signup.html', {'form_data': request.POST})

        # Create user + profile
        from django.db import transaction
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            ERPUserProfile.objects.create(
                user=user,
                role='operator',
                department=department,
                phone=phone,
                is_erp_active=True,
            )

        # Auto-login
        request.session['sgi_user_id'] = user.id
        request.session.set_expiry(86400 * 30)
        messages.success(request, f'Welcome to SGIERP, {user.get_full_name() or username}!')
        return redirect('sgierp:dashboard')

    return render(request, 'sgierp/auth/signup.html', {'form_data': {}})

