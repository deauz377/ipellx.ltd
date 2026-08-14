from django.urls import path
from . import views

app_name = 'payroll'

urlpatterns = [
    # Dashboard
    path('', views.payroll_dashboard, name='dashboard'),
    
    # Salary Structure
    path('structures/', views.SalaryStructureListView.as_view(), name='structure_list'),
    path('structures/create/', views.SalaryStructureCreateView.as_view(), name='structure_create'),
    path('structures/<int:pk>/edit/', views.SalaryStructureUpdateView.as_view(), name='structure_update'),
    path('structures/<int:pk>/delete/', views.SalaryStructureDeleteView.as_view(), name='structure_delete'),
    
    # Allowances
    path('allowances/', views.AllowanceListView.as_view(), name='allowance_list'),
    path('allowances/create/', views.AllowanceCreateView.as_view(), name='allowance_create'),
    path('allowances/<int:pk>/edit/', views.AllowanceUpdateView.as_view(), name='allowance_update'),
    path('allowances/<int:pk>/delete/', views.AllowanceDeleteView.as_view(), name='allowance_delete'),
    
    # Deductions
    path('deductions/', views.DeductionListView.as_view(), name='deduction_list'),
    path('deductions/create/', views.DeductionCreateView.as_view(), name='deduction_create'),
    path('deductions/<int:pk>/edit/', views.DeductionUpdateView.as_view(), name='deduction_update'),
    path('deductions/<int:pk>/delete/', views.DeductionDeleteView.as_view(), name='deduction_delete'),
    
    # Payroll Periods
    path('periods/', views.PayrollPeriodListView.as_view(), name='period_list'),
    path('periods/create/', views.PayrollPeriodCreateView.as_view(), name='period_create'),
    
    # Payroll Runs
    path('runs/', views.PayrollRunListView.as_view(), name='run_list'),
    path('runs/create/', views.PayrollRunCreateView.as_view(), name='run_create'),
    path('runs/<int:pk>/payslips/', views.generate_payslips, name='generate_payslips'),
    path('runs/<int:pk>/process-payments/', views.process_payments, name='process_payments'),
    
    # Payslips
    path('payslips/<int:pk>/', views.payslip_detail, name='payslip_detail'),
]
