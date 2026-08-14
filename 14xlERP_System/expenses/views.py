from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Expense
from .forms import ExpenseForm

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from .models import Expense
from .forms import ExpenseForm

def expense_list(request):
    expenses = Expense.objects.all().order_by('-date')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        expenses = expenses.filter(
            description__icontains=search_query
        )
    
    # Category filter
    category_filter = request.GET.get('category', '')
    if category_filter:
        expenses = expenses.filter(category=category_filter)
    
    # Date range filter
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if start_date:
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        expenses = expenses.filter(date__lte=end_date)
    
    # Statistics
    total_expenses = expenses.aggregate(
        total_amount=Sum('amount'),
        count=Count('id')
    )
    
    # Monthly breakdown for current month
    today = timezone.now().date()
    current_month_expenses = Expense.objects.filter(
        date__year=today.year,
        date__month=today.month
    ).aggregate(
        monthly_total=Sum('amount'),
        monthly_count=Count('id')
    )
    
    # Category breakdown
    category_totals = Expense.objects.values('category').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    context = {
        'expenses': expenses,
        'search_query': search_query,
        'category_filter': category_filter,
        'start_date': start_date,
        'end_date': end_date,
        'total_expenses': total_expenses,
        'current_month_expenses': current_month_expenses,
        'category_totals': category_totals,
        'categories': Expense.CATEGORY_CHOICES,
    }
    return render(request, 'expenses/expense_list.html', context)

def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense recorded successfully!')
            return redirect('expenses:expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Record Expense'})

def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated!')
            return redirect('expenses:expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'expenses/expense_form.html', {'form': form, 'title': 'Edit Expense'})

def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted!')
        return redirect('expenses:expense_list')
    return render(request, 'expenses/expense_confirm_delete.html', {'expense': expense})

