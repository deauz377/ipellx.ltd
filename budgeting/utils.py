from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone


def category_spend(tenant, category, start, end):
    """Total actually spent in `category` between start/end (inclusive),
    for `tenant`. Shared by Budget.spent_amount and the dashboard's
    category breakdown (which needs this for categories that don't have a
    budget yet too), so the category -> source-model mapping only lives
    in one place."""
    if start is None or end is None or end < start:
        return Decimal('0')

    if category == 'stock_purchases':
        from sales.models import Order
        total = Order.objects.filter(
            tenant=tenant, order_type='supplier', date__date__range=(start, end),
        ).exclude(status='cancelled').aggregate(t=Sum('total'))['t']
    else:
        from expenses.models import Expense
        total = Expense.objects.filter(
            tenant=tenant, category=category, date__range=(start, end),
        ).aggregate(t=Sum('amount'))['t']

    return total or Decimal('0')


def period_bounds(period, reference_date=None):
    """(start, end) date range for 'daily'/'weekly'/'monthly', containing
    reference_date (defaults to today). Weekly is Mon-Sun; monthly is the
    1st to the last day of that month."""
    reference_date = reference_date or timezone.localdate()

    if period == 'daily':
        return reference_date, reference_date

    if period == 'weekly':
        start = reference_date - timezone.timedelta(days=reference_date.weekday())
        return start, start + timezone.timedelta(days=6)

    # monthly
    start = reference_date.replace(day=1)
    if start.month == 12:
        next_month_start = start.replace(year=start.year + 1, month=1)
    else:
        next_month_start = start.replace(month=start.month + 1)
    end = next_month_start - timezone.timedelta(days=1)
    return start, end


def previous_period_bounds(period, current_start):
    """The immediately-preceding period's (start, end), for
    period-over-period comparisons (e.g. "vs last month")."""
    if period == 'daily':
        prev_day = current_start - timezone.timedelta(days=1)
        return prev_day, prev_day
    if period == 'weekly':
        prev_start = current_start - timezone.timedelta(days=7)
        return prev_start, prev_start + timezone.timedelta(days=6)
    # monthly: step back one day from the 1st to land in the previous month
    prev_month_end = current_start - timezone.timedelta(days=1)
    return period_bounds('monthly', prev_month_end)


def daily_totals(tenant, start, end):
    """[(date, total_spent), ...] for each day in [start, end] -- combines
    every Expense plus supplier Orders (stock/purchases), i.e. total
    day-by-day spend regardless of which categories have budgets set."""
    from django.db.models.functions import TruncDate
    from expenses.models import Expense
    from sales.models import Order

    expense_rows = (
        Expense.objects.filter(tenant=tenant, date__range=(start, end))
        .values('date').annotate(total=Sum('amount'))
    )
    expense_by_day = {row['date']: row['total'] for row in expense_rows}

    order_rows = (
        Order.objects.filter(tenant=tenant, order_type='supplier', date__date__range=(start, end))
        .exclude(status='cancelled')
        .annotate(day=TruncDate('date')).values('day').annotate(total=Sum('total'))
    )
    order_by_day = {row['day']: row['total'] for row in order_rows}

    totals = []
    day = start
    while day <= end:
        totals.append((day, (expense_by_day.get(day) or Decimal('0')) + (order_by_day.get(day) or Decimal('0'))))
        day += timezone.timedelta(days=1)
    return totals
