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


def period_summary(tenant, period, reference_date=None):
    """Budgeted / spent / remaining totals for every budget of `period`
    overlapping the current period window.

    Spend is computed per budget over that budget's own date range (the
    same way Budget.spent_amount does it), not over the period window, so
    these figures always agree exactly with the Budgeting dashboard --
    two pages showing different numbers for the same thing would read as
    a bug to a business owner. The cache only avoids repeating an
    identical query; budgets sharing a category and range are still each
    counted, matching the Budgeting dashboard's own totals.
    """
    from .models import Budget

    start, end = period_bounds(period, reference_date)
    summary = {
        'period': period,
        'label': dict(Budget.PERIOD_CHOICES).get(period, period),
        'start': start,
        'end': end,
        'budgeted': Decimal('0'),
        'spent': Decimal('0'),
        'remaining': Decimal('0'),
        'usage_percent': Decimal('0'),
        'count': 0,
        'over_budget': False,
    }
    if tenant is None:
        return summary

    budgets = Budget.objects.filter(
        tenant=tenant, period=period, start_date__lte=end, end_date__gte=start,
    )

    spend_cache = {}
    for budget in budgets:
        summary['count'] += 1
        summary['budgeted'] += budget.amount
        window_start, window_end = budget._spend_window()
        key = (budget.category, window_start, window_end)
        if key not in spend_cache:
            spend_cache[key] = category_spend(tenant, budget.category, window_start, window_end)
        summary['spent'] += spend_cache[key]

    summary['remaining'] = summary['budgeted'] - summary['spent']
    if summary['budgeted']:
        summary['usage_percent'] = (summary['spent'] / summary['budgeted']) * 100
    summary['over_budget'] = summary['spent'] > summary['budgeted'] and summary['budgeted'] > 0
    return summary


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
