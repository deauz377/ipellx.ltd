from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import Invoice, InvoiceItem, Payment, Order, OrderItem, DailySalesEntry, ProfitEntry
from .forms import (
    InvoiceForm, InvoiceItemForm, PaymentForm, OrderForm, OrderItemForm,
    QuickSaleForm, QuickSaleItemFormSet, DailySalesEntryForm, ProfitEntryForm,
)
from inventory.models import Product
from customers.models import Customer
from .utils import compute_daily_profit
from django.utils.dateparse import parse_date
from tenants.decorators import role_required

@login_required
def sales_overview(request):
    # Get today's sales
    today = timezone.localdate()
    sales_today = Invoice.objects.filter(date__date=today).aggregate(total=Sum('total'))['total'] or 0

    # Get this month's sales
    month_start = today.replace(day=1)
    sales_month = Invoice.objects.filter(date__date__gte=month_start).aggregate(total=Sum('total'))['total'] or 0

    # Get total outstanding payments
    outstanding = Invoice.objects.aggregate(total=Sum('total'), paid=Sum('paid'))['total'] or 0
    total_paid = Invoice.objects.aggregate(paid=Sum('paid'))['paid'] or 0
    outstanding_amount = outstanding - total_paid

    # Get recent invoices
    recent_invoices = Invoice.objects.all().order_by('-date')[:5]

    # Get top selling products (by quantity)
    top_products = InvoiceItem.objects.values('product__name').annotate(
        total_quantity=Sum('qty')
    ).order_by('-total_quantity')[:5]

    context = {
        'sales_today': sales_today,
        'sales_month': sales_month,
        'outstanding_amount': outstanding_amount,
        'recent_invoices': recent_invoices,
        'top_products': top_products,
    }
    return render(request, 'sales/overview.html', context)

@login_required
def quick_sale(request):
    if request.method == 'POST':
        form = QuickSaleForm(request.POST)
        formset = QuickSaleItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            lines = []
            stock_errors = []
            channel_prices = {
                'retail': lambda p: p.retail_price,
                'wholesale': lambda p: p.wholesale_price,
                'online': lambda p: p.online_price,
            }
            for line_form in formset:
                product = line_form.cleaned_data.get('product')
                qty = line_form.cleaned_data.get('qty')
                if not product or not qty:
                    continue
                channel = line_form.cleaned_data.get('channel') or 'retail'
                price = line_form.cleaned_data.get('price')
                if price is None:
                    price = channel_prices.get(channel, channel_prices['retail'])(product)
                if qty > product.quantity:
                    stock_errors.append(
                        f"Only {product.quantity} of \"{product.name}\" in stock (you entered {qty})."
                    )
                lines.append({'product': product, 'qty': qty, 'price': price, 'channel': channel})

            if not lines:
                form.add_error(None, 'Add at least one product with a quantity.')
            elif stock_errors:
                for err in stock_errors:
                    form.add_error(None, err)
            else:
                customer = form.cleaned_data.get('customer')
                if not customer:
                    customer, _ = Customer.objects.get_or_create(name='Walk-in Customer')

                discount = form.cleaned_data.get('discount') or 0
                subtotal = sum(l['qty'] * l['price'] for l in lines)
                total = subtotal - discount

                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        customer=customer, discount=discount, total=total,
                        created_by=request.user,
                    )

                    for l in lines:
                        InvoiceItem.objects.create(
                            invoice=invoice, product=l['product'], qty=l['qty'], price=l['price'],
                            cost_price=l['product'].cost_price, sale_channel=l['channel'],
                        )
                        product = l['product']
                        product.quantity = F('quantity') - l['qty']
                        product.save(update_fields=['quantity'])

                    amount_received = form.cleaned_data.get('amount_received')
                    paid_amount = amount_received if amount_received is not None else total
                    invoice.paid = paid_amount
                    invoice.save(update_fields=['paid'])

                    if paid_amount > 0:
                        Payment.objects.create(
                            invoice=invoice,
                            method=form.cleaned_data['payment_method'],
                            amount=paid_amount,
                        )

                messages.success(request, f'Sale recorded — Invoice #{invoice.pk}.')
                return redirect('sales:invoice_detail', pk=invoice.pk)
    else:
        form = QuickSaleForm()
        formset = QuickSaleItemFormSet()

    return render(request, 'sales/quick_sale.html', {'form': form, 'formset': formset})


