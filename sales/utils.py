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
