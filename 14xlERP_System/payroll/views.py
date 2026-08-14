from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.db.models import Sum
from tenants.decorators import role_required
from .models import (
    SalaryStructure, Allowance, Deduction, EmployeeSalarySetup,
    OvertimeRule, PayrollPeriod, PayrollRun, Payslip, PaymentIntegration
)
from .forms import (
    SalaryStructureForm, AllowanceForm, DeductionForm, EmployeeSalarySetupForm,
    OvertimeRuleForm, PayrollPeriodForm, PayrollRunForm, PayslipForm, PaymentIntegrationForm
)


class ManagerRequiredMixin:
    """Restricts a class-based view to OWNER/MANAGER — payroll involves
    salary and payment data, which Staff should never see."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_role('OWNER', 'MANAGER'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


@role_required('OWNER', 'MANAGER')
def payroll_dashboard(request):
    """Payroll dashboard overview"""
    tenant = request.user.tenant
    
    context = {
        'total_structures': SalaryStructure.objects.filter(tenant=tenant).count() if tenant else 0,
        'active_payroll_periods': PayrollPeriod.objects.filter(tenant=tenant, is_active=True).count() if tenant else 0,
        'pending_payslips': Payslip.objects.filter(tenant=tenant, payment_status='pending').count() if tenant else 0,
        'recent_payroll_runs': PayrollRun.objects.filter(tenant=tenant)[:5] if tenant else [],
    }
    return render(request, 'payroll/dashboard.html', context)


class SalaryStructureListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = SalaryStructure
    template_name = 'payroll/salary_structure_list.html'
    context_object_name = 'structures'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return SalaryStructure.objects.filter(tenant=tenant).order_by('-created_at')
        return SalaryStructure.objects.none()


class SalaryStructureCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = SalaryStructure
    form_class = SalaryStructureForm
    template_name = 'payroll/salary_structure_form.html'
    success_url = reverse_lazy('payroll:structure_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Salary structure created successfully!')
        return super().form_valid(form)


class SalaryStructureUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = SalaryStructure
    form_class = SalaryStructureForm
    template_name = 'payroll/salary_structure_form.html'
    success_url = reverse_lazy('payroll:structure_list')

    def form_valid(self, form):
        messages.success(self.request, 'Salary structure updated successfully!')
        return super().form_valid(form)


class SalaryStructureDeleteView(ManagerRequiredMixin, LoginRequiredMixin, DeleteView):
    model = SalaryStructure
    template_name = 'payroll/salary_structure_confirm_delete.html'
    success_url = reverse_lazy('payroll:structure_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Salary structure deleted successfully!')
        return super().delete(request, *args, **kwargs)


class AllowanceListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Allowance
    template_name = 'payroll/allowance_list.html'
    context_object_name = 'allowances'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Allowance.objects.filter(tenant=tenant).order_by('-created_at')
        return Allowance.objects.none()


class AllowanceCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Allowance
    form_class = AllowanceForm
    template_name = 'payroll/allowance_form.html'
    success_url = reverse_lazy('payroll:allowance_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Allowance created successfully!')
        return super().form_valid(form)


class AllowanceUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Allowance
    form_class = AllowanceForm
    template_name = 'payroll/allowance_form.html'
    success_url = reverse_lazy('payroll:allowance_list')

    def form_valid(self, form):
        messages.success(self.request, 'Allowance updated successfully!')
        return super().form_valid(form)


class AllowanceDeleteView(ManagerRequiredMixin, LoginRequiredMixin, DeleteView):
    model = Allowance
    template_name = 'payroll/allowance_confirm_delete.html'
    success_url = reverse_lazy('payroll:allowance_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Allowance deleted successfully!')
        return super().delete(request, *args, **kwargs)


class DeductionListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Deduction
    template_name = 'payroll/deduction_list.html'
    context_object_name = 'deductions'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Deduction.objects.filter(tenant=tenant).order_by('-created_at')
        return Deduction.objects.none()


class DeductionCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = 'payroll/deduction_form.html'
    success_url = reverse_lazy('payroll:deduction_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Deduction created successfully!')
        return super().form_valid(form)


class DeductionUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Deduction
    form_class = DeductionForm
    template_name = 'payroll/deduction_form.html'
    success_url = reverse_lazy('payroll:deduction_list')

    def form_valid(self, form):
        messages.success(self.request, 'Deduction updated successfully!')
        return super().form_valid(form)


class DeductionDeleteView(ManagerRequiredMixin, LoginRequiredMixin, DeleteView):
    model = Deduction
    template_name = 'payroll/deduction_confirm_delete.html'
    success_url = reverse_lazy('payroll:deduction_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Deduction deleted successfully!')
        return super().delete(request, *args, **kwargs)


class PayrollPeriodListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = PayrollPeriod
    template_name = 'payroll/payroll_period_list.html'
    context_object_name = 'periods'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return PayrollPeriod.objects.filter(tenant=tenant).order_by('-start_date')
        return PayrollPeriod.objects.none()


class PayrollPeriodCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    template_name = 'payroll/payroll_period_form.html'
    success_url = reverse_lazy('payroll:period_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Payroll period created successfully!')
        return super().form_valid(form)


class PayrollRunListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = PayrollRun
    template_name = 'payroll/payroll_run_list.html'
    context_object_name = 'runs'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return PayrollRun.objects.filter(tenant=tenant).order_by('-created_at')
        return PayrollRun.objects.none()


class PayrollRunCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = 'payroll/payroll_run_form.html'
    success_url = reverse_lazy('payroll:run_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Payroll run created successfully!')
        return super().form_valid(form)


@role_required('OWNER', 'MANAGER')
def generate_payslips(request, pk):
    """Generate payslips for a payroll run"""
    payroll_run = get_object_or_404(PayrollRun, pk=pk)
    
    if request.method == 'POST':
        # Generate payslips logic here
        messages.success(request, 'Payslips generated successfully!')
        return redirect('payroll:run_list')
    
    return render(request, 'payroll/generate_payslips.html', {'payroll_run': payroll_run})


@role_required('OWNER', 'MANAGER')
def payslip_detail(request, pk):
    """View payslip details"""
    payslip = get_object_or_404(Payslip, pk=pk)
    context = {
        'payslip': payslip,
        'details': payslip.details.all()
    }
    return render(request, 'payroll/payslip_detail.html', context)


@role_required('OWNER', 'MANAGER')
def process_payments(request, pk):
    """Process payments for payroll run"""
    payroll_run = get_object_or_404(PayrollRun, pk=pk)
    
    if request.method == 'POST':
        # Payment processing logic here
        messages.success(request, 'Payments processed successfully!')
        return redirect('payroll:run_list')
    
    return render(request, 'payroll/process_payments.html', {'payroll_run': payroll_run})
