from django import forms
from django.forms import formset_factory
from .models import Invoice, InvoiceItem, Payment, Order, OrderItem, DailySalesEntry, ProfitEntry
from inventory.models import Product
from customers.models import Customer


class ProductSelect(forms.Select):
    """Select widget that stamps each <option> with data-price/data-stock
    so the quick sale page can auto-fill price and show stock without
    a round trip to the server."""
    def __init__(self, *args, product_data=None, **kwargs):
        self.product_data = product_data or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        data = self.product_data.get(str(value))
        if data:
            option['attrs']['data-price'] = str(data['price'])
            option['attrs']['data-stock'] = str(data['stock'])
        return option

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['customer', 'discount']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Discount amount'}),
        }

class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['product', 'qty', 'price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

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
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['method', 'amount']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class QuickSaleForm(forms.Form):
    """The top-level fields for a one-page daily sale entry: who bought,
    how they paid, and any overall discount."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all().order_by('name'),
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


class QuickSaleItemForm(forms.Form):
    """One product line in the quick sale table. Left blank rows are
    ignored, so the form works whether the seller fills in one item
    or a dozen."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(), required=False,
        widget=ProductSelect(attrs={'class': 'form-select quick-sale-product'}),
    )
    qty = forms.IntegerField(
        required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control quick-sale-qty', 'min': '1'}),
    )
    price = forms.DecimalField(
        required=False, min_value=0, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control quick-sale-price', 'step': '0.01'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.objects.all().order_by('name')
        self.fields['product'].queryset = products
        self.fields['product'].widget.product_data = {
            str(p.pk): {'price': p.retail_price, 'stock': p.quantity} for p in products
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
