"""Forms for the stock workflows.

Every people/product/location picker sets its queryset inside __init__ from an
explicitly passed tenant. A queryset written at class level is evaluated once
at import, before any request exists, and that stale result is then reused for
the life of the process -- the bug already fixed in sales and inventory forms
earlier, where a dropdown silently offered (and accepted) every tenant's rows.
"""
from django import forms
from django.utils import timezone

from .models import (
    GoodsReceipt, GoodsReceiptLine, Location, Product, StockCount, StockTransfer,
)


class TenantScopedForm(forms.ModelForm):
    """Base that scopes the listed fields to one business, per request."""

    product_fields = ()
    location_fields = ()
    supplier_fields = ()

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is None:
            return
        for name in self.product_fields:
            if name in self.fields:
                self.fields[name].queryset = Product.objects.filter(
                    tenant=tenant, is_active=True,
                ).order_by('name')
        for name in self.location_fields:
            if name in self.fields:
                self.fields[name].queryset = Location.objects.filter(
                    tenant=tenant, is_active=True,
                ).order_by('name')
        for name in self.supplier_fields:
            if name in self.fields:
                from .models import Supplier
                self.fields[name].queryset = Supplier.objects.filter(
                    tenant=tenant,
                ).order_by('name')

    def _belongs_to_tenant(self, obj, field_name):
        """Second line of defence: even if a queryset were mis-set, a raw POST
        naming another business's row must not get through."""
        if obj is not None and obj.tenant_id != getattr(self.tenant, 'pk', None):
            self.add_error(field_name, 'That does not belong to your business.')


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'code', 'kind', 'address', 'is_default', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Nakuru Branch'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. NKR-01'}),
            'kind': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class GoodsReceiptForm(TenantScopedForm):
    location_fields = ('location',)
    supplier_fields = ('supplier',)

    class Meta:
        model = GoodsReceipt
        fields = ['supplier', 'purchase_order', 'invoice_number', 'location', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier invoice / delivery note number'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.tenant is not None:
            from sales.models import Order
            # Supplier orders are this ERP's purchase orders -- no new PO model.
            self.fields['purchase_order'].queryset = Order.objects.filter(
                tenant=self.tenant, order_type='supplier',
            ).exclude(status='cancelled').order_by('-date')
            self.fields['purchase_order'].required = False
            self.fields['purchase_order'].empty_label = 'No purchase order (direct delivery)'
            self.fields['supplier'].required = False
            self.fields['supplier'].empty_label = 'Not recorded'

    def clean_location(self):
        location = self.cleaned_data.get('location')
        self._belongs_to_tenant(location, 'location')
        return location


class GoodsReceiptLineForm(TenantScopedForm):
    product_fields = ('product',)

    class Meta:
        model = GoodsReceiptLine
        fields = ['product', 'quantity_ordered', 'quantity_received',
                  'quantity_rejected', 'unit_cost', 'batch_number', 'expiry_date']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity_ordered': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'quantity_rejected': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lot / batch number'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_product(self):
        product = self.cleaned_data.get('product')
        self._belongs_to_tenant(product, 'product')
        return product

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        received = cleaned.get('quantity_received')
        expiry = cleaned.get('expiry_date')

        if received is not None and received < 0:
            self.add_error('quantity_received', 'Received quantity cannot be negative.')
        if product is not None and product.tracks_expiry and not expiry:
            self.add_error(
                'expiry_date',
                f'{product.name} is tracked by expiry, so an expiry date is required.',
            )
        if expiry and expiry < timezone.localdate():
            self.add_error('expiry_date', 'That expiry date is already in the past.')
        return cleaned


class StockTransferForm(TenantScopedForm):
    product_fields = ('product',)
    location_fields = ('source', 'destination')

    class Meta:
        model = StockTransfer
        fields = ['product', 'quantity', 'source', 'destination', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'destination': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional note'}),
        }

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        source = cleaned.get('source')
        destination = cleaned.get('destination')
        quantity = cleaned.get('quantity')

        self._belongs_to_tenant(product, 'product')
        self._belongs_to_tenant(source, 'source')
        self._belongs_to_tenant(destination, 'destination')

        if quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be greater than zero.')
        if source and destination and source.pk == destination.pk:
            self.add_error('destination', 'Pick a different destination from the source.')

        # Advisory only: stock is re-checked under lock at dispatch, since it
        # can move between requesting a transfer and sending it.
        if product and source and quantity:
            from .services import available_quantity
            on_hand = available_quantity(product, source)
            if on_hand < quantity:
                self.add_error(
                    'quantity',
                    f'Only {on_hand} of {product.name} at {source.name} right now.',
                )
        return cleaned


class StockCountStartForm(forms.Form):
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='A count covers one location at a time.',
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is not None:
            self.fields['location'].queryset = Location.objects.filter(
                tenant=tenant, is_active=True,
            ).order_by('name')


class StockCountRejectForm(forms.Form):
    reason = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Why is this count being rejected?'}),
    )
