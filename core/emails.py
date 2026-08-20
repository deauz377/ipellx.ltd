import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def _absolute_url(path, request=None):
    """Same request-aware / SITE_URL-fallback pattern as
    sales.utils.build_pay_url() -- never a hardcoded domain."""
    if request is not None:
        return request.build_absolute_uri(path)
    return f'{settings.SITE_URL}{path}' if settings.SITE_URL else path


def send_verification_email(user, request=None):
    """Sends (or re-sends) user's signup verification email.

    Returns True on success, False if sending failed. Callers decide how to
    surface that: signup() lets the account through either way (the account
    already exists at that point; a resend link covers a delivery hiccup),
    and resend_verification() shows the same generic message regardless of
    success, so a delivery failure can't be used to probe which emails have
    accounts."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse('core:verify_email', kwargs={'uidb64': uid, 'token': token})
    context = {'user': user, 'verify_url': _absolute_url(path, request)}

    subject = render_to_string('core/verification_subject.txt', context).strip()
    text_body = render_to_string('core/verification_email.txt', context)
    html_body = render_to_string('core/verification_email.html', context)

    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    email.attach_alternative(html_body, 'text/html')
    try:
        email.send(fail_silently=False)
    except Exception:
        logger.exception('Failed to send verification email to user id=%s', user.pk)
        return False

    user.verification_sent_at = timezone.now()
    user.save(update_fields=['verification_sent_at'])
    return True
