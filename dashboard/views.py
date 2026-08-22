from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect, render
from django.db.models import Sum, F, Count, Q, DecimalField
from django.db.models.functions import TruncDate, TruncMonth
from django.urls import reverse
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

    # Budget vs spending for each period, shown as summary cards at the top
    # of the dashboard. Restricted to the same roles that can reach the
    # Budgeting section itself -- budgets reveal planned spend and salary
    # figures that Staff/Sales roles shouldn't see just by logging in.
    budget_summaries = None
    if request.user.has_role('OWNER', 'MANAGER', 'ACCOUNTANT'):
        from budgeting.utils import period_summary
        budget_summaries = [
            period_summary(request.user.tenant, period)
            for period in ('daily', 'weekly', 'monthly')
        ]

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
        'budget_summaries': budget_summaries,

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


PERIOD_LABELS = {
    'today': 'Today',
    'week': 'This Week',
    'month': 'This Month',
    'quarter': 'This Quarter',
    'year': 'This Year',
}


def _period_range(period):
    """(start_date, end_date) inclusive, both dates, for the given period
    key. Every KPI on the CEO dashboard filters against this same pair,
    computed once, so the date math only has to be right in one place."""
    today = timezone.localdate()
    if period == 'today':
        return today, today
    if period == 'week':
        return today - timedelta(days=today.weekday()), today
    if period == 'quarter':
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_start_month, day=1), today
    if period == 'year':
        return today.replace(month=1, day=1), today
    return today.replace(day=1), today  # 'month', and the default for anything unrecognised


