from django.test import TestCase
from django.contrib.auth.models import User
from .models import SalaryStructure, Allowance, Deduction, EmployeeSalarySetup


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
