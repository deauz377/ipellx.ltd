from django import forms
from .models import Customer, CreditRecord

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'credit_limit', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address (optional)'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Preferences, history, anything worth remembering'}),
        }

class CreditRecordForm(forms.ModelForm):
    class Meta:
        model = CreditRecord
        fields = ['customer', 'invoice', 'amount', 'due_date']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Meta.fields would otherwise build these dropdowns' querysets once,
        # at class-definition time -- before any request/tenant context
        # exists, permanently baking in every tenant's customers/invoices.
        # Re-set them here so they run per-request, after TenantMiddleware
        # has set the current tenant.
        self.fields['customer'].queryset = Customer.objects.all()
        from sales.models import Invoice
        self.fields['invoice'].queryset = Invoice.objects.all()
