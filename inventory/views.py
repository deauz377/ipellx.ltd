from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, ProtectedError
from django.http import HttpResponse
import csv
from .models import Product, Supplier
from .forms import ProductForm, SupplierForm
from .services import low_stock_queryset, stock_value
from tenants.decorators import role_required

# These views had no role restriction at all: any signed-in user, including
# Sales Staff, could create, edit or delete products. Stock-changing screens
# are limited to the roles that own inventory; the read-only lists stay open
# to the Accountant (valuation) and Sales Staff (availability), who need to
# see stock without being able to change it.
STOCK_ROLES = ('OWNER', 'MANAGER', 'INVENTORY_MANAGER')
VIEW_ROLES = STOCK_ROLES + ('ACCOUNTANT', 'SALES_STAFF')

@role_required(*VIEW_ROLES)
def inventory_overview(request):
    # Get inventory statistics
    tenant = request.user.tenant
    total_products = Product.objects.count()
    total_suppliers = Supplier.objects.count()
    # Both of these used to be worked out here, and both were wrong: "low"
    # meant "below the catalogue average", and the value multiplied the sum of
    # every price by the sum of every quantity. They now come from the same
    # helpers the Stock Control and CEO screens use, so the figures agree.
    low_stock = low_stock_queryset(tenant)
    low_stock_products = low_stock.count()
    total_stock_value = stock_value(tenant)

    # Get recent products
    recent_products = Product.objects.all().order_by('-id')[:5]

    # Get low stock alerts
    low_stock_alerts = low_stock[:5]

    context = {
        'total_products': total_products,
        'total_suppliers': total_suppliers,
        'low_stock_products': low_stock_products,
        'total_stock_value': total_stock_value,
        'recent_products': recent_products,
        'low_stock_alerts': low_stock_alerts,
    }
    return render(request, 'inventory/overview.html', context)

# Products
@role_required(*VIEW_ROLES)
def product_list(request):
    products = Product.objects.all()
    search_query = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(supplier__name__icontains=search_query)
        )

    if category_filter:
        products = products.filter(category__icontains=category_filter)

    products = products.order_by('name')

    context = {
        'products': products,
        'search_query': search_query,
        'category_filter': category_filter,
    }
    return render(request, 'inventory/product_list.html', context)

@role_required(*STOCK_ROLES)
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product added successfully!')
            return redirect('inventory:product_list')
    else:
        form = ProductForm()
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Add Product'})

@role_required(*STOCK_ROLES)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('inventory:product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Edit Product'})

@role_required(*STOCK_ROLES)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    # Check if product can be safely deleted
    from sales.models import InvoiceItem, OrderItem
    has_invoice_items = InvoiceItem.objects.filter(product=product).exists()
    has_order_items = OrderItem.objects.filter(product=product).exists()
    can_delete = not (has_invoice_items or has_order_items)
    
    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, 'Product deleted successfully!')
            return redirect('inventory:product_list')
        except ProtectedError:
            messages.error(request, 'Cannot delete this product because it is referenced in existing orders or invoices. Please remove all related records first.')
            return redirect('inventory:product_list')
    
    context = {
        'product': product,
        'can_delete': can_delete,
        'has_invoice_items': has_invoice_items,
        'has_order_items': has_order_items,
    }
    return render(request, 'inventory/product_confirm_delete.html', context)

# Suppliers
@role_required(*VIEW_ROLES)
def supplier_list(request):
    suppliers = Supplier.objects.all()
    return render(request, 'inventory/supplier_list.html', {'suppliers': suppliers})

@role_required(*STOCK_ROLES)
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier added successfully!')
            return redirect('inventory:supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'inventory/supplier_form.html', {'form': form, 'title': 'Add Supplier'})

@role_required(*VIEW_ROLES)
def product_export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'SKU', 'Retail Price', 'Wholesale Price', 'Online Price', 'Quantity', 'Min Stock', 'Supplier'])

    products = Product.objects.all().values_list(
        'name', 'sku', 'retail_price', 'wholesale_price', 'online_price', 'quantity', 'minimum_stock', 'supplier__name'
    )
    for product in products:
        writer.writerow(product)

    return response

@role_required(*STOCK_ROLES)
def product_import_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)

        imported_count = 0
        for row in reader:
            try:
                supplier, created = Supplier.objects.get_or_create(name=row['Supplier'])
                Product.objects.create(
                    name=row['Name'],
                    sku=row['SKU'],
                    retail_price=row['Retail Price'],
                    wholesale_price=row['Wholesale Price'],
                    online_price=row['Online Price'],
                    quantity=row['Quantity'],
                    minimum_stock=row['Min Stock'],
                    supplier=supplier,
                )
                imported_count += 1
            except Exception as e:
                messages.error(request, f'Error importing row: {e}')
                continue

        messages.success(request, f'Successfully imported {imported_count} products!')
        return redirect('inventory:product_list')

    return render(request, 'inventory/product_import.html')