@login_required
def daily_sales_list(request):
    date_filter = request.GET.get('date', '').strip()
    entries = DailySalesEntry.objects.all()
    if date_filter:
        entries = entries.filter(date=date_filter)
    else:
        date_filter = datetime.now().date().isoformat()
        entries = entries.filter(date=date_filter)

    day_total = entries.aggregate(total=Sum('total'))['total'] or 0

    context = {
        'entries': entries,
        'date_filter': date_filter,
        'day_total': day_total,
    }
    return render(request, 'sales/daily_sales_list.html', context)


@login_required
def daily_sales_create(request):
    if request.method == 'POST':
        form = DailySalesEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.created_by = request.user
            entry.save()
            messages.success(request, f'Recorded "{entry.particulars}" for {entry.date}.')
            return redirect('sales:daily_sales_list')
    else:
        form = DailySalesEntryForm(initial={'date': datetime.now().date()})

    return render(request, 'sales/daily_sales_form.html', {'form': form})


@role_required('OWNER', 'MANAGER')
def profit_entry_list(request):
    date_filter = request.GET.get('date', '').strip()
    entries = ProfitEntry.objects.all()
    if date_filter:
        entries = entries.filter(date=date_filter)
    else:
        date_filter = datetime.now().date().isoformat()
        entries = entries.filter(date=date_filter)

    total_profit = entries.aggregate(total=Sum('profit'))['total'] or 0
    total_revenue = entries.aggregate(total=Sum('revenue'))['total'] or 0
    total_cost = entries.aggregate(total=Sum('cost'))['total'] or 0
    total_expenses = entries.aggregate(total=Sum('expenses'))['total'] or 0

    context = {
        'entries': entries,
        'date_filter': date_filter,
        'total_profit': total_profit,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_expenses': total_expenses,
    }
    return render(request, 'sales/profit_entry_list.html', context)


@role_required('OWNER', 'MANAGER')
def profit_entry_create(request):
    if request.method == 'POST':
        form = ProfitEntryForm(request.POST)
        if form.is_valid():
            entry = form.save()
            messages.success(request, f'Recorded profit entry "{entry.description}" for {entry.date}.')
            return redirect('sales:profit_entry_list')
    else:
        form = ProfitEntryForm(initial={'date': datetime.now().date()})

    return render(request, 'sales/profit_entry_form.html', {'form': form})


@role_required('OWNER', 'MANAGER')
def daily_sales_delete(request, pk):
    entry = get_object_or_404(DailySalesEntry, pk=pk)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Entry deleted.')
        return redirect('sales:daily_sales_list')
    return render(request, 'sales/daily_sales_confirm_delete.html', {'entry': entry})


