from django.contrib import admin
from .models import (
    Employee, Department, Position, LeaveType, LeaveRequest, Attendance,
    EmployeeAdvance, PerformanceReview, Training, EmployeeTraining,
    Recruitment, JobApplication, OrganizationStructure
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'manager', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'reports_to', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('name',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'department', 'position', 'employment_status', 'date_of_joining')
    list_filter = ('employment_status', 'employment_type', 'department', 'date_of_joining')
    search_fields = ('employee_id', 'user__first_name', 'user__last_name', 'national_id')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'employee_id')
        }),
        ('Employment Details', {
            'fields': ('department', 'position', 'manager', 'employment_type', 'employment_status', 'date_of_joining', 'date_of_termination')
        }),
        ('Personal Information', {
            'fields': ('date_of_birth', 'national_id', 'phone_number', 'mobile_number'),
            'classes': ('collapse',)
        }),
        ('Financial Information', {
            'fields': ('bank_account', 'mpesa_number', 'tax_id'),
            'classes': ('collapse',)
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship'),
            'classes': ('collapse',)
        }),
        ('Other', {
            'fields': ('profile_image', 'address', 'is_active'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'days_per_year', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status', 'created_at')
    list_filter = ('status', 'leave_type', 'start_date', 'created_at')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    readonly_fields = ('days_requested', 'created_at', 'updated_at')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'check_in_time', 'check_out_time')
    list_filter = ('status', 'date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')


@admin.register(EmployeeAdvance)
class EmployeeAdvanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'amount', 'status', 'advance_date', 'repayment_months')
    list_filter = ('status', 'advance_date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    fieldsets = (
        ('Employee & Amount', {
            'fields': ('employee', 'amount', 'advance_date')
        }),
        ('Repayment Details', {
            'fields': ('repayment_start_date', 'repayment_months', 'repaid_amount')
        }),
        ('Status', {
            'fields': ('status', 'approved_by', 'approval_date', 'disbursement_date')
        }),
        ('Additional', {
            'fields': ('reason', 'notes'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'review_date', 'overall_rating', 'reviewed_by')
    list_filter = ('overall_rating', 'review_date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Training)
class TrainingAdmin(admin.ModelAdmin):
    list_display = ('name', 'trainer', 'start_date', 'end_date', 'status', 'location')
    list_filter = ('status', 'start_date')
    search_fields = ('name', 'trainer')


@admin.register(EmployeeTraining)
class EmployeeTrainingAdmin(admin.ModelAdmin):
    list_display = ('employee', 'training', 'attendance', 'score')
    list_filter = ('attendance', 'training')
    search_fields = ('employee__user__first_name', 'training__name')


@admin.register(Recruitment)
class RecruitmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'position', 'status', 'number_of_positions', 'closing_date')
    list_filter = ('status', 'posted_date', 'closing_date')
    search_fields = ('title', 'position__name')


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'recruitment', 'status', 'applied_date', 'rating')
    list_filter = ('status', 'applied_date', 'recruitment')
    search_fields = ('first_name', 'last_name', 'email')
    readonly_fields = ('applied_date', 'updated_date')


@admin.register(OrganizationStructure)
class OrganizationStructureAdmin(admin.ModelAdmin):
    list_display = ('name', 'root_department', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name',)
