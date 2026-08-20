from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import ChartOfAccounts, Journal, BankAccount, Bill


class ChartOfAccountsTestCase(TestCase):
    def setUp(self):
        self.account = ChartOfAccounts.objects.create(
            account_number='1000',
            account_name='Cash',
            account_type='asset',
            opening_balance=10000.00
        )

    def test_chart_of_accounts_creation(self):
        self.assertTrue(isinstance(self.account, ChartOfAccounts))
        self.assertEqual(self.account.account_name, 'Cash')


class JournalTestCase(TestCase):
    def setUp(self):
        self.journal = Journal.objects.create(
            name='General Journal',
            journal_type='general'
        )

    def test_journal_creation(self):
        self.assertTrue(isinstance(self.journal, Journal))
        self.assertEqual(self.journal.journal_type, 'general')


class BankAccountTestCase(TestCase):
    def setUp(self):
        self.account = BankAccount.objects.create(
            account_name='Main Business Account',
            account_type='checking',
            account_number='123456789',
            bank_name='Test Bank',
            opening_balance=50000.00
        )

    def test_bank_account_creation(self):
        self.assertTrue(isinstance(self.account, BankAccount))
        self.assertEqual(self.account.account_type, 'checking')


class AccountingDashboardTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='accounting-user', password='secret123', role=User.Role.OWNER)
        self.client.force_login(self.user)

    def test_dashboard_renders_with_expected_metrics(self):
        response = self.client.get(reverse('accounting:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Accounting Dashboard')
        self.assertIn('total_invoices', response.context)
        self.assertEqual(response.context['total_invoices'], 0)


class BillCreateViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='bill-user', password='secret123', role=User.Role.OWNER)
        self.client.force_login(self.user)

    def test_bill_create_page_renders(self):
        response = self.client.get(reverse('accounting:bill_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Bill')


class BillDetailViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='bill-detail-user', password='secret123', role=User.Role.OWNER)
        self.client.force_login(self.user)
        self.bill = Bill.objects.create(
            bill_number='BILL-1001',
            bill_date='2026-07-01',
            due_date='2026-07-15',
            vendor='Test Vendor',
            vendor_email='vendor@example.com',
            vendor_phone='0712345678',
            payment_terms='Net 30',
            notes='Test bill',
            total_amount=1500.00,
            paid_amount=0.00,
            status='received',
        )

    def test_bill_detail_page_renders(self):
        response = self.client.get(reverse('accounting:bill_detail', kwargs={'pk': self.bill.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bill Details')


from tenants.tests import TwoTenantTestCase

from .models import BankAccount, BankReconciliation


class AccountingTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #33 -- plus a direct regression test for the bank
    reconciliation view (accounting/views.py:bank_reconciliation), which
    used to take bank_account straight from POST data with no check that
    it belonged to the current tenant."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bill_a = Bill.objects.create(
            bill_number='BILL-A-ISO', bill_date='2026-07-01', due_date='2026-07-15',
            vendor='Vendor A', total_amount=500, tenant=cls.tenant_a,
        )
        cls.bill_b = Bill.objects.create(
            bill_number='BILL-B-ISO', bill_date='2026-07-01', due_date='2026-07-15',
            vendor='Vendor B', total_amount=700, tenant=cls.tenant_b,
        )
        cls.bank_account_b = BankAccount.objects.create(
            account_name='Tenant B Checking', account_type='checking',
            account_number='B-ACC-001', tenant=cls.tenant_b,
        )

    def test_user_a_cannot_view_user_b_bill_by_id(self):
        self.login_a()
        response = self.client.get(reverse('accounting:bill_detail', kwargs={'pk': self.bill_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_bill_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.bill_b.pk, 999999):
            response = self.client.get(reverse('accounting:bill_detail', kwargs={'pk': pk}))
            self.assertEqual(response.status_code, 404)

    def test_bank_reconciliation_rejects_cross_tenant_bank_account_id(self):
        """Regression test for the accounting/views.py:bank_reconciliation
        fix: bank_account_id used to be taken straight from POST with no
        ownership check."""
        self.login_a()
        response = self.client.post(reverse('accounting:bank_reconciliation'), {
            'bank_balance': '1000', 'book_balance': '1000',
            'reconciliation_date': '2026-08-01',
            'bank_account': self.bank_account_b.pk,
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(BankReconciliation.objects.filter(bank_account=self.bank_account_b).exists())
