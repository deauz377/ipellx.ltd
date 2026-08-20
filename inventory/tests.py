from django.urls import reverse

from tenants.tests import TwoTenantTestCase

from .models import Product, Supplier


class InventoryTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #29, #30, #38 -- plus a regression test for the ProductForm
    FK-injection bug fixed in inventory/forms.py."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier_a = Supplier.objects.create(name='Supplier A', tenant=cls.tenant_a)
        cls.supplier_b = Supplier.objects.create(name='Supplier B', tenant=cls.tenant_b)
        cls.product_a = Product.objects.create(
            name='Product A', sku='SKU-A-INV', retail_price=100, wholesale_price=80,
            online_price=90, supplier=cls.supplier_a, tenant=cls.tenant_a,
        )
        cls.product_b = Product.objects.create(
            name='Product B', sku='SKU-B-INV', retail_price=200, wholesale_price=160,
            online_price=180, supplier=cls.supplier_b, tenant=cls.tenant_b,
        )

    def test_user_a_product_list_excludes_user_b_products(self):
        self.login_a()
        response = self.client.get(reverse('inventory:product_list'))
        self.assertContains(response, 'Product A')
        self.assertNotContains(response, 'Product B')

    def test_product_id_manipulation_does_not_bypass_authorization(self):
        self.login_a()
        for pk in (self.product_b.pk, 999999):
            response = self.client.get(reverse('inventory:product_edit', kwargs={'pk': pk}))
            self.assertEqual(response.status_code, 404)

    def test_product_form_rejects_cross_tenant_supplier_id(self):
        self.login_a()
        response = self.client.post(reverse('inventory:product_edit', kwargs={'pk': self.product_a.pk}), {
            'name': 'Product A', 'sku': 'SKU-A-INV', 'category': '',
            'cost_price': '50', 'retail_price': '100', 'wholesale_price': '80', 'online_price': '90',
            'quantity': '10', 'minimum_stock': '5',
            'supplier': self.supplier_b.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'supplier', [
            'Select a valid choice. That choice is not one of the available choices.',
        ])
