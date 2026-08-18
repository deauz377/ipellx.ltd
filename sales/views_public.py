"""The customer-facing side of a payment request: a page reachable with
no login at all, secured only by the unguessable token in the URL. See
core/middleware.py's EXEMPT_PREFIXES ('/pay/') and PaymentRequest.token
(sales/models.py) for the two halves of that security boundary.

Every view here looks up PaymentRequest via _base_manager, never
.objects -- an anonymous request has no real tenant in scope (see
tenants/middleware.py), so the ordinary tenant-scoped manager would
silently 404 every payment link that doesn't happen to belong to
whichever tenant an anonymous request resolves to. _base_manager is a
plain, un-mutated Manager Django creates automatically for every model,
completely separate from that tenant-filtering logic.

The amount charged is always invoice.balance, computed fresh from the
database on every request -- never a client-supplied value, and never
the PaymentRequest.amount_due snapshot, which goes stale the moment any
other payment lands against the invoice."""
from datetime import timedelta
from decimal import InvalidOperation

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import MpesaTransaction, PaymentAuditLog, PaymentRequest
from . import mpesa

# How long a still-pending STK Push attempt blocks a new one for the same
# invoice -- long enough to cover the real round-trip to the customer's
# phone and back, short enough that a genuinely abandoned attempt doesn't
# lock the page for good.
DUPLICATE_PUSH_WINDOW = timedelta(seconds=90)


def _get_payment_request_or_404(token):
    try:
        return PaymentRequest._base_manager.select_related('invoice__customer', 'invoice__tenant').get(token=token)
    except PaymentRequest.DoesNotExist:
        raise Http404('Payment link not found')


def pay(request, token):
    payment_request = _get_payment_request_or_404(token)
    invoice = payment_request.invoice
    tenant = invoice.tenant

    if payment_request.status == 'cancelled':
        return render(request, 'sales/pay_public.html', {'inactive': True, 'tenant': tenant})

    balance = invoice.balance
    if balance <= 0:
        if payment_request.status != 'paid':
            payment_request.status = 'paid'
            payment_request.save(update_fields=['status'])
        return render(request, 'sales/pay_public.html', {'already_paid': True, 'tenant': tenant, 'invoice': invoice})

    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip()
        recent_pending = MpesaTransaction._base_manager.filter(
            invoice=invoice, status='pending', created_at__gte=timezone.now() - DUPLICATE_PUSH_WINDOW,
        ).exists()
        if recent_pending:
            error = "A payment prompt was already sent to a phone for this invoice moments ago — check your phone, or wait a bit before trying again."
        else:
            success, note, _txn = mpesa.initiate_stk_push(invoice, phone_number, balance, user=None)
            PaymentAuditLog.objects.create(
                invoice=invoice, payment_request=payment_request, action='stk_push_initiated',
                tenant=tenant, metadata={'amount': str(balance), 'success': success},
            )
            if success:
                return redirect('pay:pay', token=token)
            error = note
    else:
        error = None

    context = {
        'payment_request': payment_request,
        'invoice': invoice,
        'tenant': tenant,
        'customer': invoice.customer,
        'balance': balance,
        'error': error,
        'pending_transaction': MpesaTransaction._base_manager.filter(invoice=invoice, status='pending').order_by('-created_at').first(),
    }
    return render(request, 'sales/pay_public.html', context)


def pay_status(request, token):
    """Polled by the page's JS while an STK Push is pending, so the
    customer sees confirmation without reloading the page themselves."""
    payment_request = _get_payment_request_or_404(token)
    invoice = payment_request.invoice
    latest_txn = MpesaTransaction._base_manager.filter(invoice=invoice).order_by('-created_at').first()
    return JsonResponse({
        'balance': str(invoice.balance),
        'payment_status': invoice.payment_status,
        'mpesa_status': latest_txn.status if latest_txn else None,
    })
