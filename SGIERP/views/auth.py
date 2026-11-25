"""SGIERP Auth views: login, logout, forgot password with OTP."""
import logging
import re
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from SGIERP.models import OTPToken, ERPUserProfile
from SGIERP.decorators import get_sgi_user

logger = logging.getLogger(__name__)


def _mask_email(email):
    """Mask email for privacy, e.g. ni****60@gmail.com, ad***@domain.com."""
    if not email or '@' not in email:
        return ''
    user_part, domain = email.strip().split('@', 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + '*'
    elif len(user_part) <= 4:
        masked_user = user_part[0] + '*' * (len(user_part) - 2) + user_part[-1]
    else:
        masked_user = user_part[:2] + '*' * (len(user_part) - 4) + user_part[-2:]
    return f"{masked_user}@{domain}"


def _send_otp_email(user, token):
    """Send OTP email with both plain text and rich HTML layout."""
    subject = 'SGIERP Password Reset OTP'
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 28px 24px; border: 1px solid #e2e8f0; border-radius: 10px; background: #ffffff;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #18304f; margin: 0 0 6px 0; font-size: 22px;">Shree Gayatri Industries</h2>
            <div style="color: #64748b; font-size: 13px;">ERP System Password Reset</div>
        </div>
        <p style="color: #334155; font-size: 15px; margin-bottom: 12px;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
        <p style="color: #475569; font-size: 14px; line-height: 1.5; margin-bottom: 20px;">
            We received a request to reset the password for your SGIERP account (<strong>{user.username}</strong>).
            Enter the 6-digit verification code below to proceed:
        </p>
        <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
            <div style="font-size: 32px; font-weight: 800; letter-spacing: 10px; color: #18304f; font-family: 'Courier New', Courier, monospace;">{token.otp}</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 6px; text-transform: uppercase; letter-spacing: 1px;">Valid for 5 minutes &middot; Single Use</div>
        </div>
        <p style="color: #64748b; font-size: 12.5px; line-height: 1.4; margin-bottom: 20px;">
            If you did not request this password reset, please ignore this email. Your current password remains secure.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <div style="color: #94a3b8; font-size: 11px; text-align: center;">
            This is an automated security message from SGIERP. Please do not reply to this email.
        </div>
    </div>
    """
    plain_message = (
        f"Hello {user.get_full_name() or user.username},\n\n"
        f"Your OTP for SGIERP password reset is: {token.otp}\n\n"
        f"This OTP expires in 5 minutes and is valid for a single use. Do not share it with anyone.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— Shree Gayatri Industries ERP"
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'machmate.contact@gmail.com'

    # Always log OTP in console/terminal for development visibility
    print(f"[AUTH OTP] User: {user.username} ({user.email}) -> OTP: {token.otp}")

    send_mail(
        subject=subject,
        message=plain_message,
        html_message=html_content,
        from_email=from_email,
        recipient_list=[user.email],
        fail_silently=False,
    )


def login_view(request):
    """Login with username/email + password."""
    if request.session.get('sgi_user_id'):
        return redirect('sgierp:dashboard')

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        if not identifier or not password:
            messages.error(request, 'Please enter username/email and password.')
            return render(request, 'sgierp/auth/login.html')

        user = User.objects.select_related('erp_profile').filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier),
            is_active=True
        ).first()

        if not user or not user.check_password(password):
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
    """Step 1: Enter username or email, receive OTP on registered email."""
    if request.session.get('sgi_user_id'):
        return redirect('sgierp:dashboard')

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        if not identifier:
            messages.error(request, 'Please enter your username or registered email.')
            return render(request, 'sgierp/auth/forgot_password.html')

        user = User.objects.select_related('erp_profile').filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier),
            is_active=True
        ).first()

        if not user:
            messages.error(request, 'No active account found with that username or email address.')
            return render(request, 'sgierp/auth/forgot_password.html', {'entered_username': identifier})

        if not user.email or not user.email.strip():
            messages.error(
                request,
                f'Account "{user.username}" does not have a registered email address. '
                f'Please contact an administrator to reset your password.'
            )
            return render(request, 'sgierp/auth/forgot_password.html', {'entered_username': identifier})

        try:
            token = OTPToken.generate_for_user(user)
            _send_otp_email(user, token)
        except Exception as e:
            logger.exception(f"Error sending OTP email for {user.username} ({user.email}): {e}")
            messages.error(
                request,
                'Could not send OTP email due to a mail server error. Please try again or contact administrator.'
            )
            return render(request, 'sgierp/auth/forgot_password.html', {'entered_username': identifier})

        masked = _mask_email(user.email)
        request.session['sgi_pw_reset_user'] = user.id
        request.session['sgi_pw_reset_masked_email'] = masked
        messages.success(request, f'An OTP has been sent to {masked}. Please check your inbox.')
        return redirect('sgierp:verify_otp')

    return render(request, 'sgierp/auth/forgot_password.html')


def verify_otp_view(request):
    """Step 2: Enter OTP to verify identity."""
    user_id = request.session.get('sgi_pw_reset_user')
    masked_email = request.session.get('sgi_pw_reset_masked_email', '')

    if not user_id:
        messages.error(request, 'Please enter your username or email first.')
        return redirect('sgierp:forgot_password')

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, 'Account not found. Please try again.')
        request.session.pop('sgi_pw_reset_user', None)
        request.session.pop('sgi_pw_reset_masked_email', None)
        return redirect('sgierp:forgot_password')

    if not masked_email and user.email:
        masked_email = _mask_email(user.email)

    # Handle Resend OTP
    if request.method == 'POST' and request.POST.get('action') == 'resend':
        try:
            token = OTPToken.generate_for_user(user)
            _send_otp_email(user, token)
            messages.success(request, f'A fresh OTP has been sent to {masked_email or user.email}.')
        except Exception as e:
            logger.exception(f"Error resending OTP email for {user.username}: {e}")
            messages.error(request, 'Could not resend OTP email. Please try again in a moment.')
        return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user})

    if request.method == 'POST':
        otp_input = request.POST.get('otp', '').strip()
        if not otp_input:
            messages.error(request, 'Please enter the 6-digit OTP.')
            return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user})

        token = OTPToken.objects.filter(
            user=user, is_used=False
        ).order_by('-created_at').first()

        if not token:
            messages.error(request, 'No active OTP found. Please request a new one.')
            return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user})

        token.attempt_count += 1
        token.save(update_fields=['attempt_count'])

        if not token.is_valid():
            if timezone.now() >= token.expires_at:
                messages.error(request, 'This OTP has expired (5 minute limit). Please click Resend OTP.')
            elif token.attempt_count >= 5:
                messages.error(request, 'Maximum verification attempts exceeded. Please request a new OTP.')
            else:
                messages.error(request, 'OTP is no longer valid. Please request a new one.')
            return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user, 'can_resend': True})

        if token.otp != otp_input:
            remaining = max(0, 5 - token.attempt_count)
            if remaining > 0:
                messages.error(request, f'Invalid OTP. {remaining} attempt(s) remaining.')
            else:
                messages.error(request, 'Maximum verification attempts exceeded. Please request a new OTP.')
            return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user})

        # OTP correct — mark used and allow password reset
        token.is_used = True
        token.save(update_fields=['is_used'])
        request.session['sgi_pw_verified_user'] = user_id
        request.session.pop('sgi_pw_reset_user', None)
        request.session.pop('sgi_pw_reset_masked_email', None)
        return redirect('sgierp:reset_password')

    return render(request, 'sgierp/auth/verify_otp.html', {'masked_email': masked_email, 'user_obj': user})


def reset_password_view(request):
    """Step 3: Set new password after OTP verification."""
    user_id = request.session.get('sgi_pw_verified_user')
    if not user_id:
        messages.error(request, 'Session expired. Please request a new OTP.')
        return redirect('sgierp:forgot_password')

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, 'Account not found.')
        return redirect('sgierp:forgot_password')

    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        confirm = request.POST.get('confirm_password', '').strip()

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'sgierp/auth/reset_password.html', {'user_obj': user})

        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'sgierp/auth/reset_password.html', {'user_obj': user})

        user.set_password(password)
        user.save()
        request.session.pop('sgi_pw_verified_user', None)
        messages.success(request, 'Password reset successfully! Please sign in with your new password.')
        return redirect('sgierp:login')

    return render(request, 'sgierp/auth/reset_password.html', {'user_obj': user})


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

