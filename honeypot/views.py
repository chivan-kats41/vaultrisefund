import logging

from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from .models import HoneypotAttempt
from .utils import get_client_ip

logger = logging.getLogger('honeypot')


def _log_attempt(request, email_tried=''):
    HoneypotAttempt.objects.create(
        ip_address=get_client_ip(request),
        path=request.path,
        method=request.method,
        email_tried=email_tried,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )
    logger.info(f"Honeypot hit: {get_client_ip(request)} {request.method} {request.path}")


def trap_view(request, *args, **kwargs):
    """Generic trap for wp-admin, .env, etc — just logs, no blocking."""
    _log_attempt(request)
    return render(request, 'honeypot/generic_trap.html', status=404)


@csrf_protect
def fake_admin_login(request):
    """
    Fake /admin/ login page. Logs every visit and every login attempt
    (including the email they tried), but never blocks — they can keep
    trying as many times as they like.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '')
        _log_attempt(request, email_tried=email)
        return render(request, 'honeypot/fake_admin_login.html', {'show_error': True})

    _log_attempt(request)
    return render(request, 'honeypot/fake_admin_login.html', {'show_error': False})