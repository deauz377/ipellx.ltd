"""Accountant Dashboard -- the finance work queue.

Deliberately sourced from where this business's money actually moves
(sales.Invoice, sales.Payment, MpesaTransaction, expenses.Expense,
sales.Order) rather than from the accounting app's own double-entry tables,
which are empty in this deployment. A dashboard built on ChartOfAccounts and
accounting.Invoice would render all zeros on day one.

Every figure is filtered by tenant explicitly rather than relying on
TenantManager's implicit scoping -- the same defensive style used in
dashboard.views.ceo_dashboard, since this aggregates across several apps at
once and a silent scoping miss would show another business's money.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

ZERO = Decimal('0')
MONEY = DecimalField(max_digits=14, decimal_places=2)

# Receivables ageing buckets, as (key, label, min_days_overdue, max_days_overdue).
AGEING_BUCKETS = (
    ('current', 'Not yet due', None, 0),
    ('d1_30', '1-30 days', 1, 30),
    ('d31_60', '31-60 days', 31, 60),
    ('d61_90', '61-90 days', 61, 90),
    ('d90_plus', 'Over 90 days', 91, None),
)


def _sum(queryset, field='amount'):
    return queryset.aggregate(t=Coalesce(Sum(field), ZERO, output_field=MONEY))['t']


def receivables(tenant, today):
    """Unpaid customer invoices, aged.

    Uses due_date when the invoice has one and falls back to the invoice date,
    so invoices raised before due dates existed still age sensibly instead of
    silently dropping out of the report.
    """
    from sales.models import Invoice

    open_invoices = (
        Invoice.objects.filter(tenant=tenant, paid__lt=F('total'))
        .select_related('customer')
    )

    rows, total, overdue_total = [], ZERO, ZERO
    buckets = {key: {'label': label, 'total': ZERO, 'count': 0}
               for key, label, _, _ in AGEING_BUCKETS}

    for inv in open_invoices:
        due = inv.due_date or inv.date.date()
        days_overdue = (today - due).days
        outstanding = inv.total - inv.paid
        total += outstanding
        if days_overdue > 0:
            overdue_total += outstanding

        for key, _label, low, high in AGEING_BUCKETS:
            if low is None:
                matched = days_overdue <= 0
            elif high is None:
                matched = days_overdue >= low
            else:
                matched = low <= days_overdue <= high
            if matched:
                buckets[key]['total'] += outstanding
                buckets[key]['count'] += 1
                break

        rows.append({
            'invoice': inv, 'due': due,
            'days_overdue': days_overdue, 'outstanding': outstanding,
        })

    rows.sort(key=lambda r: r['days_overdue'], reverse=True)
    return {
        'receivables_total': total,
        'receivables_overdue': overdue_total,
        'receivables_buckets': [buckets[key] for key, _, _, _ in AGEING_BUCKETS],
        'receivables_rows': rows[:10],
        'receivables_count': len(rows),
    }


def payables(tenant, today):
    """What the business owes: supplier purchase orders still live, plus any
    accounting Bills if that module is in use."""
    from accounting.models import Bill
    from sales.models import Order

    open_orders = (
        Order.objects.filter(tenant=tenant, order_type='supplier')
        .exclude(status='cancelled')
        .select_related('supplier')
        .order_by('-date')
    )
    unpaid_bills = (
        Bill.objects.filter(tenant=tenant)
        .exclude(status__in=['paid', 'cancelled'])
        .order_by('due_date')
    )

    return {
        'payables_orders': open_orders[:10],
        'payables_orders_total': _sum(open_orders, 'total'),
        'payables_orders_count': open_orders.count(),
        'payables_bills': unpaid_bills[:10],
        'payables_bills_total': _sum(
            unpaid_bills.annotate(due_amt=F('total_amount') - F('paid_amount')), 'due_amt',
        ),
        'payables_bills_overdue': unpaid_bills.filter(due_date__lt=today).count(),
    }


def cash_position(tenant, today):
    """Money actually received, by channel.

    A Payment row only ever represents confirmed money (see sales.models.Payment),
    so a still-pending M-Pesa push is reported separately rather than counted as
    cash in hand -- treating it as received is how a business talks itself into
    spending money that never arrived.
    """
    from sales.models import MpesaTransaction, Payment

    month_start = today.replace(day=1)
    confirmed = Payment.objects.filter(tenant=tenant, status='confirmed')
    this_month = confirmed.filter(date__date__gte=month_start)

    method_labels = dict(Payment.METHOD_CHOICES)
    by_method = [
        {'method': method_labels.get(row['method'], row['method']),
         'total': row['t'], 'count': row['n']}
        for row in this_month.values('method')
        .annotate(t=Coalesce(Sum('amount'), ZERO, output_field=MONEY), n=Count('id'))
        .order_by('-t')
    ]

    pending = MpesaTransaction.objects.filter(tenant=tenant, status='pending')
    return {
        'cash_month_total': _sum(this_month),
        'cash_today_total': _sum(confirmed.filter(date__date=today)),
        'cash_by_method': by_method,
        'mpesa_pending_count': pending.count(),
        'mpesa_pending_total': _sum(pending),
    }


def payroll_position(tenant, today):
    """The next payroll to fund, and anything processed but still unpaid."""
    from payroll.models import PayrollRun, Payslip

    upcoming = (
        PayrollRun.objects.filter(tenant=tenant)
        .exclude(status__in=['paid', 'cancelled'])
        .select_related('payroll_period')
        .order_by('payroll_period__payment_date')
        .first()
    )
    latest_paid = (
        PayrollRun.objects.filter(tenant=tenant, status='paid')
        .select_related('payroll_period')
        .order_by('-processing_date')
        .first()
    )
    unpaid_payslips = Payslip.objects.filter(tenant=tenant).exclude(payment_status='paid')

    return {
        'payroll_upcoming': upcoming,
        'payroll_latest_paid': latest_paid,
        'payroll_unpaid_count': unpaid_payslips.count(),
        'payroll_unpaid_total': _sum(unpaid_payslips, 'net_salary'),
    }


def tax_position(tenant, today):
    """Statutory deductions withheld, and therefore payable onward.

    Taken from payslip lines rather than a separate tax ledger: PAYE, NHIF and
    NSSF are modelled in this system as payroll Deductions, so the payslip
    breakdown is the authoritative record of what was actually withheld.

    Configured VAT/income-tax rates are surfaced alongside, but only when the
    business has set any up -- TaxConfiguration requires a ChartOfAccounts
    entry, so it stays empty until the double-entry ledger is in use.
    """
    from accounting.models import TaxConfiguration
    from payroll.models import PayslipDetail

    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    withheld = PayslipDetail.objects.filter(tenant=tenant, component_type='deduction')
    this_month = withheld.filter(
        payslip__payroll_run__payroll_period__payment_date__gte=month_start,
    )

    by_type = [
        {'name': row['component_name'], 'total': row['t']}
        for row in this_month.values('component_name')
        .annotate(t=Coalesce(Sum('amount'), ZERO, output_field=MONEY))
        .order_by('-t')
    ]

    return {
        'tax_withheld_month': _sum(this_month),
        'tax_withheld_year': _sum(
            withheld.filter(payslip__payroll_run__payroll_period__payment_date__gte=year_start),
        ),
        'tax_by_type': by_type,
        'tax_rates': TaxConfiguration.objects.filter(tenant=tenant, is_active=True),
    }


def spending_position(tenant, today):
    """Operating spend this month by category -- the other half of the picture
    from cash received."""
    from expenses.models import Expense

    month_start = today.replace(day=1)
    month_expenses = Expense.objects.filter(tenant=tenant, date__gte=month_start)
    category_labels = dict(Expense.CATEGORY_CHOICES)
    by_category = [
        {'category': category_labels.get(row['category'], row['category']), 'total': row['t']}
        for row in month_expenses.values('category')
        .annotate(t=Coalesce(Sum('amount'), ZERO, output_field=MONEY))
        .order_by('-t')[:6]
    ]
    return {
        'expenses_month_total': _sum(month_expenses),
        'expenses_by_category': by_category,
    }


def build_context(request):
    tenant = request.user.tenant
    today = timezone.localdate()

    context = {'today': today, 'week_ahead': today + timedelta(days=7)}
    for section in (receivables, payables, cash_position,
                    payroll_position, tax_position, spending_position):
        context.update(section(tenant, today))

    # One "does anything need attention today" signal for the header: every
    # overdue receivable bucket, overdue bills, and unpaid payslips.
    overdue_invoice_count = sum(
        bucket['count'] for bucket in context['receivables_buckets'][1:]
    )
    context['overdue_invoice_count'] = overdue_invoice_count
    context['action_count'] = (
        overdue_invoice_count
        + context['payables_bills_overdue']
        + context['payroll_unpaid_count']
    )
    return context
