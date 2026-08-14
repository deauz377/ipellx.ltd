from django import forms
from .models import (
    SalaryStructure, Allowance, Deduction, EmployeeSalarySetup,
    OvertimeRule, PayrollPeriod, PayrollRun, Payslip, PaymentIntegration
)


class SalaryStructureForm(forms.ModelForm):
    class Meta:
        model = SalaryStructure
        fields = ['name', 'basic_salary', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = Allowance
        fields = ['name', 'allowance_type', 'value', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'allowance_type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DeductionForm(forms.ModelForm):
    class Meta:
        model = Deduction
        fields = ['name', 'deduction_type', 'value', 'description', 'is_mandatory', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'deduction_type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class EmployeeSalarySetupForm(forms.ModelForm):
    class Meta:
        model = EmployeeSalarySetup
        fields = ['employee', 'salary_structure', 'allowances', 'deductions', 'effective_date', 'is_active']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'salary_structure': forms.Select(attrs={'class': 'form-control'}),
            'allowances': forms.CheckboxSelectMultiple(attrs={'class': 'form-check'}),
            'deductions': forms.CheckboxSelectMultiple(attrs={'class': 'form-check'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class OvertimeRuleForm(forms.ModelForm):
    class Meta:
        model = OvertimeRule
        fields = ['name', 'multiplier', 'day_type', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'multiplier': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'day_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PayrollPeriodForm(forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ['name', 'period_type', 'start_date', 'end_date', 'payment_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'period_type': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PayrollRunForm(forms.ModelForm):
    class Meta:
        model = PayrollRun
        fields = ['payroll_period', 'status', 'payment_method', 'notes']
        widgets = {
            'payroll_period': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PayslipForm(forms.ModelForm):
    class Meta:
        model = Payslip
        fields = ['payroll_run', 'employee', 'overtime_hours', 'notes']
        widgets = {
            'payroll_run': forms.Select(attrs={'class': 'form-control'}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'overtime_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PaymentIntegrationForm(forms.ModelForm):
    class Meta:
        model = PaymentIntegration
        fields = ['name', 'payment_type', 'api_key', 'api_secret', 'api_endpoint', 'account_number', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-control'}),
            'api_key': forms.PasswordInput(attrs={'class': 'form-control'}),
            'api_secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'api_endpoint': forms.URLInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
