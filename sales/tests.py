from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from customers.models import Customer
from .models import Invoice


class SalesInvoiceDetailViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='sales-user', password='secret123')
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name='Test Customer', phone='0712345678')
        self.invoice = Invoice.objects.create(customer=self.customer, total=1000.00, paid=0.00)

    def test_invoice_detail_page_renders(self):
        response = self.client.get(reverse('sales:invoice_detail', kwargs={'pk': self.invoice.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invoice #')


from inventory.models import Product
from tenants.tests import TwoTenantTestCase


class SalesTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #27, #31, #36, #38, #41 -- and a direct regression test for
    the ModelForm FK-injection bug fixed in sales/forms.py (Meta.fields
    dropdowns were built with an unfiltered queryset at class-definition
    time, before any tenant existed, so any tenant's customer/product ID
    used to be silently accepted)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer_a = Customer.objects.create(name='Customer A', tenant=cls.tenant_a)
        cls.customer_b = Customer.objects.create(name='Customer B', tenant=cls.tenant_b)
        cls.invoice_a = Invoice.objects.create(customer=cls.customer_a, total=1000, tenant=cls.tenant_a)
        cls.invoice_b = Invoice.objects.create(customer=cls.customer_b, total=2000, tenant=cls.tenant_b)
        cls.product_a = Product.objects.create(
            name='Product A', sku='SKU-A-ISO', retail_price=100, wholesale_price=80,
            online_price=90, tenant=cls.tenant_a,
        )
        cls.product_b = Product.objects.create(
            name='Product B', sku='SKU-B-ISO', retail_price=200, wholesale_price=160,
            online_price=180, tenant=cls.tenant_b,
        )

    def test_user_a_cannot_view_user_b_invoice_by_id(self):
        self.login_a()
        response = self.client.get(reverse('sales:invoice_detail', kwargs={'pk': self.invoice_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_a_invoice_list_excludes_user_b_invoices(self):
        self.login_a()
        response = self.client.get(reverse('sales:invoice_list'))
        self.assertContains(response, str(self.invoice_a.pk))
        self.assertNotContains(response, self.customer_b.name)

    def test_invoice_id_manipulation_in_url_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.invoice_b.pk, 999999):
            response = self.client.get(reverse('sales:invoice_detail', kwargs={'pk': pk}))
            self.assertEqual(response.status_code, 404)

    def test_invoice_form_rejects_cross_tenant_customer_id(self):
        """Regression test for the class-definition-time queryset bug:
        submitting Tenant B's customer id while logged in as Tenant A's
        owner must be rejected by form validation, not silently accepted."""
        self.login_a()
        response = self.client.post(reverse('sales:invoice_create'), {
            'customer': self.customer_b.pk, 'discount': '0',
        })
        self.assertEqual(response.status_code, 200)  # re-renders the form, no redirect on success
        self.assertFormError(response.context['form'], 'customer', [
            'Select a valid choice. That choice is not one of the available choices.',
        ])
        self.assertFalse(Invoice.objects.filter(customer=self.customer_b, tenant=self.tenant_a).exists())

    def test_invoice_item_form_rejects_cross_tenant_product_id(self):
        self.login_a()
        response = self.client.post(
            reverse('sales:invoice_item_add', kwargs={'invoice_pk': self.invoice_a.pk}),
            {'product': self.product_b.pk, 'qty': '1', 'price': '10', 'sale_channel': 'retail'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'product', [
            'Select a valid choice. That choice is not one of the available choices.',
        ])
