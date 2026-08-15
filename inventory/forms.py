from django import forms
from .models import Product, Supplier

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'category', 'cost_price', 'retail_price', 'wholesale_price', 'online_price', 'quantity', 'minimum_stock', 'supplier']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product name'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'What you paid/spent per unit'}),
            'retail_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'wholesale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'online_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g. 2.5 for fractional stock (kg, litres, etc.)'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
        }

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier name'}),
            'contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person / email'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 254712345678'}),
        }
