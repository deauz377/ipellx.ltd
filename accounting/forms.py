from django import forms
from .models import (
    ChartOfAccounts, Journal, JournalEntry, Invoice, InvoiceItem,
    Bill, BillItem, BankAccount, BankTransaction, Budget, BudgetLine,
    TaxConfiguration, MPesaIntegration, BankReconciliation
)


class ChartOfAccountsForm(forms.ModelForm):
    class Meta:
        model = ChartOfAccounts
        fields = ['account_number', 'account_name', 'account_type', 'description', 'opening_balance', 'is_active']
        widgets = {
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JournalForm(forms.ModelForm):
    class Meta:
        model = Journal
        fields = ['name', 'journal_type', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'journal_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['journal', 'reference_number', 'entry_date', 'account', 'entry_type', 'amount', 'description', 'related_document']
        widgets = {
            'journal': forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'entry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'account': forms.Select(attrs={'class': 'form-control'}),
            'entry_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'related_document': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['invoice_number', 'invoice_date', 'due_date', 'customer', 'customer_name', 'customer_email', 'customer_phone', 'payment_terms', 'notes', 'terms_and_conditions']
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'customer': forms.Select(attrs={'class': 'form-control'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'terms_and_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['description', 'quantity', 'unit_price', 'tax_rate']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class BillForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = ['bill_number', 'bill_date', 'due_date', 'vendor', 'vendor_email', 'vendor_phone', 'payment_terms', 'notes']
        widgets = {
            'bill_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bill_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'vendor': forms.TextInput(attrs={'class': 'form-control'}),
            'vendor_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'vendor_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['account_name', 'account_type', 'account_number', 'bank_name', 'branch_code', 'opening_balance', 'currency', 'is_active']
        widgets = {
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'branch_code': forms.TextInput(attrs={'class': 'form-control'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '3'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BankTransactionForm(forms.ModelForm):
    class Meta:
        model = BankTransaction
        fields = ['bank_account', 'transaction_type', 'transaction_date', 'reference_number', 'description', 'amount']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'transaction_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['name', 'fiscal_year', 'budget_period', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'fiscal_year': forms.NumberInput(attrs={'class': 'form-control', 'min': '2000'}),
            'budget_period': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class TaxConfigurationForm(forms.ModelForm):
    class Meta:
        model = TaxConfiguration
        fields = ['tax_type', 'tax_rate', 'tax_account', 'is_active']
        widgets = {
            'tax_type': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_account': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MPesaIntegrationForm(forms.ModelForm):
    class Meta:
        model = MPesaIntegration
        fields = ['business_shortcode', 'consumer_key', 'consumer_secret', 'passkey', 'api_endpoint', 'is_active']
        widgets = {
            'business_shortcode': forms.TextInput(attrs={'class': 'form-control'}),
            'consumer_key': forms.PasswordInput(attrs={'class': 'form-control'}),
            'consumer_secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'passkey': forms.PasswordInput(attrs={'class': 'form-control'}),
            'api_endpoint': forms.URLInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BankReconciliationForm(forms.ModelForm):
    class Meta:
        model = BankReconciliation
        fields = ['bank_account', 'reconciliation_date', 'bank_balance', 'book_balance', 'notes']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-control'}),
            'reconciliation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'book_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
