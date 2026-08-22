from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from expenses.models import Expense
from sales.models import Invoice, Payment
from tenants.models import User
from tenants.tests import TwoTenantTestCase


class FinanceDeskTests(TwoTenantTestCase):
    """The Finance Desk reads from where money actually moves in this system
    (sales invoices, payments, expenses) rather than the double-entry tables,
    which are empty in production -- so these assert against those sources."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.accountant = User.objects.create_user(
            username='fd_acct', password='TestPass123!', tenant=cls.tenant_a,
            role=User.Role.ACCOUNTANT, email_verified=True,
        )
        cls.staff = User.objects.create_user(
            username='fd_staff', password='TestPass123!', tenant=cls.tenant_a,
            role=User.Role.STAFF, email_verified=True,
        )
        cls.customer_a = Customer.objects.create(name='Customer A', tenant=cls.tenant_a)
        cls.customer_b = Customer.objects.create(name='Customer B', tenant=cls.tenant_b)

    def login_accountant(self):
        self.client.login(username='fd_acct', password='TestPass123!')

    def _get(self):
        return self.client.get(reverse('accounting:accountant_dashboard'))

    # --- access -----------------------------------------------------------

    def test_accountant_can_open_it(self):
        self.login_accountant()
        self.assertEqual(self._get().status_code, 200)

    def test_staff_cannot(self):
        self.client.login(username='fd_staff', password='TestPass123!')
        self.assertEqual(self._get().status_code, 403)

    def test_anonymous_redirected(self):
        response = self._get()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response.url)

    def test_renders_with_no_data_at_all(self):
        """A brand-new business must not see a broken page or a division error."""
        self.login_accountant()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['receivables_total'], Decimal('0'))
        self.assertEqual(response.context['action_count'], 0)
        self.assertContains(response, 'Every invoice is paid in full')

    # --- receivables ageing ----------------------------------------------

    def test_unpaid_invoice_ages_into_the_right_bucket(self):
        today = timezone.localdate()
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a, total=Decimal('1000'),
            paid=Decimal('250'), due_date=today - timedelta(days=45),
        )
        self.login_accountant()
        ctx = self._get().context

        self.assertEqual(ctx['receivables_total'], Decimal('750'))
        self.assertEqual(ctx['receivables_overdue'], Decimal('750'))
        buckets = {b['label']: b for b in ctx['receivables_buckets']}
        self.assertEqual(buckets['31-60 days']['total'], Decimal('750'))
        self.assertEqual(buckets['31-60 days']['count'], 1)
        self.assertEqual(buckets['1-30 days']['count'], 0)

    def test_not_yet_due_invoice_is_not_counted_as_overdue(self):
        today = timezone.localdate()
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a, total=Decimal('500'),
            paid=Decimal('0'), due_date=today + timedelta(days=10),
        )
        self.login_accountant()
        ctx = self._get().context
        self.assertEqual(ctx['receivables_total'], Decimal('500'))
        self.assertEqual(ctx['receivables_overdue'], Decimal('0'))
        self.assertEqual(ctx['overdue_invoice_count'], 0)

    def test_fully_paid_invoice_drops_out(self):
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a,
            total=Decimal('400'), paid=Decimal('400'),
        )
        self.login_accountant()
        self.assertEqual(self._get().context['receivables_count'], 0)

    def test_invoice_without_due_date_still_ages(self):
        """Invoices raised before due dates existed must not vanish from the
        report -- they fall back to the invoice date."""
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a,
            total=Decimal('300'), paid=Decimal('0'), due_date=None,
        )
        self.login_accountant()
        self.assertEqual(self._get().context['receivables_count'], 1)

    # --- cash -------------------------------------------------------------

    def test_confirmed_payments_count_but_pending_mpesa_does_not(self):
        invoice = Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a,
            total=Decimal('1000'), paid=Decimal('1000'),
        )
        Payment.objects.create(
            tenant=self.tenant_a, invoice=invoice, method='mpesa',
            amount=Decimal('1000'), status='confirmed',
        )
        self.login_accountant()
        ctx = self._get().context
        self.assertEqual(ctx['cash_month_total'], Decimal('1000'))
        self.assertEqual(ctx['mpesa_pending_total'], Decimal('0'))

    def test_refunded_payment_is_not_counted_as_received(self):
        invoice = Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a,
            total=Decimal('800'), paid=Decimal('0'),
        )
        Payment.objects.create(
            tenant=self.tenant_a, invoice=invoice, method='cash',
            amount=Decimal('800'), status='refunded',
        )
        self.login_accountant()
        self.assertEqual(self._get().context['cash_month_total'], Decimal('0'))

    # --- spending ---------------------------------------------------------

    def test_expenses_grouped_by_category(self):
        today = timezone.localdate()
        Expense.objects.create(tenant=self.tenant_a, category='rent', amount=Decimal('5000'), date=today)
        Expense.objects.create(tenant=self.tenant_a, category='transport', amount=Decimal('1200'), date=today)
        self.login_accountant()
        ctx = self._get().context
        self.assertEqual(ctx['expenses_month_total'], Decimal('6200'))
        self.assertEqual(ctx['expenses_by_category'][0]['total'], Decimal('5000'))

    # --- tenant isolation -------------------------------------------------

    def test_another_business_money_never_appears(self):
        today = timezone.localdate()
        Invoice.objects.create(
            tenant=self.tenant_b, customer=self.customer_b, total=Decimal('999999'),
            paid=Decimal('0'), due_date=today - timedelta(days=200),
        )
        Expense.objects.create(tenant=self.tenant_b, category='rent', amount=Decimal('777777'), date=today)

        self.login_accountant()
        ctx = self._get().context
        self.assertEqual(ctx['receivables_total'], Decimal('0'))
        self.assertEqual(ctx['expenses_month_total'], Decimal('0'))
        self.assertNotContains(self._get(), '999999')

    def test_action_count_summarises_what_needs_attention(self):
        today = timezone.localdate()
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a, total=Decimal('100'),
            paid=Decimal('0'), due_date=today - timedelta(days=5),
        )
        Invoice.objects.create(
            tenant=self.tenant_a, customer=self.customer_a, total=Decimal('100'),
            paid=Decimal('0'), due_date=today - timedelta(days=120),
        )
        self.login_accountant()
        response = self._get()
        self.assertEqual(response.context['overdue_invoice_count'], 2)
        self.assertEqual(response.context['action_count'], 2)
        self.assertContains(response, 'need attention today')
