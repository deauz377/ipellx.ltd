"""M-Pesa Daraja API (Safaricom) integration: STK Push customer payments.

Needs real setup only the business owner can do -- see MPESA_SETUP.md.
Two calls happen at very different times:

  1. initiate_stk_push() -- called synchronously from a view when someone
     clicks "Pay with M-Pesa". Sends the push, gets back a
     CheckoutRequestID immediately, creates a *pending* MpesaTransaction.
  2. handle_callback() -- called later (seconds to minutes, or never, if
     the customer just ignores the prompt) by Safaricom POSTing to
     MPESA_CALLBACK_URL. Only this step creates a real Payment and moves
     invoice.paid -- initiate_stk_push() by itself proves nothing.
"""
import base64
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from .models import Invoice, MpesaTransaction, Payment

DARAJA_BASE_URLS = {
    'sandbox': 'https://sandbox.safaricom.co.ke',
    'production': 'https://api.safaricom.co.ke',
}


def _base_url():
    return DARAJA_BASE_URLS.get(settings.MPESA_ENVIRONMENT, DARAJA_BASE_URLS['sandbox'])


def _configured():
    return bool(
        settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET
        and settings.MPESA_SHORTCODE and settings.MPESA_PASSKEY and settings.MPESA_CALLBACK_URL
    )


def normalize_phone(raw):
    """07XXXXXXXX / +2547XXXXXXXX / 2547XXXXXXXX -> 2547XXXXXXXX (what
    Daraja expects). Returns None if it doesn't look like a Kenyan
    mobile number at all, rather than sending Safaricom something that
    will just be rejected less clearly."""
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits.startswith('254') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '254' + digits[1:]
    if digits.startswith('7') and len(digits) == 9:
        return '254' + digits
    return None


def _get_access_token():
    credentials = f'{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}'
    auth = base64.b64encode(credentials.encode()).decode()
    response = requests.get(
        f'{_base_url()}/oauth/v1/generate',
        params={'grant_type': 'client_credentials'},
        headers={'Authorization': f'Basic {auth}'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()['access_token']


def initiate_stk_push(invoice, phone_number, amount, user=None):
    """Sends an STK Push prompt to phone_number for `amount` against
    `invoice`. Returns (success: bool, message: str, transaction:
    MpesaTransaction | None). Never raises -- network/API/auth failures
    are caught and reported, not left to crash the view that called this.
    """
    if not _configured():
        return False, (
            "M-Pesa isn't set up for this deployment yet. See MPESA_SETUP.md — "
            'you need a Daraja account, a paybill/till shortcode, and the '
            'MPESA_* environment variables set.'
        ), None

    normalized_phone = normalize_phone(phone_number)
    if not normalized_phone:
        return False, f'"{phone_number}" doesn\'t look like a valid Kenyan phone number.', None

    try:
        access_token = _get_access_token()
    except requests.RequestException as exc:
        return False, f'Could not authenticate with M-Pesa: {exc}', None

    timestamp = timezone.localtime().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(
        f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'.encode()
    ).decode()

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        # Daraja wants a whole-shilling amount, not cents.
        'Amount': int(amount),
        'PartyA': normalized_phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': normalized_phone,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': f'Invoice{invoice.pk}',
        'TransactionDesc': f'Payment for Invoice #{invoice.pk}',
    }

    try:
        response = requests.post(
            f'{_base_url()}/mpesa/stkpush/v1/processrequest',
            json=payload,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f'Could not reach M-Pesa: {exc}', None

    data = response.json() if response.content else {}
    if response.status_code >= 400 or data.get('ResponseCode') != '0':
        error_message = data.get('errorMessage') or data.get('ResponseDescription') or response.text[:200]
        return False, f'M-Pesa rejected the request: {error_message}', None

    transaction = MpesaTransaction.objects.create(
        invoice=invoice,
        # Explicit, not left to auto-assignment -- the invoice's own tenant
        # is the correct source of truth for who this belongs to, not
        # whatever the current request context happens to resolve to.
        tenant=invoice.tenant,
        phone_number=normalized_phone,
        amount=Decimal(amount),
        checkout_request_id=data['CheckoutRequestID'],
        merchant_request_id=data.get('MerchantRequestID', ''),
        status='pending',
        initiated_by=user,
    )
    return True, data.get('CustomerMessage', 'Payment prompt sent — ask the customer to check their phone.'), transaction


def handle_callback(payload):
    """Processes Safaricom's STK Push callback body. Looks up the
    matching MpesaTransaction by CheckoutRequestID; on success (ResultCode
    0) creates a real Payment and updates invoice.paid, exactly matching
    what the manual "Record Payment" flow does, since this is just a
    different way of arriving at the same recorded payment.

    Returns True if a matching transaction was found and processed (even
    if the result was a failure/cancellation), False if the
    CheckoutRequestID is unrecognised -- the view uses this only for
    logging; Safaricom gets a 200 either way, since re-sending the
    callback would just repeat the same "unknown ID" outcome."""
    try:
        stk_callback = payload['Body']['stkCallback']
        checkout_request_id = stk_callback['CheckoutRequestID']
        result_code = stk_callback['ResultCode']
        result_desc = stk_callback.get('ResultDesc', '')
    except (KeyError, TypeError):
        return False

    try:
        transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
    except MpesaTransaction.DoesNotExist:
        return False

    if transaction.status != 'pending':
        # Safaricom can retry callbacks; only act on it once.
        return True

    transaction.result_description = result_desc
    transaction.completed_at = timezone.now()

    if result_code == 0:
        items = {
            item['Name']: item.get('Value')
            for item in stk_callback.get('CallbackMetadata', {}).get('Item', [])
        }
        transaction.status = 'success'
        transaction.mpesa_receipt_number = str(items.get('MpesaReceiptNumber', ''))
        transaction.save()

        # tenant= is explicit and required here, not left to TenantModel's
        # auto-assignment: this runs from an unauthenticated webhook (there
        # is no logged-in user whose tenant the middleware could have set),
        # so relying on that would fall back to the 'default' tenant rather
        # than whichever business this invoice actually belongs to.
        payment = Payment.objects.create(
            invoice=transaction.invoice, method='mpesa', amount=transaction.amount,
            tenant=transaction.tenant,
        )
        invoice = transaction.invoice
        invoice.paid = invoice.paid + transaction.amount
        invoice.save(update_fields=['paid'])
    else:
        transaction.status = 'failed'
        transaction.save()

    return True
