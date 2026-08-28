"""Read-only financial reporting derived from the ERP's primary records.

No row in this module is a ledger entry.  InvoiceItem is the product-sales
ledger, Payment is the money-received ledger, Expense is the operating-cost
ledger and StockMovement is the inventory ledger.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from expenses.models import Expense
from inventory.models import Product, StockMovement
from .models import Invoice, InvoiceItem, Payment


MONEY = DecimalField(max_digits=16, decimal_places=2)
ZERO = Decimal('0')


def _date_filter(queryset, field, start, end):
    return queryset.filter(**{f'{field}__gte': start, f'{field}__lte': end})


def product_totals(tenant, start, end):
    """Return sales/COGS/gross-profit by product for an inclusive date range."""
    items = _date_filter(
        InvoiceItem.objects.filter(tenant=tenant), 'invoice__date__date', start, end,
    ).annotate(
        revenue=ExpressionWrapper(F('qty') * F('price'), output_field=MONEY),
        cogs=ExpressionWrapper(F('qty') * F('cost_price'), output_field=MONEY),
    )
    return items.values('product_id').annotate(
        units_sold=Sum('qty'), revenue=Sum('revenue'), cogs=Sum('cogs'),
    )


def product_performance(tenant, today, week_start, month_start):
    """One row per product, augmented from three bounded aggregate queries."""
    windows = {
        'today': product_totals(tenant, today, today),
        'week': product_totals(tenant, week_start, today),
        'month': product_totals(tenant, month_start, today),
    }
    totals = {key: {r['product_id']: r for r in rows} for key, rows in windows.items()}
    rows = []
    for product in Product.objects.filter(tenant=tenant, is_active=True).order_by('name'):
        row = {'product': product}
        for prefix in ('today', 'week', 'month'):
            value = totals[prefix].get(product.pk, {})
            revenue = value.get('revenue') or ZERO
            cogs = value.get('cogs') or ZERO
            row[f'{prefix}_units'] = value.get('units_sold') or ZERO
            row[f'{prefix}_revenue'] = revenue
            row[f'{prefix}_cogs'] = cogs
            row[f'{prefix}_gross_profit'] = revenue - cogs
        row['restock_quantity'] = product.recommended_order_quantity
        row['restock_cost'] = row['restock_quantity'] * product.cost_price
        row['stock_value'] = product.stock_value
        rows.append(row)
    return rows


def business_day_summary(tenant, business_date):
    """An auditable day-close report, calculated directly from real records."""
    product_rows = []
    totals = list(product_totals(tenant, business_date, business_date))
    products = Product.objects.filter(
        tenant=tenant, pk__in=[row['product_id'] for row in totals],
    ).in_bulk()
    for row in totals:
        product = products.get(row['product_id'])
        if not product:
            continue
        revenue = row['revenue'] or ZERO
        cogs = row['cogs'] or ZERO
        product_rows.append({
            'product_id': product.pk, 'product': product.name,
            'quantity_sold': row['units_sold'] or ZERO,
            'revenue': revenue, 'cogs': cogs, 'gross_profit': revenue - cogs,
        })

    invoices = Invoice.objects.filter(tenant=tenant, date__date=business_date)
    revenue = invoices.aggregate(value=Sum('total'))['value'] or ZERO
    expenses = Expense.objects.filter(tenant=tenant, date=business_date)
    expense_total = expenses.aggregate(value=Sum('amount'))['value'] or ZERO
    cogs = sum((row['cogs'] for row in product_rows), ZERO)
    payments = Payment.objects.filter(tenant=tenant, status='confirmed', date__date=business_date)
    payment_methods = {
        row['method']: row['amount'] or ZERO
        for row in payments.values('method').annotate(amount=Sum('amount'))
    }
    movements = StockMovement.objects.filter(tenant=tenant, created_at__date=business_date)

    return {
        'business_date': business_date.isoformat(),
        'sales': {'invoice_count': invoices.count(), 'revenue': revenue, 'payment_methods': payment_methods},
        'product_performance': product_rows,
        'expenses': list(expenses.values('category').annotate(amount=Sum('amount')).order_by('category')),
        'inventory': {
            'movement_count': movements.count(),
            'sold_quantity': movements.filter(movement_type=StockMovement.SALE).aggregate(value=Sum('quantity_delta'))['value'] or ZERO,
        },
        'financial_summary': {
            'revenue': revenue, 'cogs': cogs, 'gross_profit': revenue - cogs,
            'operating_expenses': expense_total, 'net_profit': revenue - cogs - expense_total,
        },
    }


def json_safe(value):
    """Convert Decimal-rich ORM aggregates into a stable JSON close snapshot."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value
