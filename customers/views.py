from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Max
from .models import Customer, CreditRecord
from .forms import CustomerForm, CreditRecordForm

def customer_list(request):
    customers = Customer.objects.all()
    return render(request, 'customers/customer_list.html', {'customers': customers})


@login_required
def crm_dashboard(request):
    """Relationship-focused view of the customer base: who's bought the
    most, who hasn't been back in a while, who's over their credit limit,
    and who has notes worth a glance before the next conversation with
    them. Everything here is read-only, built from existing Invoice and
    CreditRecord data -- nothing is written."""
    customers = list(Customer.objects.annotate(
        lifetime_sales=Sum('invoice__total'),
        order_count=Count('invoice', distinct=True),
        last_purchase=Max('invoice__date'),
    ).order_by('-lifetime_sales'))

    context = {
        'customers': customers,
        'total_customers': len(customers),
        'total_outstanding': sum((c.balance for c in customers), Decimal('0')),
        'over_limit_count': sum(1 for c in customers if c.credit_limit and c.balance > c.credit_limit),
        'with_notes_count': sum(1 for c in customers if c.notes),
    }
    return render(request, 'customers/crm_dashboard.html', context)

def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer added successfully!')
            return redirect('customers:customer_list')
    else:
        form = CustomerForm()
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Add Customer'})

def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    credits = CreditRecord.objects.filter(customer=customer)
    return render(request, 'customers/customer_detail.html', {'customer': customer, 'credits': credits})

def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated!')
            return redirect('customers:customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Edit Customer'})

