"""WhatsApp Business Cloud API integration for supplier order alerts.

Needs three things only the business owner can set up -- see
WHATSAPP_SETUP.md at the repo root:
  1. A Meta Business Account with a verified WhatsApp Business phone number.
  2. An approved message template (business-initiated WhatsApp messages
     must use one; free-form text only works within 24 hours of the
     recipient messaging first).
  3. WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and (if not using the
     default name) WHATSAPP_TEMPLATE_NAME set in the environment.

Without those, send_supplier_order_alert() reports 'not_configured'
rather than silently doing nothing or pretending to have sent something.
"""
import requests
from django.conf import settings
from django.utils import timezone

WHATSAPP_API_VERSION = 'v20.0'


def _format_items_summary(order):
    lines = [f'{item.qty} x {item.product.name}' for item in order.items.all()]
    return '; '.join(lines) if lines else '(no items yet)'


def send_supplier_order_alert(order):
    """Sends a WhatsApp template message to order.supplier for this
    purchase order. Sets order.supplier_notified_at and
    order.supplier_notification_status on the passed-in instance, but
    does not save() it -- the caller decides when, so this can share a
    transaction with whatever else it's doing.

    Returns (success: bool, message: str) meant to be shown to the user
    directly. Never raises: network failures and API rejections are
    caught and reported as a 'failed' status instead of taking down
    the request that triggered this.
    """
    if not (settings.WHATSAPP_API_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID):
        order.supplier_notification_status = 'not_configured'
        return False, (
            "WhatsApp isn't set up for this deployment yet. See WHATSAPP_SETUP.md — "
            'you need a Meta Business Account, an approved message template, and '
            'WHATSAPP_API_TOKEN / WHATSAPP_PHONE_NUMBER_ID in the environment.'
        )

    supplier = order.supplier
    if not supplier or not supplier.phone:
        order.supplier_notification_status = 'no_phone'
        return False, 'This supplier has no WhatsApp number on file. Add one on the supplier record first.'

    business_name = order.tenant.name if order.tenant else 'Your business'
    items_summary = _format_items_summary(order)

    url = f'https://graph.facebook.com/{WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
    payload = {
        'messaging_product': 'whatsapp',
        'to': supplier.phone,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_NAME,
            'language': {'code': 'en_US'},
            # Parameter order must match whatever body text was approved
            # for this template in Meta Business Manager -- see
            # WHATSAPP_SETUP.md for the exact wording these line up with.
            'components': [{
                'type': 'body',
                'parameters': [
                    {'type': 'text', 'text': business_name},
                    {'type': 'text', 'text': str(order.pk)},
                    {'type': 'text', 'text': items_summary},
                    {'type': 'text', 'text': f'KES {order.total:,.2f}'},
                ],
            }],
        },
    }
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_API_TOKEN}',
        'Content-Type': 'application/json',
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        order.supplier_notification_status = 'failed'
        return False, f'Could not reach WhatsApp: {exc}'

    if response.status_code >= 400:
        order.supplier_notification_status = 'failed'
        return False, f'WhatsApp API rejected the message ({response.status_code}): {response.text[:200]}'

    order.supplier_notified_at = timezone.now()
    order.supplier_notification_status = 'sent'
    return True, f'Alert sent to {supplier.name} via WhatsApp.'
