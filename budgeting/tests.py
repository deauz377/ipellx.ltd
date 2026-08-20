from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from expenses.models import Expense
from inventory.models import Supplier
from sales.models import Order
from tenants.models import User
from tenants.tests import TwoTenantTestCase, create_tenant_and_owner

from .models import Budget


def make_budget(tenant, user, **overrides):
    defaults = {
        'tenant': tenant, 'created_by': user, 'name': 'Test Budget', 'period': 'monthly',
        'category': 'rent', 'amount': Decimal('10000'),
        'start_date': date(2026, 8, 1), 'end_date': date(2026, 8, 31),
    }
    defaults.update(overrides)
    return Budget.objects.create(**defaults)


class BudgetWorkflowTests(TwoTenantTestCase):
    """Part 15's exact end-to-end workflow: Create Budget -> Record Expense
    -> Expense Automatically Updates Budget -> Alerts Trigger -> Reports
    Show Correct Figures. No manual "sync" step exists anywhere in this
    flow by design -- spent_amount is computed live."""

    def test_expense_automatically_updates_matching_budget(self):
        budget = make_budget(self.tenant_a, self.user_a, category='rent', amount=Decimal('10000'))
        self.assertEqual(budget.spent_amount, Decimal('0'))
        self.assertEqual(budget.usage_percent, Decimal('0'))
        self.assertIsNone(budget.alert_level)

        Expense.objects.create(tenant=self.tenant_a, category='rent', amount=Decimal('6500'), date=date(2026, 8, 5))

        self.assertEqual(budget.spent_amount, Decimal('6500'))
        self.assertEqual(budget.usage_percent, Decimal('65.00'))
        self.assertEqual(budget.alert_level, 50)
        self.assertFalse(budget.is_over_budget)

    def test_supplier_order_updates_stock_purchases_budget(self):
        budget = make_budget(self.tenant_a, self.user_a, category='stock_purchases', amount=Decimal('50000'))
        supplier = Supplier.objects.create(tenant=self.tenant_a, name='Test Supplier')

        Order.objects.create(
            tenant=self.tenant_a, order_type='supplier', supplier=supplier,
            status='confirmed', total=Decimal('5000'), date=date(2026, 8, 5),
        )
        self.assertEqual(budget.spent_amount, Decimal('5000'))

        # Cancelled purchase orders are not real spending.
        Order.objects.create(
            tenant=self.tenant_a, order_type='supplier', supplier=supplier,
            status='cancelled', total=Decimal('9000'), date=date(2026, 8, 6),
        )
        self.assertEqual(budget.spent_amount, Decimal('5000'))

    def test_expense_outside_budget_date_range_does_not_count(self):
        budget = make_budget(self.tenant_a, self.user_a, category='rent', start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
        Expense.objects.create(tenant=self.tenant_a, category='rent', amount=Decimal('1000'), date=date(2026, 9, 1))
        self.assertEqual(budget.spent_amount, Decimal('0'))

    def test_expense_in_different_category_does_not_count(self):
        budget = make_budget(self.tenant_a, self.user_a, category='rent')
        Expense.objects.create(tenant=self.tenant_a, category='transport', amount=Decimal('1000'), date=date(2026, 8, 5))
        self.assertEqual(budget.spent_amount, Decimal('0'))

    def test_alert_thresholds_fire_at_correct_levels(self):
        budget = make_budget(self.tenant_a, self.user_a, category='rent', amount=Decimal('1000'))
        cases = [
            (Decimal('400'), None), (Decimal('100'), 50), (Decimal('250'), 75),
            (Decimal('150'), 90), (Decimal('100'), 100), (Decimal('50'), 'over'),
        ]
        running_total = Decimal('0')
        for add, expected_level in cases:
            Expense.objects.create(tenant=self.tenant_a, category='rent', amount=add, date=date(2026, 8, 5))
            running_total += add
            self.assertEqual(budget.spent_amount, running_total)
            self.assertEqual(budget.alert_level, expected_level)

    def test_empty_budget_amount_is_safe(self):
        """A budget with zero expenses recorded must render 0%, not
        divide-by-zero -- Budget.amount itself is always > 0 (form-enforced),
        but a fresh budget with no matching spend yet must be safe too."""
        budget = make_budget(self.tenant_a, self.user_a, category='marketing', amount=Decimal('5000'))
        self.assertEqual(budget.spent_amount, Decimal('0'))
        self.assertEqual(budget.usage_percent, Decimal('0'))
        self.assertEqual(budget.remaining_amount, Decimal('5000'))
        self.assertFalse(budget.is_over_budget)

    def test_report_totals_match_underlying_expenses(self):
        make_budget(self.tenant_a, self.user_a, category='rent', amount=Decimal('10000'))
        Expense.objects.create(tenant=self.tenant_a, category='rent', amount=Decimal('4000'), date=date(2026, 8, 5))
        Expense.objects.create(tenant=self.tenant_a, category='transport', amount=Decimal('1500'), date=date(2026, 8, 6))

        self.login_a()
        response = self.client.get(reverse('budgeting:budget_report_csv'), {
            'range': 'custom', 'start': '2026-08-01', 'end': '2026-08-31',
        })
        content = response.content.decode()
        self.assertIn('4000', content)
        self.assertIn('1500', content)


class BudgetPeriodTests(TwoTenantTestCase):
    """Daily, weekly, and monthly budgets are independent -- a budget of
    one period type must not appear in another period's dashboard totals."""

    def test_daily_weekly_monthly_are_independent(self):
        today = date(2026, 8, 15)  # a Saturday
        make_budget(self.tenant_a, self.user_a, period='daily', category='rent', start_date=today, end_date=today, name='Daily')
        make_budget(self.tenant_a, self.user_a, period='weekly', category='transport', start_date=date(2026, 8, 10), end_date=date(2026, 8, 16), name='Weekly')
        make_budget(self.tenant_a, self.user_a, period='monthly', category='marketing', start_date=date(2026, 8, 1), end_date=date(2026, 8, 31), name='Monthly')

        self.assertEqual(Budget.objects.filter(tenant=self.tenant_a, period='daily').count(), 1)
        self.assertEqual(Budget.objects.filter(tenant=self.tenant_a, period='weekly').count(), 1)
        self.assertEqual(Budget.objects.filter(tenant=self.tenant_a, period='monthly').count(), 1)

    def test_dashboard_renders_for_all_three_periods_with_no_data(self):
        self.login_a()
        for period in ('daily', 'weekly', 'monthly'):
            response = self.client.get(reverse('budgeting:dashboard'), {'period': period})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Traceback')


class BudgetTenantIsolationTests(TwoTenantTestCase):
    """Cross-tenant isolation: Tenant B's expenses/budgets must never
    affect Tenant A's figures, and Tenant A must never be able to view or
    manipulate Tenant B's budgets by ID."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.budget_a = make_budget(cls.tenant_a, cls.user_a, category='rent', amount=Decimal('10000'), name='Budget A')
        cls.budget_b = make_budget(cls.tenant_b, cls.user_b, category='rent', amount=Decimal('20000'), name='Budget B')

    def test_tenant_b_expense_does_not_affect_tenant_a_budget(self):
        Expense.objects.create(tenant=self.tenant_b, category='rent', amount=Decimal('999999'), date=date(2026, 8, 5))
        self.assertEqual(self.budget_a.spent_amount, Decimal('0'))

    def test_user_a_cannot_view_user_b_budget_by_id(self):
        self.login_a()
        response = self.client.get(reverse('budgeting:budget_detail', kwargs={'pk': self.budget_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_a_budget_list_excludes_user_b_budgets(self):
        self.login_a()
        response = self.client.get(reverse('budgeting:budget_list'))
        self.assertContains(response, 'Budget A')
        self.assertNotContains(response, 'Budget B')

    def test_budget_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.budget_b.pk, 999999):
            for url_name in ('budget_detail', 'budget_edit', 'budget_delete'):
                response = self.client.get(reverse(f'budgeting:{url_name}', kwargs={'pk': pk}))
                self.assertEqual(response.status_code, 404)

    def test_user_a_cannot_delete_user_b_budget_via_post(self):
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_delete', kwargs={'pk': self.budget_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Budget.objects.filter(pk=self.budget_b.pk).exists())

    def test_created_budget_is_scoped_to_creators_tenant_not_a_posted_value(self):
        """The tenant is set server-side from request.user.tenant, never
        trusted from POST data -- there is no tenant field in BudgetForm at
        all, so there's nothing to spoof, but confirm the outcome directly."""
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_create'), {
            'name': 'Spoofed Budget', 'period': 'monthly', 'category': 'rent',
            'amount': '1000', 'start_date': '2026-08-01', 'end_date': '2026-08-31',
        })
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(name='Spoofed Budget')
        self.assertEqual(budget.tenant, self.tenant_a)


