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
        self.user = User.objects.create_user(username='hr-user', password='secret123')
        self.client.force_login(self.user)

    def test_dashboard_renders_without_reverse_errors(self):
        response = self.client.get(reverse('hr:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HR Management Dashboard')