@role_required('OWNER')
def ceo_dashboard(request):
    """Executive dashboard: business-wide KPIs for a selectable period.
    OWNER-only -- this surfaces payroll totals, cash position, and budget
    data that Managers/Staff shouldn't see by default even though they
    can reach other business modules.

    Every query below is explicitly filtered by tenant, not left to
    TenantManager's implicit request-context scoping -- same defensive
    style used throughout the payment module, since this view aggregates
    across many apps' models at once and a silent scoping miss here would
    show the wrong business's numbers rather than erroring visibly.
    """
    from accounting.models import Bill, Budget, BudgetLine, BankAccount, BankTransaction
    from payroll.models import PayrollRun
    from hr.models import LeaveRequest, EmployeeAdvance

    tenant = request.user.tenant
    period = request.GET.get('period', 'month')
    if period not in PERIOD_LABELS:
        period = 'month'
    start_date, end_date = _period_range(period)

    # --- Revenue / expenses / profit ---
    invoices_period = Invoice.objects.filter(tenant=tenant, date__date__range=(start_date, end_date))
    total_revenue = invoices_period.aggregate(t=Sum('total'))['t'] or 0

    expenses_period = Expense.objects.filter(tenant=tenant, date__range=(start_date, end_date))
    total_expenses = expenses_period.aggregate(t=Sum('amount'))['t'] or 0

    net_profit = total_revenue - total_expenses

    # --- Cash position: live-computed, not the unmaintained BankAccount.current_balance field ---
    bank_accounts = BankAccount.objects.filter(tenant=tenant)
    opening_total = sum((b.opening_balance for b in bank_accounts), Decimal('0'))
    deposits = BankTransaction.objects.filter(bank_account__tenant=tenant, transaction_type='deposit').aggregate(t=Sum('amount'))['t'] or 0
    withdrawals = BankTransaction.objects.filter(bank_account__tenant=tenant, transaction_type='withdrawal').aggregate(t=Sum('amount'))['t'] or 0
    cash_position = opening_total + deposits - withdrawals

    # --- Outstanding balances (all-time, not period-scoped -- "what's owed right now") ---
    all_invoices = Invoice.objects.filter(tenant=tenant)
    outstanding = all_invoices.aggregate(t=Sum('total'), p=Sum('paid'))
    outstanding_customer_payments = (outstanding['t'] or 0) - (outstanding['p'] or 0)

    bills = Bill.objects.filter(tenant=tenant)
    payable = bills.aggregate(t=Sum('total_amount'), p=Sum('paid_amount'))
    outstanding_supplier_payments = (payable['t'] or 0) - (payable['p'] or 0)

    # --- Inventory ---
    products = Product.objects.filter(tenant=tenant)
    inventory_value = products.aggregate(
        v=Sum(F('cost_price') * F('quantity'), output_field=DecimalField())
    )['v'] or 0
    low_stock_qs = products.filter(quantity__lte=F('minimum_stock')).order_by('quantity')
    low_stock_count = low_stock_qs.count()
    low_stock_products = low_stock_qs[:8]

    # --- People ---
    employee_count = Employee.objects.filter(tenant=tenant, is_active=True).count()
    latest_payroll_run = PayrollRun.objects.filter(tenant=tenant).order_by('-created_at').first()

    # --- Budget: live estimate, not BudgetLine.actual_amount (nothing populates that field
    # yet -- real actual-vs-budgeted tracking is the Budgeting phase, not this one) ---
    current_year = timezone.localdate().year
    active_budgets = Budget.objects.filter(tenant=tenant, fiscal_year=current_year, status__in=['approved', 'active'])
    total_budgeted = BudgetLine.objects.filter(budget__in=active_budgets).aggregate(t=Sum('budgeted_amount'))['t'] or 0
    budget_utilization_pct = round((total_expenses / total_budgeted) * 100, 1) if total_budgeted else None

    # --- Sales trend: daily buckets for short periods, monthly for long ones ---
    span_days = (end_date - start_date).days
    trunc_fn = TruncDate if span_days <= 31 else TruncMonth
    label_fmt = '%d %b' if span_days <= 31 else '%b %Y'
    trend_rows = list(
        invoices_period.annotate(bucket=trunc_fn('date')).values('bucket')
        .annotate(total=Sum('total')).order_by('bucket')
    )
    sales_trend_labels = [row['bucket'].strftime(label_fmt) for row in trend_rows]
    sales_trend_data = [float(row['total'] or 0) for row in trend_rows]

    # --- Expense breakdown by category ---
    expense_rows = list(expenses_period.values('category').annotate(total=Sum('amount')).order_by('-total'))
    category_labels = dict(Expense.CATEGORY_CHOICES)
    expense_category_labels = [category_labels.get(row['category'], row['category']) for row in expense_rows]
    expense_category_data = [float(row['total'] or 0) for row in expense_rows]

    # --- Approvals + alerts ---
    pending_leave_count = LeaveRequest.objects.filter(tenant=tenant, status='pending').count()
    pending_advance_count = EmployeeAdvance.objects.filter(tenant=tenant, status='requested').count()
    pending_approvals_count = pending_leave_count + pending_advance_count

    overdue_invoices_count = all_invoices.filter(due_date__lt=timezone.localdate(), paid__lt=F('total')).count()

    alerts = []
    if low_stock_count:
        alerts.append({'level': 'warning', 'icon': 'exclamation-triangle', 'text': f'{low_stock_count} product(s) low on stock.'})
    if overdue_invoices_count:
        alerts.append({'level': 'error', 'icon': 'clock-history', 'text': f'{overdue_invoices_count} invoice(s) overdue.'})
    if pending_approvals_count:
        alerts.append({'level': 'info', 'icon': 'inbox', 'text': f'{pending_approvals_count} item(s) awaiting your approval.'})
    if not alerts:
        alerts.append({'level': 'success', 'icon': 'check-circle', 'text': 'No urgent alerts right now.'})

    context = {
        'period': period,
        'period_label': PERIOD_LABELS[period],
        'period_options': PERIOD_LABELS,
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'cash_position': cash_position,
        'outstanding_customer_payments': outstanding_customer_payments,
        'outstanding_supplier_payments': outstanding_supplier_payments,
        'inventory_value': inventory_value,
        'low_stock_count': low_stock_count,
        'low_stock_products': low_stock_products,
        'employee_count': employee_count,
        'latest_payroll_run': latest_payroll_run,
        'total_budgeted': total_budgeted,
        'budget_utilization_pct': budget_utilization_pct,
        'sales_trend_labels': json.dumps(sales_trend_labels),
        'sales_trend_data': json.dumps(sales_trend_data),
        'expense_category_labels': json.dumps(expense_category_labels),
        'expense_category_data': json.dumps(expense_category_data),
        'pending_approvals_count': pending_approvals_count,
        'alerts': alerts,
    }

    # CEO Portal: the team roster, open tasks, upcoming meetings and unread
    # message counts that make this dashboard actionable rather than purely
    # observational. Built in the collaboration app so the models and their
    # tenant-scoping rules stay in one place.
    from collaboration.views import ceo_portal_context
    context.update(ceo_portal_context(request))

    return render(request, 'dashboard/ceo_dashboard.html', context)


