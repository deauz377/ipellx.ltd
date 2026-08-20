from django.urls import reverse

from sales.models import Invoice
from tenants.tests import TwoTenantTestCase

from .models import Customer, CreditRecord


class CustomerTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #28, #37 -- plus a regression test for the CreditRecordForm
    FK-injection bug fixed in customers/forms.py."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer_a = Customer.objects.create(name='Customer A', tenant=cls.tenant_a)
        cls.customer_b = Customer.objects.create(name='Customer B', tenant=cls.tenant_b)
        cls.invoice_a = Invoice.objects.create(customer=cls.customer_a, total=500, tenant=cls.tenant_a)

    def test_user_a_cannot_view_user_b_customer_by_id(self):
        self.login_a()
        response = self.client.get(reverse('customers:customer_detail', kwargs={'pk': self.customer_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_a_customer_list_excludes_user_b_customers(self):
        self.login_a()
        response = self.client.get(reverse('customers:customer_list'))
        self.assertContains(response, 'Customer A')
        self.assertNotContains(response, 'Customer B')

    def test_customer_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.customer_b.pk, 999999):
            self.assertEqual(
                self.client.get(reverse('customers:customer_detail', kwargs={'pk': pk})).status_code, 404,
            )

    def test_credit_record_form_rejects_cross_tenant_customer_and_invoice(self):
        """CreditRecordForm isn't wired to any URL (imported in
        customers/views.py but never instantiated there) -- exercise it
        directly. Real usage would always happen mid-request, after
        TenantMiddleware has set the current tenant; set the thread-local
        the same way here rather than through the client, since
        tenants.signals.clear_current_tenant resets it the instant any
        actual request finishes."""
        from tenants import middleware as tenant_middleware

        tenant_middleware._local.tenant = self.tenant_a
        try:
            from .forms import CreditRecordForm
            form = CreditRecordForm(data={
                'customer': self.customer_b.pk, 'invoice': self.invoice_a.pk,
                'amount': '100', 'due_date': '2026-12-31',
            })
            self.assertFalse(form.is_valid())
            self.assertIn('customer', form.errors)
        finally:
            tenant_middleware._local.tenant = None
