from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from tenants.decorators import role_required


class ManagerRequiredMixin:
    """Restricts a class-based view to OWNER/MANAGER (or super admin)."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_role('OWNER', 'MANAGER'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffOnlyMixin:
    """Attendance self-service is open to everyone — Staff, Manager, and
    Owner alike — so this is now just a login check. Kept as a named
    mixin in case a role-specific restriction is needed here later."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class LeaveSelfServiceMixin:
    """Restricts leave-request self-filing to Staff and Manager. The
    Owner is excluded — there's no one above them to ask for leave —
    but Managers DO file their own requests here, since they report to
    the Owner/CEO."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role == 'OWNER':
            raise PermissionDenied("Owners don't file leave requests — there's no one to approve them.")
        return super().dispatch(request, *args, **kwargs)


from django.db.models import Q, Count
from datetime import datetime
from django.utils import timezone
from .models import (
    Employee, Department, Position, LeaveType, LeaveRequest, Attendance,
    EmployeeAdvance, PerformanceReview, Training, EmployeeTraining,
    Recruitment, JobApplication, OrganizationStructure
)
from .forms import (
    EmployeeForm, DepartmentForm, PositionForm, LeaveRequestForm,
    AttendanceForm, EmployeeAdvanceForm, PerformanceReviewForm,
    RecruitmentForm, JobApplicationForm
)


def find_employee_by_name(tenant, name):
    """Matches a typed name against existing employees — tries their full
    name first, then username, then employee ID, all case-insensitive with
    surrounding whitespace ignored. Returns the Employee or None."""
    typed = (name or '').strip().lower()
    if not typed:
        return None
    for employee in Employee.objects.filter(tenant=tenant).select_related('user'):
        candidates = [
            employee.user.get_full_name(),
            employee.user.username,
            employee.employee_id,
        ]
        if any((c or '').strip().lower() == typed for c in candidates):
            return employee
    return None


@login_required
def staff_portal(request):
    """Self-service portal for attendance and leave requests. Owners
    (as CEO) and Managers get access too — Managers see a "Manager
    Portal" that shows who they report to (the Owner/CEO), and unlike
    the Owner, Managers DO file their own leave requests since they
    report to someone."""
    employee = getattr(request.user, 'employee_profile', None)
    if not employee:
        messages.error(request, 'Your account has no employee profile set up. Contact management.')
        return redirect('dashboard_overview')

    is_owner = request.user.role == 'OWNER'
    is_manager = request.user.role == 'MANAGER'
    portal_label = 'CEO' if is_owner else ('Manager' if is_manager else 'Staff')

    reports_to = None
    if is_manager:
        from tenants.models import User
        reports_to = User.objects.filter(tenant=request.user.tenant, role='OWNER').first()

    context = {
        'employee': employee,
        'portal_label': portal_label,
        'is_owner': is_owner,
        'is_manager': is_manager,
        'reports_to': reports_to,
        'my_attendance': employee.attendance_records.all().order_by('-date')[:7],
        'my_leave_requests': employee.leave_requests.all().order_by('-created_at')[:5],
        'pending_requests': employee.leave_requests.filter(status='pending').count(),
        'approved_requests': employee.leave_requests.filter(status='approved').count(),
    }
    return render(request, 'hr/staff_portal.html', context)


@login_required
def hr_dashboard(request):
    """HR dashboard - routes to staff portal or management dashboard based on role"""
    # If staff/employee, redirect to staff portal
    if not request.user.has_role('OWNER', 'MANAGER'):
        return redirect('hr:staff_portal')
    
    # Management dashboard - only for OWNER/MANAGER
    tenant = request.user.tenant
    
    context = {
        'total_employees': Employee.objects.filter(tenant=tenant).count() if tenant else 0,
        'active_employees': Employee.objects.filter(tenant=tenant, employment_status='active').count() if tenant else 0,
        'departments': Department.objects.filter(tenant=tenant).count() if tenant else 0,
        'pending_leave_requests': LeaveRequest.objects.filter(tenant=tenant, status='pending').count() if tenant else 0,
        'open_positions': Recruitment.objects.filter(tenant=tenant, status='open').count() if tenant else 0,
        'pending_applications': JobApplication.objects.filter(tenant=tenant, status='submitted').count() if tenant else 0,
        'active_trainings': Training.objects.filter(tenant=tenant, status='ongoing').count() if tenant else 0,
    }
    return render(request, 'hr/dashboard.html', context)


class EmployeeListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Employee
    template_name = 'hr/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Employee.objects.filter(tenant=tenant).select_related('department', 'position')
        return Employee.objects.none()


class EmployeeDetailView(ManagerRequiredMixin, LoginRequiredMixin, DetailView):
    model = Employee
    template_name = 'hr/employee_detail.html'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['leave_requests'] = self.object.leave_requests.all()[:5]
        context['performance_reviews'] = self.object.performance_reviews.all()[:5]
        context['advances'] = self.object.advances.all()[:5]
        return context


class EmployeeCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = reverse_lazy('hr:employee_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Employee created successfully!')
        return super().form_valid(form)


class EmployeeUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = reverse_lazy('hr:employee_list')

    def form_valid(self, form):
        messages.success(self.request, 'Employee updated successfully!')
        return super().form_valid(form)


class DepartmentListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Department
    template_name = 'hr/department_list.html'
    context_object_name = 'departments'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Department.objects.filter(tenant=tenant)
        return Department.objects.none()


class DepartmentCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'hr/department_form.html'
    success_url = reverse_lazy('hr:department_list')

    def form_valid(self, form):
        manager_name = form.cleaned_data.get('manager_name')
        manager = find_employee_by_name(self.request.user.tenant, manager_name)
        if manager_name and manager is None:
            form.add_error('manager_name', f'No employee named "{manager_name}" found. Check the spelling, or add them as an employee first.')
            return self.form_invalid(form)
        form.instance.tenant = self.request.user.tenant
        form.instance.manager = manager
        messages.success(self.request, 'Department created successfully!')
        return super().form_valid(form)


class DepartmentUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'hr/department_form.html'
    success_url = reverse_lazy('hr:department_list')

    def form_valid(self, form):
        manager_name = form.cleaned_data.get('manager_name')
        manager = find_employee_by_name(self.request.user.tenant, manager_name)
        if manager_name and manager is None:
            form.add_error('manager_name', f'No employee named "{manager_name}" found. Check the spelling, or add them as an employee first.')
            return self.form_invalid(form)
        form.instance.manager = manager
        messages.success(self.request, 'Department updated successfully!')
        return super().form_valid(form)


class LeaveRequestCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    """Manager/Owner view for creating leave requests on behalf of employees."""
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'hr/leave_request_form.html'
    success_url = reverse_lazy('hr:leave_request_list')

    def form_valid(self, form):
        # Managers can only create requests via the admin panel or this form should show employee selector
        # For now, redirect to the staff portal or require employee selection
        messages.info(self.request, 'Note: Employees should submit their own leave requests via the Staff Portal.')
        return super().form_valid(form)


class LeaveRequestListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = LeaveRequest
    template_name = 'hr/leave_request_list.html'
    context_object_name = 'requests'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return LeaveRequest.objects.filter(tenant=tenant).order_by('-created_at')
        return LeaveRequest.objects.none()


class EmployeeLeaveRequestCreateView(LeaveSelfServiceMixin, LoginRequiredMixin, CreateView):
    """Self-service leave request for staff/employees only (not for OWNER/MANAGER)."""
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'hr/employee_leave_request_form.html'
    success_url = reverse_lazy('hr:employee_leave_requests')

    def form_valid(self, form):
        employee = getattr(self.request.user, 'employee_profile', None)
        if employee is None:
            form.add_error(None, "Your account has no employee profile set up, so a leave request can't be filed under your name. Ask the Owner to add one for you.")
            return self.form_invalid(form)
        leave_type_name = form.cleaned_data['leave_type_name'].strip()
        leave_type, _ = LeaveType.objects.get_or_create(
            tenant=self.request.user.tenant, name__iexact=leave_type_name,
            defaults={'name': leave_type_name, 'days_per_year': 0},
        )
        form.instance.tenant = self.request.user.tenant
        form.instance.employee = employee
        form.instance.leave_type = leave_type
        messages.success(self.request, 'Leave request submitted successfully!')
        return super().form_valid(form)


class EmployeeLeaveRequestListView(LeaveSelfServiceMixin, LoginRequiredMixin, ListView):
    """Self-service view for staff to see their own leave requests."""
    model = LeaveRequest
    template_name = 'hr/employee_leave_request_list.html'
    context_object_name = 'requests'
    paginate_by = 10

    def get_queryset(self):
        employee = getattr(self.request.user, 'employee_profile', None)
        if employee:
            return employee.leave_requests.all().order_by('-created_at')
        return LeaveRequest.objects.none()


class EmployeeAttendanceCreateView(StaffOnlyMixin, LoginRequiredMixin, CreateView):
    """Self-service attendance logging for staff (e.g., for manual entry of past days)."""
    model = Attendance
    form_class = AttendanceForm
    template_name = 'hr/employee_attendance_form.html'
    success_url = reverse_lazy('hr:employee_attendance_list')

    def form_valid(self, form):
        employee = getattr(self.request.user, 'employee_profile', None)
        if employee is None:
            form.add_error(None, "Your account has no employee profile set up yet. Ask the Owner to add one for you.")
            return self.form_invalid(form)
        date = form.cleaned_data.get('date')
        if date and Attendance.objects.filter(employee=employee, date=date).exists():
            form.add_error('date', f'You already have an attendance record for {date}.')
            return self.form_invalid(form)
        form.instance.tenant = employee.tenant
        form.instance.employee = employee
        messages.success(self.request, 'Attendance record submitted successfully!')
        return super().form_valid(form)


class EmployeeAttendanceListView(StaffOnlyMixin, LoginRequiredMixin, ListView):
    """Self-service view for staff to see their own attendance records."""
    model = Attendance
    template_name = 'hr/employee_attendance_list.html'
    context_object_name = 'attendance_records'
    paginate_by = 20

    def get_queryset(self):
        employee = getattr(self.request.user, 'employee_profile', None)
        if employee:
            return employee.attendance_records.all().order_by('-date')
        return Attendance.objects.none()


@role_required('OWNER', 'MANAGER')
def approve_leave_request(request, pk):
    """Approve a leave request. A Manager can't approve their own — only
    the Owner can, since Managers report to the Owner."""
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if leave_request.employee.user_id == request.user.id:
        messages.error(request, "You can't approve your own leave request. Ask the Owner to review it.")
        return redirect('hr:leave_request_list')
    if request.method == 'POST':
        leave_request.status = 'approved'
        leave_request.approved_by = request.user
        leave_request.approval_date = timezone.now()
        leave_request.save()
        messages.success(request, 'Leave request approved!')
        return redirect('hr:leave_request_list')
    return render(request, 'hr/approve_leave.html', {'leave_request': leave_request})


@role_required('OWNER', 'MANAGER')
def reject_leave_request(request, pk):
    """Reject a leave request. Same self-approval restriction applies —
    a Manager can't reject (or approve) their own request either."""
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if leave_request.employee.user_id == request.user.id:
        messages.error(request, "You can't act on your own leave request. Ask the Owner to review it.")
        return redirect('hr:leave_request_list')
    if request.method == 'POST':
        leave_request.status = 'rejected'
        leave_request.rejection_reason = request.POST.get('rejection_reason', '')
        leave_request.save()
        messages.success(request, 'Leave request rejected!')
        return redirect('hr:leave_request_list')
    return render(request, 'hr/reject_leave.html', {'leave_request': leave_request})


class AttendanceListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Attendance
    template_name = 'hr/attendance_list.html'
    context_object_name = 'attendance_records'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Attendance.objects.filter(tenant=tenant).order_by('-date')
        return Attendance.objects.none()


class AttendanceCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Attendance
    form_class = AttendanceForm
    template_name = 'hr/attendance_form.html'
    success_url = reverse_lazy('hr:attendance_list')

    def form_valid(self, form):
        employee_name = form.cleaned_data['employee_name'].strip()
        if not employee_name:
            form.add_error('employee_name', 'This field is required.')
            return self.form_invalid(form)
        employee = find_employee_by_name(self.request.user.tenant, employee_name)
        if employee is None:
            form.add_error('employee_name', f'No employee named "{employee_name}" found. Check the spelling, or add them as an employee first.')
            return self.form_invalid(form)
        date = form.cleaned_data.get('date')
        if date and Attendance.objects.filter(employee=employee, date=date).exists():
            form.add_error('date', f'{employee} already has an attendance record for {date}. Edit that one instead of adding a duplicate.')
            return self.form_invalid(form)
        form.instance.tenant = self.request.user.tenant
        form.instance.employee = employee
        messages.success(self.request, 'Attendance record created successfully!')
        return super().form_valid(form)


class EmployeeAdvanceListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = EmployeeAdvance
    template_name = 'hr/advance_list.html'
    context_object_name = 'advances'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return EmployeeAdvance.objects.filter(tenant=tenant).order_by('-created_at')
        return EmployeeAdvance.objects.none()


class EmployeeAdvanceCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = EmployeeAdvance
    form_class = EmployeeAdvanceForm
    template_name = 'hr/advance_form.html'
    success_url = reverse_lazy('hr:advance_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.employee = self.request.user.employee_profile
        messages.success(self.request, 'Advance request submitted successfully!')
        return super().form_valid(form)


@role_required('OWNER', 'MANAGER')
def approve_advance(request, pk):
    """Approve an employee advance"""
    advance = get_object_or_404(EmployeeAdvance, pk=pk)
    if request.method == 'POST':
        advance.status = 'approved'
        advance.approved_by = request.user
        advance.approval_date = timezone.now()
        advance.save()
        messages.success(request, 'Advance approved!')
        return redirect('hr:advance_list')
    return render(request, 'hr/approve_advance.html', {'advance': advance})


class RecruitmentListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Recruitment
    template_name = 'hr/recruitment_list.html'
    context_object_name = 'openings'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Recruitment.objects.filter(tenant=tenant).order_by('-posted_date')
        return Recruitment.objects.none()


class RecruitmentCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Recruitment
    form_class = RecruitmentForm
    template_name = 'hr/recruitment_form.html'
    success_url = reverse_lazy('hr:recruitment_list')

    def form_valid(self, form):
        position_name = form.cleaned_data['position_name'].strip()
        department = Department.objects.filter(tenant=self.request.user.tenant).first()
        if department is None:
            form.add_error('position_name', 'Add at least one department first (HR → Departments) before opening a position.')
            return self.form_invalid(form)
        position, _ = Position.objects.get_or_create(
            tenant=self.request.user.tenant, name__iexact=position_name,
            defaults={'name': position_name, 'department': department},
        )
        form.instance.tenant = self.request.user.tenant
        form.instance.position = position
        messages.success(self.request, 'Job opening created successfully!')
        return super().form_valid(form)


class JobApplicationListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = JobApplication
    template_name = 'hr/job_application_list.html'
    context_object_name = 'applications'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return JobApplication.objects.filter(tenant=tenant).order_by('-applied_date')
        return JobApplication.objects.none()


class JobApplicationDetailView(ManagerRequiredMixin, LoginRequiredMixin, DetailView):
    model = JobApplication
    template_name = 'hr/job_application_detail.html'
    context_object_name = 'application'


@login_required
def clock_in_out(request):
    """Self-service clock in/out for the logged-in user's own Employee
    record. Anyone can use this for themselves — it never touches
    anyone else's attendance."""
    from django.utils import timezone

    employee = getattr(request.user, 'employee_profile', None)
    if employee is None:
        messages.error(
            request,
            'Your account has no employee profile set up yet. Ask the Owner to add one for you.',
        )
        return redirect('dashboard_overview')

    today = timezone.localdate()
    now = timezone.localtime().time()
    record, _ = Attendance.objects.get_or_create(
        employee=employee, date=today,
        defaults={'tenant': employee.tenant, 'status': 'present'},
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'clock_in' and not record.check_in_time:
            record.check_in_time = now
            record.status = 'present'
            record.save(update_fields=['check_in_time', 'status'])
            messages.success(request, f'Clocked in at {now.strftime("%H:%M")}.')
        elif action == 'clock_out' and record.check_in_time and not record.check_out_time:
            record.check_out_time = now
            record.save(update_fields=['check_out_time'])
            messages.success(request, f'Clocked out at {now.strftime("%H:%M")}.')
        return redirect('hr:clock_in_out')

    # Last 7 days for this employee, so they can see their own recent record
    recent = Attendance.objects.filter(employee=employee).order_by('-date')[:7]

    context = {
        'record': record,
        'recent': recent,
    }
    return render(request, 'hr/clock_in_out.html', context)