@role_required('OWNER', 'MANAGER')
def approval_center(request):
    """Single queue for everything currently awaiting approval. Built by
    merging the approval-shaped models that actually exist today
    (LeaveRequest, EmployeeAdvance) into one list -- not a new generic
    Approval model, which would be premature for two source types. When
    Expense/Budget/Refund approvals exist (a later phase), extend this
    same merge; only introduce a real polymorphic model if the list of
    types grows enough to justify it."""
    from hr.models import LeaveRequest, EmployeeAdvance

    tenant = request.user.tenant
    status_filter = request.GET.get('status', 'pending')
    if status_filter not in ('pending', 'approved', 'rejected'):
        status_filter = 'pending'
    # EmployeeAdvance's pending value is 'requested', not 'pending' --
    # everything else lines up with LeaveRequest's status strings.
    advance_status = 'requested' if status_filter == 'pending' else status_filter

    items = []
    leave_requests = LeaveRequest.objects.filter(tenant=tenant, status=status_filter).select_related('employee__user', 'leave_type')
    for lr in leave_requests:
        items.append({
            'type': 'Leave Request',
            'icon': 'calendar-x',
            'requester': lr.employee.user.get_full_name() or lr.employee.user.username,
            'detail': f'{lr.leave_type.name}, {lr.days_requested} day(s): {lr.start_date} to {lr.end_date}',
            'submitted_at': lr.created_at,
            'status': lr.status,
            'approve_url': reverse('hr:approve_leave_request', args=[lr.pk]) if status_filter == 'pending' else None,
            'reject_url': reverse('hr:reject_leave_request', args=[lr.pk]) if status_filter == 'pending' else None,
        })

    advances = EmployeeAdvance.objects.filter(tenant=tenant, status=advance_status).select_related('employee__user')
    for adv in advances:
        items.append({
            'type': 'Employee Advance',
            'icon': 'cash-coin',
            'requester': adv.employee.user.get_full_name() or adv.employee.user.username,
            'detail': f'KES {adv.amount:,.2f} — {adv.reason or "No reason given"}',
            'submitted_at': adv.created_at,
            'status': adv.status,
            'approve_url': reverse('hr:approve_advance', args=[adv.pk]) if status_filter == 'pending' else None,
            'reject_url': reverse('hr:reject_advance', args=[adv.pk]) if status_filter == 'pending' else None,
        })

    items.sort(key=lambda i: i['submitted_at'], reverse=True)

    pending_count = (
        LeaveRequest.objects.filter(tenant=tenant, status='pending').count()
        + EmployeeAdvance.objects.filter(tenant=tenant, status='requested').count()
    )

    context = {
        'items': items,
        'status_filter': status_filter,
        'pending_count': pending_count,
    }
    return render(request, 'dashboard/approval_center.html', context)
