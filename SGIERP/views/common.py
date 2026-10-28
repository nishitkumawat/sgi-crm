"""SGIERP common views."""
from django.shortcuts import render
from SGIERP.decorators import get_sgi_user


def error_view(request, error_code=500, error_message=None):
    """Generic error page view for manual use."""
    # Try to get user but don't require login
    user = None
    try:
        user = get_sgi_user(request)
    except:
        pass

    # Default error messages based on code
    if not error_message:
        if error_code == 404:
            error_message = "The page you're looking for doesn't exist."
        elif error_code == 403:
            error_message = "You don't have permission to access this page."
        elif error_code == 500:
            error_message = "An unexpected error occurred on the server."
        else:
            error_message = "Something went wrong. Please try again."

    context = {
        'error_code': error_code,
        'error_message': error_message,
        'page_title': f'Error {error_code}' if error_code else 'Error',
        'sgi_user': user,
    }
    return render(request, 'sgierp/error.html', context, status=error_code)


def custom_404(request, exception):
    """Custom 404 error handler."""
    return error_view(request, error_code=404)


def custom_500(request):
    """Custom 500 error handler."""
    return error_view(request, error_code=500)


def custom_403(request, exception):
    """Custom 403 error handler."""
    return error_view(request, error_code=403)
