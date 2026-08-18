from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import date as _date

from .models import InvoiceItem, DailySalesEntry
from expenses.models import Expense


def compute_daily_profit(target_date=None):
    """Compute daily profit for target_date (date object).

    Profit = revenue - cost - expenses
    - revenue: sum of invoice item selling price * qty + DailySalesEntry.total
    - cost: sum of invoice item product.cost_price * qty
    - expenses: sum of Expense.amount for date

    Returns a dict with breakdown.
    """
    if target_date is None:
        target_date = _date.today()

    # Revenue and cost from invoice items
    items = (
        InvoiceItem.objects.filter(invoice__date__date=target_date)
        .annotate(
            revenue_item=ExpressionWrapper(F('price') * F('qty'), output_field=DecimalField()),
            cost_item=ExpressionWrapper(F('product__cost_price') * F('qty'), output_field=DecimalField()),
        )
        .aggregate(total_revenue=Sum('revenue_item'), total_cost=Sum('cost_item'))
    )

    revenue_from_items = items.get('total_revenue') or Decimal('0')
    cost_from_items = items.get('total_cost') or Decimal('0')

    # Include DailySalesEntry (free-text sales) in revenue; assume cost unknown (0)
    entries_total = (
        DailySalesEntry.objects.filter(date=target_date).aggregate(total=Sum('total'))['total'] or Decimal('0')
    )

    revenue = revenue_from_items + entries_total

    # Expenses
    expenses_total = Expense.objects.filter(date=target_date).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    gross_profit = revenue - cost_from_items
    net_profit = gross_profit - expenses_total

    return {
        'date': target_date,
        'revenue': revenue,
        'cost': cost_from_items,
        'gross_profit': gross_profit,
        'expenses': expenses_total,
        'net_profit': net_profit,
    }


def build_pay_url(payment_request, request=None):
    """Absolute URL for a payment request's public page. Prefers
    request.build_absolute_uri() when called from a view (correct host
    even behind a proxy); falls back to settings.SITE_URL for contexts
    with no request at all, like the send_payment_reminders management
    command running under Vercel Cron."""
    from django.conf import settings
    from django.urls import reverse

    path = reverse('pay:pay', args=[payment_request.token])
    if request is not None:
        return request.build_absolute_uri(path)
    return f'{settings.SITE_URL}{path}' if settings.SITE_URL else path


def send_payment_request_reminder(payment_request, pay_url):
    """Sends a reminder for payment_request via whichever channels are
    actually configured (WhatsApp, then SMS) -- shared by the manual
    "Send Reminder" view and the scheduled send_payment_reminders
    command, so the two can't silently drift apart. Amount is always
    invoice.balance, recomputed fresh here, never a stale snapshot.

    Returns the list of channel names actually sent via (empty if none
    configured or all failed). Never raises."""
    from .whatsapp import send_payment_request_whatsapp
    from .sms import send_sms

    invoice = payment_request.invoice
    amount = invoice.balance
    sent_via = []

    wa_success, _wa_note = send_payment_request_whatsapp(payment_request, amount)
    if wa_success:
        sent_via.append('WhatsApp')

    sms_message = (
        f"Reminder: your invoice #{invoice.pk} has an outstanding balance of "
        f"KES {amount:,.2f}. Pay here: {pay_url}"
    )
    sms_success, _sms_note = send_sms(invoice.customer.phone, sms_message)
    if sms_success:
        sent_via.append('SMS')

    return sent_via
