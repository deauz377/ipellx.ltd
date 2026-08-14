from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from tenants.models import TenantModel
from datetime import datetime


class SalaryStructure(TenantModel):
    """
    Defines the base salary structure for employees
    """
    name = models.CharField(max_length=100)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Salary Structure'
        verbose_name_plural = 'Salary Structures'

    def __str__(self):
        return f"{self.name} - {self.basic_salary}"


class Allowance(TenantModel):
    """
    Types of allowances employees can receive
    """
    ALLOWANCE_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('percentage', 'Percentage of Basic'),
        ('variable', 'Variable'),
    ]

    name = models.CharField(max_length=100)
    allowance_type = models.CharField(max_length=20, choices=ALLOWANCE_TYPE_CHOICES)
    value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Allowance'
        verbose_name_plural = 'Allowances'

    def __str__(self):
        return f"{self.name} ({self.get_allowance_type_display()})"


class Deduction(TenantModel):
    """
    Types of deductions from employee salaries
    """
    DEDUCTION_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('percentage', 'Percentage of Basic'),
        ('tax', 'Tax'),
        ('variable', 'Variable'),
    ]

    name = models.CharField(max_length=100)
    deduction_type = models.CharField(max_length=20, choices=DEDUCTION_TYPE_CHOICES)
    value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Deduction'
        verbose_name_plural = 'Deductions'

    def __str__(self):
        return f"{self.name} ({self.get_deduction_type_display()})"


class EmployeeSalarySetup(TenantModel):
    """
    Employee-specific salary configuration
    """
    employee = models.OneToOneField('hr.Employee', on_delete=models.CASCADE, related_name='salary_setup')
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.PROTECT)
    allowances = models.ManyToManyField(Allowance, blank=True, related_name='employee_salary_setups')
    deductions = models.ManyToManyField(Deduction, blank=True, related_name='employee_salary_setups')
    effective_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Employee Salary Setup'
        verbose_name_plural = 'Employee Salary Setups'

    def __str__(self):
        return f"{self.employee} - {self.salary_structure}"

    def get_gross_salary(self):
        """Calculate gross salary"""
        gross = self.salary_structure.basic_salary
        for allowance in self.allowances.all():
            if allowance.allowance_type == 'fixed':
                gross += allowance.value
            elif allowance.allowance_type == 'percentage':
                gross += (self.salary_structure.basic_salary * allowance.value / 100)
        return gross

    def get_total_deductions(self):
        """Calculate total deductions"""
        total = 0
        for deduction in self.deductions.all():
            if deduction.deduction_type == 'fixed':
                total += deduction.value
            elif deduction.deduction_type == 'percentage':
                total += (self.salary_structure.basic_salary * deduction.value / 100)
        return total

    def get_net_salary(self):
        """Calculate net salary"""
        return self.get_gross_salary() - self.get_total_deductions()


class OvertimeRule(TenantModel):
    """
    Overtime calculation rules
    """
    name = models.CharField(max_length=100)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, help_text="E.g., 1.5 for 1.5x pay")
    day_type = models.CharField(max_length=20, choices=[
        ('weekday', 'Weekday'),
        ('weekend', 'Weekend'),
        ('holiday', 'Holiday')
    ])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Overtime Rule'
        verbose_name_plural = 'Overtime Rules'

    def __str__(self):
        return f"{self.name} ({self.multiplier}x)"


class PayrollPeriod(TenantModel):
    """
    Defines payroll periods (monthly, bi-weekly, etc.)
    """
    PERIOD_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('bi-weekly', 'Bi-Weekly'),
        ('weekly', 'Weekly'),
    ]

    name = models.CharField(max_length=100)
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    payment_date = models.DateField()
    is_locked = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payroll Period'
        verbose_name_plural = 'Payroll Periods'
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"


class PayrollRun(TenantModel):
    """
    Represents a single payroll processing run
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('processed', 'Processed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name='runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_gross = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    processing_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=[
        ('bank_transfer', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('cash', 'Cash'),
        ('check', 'Check')
    ], default='bank_transfer')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='payroll_runs')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payroll_runs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payroll Run'
        verbose_name_plural = 'Payroll Runs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Payroll {self.payroll_period.name} - {self.get_status_display()}"


class Payslip(TenantModel):
    """
    Individual employee payslip for a payroll run
    """
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    employee = models.ForeignKey('hr.Employee', on_delete=models.CASCADE, related_name='payslips')
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ], default='pending')
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payslip'
        verbose_name_plural = 'Payslips'
        unique_together = ('payroll_run', 'employee')
        ordering = ['-created_at']

    def __str__(self):
        return f"Payslip - {self.employee} ({self.payroll_run})"


class PayslipDetail(TenantModel):
    """
    Detailed breakdown of payslip components
    """
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='details')
    component_type = models.CharField(max_length=20, choices=[
        ('allowance', 'Allowance'),
        ('deduction', 'Deduction'),
        ('overtime', 'Overtime'),
    ])
    component_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Payslip Detail'
        verbose_name_plural = 'Payslip Details'

    def __str__(self):
        return f"{self.payslip} - {self.component_name}: {self.amount}"


class PaymentIntegration(TenantModel):
    """
    Configuration for payment integrations (Bank, M-Pesa, etc.)
    """
    PAYMENT_TYPE_CHOICES = [
        ('bank', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    api_key = models.CharField(max_length=255, blank=True)
    api_secret = models.CharField(max_length=255, blank=True)
    api_endpoint = models.URLField(blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment Integration'
        verbose_name_plural = 'Payment Integrations'

    def __str__(self):
        return f"{self.name} ({self.get_payment_type_display()})"


class PaymentRecord(TenantModel):
    """
    Tracks actual payment transactions
    """
    payslip = models.OneToOneField(Payslip, on_delete=models.CASCADE, related_name='payment_record')
    payment_method = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_gateway = models.ForeignKey(PaymentIntegration, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('initiated', 'Initiated'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ], default='initiated')
    payment_date = models.DateTimeField()
    recipient_account = models.CharField(max_length=100)
    receipt = models.FileField(upload_to='payroll/receipts/', blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment Record'
        verbose_name_plural = 'Payment Records'

    def __str__(self):
        return f"Payment - {self.payslip.employee} - {self.transaction_id}"
