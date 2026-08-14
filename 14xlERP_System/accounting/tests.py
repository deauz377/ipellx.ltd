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
        self.user = User.objects.create_user(username='accounting-user', password='secret123')
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
        self.user = User.objects.create_user(username='bill-user', password='secret123')
        self.client.force_login(self.user)

    def test_bill_create_page_renders(self):
        response = self.client.get(reverse('accounting:bill_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Bill')


class BillDetailViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='bill-detail-user', password='secret123')
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
        self.assertContains(response, 'Test Vendor')
