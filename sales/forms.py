import json

from django import forms
from django.forms import formset_factory
from .models import Invoice, InvoiceItem, Payment, PaymentRequest, Order, OrderItem, DailySalesEntry, ProfitEntry
from inventory.models import Location, Product, Supplier
from inventory.services import available_by_location, sellable_locations
from customers.models import Customer


class ProductSelect(forms.Select):
    """Select widget that stamps each <option> with data-*-price/data-stock
    so the quick sale page can auto-fill price and show stock without
    a round trip to the server. Carries all three price tiers -- which one
    actually gets used is decided client-side by the row's channel dropdown."""
    def __init__(self, *args, product_data=None, **kwargs):
        self.product_data = product_data or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        data = self.product_data.get(str(value))
        if data:
            option['attrs']['data-retail-price'] = str(data['retail_price'])
            option['attrs']['data-wholesale-price'] = str(data['wholesale_price'])
            option['attrs']['data-online-price'] = str(data['online_price'])
            # Stock per location, not one tenant-wide figure. The old
            # data-stock showed everything the business owned, including
            # goods at another branch that this till cannot sell, so a
            # seller could be told "50 in stock" and then refused.
            option['attrs']['data-stock-map'] = json.dumps(data['stock_by_location'])
        return option

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['customer', 'discount']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Discount amount'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Meta.fields would otherwise build this dropdown's queryset once, at
        # class-definition time -- before any request/tenant context exists,
        # permanently baking in every tenant's customers. Re-set it here so it
        # runs per-request, after TenantMiddleware has set the current tenant.
        self.fields['customer'].queryset = Customer.objects.all()

class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['product', 'qty', 'price', 'sale_channel', 'location']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sale_channel': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Same class-definition-time queryset issue as InvoiceForm.customer above.
        self.fields['product'].queryset = Product.objects.all()

        locations = sellable_locations(tenant) if tenant else Location.objects.none()
        self.fields['location'].queryset = locations
        self.fields['location'].initial = locations.first()
        self.fields['location'].empty_label = None
        self.single_location = locations.count() <= 1

    def clean_location(self):
        # Same fallback as QuickSaleForm: a hidden or blank field must still
        # resolve to somewhere stock can actually come out of.
        return self.cleaned_data.get('location') or self.fields['location'].queryset.first()

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['order_type', 'customer', 'supplier', 'status']
        widgets = {
            'order_type': forms.Select(attrs={'class': 'form-select'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Same class-definition-time queryset issue as InvoiceForm.customer above.
        self.fields['customer'].queryset = Customer.objects.all()
        self.fields['supplier'].queryset = Supplier.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        order_type = cleaned_data.get('order_type')
        customer = cleaned_data.get('customer')
        supplier = cleaned_data.get('supplier')

        if order_type == 'customer' and not customer:
            raise forms.ValidationError('Customer is required for customer orders.')
        if order_type == 'supplier' and not supplier:
            raise forms.ValidationError('Supplier is required for supplier orders.')
        return cleaned_data

class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'qty', 'price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Same class-definition-time queryset issue as InvoiceForm.customer above.
        self.fields['product'].queryset = Product.objects.all()

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['method', 'amount', 'reference', 'notes']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Transaction/reference number (optional)'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }


class PaymentRequestForm(forms.ModelForm):
    class Meta:
        model = PaymentRequest
        fields = ['amount_due', 'due_date', 'instructions']
        widgets = {
            'amount_due': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional payment instructions shown to the customer'}),
        }


class PaymentRefundForm(forms.Form):
    """Refunding always reverses the full amount of a single payment --
    no partial-amount field, which would leave it ambiguous which part
    of a multi-payment invoice the refund was actually against."""
    refund_reason = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Why is this being refunded?'}),
    )


class QuickSaleForm(forms.Form):
    """The top-level fields for a one-page daily sale entry: who bought,
    how they paid, and any overall discount."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        empty_label='Walk-in customer (no account)',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    payment_method = forms.ChoiceField(
        choices=Payment.METHOD_CHOICES,
        initial='cash',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    amount_received = forms.DecimalField(
        required=False, min_value=0, max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01',
            'placeholder': 'Leave blank if paid in full',
        }),
    )
    discount = forms.DecimalField(
        required=False, min_value=0, initial=0, max_digits=6, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    # One location per sale, not per line: a seller stands at one till and
    # sells what is on the shelf behind them.
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(), required=False, empty_label=None,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'quick-sale-location'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Same class-definition-time queryset issue as InvoiceForm.customer
        # above -- the class-body default of Customer.objects.all() would
        # otherwise be evaluated at import time, before any tenant is set.
        self.fields['customer'].queryset = Customer.objects.all().order_by('name')

        locations = sellable_locations(tenant) if tenant else Location.objects.none()
        self.fields['location'].queryset = locations
        self.fields['location'].initial = locations.first()
        # A business with one location has no choice to make, so the field is
        # not shown -- it still submits the default, and nothing about the
        # screen changes for the single-location businesses that exist today.
        self.single_location = locations.count() <= 1

    def clean_location(self):
        location = self.cleaned_data.get('location')
        if location:
            return location
        # Not shown, or submitted blank: fall back to the default rather than
        # letting the sale reach issue_stock() with nothing to sell from.
        return self.fields['location'].queryset.first()


class QuickSaleItemForm(forms.Form):
    """One product line in the quick sale table. Left blank rows are
    ignored, so the form works whether the seller fills in one item
    or a dozen."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(), required=False,
        widget=ProductSelect(attrs={'class': 'form-select quick-sale-product'}),
    )
    channel = forms.ChoiceField(
        choices=InvoiceItem.CHANNEL_CHOICES, required=False, initial='retail',
        widget=forms.Select(attrs={'class': 'form-select quick-sale-channel'}),
    )
    qty = forms.DecimalField(
        required=False, min_value=0.01, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control quick-sale-qty', 'step': '0.01', 'min': '0.01'}),
    )
    price = forms.DecimalField(
        required=False, min_value=0, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control quick-sale-price', 'step': '0.01'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.objects.all().order_by('name')
        self.fields['product'].queryset = products
        availability = available_by_location(tenant) if tenant else {}
        self.fields['product'].widget.product_data = {
            str(p.pk): {
                'retail_price': p.retail_price,
                'wholesale_price': p.wholesale_price,
                'online_price': p.online_price,
                # Formatted to two places here rather than left to str():
                # SQLite's Sum() returns Decimal('12') where PostgreSQL
                # returns Decimal('12.00'), so the seller would otherwise
                # read a different figure in production than in testing.
                'stock_by_location': {
                    str(loc_pk): format(qty, '.2f')
                    for loc_pk, qty in availability.get(p.pk, {}).items()
                },
            }
            for p in products
        }


QuickSaleItemFormSet = formset_factory(QuickSaleItemForm, extra=6)


class DailySalesEntryForm(forms.ModelForm):
    class Meta:
        model = DailySalesEntry
        fields = ['date', 'particulars', 'unit', 'quantity', 'unit_price', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'particulars': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sukuma wiki, Cooking gas refill'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }


class ProfitEntryForm(forms.ModelForm):
    class Meta:
        model = ProfitEntry
        fields = ['date', 'description', 'revenue', 'cost', 'expenses', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bulk maize sale'}),
            'revenue': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'expenses': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }
