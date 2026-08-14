from django.contrib import admin
from .models import (
    SalaryStructure, Allowance, Deduction, EmployeeSalarySetup,
    OvertimeRule, PayrollPeriod, PayrollRun, Payslip, PayslipDetail,
    PaymentIntegration, PaymentRecord
)


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ('name', 'basic_salary', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'basic_salary')
        }),
        ('Details', {
            'fields': ('description',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(Allowance)
class AllowanceAdmin(admin.ModelAdmin):
    list_display = ('name', 'allowance_type', 'value', 'is_active', 'created_at')
    list_filter = ('allowance_type', 'is_active', 'created_at')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'allowance_type', 'value')
        }),
        ('Details', {
            'fields': ('description',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(Deduction)
class DeductionAdmin(admin.ModelAdmin):
    list_display = ('name', 'deduction_type', 'value', 'is_mandatory', 'is_active', 'created_at')
    list_filter = ('deduction_type', 'is_mandatory', 'is_active', 'created_at')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'deduction_type', 'value')
        }),
        ('Details', {
            'fields': ('description', 'is_mandatory')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(EmployeeSalarySetup)
class EmployeeSalarySetupAdmin(admin.ModelAdmin):
    list_display = ('employee', 'salary_structure', 'effective_date', 'is_active', 'created_at')
    list_filter = ('is_active', 'effective_date', 'created_at')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    filter_horizontal = ('allowances', 'deductions')


@admin.register(OvertimeRule)
class OvertimeRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'multiplier', 'day_type', 'is_active', 'created_at')
    list_filter = ('day_type', 'is_active', 'created_at')
    search_fields = ('name',)


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'period_type', 'start_date', 'end_date', 'payment_date', 'is_locked', 'is_active')
    list_filter = ('period_type', 'is_locked', 'is_active', 'start_date')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('payroll_period', 'status', 'total_net', 'payment_method', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('payroll_period__name',)
    readonly_fields = ('total_gross', 'total_deductions', 'total_net', 'created_at', 'updated_at')
    fieldsets = (
        ('Payroll Information', {
            'fields': ('payroll_period', 'status', 'payment_method')
        }),
        ('Totals', {
            'fields': ('total_gross', 'total_deductions', 'total_net'),
            'classes': ('collapse',)
        }),
        ('Processing', {
            'fields': ('processing_date', 'created_by', 'approved_by', 'notes')
        }),
    )


class PayslipDetailInline(admin.TabularInline):
    model = PayslipDetail
    extra = 0


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll_run', 'net_salary', 'payment_status', 'created_at')
    list_filter = ('payment_status', 'created_at')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    readonly_fields = ('basic_salary', 'gross_salary', 'total_deductions', 'net_salary')
    inlines = [PayslipDetailInline]


@admin.register(PaymentIntegration)
class PaymentIntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'payment_type', 'is_active', 'created_at')
    list_filter = ('payment_type', 'is_active', 'created_at')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'payment_type')
        }),
        ('Credentials', {
            'fields': ('api_key', 'api_secret', 'api_endpoint', 'account_number'),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': ('configuration',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('payslip', 'transaction_id', 'amount', 'status', 'payment_date')
    list_filter = ('status', 'payment_date', 'payment_method')
    search_fields = ('transaction_id', 'payslip__employee__user__first_name')
    readonly_fields = ('created_at', 'updated_at')