@login_required
def invoice_list(request):
    invoices = Invoice.objects.all().order_by('-date')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        invoices = invoices.filter(
            Q(id__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        )

    if status_filter:
        if status_filter == 'paid':
            invoices = invoices.filter(paid__gte=F('total'))
        elif status_filter == 'partial':
            invoices = invoices.filter(paid__gt=0, paid__lt=F('total'))
        elif status_filter == 'unpaid':
            invoices = invoices.filter(paid=0)

    context = {
        'invoices': invoices,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'sales/invoice_list.html', context)

@login_required
def invoice_create(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            messages.success(request, 'Invoice created! Add items below.')
            return redirect('sales:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm()
    return render(request, 'sales/invoice_form.html', {'form': form, 'title': 'Create Invoice'})

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()
    item_rows = []
    for item in items:
        item_rows.append({
            'product_name': item.product.name,
            'qty': item.qty,
            'price': item.price,
            'subtotal': item.qty * item.price,
        })
    payments = Payment.objects.filter(invoice=invoice).order_by('date')
    return render(request, 'sales/invoice_detail.html', {'invoice': invoice, 'items': item_rows, 'payments': payments})


@login_required
def invoice_print(request, pk):
    """A clean, print-only view of an invoice. No PDF library needed —
    the user hits Print in their browser and picks 'Save as PDF' as the
    destination, which works the same on Windows/Mac/Linux without
    installing anything extra."""
    invoice = get_object_or_404(Invoice, pk=pk)
    items = invoice.items.all()
    item_rows = []
    for item in items:
        item_rows.append({
            'product_name': item.product.name,
            'qty': item.qty,
            'price': item.price,
            'subtotal': item.qty * item.price,
        })
    return render(request, 'sales/invoice_print.html', {'invoice': invoice, 'items': item_rows})


@login_required
def payment_receipt(request, pk):
    """Printable receipt for a single payment — proof of what was
    actually received, as opposed to the invoice (which is the bill)."""
    payment = get_object_or_404(Payment, pk=pk)
    invoice = payment.invoice
    items = invoice.items.all()
    item_rows = [{
        'product_name': item.product.name,
        'qty': item.qty,
        'price': item.price,
        'subtotal': item.qty * item.price,
    } for item in items]
    # Balance as of this specific payment, not necessarily the invoice's
    # current balance — matters when an invoice has multiple payments.
    paid_up_to_this = (
        Payment.objects.filter(invoice=invoice, date__lte=payment.date)
        .aggregate(total=Sum('amount'))['total'] or 0
    )
    context = {
        'payment': payment,
        'invoice': invoice,
        'items': item_rows,
        'balance_after': invoice.total - paid_up_to_this,
    }
    return render(request, 'sales/payment_receipt.html', context)


@role_required('OWNER', 'MANAGER')
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            # Restore the stock this invoice took out, since deleting the
            # sale record shouldn't leave inventory permanently short.
            for item in invoice.items.select_related('product'):
                product = item.product
                product.quantity = F('quantity') + item.qty
                product.save(update_fields=['quantity'])
            invoice.delete()
        messages.success(request, 'Invoice deleted and stock restored.')
        return redirect('sales:invoice_list')
    return render(request, 'sales/invoice_confirm_delete.html', {'invoice': invoice})


@role_required('OWNER', 'MANAGER')
def daily_profit_dashboard(request):
    """Render a simple daily profit dashboard. Accepts optional `date` GET param (YYYY-MM-DD)."""
    date_str = request.GET.get('date')
    if date_str:
        target_date = parse_date(date_str)
    else:
        target_date = None

    result = compute_daily_profit(target_date)
    return render(request, 'sales/daily_profit_dashboard.html', {'result': result})


@login_required
def order_list(request):
    orders = Order.objects.all().order_by('-date')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        )

    if status_filter:
        orders = orders.filter(status=status_filter)

    context = {
        'orders': orders,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
    }
    return render(request, 'sales/order_list.html', context)


@login_required
def order_create(request):
    initial = {}
    if request.GET.get('order_type'):
        initial['order_type'] = request.GET.get('order_type')
    if request.GET.get('supplier'):
        initial['supplier'] = request.GET.get('supplier')
    if request.GET.get('customer'):
        initial['customer'] = request.GET.get('customer')

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            if order.order_type == 'customer':
                order.supplier = None
            else:
                order.customer = None
            order.total = 0
            order.save()
            messages.success(request, 'Order created! Add items below.')
            return redirect('sales:order_detail', pk=order.pk)
    else:
        form = OrderForm(initial=initial)
    return render(request, 'sales/order_form.html', {'form': form, 'title': 'Create Order'})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    items = order.items.all()
    return render(request, 'sales/order_detail.html', {'order': order, 'items': items})


@login_required
def order_item_add(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)
    if request.method == 'POST':
        form = OrderItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.order = order
            item.save()
            total = order.items.aggregate(total=Sum(F('price') * F('qty')))['total'] or 0
            order.total = total
            order.save()
            messages.success(request, 'Item added to order!')
            return redirect('sales:order_detail', pk=order.pk)
    else:
        form = OrderItemForm()
    return render(request, 'sales/order_item_form.html', {'form': form, 'order': order})


@login_required
def invoice_item_add(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        form = InvoiceItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.invoice = invoice
            item.cost_price = item.product.cost_price
            item.save()
            messages.success(request, 'Item added to invoice!')
            return redirect('sales:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceItemForm()
    return render(request, 'sales/invoice_item_form.html', {'form': form, 'invoice': invoice})

@login_required
def payment_record(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.invoice = invoice
            payment.save()
            invoice.paid += payment.amount
            invoice.save()
            messages.success(request, 'Payment recorded!')
            return redirect('sales:invoice_detail', pk=invoice.pk)
    else:
        form = PaymentForm()
    return render(request, 'sales/payment_form.html', {'form': form, 'invoice': invoice})



@role_required('OWNER', 'MANAGER')
def product_profit_report(request):
    """Read-only report: profit per product, grouped by category.

    Built entirely from existing InvoiceItem records — nothing here
    writes to the database. Optional `start` / `end` GET params
    (YYYY-MM-DD) filter the date range; otherwise it's all-time.
    """
    money = DecimalField(max_digits=14, decimal_places=2)

    items = InvoiceItem.objects.select_related('product').annotate(
        revenue=ExpressionWrapper(F('price') * F('qty'), output_field=money),
        cost=ExpressionWrapper(F('product__cost_price') * F('qty'), output_field=money),
    )

    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None
    if start_date:
        items = items.filter(invoice__date__date__gte=start_date)
    if end_date:
        items = items.filter(invoice__date__date__lte=end_date)

    per_product = (
        items.values('product__id', 'product__name', 'product__category')
        .annotate(
            qty_sold=Sum('qty'),
            total_revenue=Sum('revenue'),
            total_cost=Sum('cost'),
        )
        .order_by('product__category', 'product__name')
    )

    categories = {}
    grand_revenue = grand_cost = 0
    for row in per_product:
        category = row['product__category'] or 'Uncategorized'
        revenue = row['total_revenue'] or 0
        cost = row['total_cost'] or 0
        profit = revenue - cost
        grand_revenue += revenue
        grand_cost += cost

        bucket = categories.setdefault(category, {'products': [], 'revenue': 0, 'cost': 0, 'profit': 0})
        bucket['products'].append({
            'name': row['product__name'],
            'qty_sold': row['qty_sold'],
            'revenue': revenue,
            'cost': cost,
            'profit': profit,
        })
        bucket['revenue'] += revenue
        bucket['cost'] += cost
        bucket['profit'] += profit

    # Sort categories by profit, descending, so the biggest earners lead
    sorted_categories = sorted(
        [{'name': name, **data} for name, data in categories.items()],
        key=lambda c: c['profit'], reverse=True,
    )

    context = {
        'categories': sorted_categories,
        'grand_revenue': grand_revenue,
        'grand_cost': grand_cost,
        'grand_profit': grand_revenue - grand_cost,
        'start_date': start_str or '',
        'end_date': end_str or '',
    }
    return render(request, 'sales/product_profit_report.html', context)


@role_required('OWNER', 'MANAGER')
def export_invoices_csv(request):
    """Download all invoices as a CSV file. Optional `start`/`end`
    (YYYY-MM-DD) GET params filter by date."""
    import csv
    from django.http import HttpResponse

    invoices = Invoice.objects.select_related('customer', 'created_by').order_by('-date')
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None
    if start_date:
        invoices = invoices.filter(date__date__gte=start_date)
    if end_date:
        invoices = invoices.filter(date__date__lte=end_date)

    response = HttpResponse(content_type='text/csv')
    filename = f"invoices_{timezone.localdate()}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Invoice ID', 'Date', 'Customer', 'Total', 'Paid', 'Balance', 'Created By'])
    for inv in invoices:
        writer.writerow([
            inv.id,
            timezone.localtime(inv.date).strftime('%Y-%m-%d %H:%M'),
            inv.customer.name,
            inv.total,
            inv.paid,
            inv.balance,
            inv.created_by.username if inv.created_by else '',
        ])
    return response


@role_required('OWNER', 'MANAGER')
def export_daily_sales_csv(request):
    """Download all Daily Sales Ledger entries as a CSV file. Optional
    `start`/`end` (YYYY-MM-DD) GET params filter by date."""
    import csv
    from django.http import HttpResponse

    entries = DailySalesEntry.objects.filter(is_deleted=False).select_related('created_by').order_by('-date')
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None
    if start_date:
        entries = entries.filter(date__gte=start_date)
    if end_date:
        entries = entries.filter(date__lte=end_date)

    response = HttpResponse(content_type='text/csv')
    filename = f"daily_sales_{timezone.localdate()}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Particulars', 'Unit', 'Quantity', 'Unit Price', 'Total', 'Notes', 'Created By'])
    for e in entries:
        writer.writerow([
            e.date, e.particulars, e.get_unit_display(), e.quantity, e.unit_price, e.total,
            e.notes, e.created_by.username if e.created_by else '',
        ])
    return response


@role_required('OWNER', 'MANAGER')
def import_daily_sales_csv(request):
    """Bulk-import Daily Sales Ledger entries from a CSV file.
    Expected columns: Date, Particulars, Unit, Quantity, Unit Price, Notes
    (Unit and Notes are optional; Unit defaults to 'pcs' if blank or
    unrecognised). Each valid row creates one DailySalesEntry; invalid
    rows are skipped and reported back, nothing else is touched."""
    import csv
    import io

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please choose a CSV file to upload.')
            return redirect('sales:import_daily_sales_csv')
        if not csv_file.name.lower().endswith('.csv'):
            messages.error(request, 'That file doesn\'t look like a CSV. Please export from Excel/Sheets as CSV first.')
            return redirect('sales:import_daily_sales_csv')

        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            messages.error(request, "Couldn't read that file — please save it as UTF-8 CSV and try again.")
            return redirect('sales:import_daily_sales_csv')

        reader = csv.DictReader(io.StringIO(decoded))
        valid_unit_codes = {code for code, _ in DailySalesEntry.UNIT_CHOICES}

        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            row = {(k or '').strip().lower(): (v or '').strip() for k, v in row.items()}
            date_str = row.get('date')
            particulars = row.get('particulars')
            unit = row.get('unit', 'pcs').lower() or 'pcs'
            quantity_str = row.get('quantity')
            unit_price_str = row.get('unit price') or row.get('unit_price')
            notes = row.get('notes', '')

            row_errors = []
            entry_date = parse_date(date_str) if date_str else None
            if not entry_date:
                row_errors.append('invalid or missing date (use YYYY-MM-DD)')
            if not particulars:
                row_errors.append('missing particulars')
            if unit not in valid_unit_codes:
                unit = 'other'
            try:
                quantity = Decimal(quantity_str)
            except Exception:
                quantity = None
                row_errors.append('invalid quantity')
            try:
                unit_price = Decimal(unit_price_str)
            except Exception:
                unit_price = None
                row_errors.append('invalid unit price')

            if row_errors:
                errors.append(f"Row {i}: {', '.join(row_errors)}")
                continue

            DailySalesEntry.objects.create(
                tenant=request.user.tenant, date=entry_date, particulars=particulars,
                unit=unit, quantity=quantity, unit_price=unit_price, notes=notes,
                created_by=request.user,
            )
            created += 1

        if created:
            messages.success(request, f"Imported {created} sales entr{'y' if created == 1 else 'ies'}.")
        if errors:
            messages.warning(request, f"{len(errors)} row(s) were skipped: " + '; '.join(errors[:10]) + (' …' if len(errors) > 10 else ''))
        if not created and not errors:
            messages.error(request, 'No rows found in that file.')
        return redirect('sales:daily_sales_list')

    return render(request, 'sales/import_daily_sales.html')
