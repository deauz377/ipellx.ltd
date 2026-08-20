from django import forms

from .models import Budget


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['name', 'period', 'category', 'custom_category', 'amount', 'start_date', 'end_date', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. August Rent'}),
            'period': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'custom_category': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Only needed if category is "Other expenses"',
            }),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError('End date cannot be before start date.')

        amount = cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('Budget amount must be greater than zero.')

        category = cleaned_data.get('category')
        custom_category = cleaned_data.get('custom_category')
        if category == 'other' and not custom_category:
            self.add_error('custom_category', 'Please describe what this "Other" category covers.')

        return cleaned_data
