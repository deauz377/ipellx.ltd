from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Customer, CreditRecord
from .forms import CustomerForm, CreditRecordForm

def customer_list(request):
    customers = Customer.objects.all()
    return render(request, 'customers/customer_list.html', {'customers': customers})

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

