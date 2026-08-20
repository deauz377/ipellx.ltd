import csv
import json
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from tenants.decorators import role_required

from .forms import BudgetForm
from .models import Budget
from .utils import category_spend, daily_totals, period_bounds, previous_period_bounds

VIEW_ROLES = ('OWNER', 'MANAGER', 'ACCOUNTANT')
EDIT_ROLES = ('OWNER', 'MANAGER')


def _budgets_for_window(tenant, start, end, period=None):
    """Budget rows overlapping [start, end], optionally restricted to one
    period type. Overlap (not exact match) so a custom-dated budget still
    shows up in the window it actually covers."""
    if tenant is None:
        return Budget.objects.none()
    qs = Budget.objects.filter(tenant=tenant, start_date__lte=end, end_date__gte=start)
    if period:
        qs = qs.filter(period=period)
    return qs


def _category_breakdown(tenant, start, end):
    """[{code, label, spent}, ...] for every category with any spend in
    the window, sorted highest first -- across ALL categories, not just
    ones with a budget set, so "top spending category" reflects reality."""
    if tenant is None:
        return []
    rows = []
    for code, label in Budget.CATEGORY_CHOICES:
        spent = category_spend(tenant, code, start, end)
        if spent:
            rows.append({'code': code, 'label': label, 'spent': spent})
    rows.sort(key=lambda r: r['spent'], reverse=True)
    return rows


@role_required(*VIEW_ROLES)
def budgeting_dashboard(request):
    tenant = request.user.tenant
    period = request.GET.get('period', 'monthly')
    if period not in dict(Budget.PERIOD_CHOICES):
        period = 'monthly'

    start, end = period_bounds(period)
    budgets = list(_budgets_for_window(tenant, start, end, period=period))

    total_budgeted = sum((b.amount for b in budgets), Decimal('0'))
    total_spent = sum((b.spent_amount for b in budgets), Decimal('0'))
    total_remaining = total_budgeted - total_spent
    usage_percent = (total_spent / total_budgeted * 100) if total_budgeted else Decimal('0')

    alerts = sorted(
        (b for b in budgets if b.alert_level is not None),
        key=lambda b: (0 if b.alert_level == 'over' else -b.alert_level),
    )
    over_budget = [b for b in budgets if b.is_over_budget]

    category_rows = _category_breakdown(tenant, start, end)
    top_category = category_rows[0] if category_rows else None

    today = timezone.localdate()
    trend_end = min(end, today)
    trend = daily_totals(tenant, start, trend_end) if tenant and trend_end >= start else []
    highest_day = max(trend, key=lambda row: row[1]) if trend else None

    prev_start, prev_end = previous_period_bounds(period, start)
    prev_budgets = list(_budgets_for_window(tenant, prev_start, prev_end, period=period))
    prev_spent = sum((b.spent_amount for b in prev_budgets), Decimal('0'))

    upcoming = (
        Budget.objects.filter(tenant=tenant, start_date__gt=today).order_by('start_date')[:5]
        if tenant else Budget.objects.none()
    )

    context = {
        'period': period,
        'period_label': dict(Budget.PERIOD_CHOICES)[period],
        'start_date': start,
        'end_date': end,
        'budgets': budgets,
        'total_budgeted': total_budgeted,
        'total_spent': total_spent,
        'total_remaining': total_remaining,
        'usage_percent': usage_percent,
        'alerts': alerts,
        'over_budget': over_budget,
        'category_rows': category_rows,
        'top_category': top_category,
        'trend': trend,
        'highest_day': highest_day,
        'prev_spent': prev_spent,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'upcoming': upcoming,
        'trend_labels_json': json.dumps([d.strftime('%d %b') for d, _ in trend]),
        'trend_data_json': json.dumps([float(t) for _, t in trend]),
        'category_labels_json': json.dumps([r['label'] for r in category_rows[:6]]),
        'category_data_json': json.dumps([float(r['spent']) for r in category_rows[:6]]),
        'budget_labels_json': json.dumps([b.display_category for b in budgets]),
        'budget_amount_json': json.dumps([float(b.amount) for b in budgets]),
        'budget_spent_json': json.dumps([float(b.spent_amount) for b in budgets]),
    }
    return render(request, 'budgeting/dashboard.html', context)


