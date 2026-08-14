from django import forms
from .models import (
    Employee, Department, Position, LeaveType, LeaveRequest, Attendance,
    EmployeeAdvance, PerformanceReview, Training, EmployeeTraining,
    Recruitment, JobApplication
)


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'employee_id', 'user', 'department', 'position', 'manager',
            'date_of_birth', 'phone_number', 'mobile_number', 'national_id',
            'tax_id', 'bank_account', 'mpesa_number', 'employment_type',
            'employment_status', 'date_of_joining', 'date_of_termination',
            'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship', 'address', 'profile_image_url'
        ]
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'position': forms.Select(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'mpesa_number': forms.TextInput(attrs={'class': 'form-control'}),
            'employment_type': forms.Select(attrs={'class': 'form-control'}),
            'employment_status': forms.Select(attrs={'class': 'form-control'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_of_termination': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relationship': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_image_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Profile image URL'}),
        }


class DepartmentForm(forms.ModelForm):
    manager_name = forms.CharField(
        required=False, label='Manager',
        help_text="Type an existing employee's name, or leave blank.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Moses Nduati'}),
    )

    class Meta:
        model = Department
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.manager:
            self.fields['manager_name'].initial = self.instance.manager.user.get_full_name() or self.instance.manager.user.username


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['name', 'department', 'description', 'reports_to', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'reports_to': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class LeaveRequestForm(forms.ModelForm):
    leave_type_name = forms.CharField(
        label='Leave Type',
        help_text="e.g. Annual, Sick, Maternity. Typing a new one creates it automatically.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Annual Leave'}),
    )

    class Meta:
        model = LeaveRequest
        fields = ['start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.leave_type:
            self.fields['leave_type_name'].initial = self.instance.leave_type.name


class AttendanceForm(forms.ModelForm):
    employee_name = forms.CharField(
        label='Name of Employee', required=False,
        help_text="Type the employee's name exactly as it appears in Employees. Leave blank if logging your own attendance.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Janet Muthoni'}),
    )

    class Meta:
        model = Attendance
        fields = ['date', 'status', 'check_in_time', 'check_out_time', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'check_in_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.employee:
            self.fields['employee_name'].initial = self.instance.employee.user.get_full_name() or self.instance.employee.user.username


class EmployeeAdvanceForm(forms.ModelForm):
    class Meta:
        model = EmployeeAdvance
        fields = ['amount', 'repayment_start_date', 'repayment_months', 'reason']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'repayment_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'repayment_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PerformanceReviewForm(forms.ModelForm):
    class Meta:
        model = PerformanceReview
        fields = ['review_date', 'period_start', 'period_end', 'overall_rating', 'strengths', 'areas_for_improvement', 'goals_for_next_period', 'comments']
        widgets = {
            'review_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'overall_rating': forms.Select(attrs={'class': 'form-control'}),
            'strengths': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'areas_for_improvement': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'goals_for_next_period': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class RecruitmentForm(forms.ModelForm):
    position_name = forms.CharField(
        label='Position',
        help_text="Type the job title. Typing a new one creates it automatically.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Cashier'}),
    )

    class Meta:
        model = Recruitment
        fields = ['title', 'description', 'requirements', 'status', 'number_of_positions', 'salary_range_min', 'salary_range_max', 'closing_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'requirements': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'number_of_positions': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'salary_range_min': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'salary_range_max': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'closing_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.position:
            self.fields['position_name'].initial = self.instance.position.name


class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ['first_name', 'last_name', 'email', 'phone', 'resume', 'cover_letter']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'resume': forms.FileInput(attrs={'class': 'form-control'}),
            'cover_letter': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
