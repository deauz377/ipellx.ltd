from django.urls import reverse

from tenants.models import User
from tenants.tests import TEST_PASSWORD, TwoTenantTestCase

from .models import Message


class ReportToCeoTests(TwoTenantTestCase):
    """Reports are delivered as Messages so they land in the CEO's existing
    inbox and drive the same unread badge -- a separate reports table would
    have needed its own notification path and its own place to be forgotten."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.accountant = User.objects.create_user(
            username='rpt_acct', password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.ACCOUNTANT, email_verified=True,
        )
        cls.staff = User.objects.create_user(
            username='rpt_staff', password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.STAFF, email_verified=True,
        )

    def login_accountant(self):
        self.client.login(username='rpt_acct', password=TEST_PASSWORD)

    def _url(self):
        return reverse('collaboration:report_to_ceo')

    def test_report_reaches_the_ceo_as_an_unread_message(self):
        self.login_accountant()
        response = self.client.post(self._url(), {
            'subject': 'Finance summary - August',
            'body': 'Receivables are up. Two invoices over 90 days.',
        })
        self.assertEqual(response.status_code, 302)

        report = Message.objects.get(kind='report')
        self.assertEqual(report.sender, self.accountant)
        self.assertEqual(report.recipient, self.user_a)      # the Owner
        self.assertEqual(report.tenant, self.tenant_a)
        self.assertEqual(report.subject, 'Finance summary - August')
        self.assertTrue(report.is_report)
        self.assertTrue(report.is_unread)
        self.assertEqual(Message.unread_count_for(self.user_a), 1)

    def test_ceo_sees_it_in_the_thread_rendered_as_a_report(self):
        self.login_accountant()
        self.client.post(self._url(), {'subject': 'Q3 numbers', 'body': 'All good.'})
        self.client.logout()

        self.login_a()
        thread = self.client.get(
            reverse('collaboration:conversation', kwargs={'user_id': self.accountant.pk}),
        )
        self.assertContains(thread, 'Q3 numbers')
        self.assertContains(thread, 'report-card')

    def test_any_non_owner_role_can_report(self):
        self.client.login(username='rpt_staff', password=TEST_PASSWORD)
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_the_ceo_cannot_report_to_themselves(self):
        self.login_a()
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response.url)

    def test_empty_subject_or_body_is_rejected(self):
        self.login_accountant()
        for payload in ({'subject': '   ', 'body': 'text'},
                        {'subject': 'Subject', 'body': '   '}):
            response = self.client.post(self._url(), payload)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Message.objects.filter(kind='report').count(), 0)

    def test_report_never_crosses_into_another_business(self):
        """The recipient is resolved from the sender's own tenant, so there is
        no owner id to tamper with -- tenant B's Owner must never receive it."""
        self.login_accountant()
        self.client.post(self._url(), {'subject': 'Internal', 'body': 'For our CEO only.'})

        self.assertEqual(Message.unread_count_for(self.user_b), 0)
        self.assertFalse(Message.objects.filter(recipient=self.user_b).exists())

    def test_finance_prefill_populates_real_figures(self):
        from decimal import Decimal

        from customers.models import Customer
        from sales.models import Invoice

        customer = Customer.objects.create(name='Prefill Co', tenant=self.tenant_a)
        Invoice.objects.create(
            tenant=self.tenant_a, customer=customer,
            total=Decimal('5000'), paid=Decimal('1000'),
        )
        self.login_accountant()
        response = self.client.get(self._url(), {'about': 'finance'})
        body = response.context['form'].initial['body']

        self.assertIn('Finance summary', body)
        self.assertIn('Owed to us', body)
        self.assertIn('4,000', body)          # 5000 - 1000 outstanding
        self.assertIn('Receivables by age', body)

    def test_blank_form_when_no_prefill_requested(self):
        self.login_accountant()
        response = self.client.get(self._url())
        self.assertEqual(response.context['form'].initial, {})

    def test_chat_messages_are_not_reports(self):
        self.login_accountant()
        self.client.post(
            reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}),
            {'body': 'quick question'},
        )
        message = Message.objects.get()
        self.assertEqual(message.kind, 'chat')
        self.assertFalse(message.is_report)
        self.assertEqual(message.subject, '')
