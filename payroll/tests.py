from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from hr.models import Employee
from tenants.models import User as TenantUser
from tenants.tests import TwoTenantTestCase

from .models import (
    SalaryStructure, Allowance, Deduction, EmployeeSalarySetup,
    PayrollPeriod, PayrollRun, Payslip,
)


class SalaryStructureTestCase(TestCase):
    def setUp(self):
        self.structure = SalaryStructure.objects.create(
            name='Standard',
            basic_salary=50000.00
        )

    def test_salary_structure_creation(self):
        self.assertTrue(isinstance(self.structure, SalaryStructure))
        self.assertEqual(self.structure.name, 'Standard')


class AllowanceTestCase(TestCase):
    def setUp(self):
        self.allowance = Allowance.objects.create(
            name='House Allowance',
            allowance_type='fixed',
            value=5000.00
        )

    def test_allowance_creation(self):
        self.assertTrue(isinstance(self.allowance, Allowance))
        self.assertEqual(self.allowance.allowance_type, 'fixed')


class DeductionTestCase(TestCase):
    def setUp(self):
        self.deduction = Deduction.objects.create(
            name='Tax',
            deduction_type='percentage',
            value=10.00
        )

    def test_deduction_creation(self):
        self.assertTrue(isinstance(self.deduction, Deduction))
        self.assertEqual(self.deduction.deduction_type, 'percentage')


class PayrollTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #34 -- payslips carry net salary, the single most sensitive
    number in the system per employee."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        staff_user_a = TenantUser.objects.create_user(
            username='staff_a_payroll', password='TestPass123!', tenant=cls.tenant_a,
            role=TenantUser.Role.STAFF, email_verified=True,
        )
        staff_user_b = TenantUser.objects.create_user(
            username='staff_b_payroll', password='TestPass123!', tenant=cls.tenant_b,
            role=TenantUser.Role.STAFF, email_verified=True,
        )
        employee_a = Employee.objects.create(user=staff_user_a, employee_id='EMP-A-PR', tenant=cls.tenant_a)
        employee_b = Employee.objects.create(user=staff_user_b, employee_id='EMP-B-PR', tenant=cls.tenant_b)

        period_a = PayrollPeriod.objects.create(
            name='Jan 2026 A', period_type='monthly',
            start_date='2026-01-01', end_date='2026-01-31', payment_date='2026-02-01',
            tenant=cls.tenant_a,
        )
        period_b = PayrollPeriod.objects.create(
            name='Jan 2026 B', period_type='monthly',
            start_date='2026-01-01', end_date='2026-01-31', payment_date='2026-02-01',
            tenant=cls.tenant_b,
        )
        run_a = PayrollRun.objects.create(payroll_period=period_a, tenant=cls.tenant_a)
        run_b = PayrollRun.objects.create(payroll_period=period_b, tenant=cls.tenant_b)

        cls.payslip_a = Payslip.objects.create(
            payroll_run=run_a, employee=employee_a, basic_salary=50000,
            gross_salary=50000, total_deductions=5000, net_salary=45000, tenant=cls.tenant_a,
        )
        cls.payslip_b = Payslip.objects.create(
            payroll_run=run_b, employee=employee_b, basic_salary=90000,
            gross_salary=90000, total_deductions=9000, net_salary=81000, tenant=cls.tenant_b,
        )

    def test_user_a_cannot_view_user_b_payslip_by_id(self):
        self.login_a()
        response = self.client.get(reverse('payroll:payslip_detail', kwargs={'pk': self.payslip_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_payslip_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.payslip_b.pk, 999999):
            response = self.client.get(reverse('payroll:payslip_detail', kwargs={'pk': pk}))
            self.assertEqual(response.status_code, 404)
