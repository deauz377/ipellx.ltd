from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Department, Employee, Position


class DepartmentTestCase(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='IT'
        )

    def test_department_creation(self):
        self.assertTrue(isinstance(self.dept, Department))
        self.assertEqual(self.dept.name, 'IT')


class PositionTestCase(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT')
        self.position = Position.objects.create(
            name='Software Developer',
            department=self.dept
        )

    def test_position_creation(self):
        self.assertTrue(isinstance(self.position, Position))
        self.assertEqual(self.position.name, 'Software Developer')


class HRDashboardTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='hr-user', password='secret123', role=User.Role.OWNER)
        self.client.force_login(self.user)

    def test_dashboard_renders_without_reverse_errors(self):
        response = self.client.get(reverse('hr:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HR Management Dashboard')


from tenants.models import User as TenantUser
from tenants.tests import TwoTenantTestCase


class HRTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #26, #34, #39 -- HR holds the most sensitive per-employee
    data in the system (national ID, salary setup), so cross-tenant access
    here matters more than most modules."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        staff_user_a = TenantUser.objects.create_user(
            username='staff_a_hr', password='TestPass123!', tenant=cls.tenant_a,
            role=TenantUser.Role.STAFF, email_verified=True,
        )
        staff_user_b = TenantUser.objects.create_user(
            username='staff_b_hr', password='TestPass123!', tenant=cls.tenant_b,
            role=TenantUser.Role.STAFF, email_verified=True,
        )
        cls.employee_a = Employee.objects.create(
            user=staff_user_a, employee_id='EMP-A-001', national_id='11111111', tenant=cls.tenant_a,
        )
        cls.employee_b = Employee.objects.create(
            user=staff_user_b, employee_id='EMP-B-001', national_id='22222222', tenant=cls.tenant_b,
        )

    def test_user_a_cannot_view_user_b_employee_by_id(self):
        self.login_a()
        response = self.client.get(reverse('hr:employee_detail', kwargs={'pk': self.employee_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_a_employee_list_excludes_user_b_employees(self):
        # The list template doesn't render employee_id, just a per-row link
        # to the detail page -- assert on that instead of a string that
        # would never appear either way.
        self.login_a()
        response = self.client.get(reverse('hr:employee_list'))
        self.assertContains(response, reverse('hr:employee_detail', kwargs={'pk': self.employee_a.pk}))
        self.assertNotContains(response, reverse('hr:employee_detail', kwargs={'pk': self.employee_b.pk}))

    def test_employee_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.employee_b.pk, 999999):
            response = self.client.get(reverse('hr:employee_detail', kwargs={'pk': pk}))
            self.assertEqual(response.status_code, 404)
