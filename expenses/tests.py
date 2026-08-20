from django.urls import reverse

from tenants.tests import TwoTenantTestCase

from .models import Expense


class ExpenseTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #32, #40."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.expense_a = Expense.objects.create(
            category='utilities', description='Tenant A electricity', amount=1000,
            date='2026-01-01', tenant=cls.tenant_a,
        )
        cls.expense_b = Expense.objects.create(
            category='utilities', description='Tenant B electricity', amount=2000,
            date='2026-01-01', tenant=cls.tenant_b,
        )

    def test_user_a_expense_list_excludes_user_b_expenses(self):
        self.login_a()
        response = self.client.get(reverse('expenses:expense_list'))
        self.assertContains(response, 'Tenant A electricity')
        self.assertNotContains(response, 'Tenant B electricity')

    def test_user_a_cannot_edit_user_b_expense_by_id(self):
        self.login_a()
        response = self.client.get(reverse('expenses:expense_edit', kwargs={'pk': self.expense_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_a_cannot_delete_user_b_expense_via_url_manipulation(self):
        self.login_a()
        response = self.client.post(reverse('expenses:expense_delete', kwargs={'pk': self.expense_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=self.expense_b.pk).exists())