@role_required(*VIEW_ROLES)
def budget_list(request):
    tenant = request.user.tenant
    budgets = Budget.objects.filter(tenant=tenant).order_by('-start_date') if tenant else Budget.objects.none()
    return render(request, 'budgeting/budget_list.html', {'budgets': budgets})


@role_required(*VIEW_ROLES)
def budget_detail(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    trend = daily_totals(
        budget.tenant, budget.start_date, min(budget.end_date, timezone.localdate()),
    ) if budget.start_date <= timezone.localdate() else []
    context = {
        'budget': budget,
        'trend_labels_json': json.dumps([d.strftime('%d %b') for d, _ in trend]),
        'trend_data_json': json.dumps([float(t) for _, t in trend]),
    }
    return render(request, 'budgeting/budget_detail.html', context)


@role_required(*EDIT_ROLES)
def budget_create(request):
    if request.method == 'POST':
        form = BudgetForm(request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.tenant = request.user.tenant
            budget.created_by = request.user
            budget.save()
            messages.success(request, f'Budget "{budget.name}" created!')
            return redirect('budgeting:budget_detail', pk=budget.pk)
    else:
        initial = {}
        period = request.GET.get('period')
        if period in dict(Budget.PERIOD_CHOICES):
            start, end = period_bounds(period)
            initial = {'period': period, 'start_date': start, 'end_date': end}
        form = BudgetForm(initial=initial)
    return render(request, 'budgeting/budget_form.html', {'form': form, 'title': 'Create Budget'})


@role_required(*EDIT_ROLES)
def budget_edit(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            form.save()
            messages.success(request, 'Budget updated!')
            return redirect('budgeting:budget_detail', pk=budget.pk)
    else:
        form = BudgetForm(instance=budget)
    return render(request, 'budgeting/budget_form.html', {'form': form, 'title': 'Edit Budget', 'budget': budget})


@role_required(*EDIT_ROLES)
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    if request.method == 'POST':
        name = budget.name
        budget.delete()
        messages.success(request, f'Budget "{name}" deleted.')
        return redirect('budgeting:budget_list')
    return render(request, 'budgeting/budget_confirm_delete.html', {'budget': budget})


def _report_range(request):
    range_type = request.GET.get('range', 'monthly')
    if range_type == 'custom':
        start = parse_date(request.GET.get('start', '') or '') or period_bounds('monthly')[0]
        end = parse_date(request.GET.get('end', '') or '') or period_bounds('monthly')[1]
        if end < start:
            start, end = end, start
    elif range_type in ('daily', 'weekly', 'monthly'):
        start, end = period_bounds(range_type)
    else:
        range_type = 'monthly'
        start, end = period_bounds('monthly')
    return range_type, start, end


@role_required(*VIEW_ROLES)
def budget_report(request):
    tenant = request.user.tenant
    range_type, start, end = _report_range(request)

    budgets = _budgets_for_window(tenant, start, end).order_by('category', '-start_date')
    category_rows = _category_breakdown(tenant, start, end)
    total_budgeted = sum((b.amount for b in budgets), Decimal('0'))
    total_spent = sum((b.spent_amount for b in budgets), Decimal('0'))

    context = {
        'range_type': range_type,
        'start_date': start,
        'end_date': end,
        'budgets': budgets,
        'category_rows': category_rows,
        'total_budgeted': total_budgeted,
        'total_spent': total_spent,
    }
    return render(request, 'budgeting/budget_report.html', context)


@role_required(*VIEW_ROLES)
def budget_report_csv(request):
    tenant = request.user.tenant
    range_type, start, end = _report_range(request)
    budgets = _budgets_for_window(tenant, start, end).order_by('category', '-start_date')

    response = HttpResponse(content_type='text/csv')
    filename = f'budget_report_{start}_{end}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Budget report', f'{start} to {end}'])
    writer.writerow([])
    writer.writerow(['Name', 'Category', 'Period', 'Start', 'End', 'Budgeted (KES)', 'Spent (KES)', 'Remaining (KES)', 'Used %'])
    for b in budgets:
        writer.writerow([
            b.name, b.display_category, b.get_period_display(), b.start_date, b.end_date,
            b.amount, b.spent_amount, b.remaining_amount, f'{b.usage_percent:.1f}',
        ])

    writer.writerow([])
    writer.writerow(['Category totals (all spending in range, budgeted or not)'])
    writer.writerow(['Category', 'Spent (KES)'])
    for row in _category_breakdown(tenant, start, end):
        writer.writerow([row['label'], row['spent']])

    return response
