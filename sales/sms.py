"""Africa's Talking SMS integration, for payment requests/reminders.

Needs two things only the business owner can set up -- see
AFRICASTALKING_SETUP.md at the repo root:
  1. An Africa's Talking account (sandbox or live).
  2. An application API key, paired with the account's username.

Without those, send_sms() reports 'not_configured' rather than silently
doing nothing or pretending to have sent something -- same defensive
pattern as sales/whatsapp.py and sales/mpesa.py.
"""
import requests
from django.conf import settings

from .mpesa import normalize_phone

AFRICASTALKING_SANDBOX_URL = 'https://api.sandbox.africastalking.com/version1/messaging'
AFRICASTALKING_LIVE_URL = 'https://api.africastalking.com/version1/messaging'


def _configured():
    return bool(settings.AT_USERNAME and settings.AT_API_KEY)


def _base_url():
    # Africa's Talking routes sandbox apps (username 'sandbox') to a
    # separate host from live ones -- sending a sandbox key to the live
    # URL (or vice versa) just fails authentication with no useful hint.
    return AFRICASTALKING_SANDBOX_URL if settings.AT_USERNAME == 'sandbox' else AFRICASTALKING_LIVE_URL


def send_sms(phone_number, message):
    """Sends `message` to phone_number via Africa's Talking. Returns
    (success: bool, detail: str) meant to be shown to the user directly.
    Never raises: network failures and API rejections are caught and
    reported, not left to crash whatever triggered this."""
    if not _configured():
        return False, (
            "SMS isn't set up for this deployment yet. See AFRICASTALKING_SETUP.md — "
            'you need an Africa\'s Talking account and AT_USERNAME / AT_API_KEY in the environment.'
        )

    normalized_phone = normalize_phone(phone_number)
    if not normalized_phone:
        return False, f'"{phone_number}" doesn\'t look like a valid Kenyan phone number.'

    payload = {
        'username': settings.AT_USERNAME,
        'to': f'+{normalized_phone}',
        'message': message,
    }
    if settings.AT_SENDER_ID:
        payload['from'] = settings.AT_SENDER_ID

    headers = {
        'apiKey': settings.AT_API_KEY,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    }

    try:
        response = requests.post(_base_url(), data=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        return False, f'Could not reach Africa\'s Talking: {exc}'

    if response.status_code >= 400:
        return False, f'Africa\'s Talking rejected the request ({response.status_code}): {response.text[:200]}'

    data = response.json() if response.content else {}
    recipients = data.get('SMSMessageData', {}).get('Recipients', [])
    if recipients and recipients[0].get('status') != 'Success':
        return False, f'Africa\'s Talking could not deliver the message: {recipients[0].get("status")}'

    return True, f'SMS sent to {normalized_phone}.'
