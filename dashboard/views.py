from django.contrib import messages
from django.shortcuts import redirect, render
from django.db.models import Sum, F, Count, Q, DecimalField
from django.utils import timezone
from datetime import timedelta, datetime
import json

from sales.models import Invoice, InvoiceItem, DailySalesEntry
from sales.models import Order
from sales.models import Payment, MpesaTransaction
from inventory.models import Product
from expenses.models import Expense
from customers.models import Customer
from core.forms import TeamMemberCreationForm
from hr.models import Employee
from tenants.decorators import role_required
from tenants.models import User, SubscriptionPlan


def overview(request):
    if not request.user.is_authenticated:
        plans = list(SubscriptionPlan.objects.filter(is_active=True).order_by('duration_days'))
        for plan in plans:
            # Only worth showing for plans long enough that a monthly
            # reading isn't just the sticker price restated.
            plan.monthly_equivalent = (
                (plan.price_kes / plan.duration_days) * 30 if plan.duration_days > 35 else None
            )
        return render(request, 'dashboard/landing.html', {'plans': plans})

    today = timezone.now().date()
    current_month = today.replace(day=1)
    last_month = (current_month - timedelta(days=1)).replace(day=1)

    # KPI Calculations
    sales_today = Invoice.objects.filter(date__date=today).aggregate(Sum('total'))['total__sum'] or 0
    sales_month = Invoice.objects.filter(
        date__date__gte=current_month
    ).aggregate(Sum('total'))['total__sum'] or 0
    sales_last_month = Invoice.objects.filter(
        date__date__gte=last_month,
        date__date__lt=current_month
    ).aggregate(Sum('total'))['total__sum'] or 0

    purchase_total = (
    Order.objects.filter(order_type='supplier')
    .aggregate(total=Sum('total'))
    .get('total') or 0
)
    total_products = Product.objects.count()
    low_stock_count = Product.objects.filter(quantity__lte=F('minimum_stock')).count()

    expenses_today = Expense.objects.filter(date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    expenses_month = Expense.objects.filter(
        date__gte=current_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    # Cost of Goods Sold: uses each item's snapshotted cost_price (what
    # it cost at the moment of sale), not the product's current cost --
    # so past profit stays accurate even if buying prices change later.
    cogs_today = InvoiceItem.objects.filter(invoice__date__date=today).aggregate(
        cogs=Sum(F('qty') * F('cost_price'), output_field=DecimalField())
    )['cogs'] or 0
    cogs_month = InvoiceItem.objects.filter(invoice__date__date__gte=current_month).aggregate(
        cogs=Sum(F('qty') * F('cost_price'), output_field=DecimalField())
    )['cogs'] or 0

    # Profit = Sales - Cost of Goods Sold - Operating Expenses
    profit_today = sales_today - cogs_today - expenses_today
    profit_month = sales_month - cogs_month - expenses_month

    # Sales by category/product for bar chart
    top_products = Product.objects.order_by('-quantity')[:5].values('name', 'quantity', 'retail_price')

    # Recent transactions
    recent_invoices = Invoice.objects.all().order_by('-date')[:8].select_related('customer').values(
        'id', 'customer__name', 'total', 'paid', 'date'
    )

    recent_expenses = Expense.objects.all().order_by('-date')[:5].values(
        'id', 'description', 'amount', 'category', 'date'
    )

    # Chart data: Sales trend (last 7 days)
    sales_trend = []
    labels = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        sales = Invoice.objects.filter(date__date=date).aggregate(Sum('total'))['total__sum'] or 0
        sales_trend.append(float(sales))
        labels.append(date.strftime('%a'))

    # Chart data: Expenses by category
    expense_categories = Expense.objects.filter(
        date__gte=current_month
    ).values('category').annotate(total=Sum('amount')).order_by('-total')[:6]

    expense_labels = [e['category'] for e in expense_categories]
    expense_data = [float(e['total']) for e in expense_categories]

    # Chart data: Top products
    top_products_list = Product.objects.order_by('-quantity')[:5].values('name', 'quantity', 'retail_price')
    product_labels = [p['name'][:15] for p in top_products_list]
    # Product.quantity is a Decimal (fractional stock support) -- json.dumps
    # can't serialize Decimal directly, same reason expense_data above is
    # wrapped in float().
    product_data = [float(p['quantity']) for p in top_products_list]

    debtors = Customer.objects.filter(balance__gt=0).order_by('-balance')[:5]

    # Payments received (cash/mpesa/bank), plus any M-Pesa STK Push attempts
    # still awaiting Safaricom's callback -- shown separately from
    # recent_payments since a pending attempt isn't money received yet,
    # and shouldn't be presented as if it were.
    recent_payments = Payment.objects.select_related('invoice', 'invoice__customer').order_by('-date')[:8]
    pending_mpesa = MpesaTransaction.objects.filter(status='pending').select_related('invoice__customer').order_by('-created_at')[:5]

    # Alerts for the notification bell (low stock) and envelope (unpaid invoices)
    low_stock_products = Product.objects.filter(
        quantity__lte=F('minimum_stock')
    ).order_by('quantity')[:8]

    unpaid_invoices = Invoice.objects.filter(
        paid__lt=F('total')
    ).select_related('customer').order_by('-date')[:8]
    unpaid_invoices_count = Invoice.objects.filter(paid__lt=F('total')).count()

    # Prepare context
    context = {
        'sales_today': sales_today,
        'sales_month': sales_month,
        'sales_last_month': sales_last_month,
        'stock_value': purchase_total,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'expenses_today': expenses_today,
        'expenses_month': expenses_month,
        'cogs_today': cogs_today,
        'cogs_month': cogs_month,
        'profit_today': profit_today,
        'profit_month': profit_month,
        'recent_invoices': recent_invoices,
        'recent_expenses': recent_expenses,
        'top_products': top_products,
        'debtors': debtors,
        'recent_payments': recent_payments,
        'pending_mpesa': pending_mpesa,
        'low_stock_products': low_stock_products,
        'unpaid_invoices': unpaid_invoices,
        'unpaid_invoices_count': unpaid_invoices_count,

        # Chart data as JSON
        'sales_trend_data': json.dumps(sales_trend),
        'sales_trend_labels': json.dumps(labels),
        'expense_labels': json.dumps(expense_labels),
        'expense_data': json.dumps(expense_data),
        'product_labels': json.dumps(product_labels),
        'product_data': json.dumps(product_data),
    }
    return render(request, 'dashboard/overview.html', context)


def global_search(request):
    query = request.GET.get('q', '').strip()

    products = customers = invoices = []
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(sku__icontains=query)
        )[:10]

        customers = Customer.objects.filter(
            Q(name__icontains=query) | Q(phone__icontains=query)
        )[:10]

        invoice_filter = Q(customer__name__icontains=query)
        if query.isdigit():
            invoice_filter |= Q(id=int(query))
        invoices = Invoice.objects.filter(invoice_filter).select_related('customer')[:10]

    context = {
        'query': query,
        'products': products,
        'customers': customers,
        'invoices': invoices,
        'result_count': len(products) + len(customers) + len(invoices),
    }
    return render(request, 'dashboard/search_results.html', context)


@role_required('OWNER')
def team_activity(request):
    """Owner-only view: a rollup of what each Manager/Staff account has
    been doing — sales recorded, hours logged, and their most recent
    actions. Read-only; nothing here can be edited from this page."""
    from hr.models import Attendance, Employee  # local import avoids a hard dep from dashboard -> hr

    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    team = User.objects.filter(
        tenant=request.user.tenant, role__in=[User.Role.MANAGER, User.Role.STAFF],
    ).order_by('role', 'username')

    rows = []
    for member in team:
        invoices_month = Invoice.objects.filter(created_by=member, date__date__gte=month_start)
        invoice_count = invoices_month.count()
        invoice_total = invoices_month.aggregate(total=Sum('total'))['total'] or 0

        daily_entries_month = DailySalesEntry.objects.filter(created_by=member, date__gte=month_start, is_deleted=False)
        daily_total = daily_entries_month.aggregate(total=Sum('total'))['total'] or 0

        hours_this_week = 0
        employee = getattr(member, 'employee_profile', None)
        if employee:
            week_records = Attendance.objects.filter(
                employee=employee, date__gte=week_start, date__lte=today,
                check_in_time__isnull=False, check_out_time__isnull=False,
            )
            for rec in week_records:
                worked = datetime.combine(rec.date, rec.check_out_time) - datetime.combine(rec.date, rec.check_in_time)
                hours_this_week += worked.total_seconds() / 3600

        last_invoice = invoices_month.order_by('-date').first()
        last_daily_entry = daily_entries_month.order_by('-created_at').first()
        last_activity = None
        if last_invoice and last_daily_entry:
            last_activity = max(last_invoice.date, last_daily_entry.created_at)
        elif last_invoice:
            last_activity = last_invoice.date
        elif last_daily_entry:
            last_activity = last_daily_entry.created_at

        rows.append({
            'user': member,
            'invoice_count': invoice_count,
            'invoice_total': invoice_total,
            'daily_sales_total': daily_total,
            'sales_total_month': invoice_total + daily_total,
            'hours_this_week': round(hours_this_week, 1),
            'last_activity': last_activity,
        })

    context = {
        'rows': rows,
        'month_start': month_start,
        'week_start': week_start,
    }
    return render(request, 'dashboard/team_activity.html', context)


@role_required('OWNER')
def add_team_member(request):
    """Owner-only: creates a Manager or Staff login under the Owner's own
    tenant. Not exposed to Managers -- letting a Manager create another
    Manager account would be a privilege-escalation path, and this matches
    team_activity's existing Owner-only access to the same "Team" area."""
    if request.method == 'POST':
        form = TeamMemberCreationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password1'],
                tenant=request.user.tenant,
                role=data['role'],
            )
            # Without this, the account can sign in but the Staff/Manager
            # Portal (hr:staff_portal) immediately bounces them back to the
            # dashboard with "no employee profile set up" -- every field
            # here except employee_id has a default or is optional, so this
            # is enough to make the portal usable right away; department,
            # position, and the rest can be filled in later from HR.
            Employee.objects.create(
                user=user, tenant=request.user.tenant, employee_id=f'EMP-{user.pk:04d}',
            )
            messages.success(
                request,
                f"{user.username} can now sign in as {user.get_role_display()}. "
                f"Share their username and password with them directly.",
            )
            return redirect('team_activity')
    else:
        form = TeamMemberCreationForm()
    return render(request, 'dashboard/team_add_member.html', {'form': form})