class BudgetPermissionTests(TwoTenantTestCase):
    """Part 11: only OWNER/MANAGER can create/edit/delete; view access is
    restricted to OWNER/MANAGER/ACCOUNTANT (budgets can reveal planned
    spending and salary figures not every role should see)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.budget = make_budget(cls.tenant_a, cls.user_a)
        cls.accountant = User.objects.create_user(
            username='accountant_a', password='TestPass123!', tenant=cls.tenant_a,
            role=User.Role.ACCOUNTANT, email_verified=True,
        )
        cls.staff = User.objects.create_user(
            username='staff_a', password='TestPass123!', tenant=cls.tenant_a,
            role=User.Role.STAFF, email_verified=True,
        )

    def test_accountant_can_view_but_not_create(self):
        self.client.login(username='accountant_a', password='TestPass123!')
        self.assertEqual(self.client.get(reverse('budgeting:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('budgeting:budget_detail', kwargs={'pk': self.budget.pk})).status_code, 200)
        self.assertEqual(self.client.get(reverse('budgeting:budget_create')).status_code, 403)

    def test_staff_cannot_view_or_create(self):
        self.client.login(username='staff_a', password='TestPass123!')
        self.assertEqual(self.client.get(reverse('budgeting:dashboard')).status_code, 403)
        self.assertEqual(self.client.get(reverse('budgeting:budget_create')).status_code, 403)

    def test_owner_can_create_edit_delete(self):
        self.login_a()
        self.assertEqual(self.client.get(reverse('budgeting:budget_create')).status_code, 200)
        self.assertEqual(self.client.get(reverse('budgeting:budget_edit', kwargs={'pk': self.budget.pk})).status_code, 200)
        response = self.client.post(reverse('budgeting:budget_delete', kwargs={'pk': self.budget.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Budget.objects.filter(pk=self.budget.pk).exists())

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse('budgeting:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response.url)


class BudgetFormValidationTests(TwoTenantTestCase):
    def test_end_date_before_start_date_rejected(self):
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_create'), {
            'name': 'Bad Dates', 'period': 'monthly', 'category': 'rent',
            'amount': '1000', 'start_date': '2026-08-31', 'end_date': '2026-08-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Budget.objects.filter(name='Bad Dates').exists())

    def test_zero_amount_rejected(self):
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_create'), {
            'name': 'Zero Amount', 'period': 'monthly', 'category': 'rent',
            'amount': '0', 'start_date': '2026-08-01', 'end_date': '2026-08-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Budget.objects.filter(name='Zero Amount').exists())

    def test_other_category_without_custom_label_rejected(self):
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_create'), {
            'name': 'Unlabeled Other', 'period': 'monthly', 'category': 'other', 'custom_category': '',
            'amount': '1000', 'start_date': '2026-08-01', 'end_date': '2026-08-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Budget.objects.filter(name='Unlabeled Other').exists())

    def test_other_category_with_custom_label_accepted(self):
        self.login_a()
        response = self.client.post(reverse('budgeting:budget_create'), {
            'name': 'Labeled Other', 'period': 'monthly', 'category': 'other', 'custom_category': 'Licensing fees',
            'amount': '1000', 'start_date': '2026-08-01', 'end_date': '2026-08-31',
        })
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(name='Labeled Other')
        self.assertEqual(budget.display_category, 'Licensing fees')
