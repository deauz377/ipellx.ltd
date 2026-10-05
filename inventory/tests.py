from io import StringIO

from django.core.management import call_command
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
            online_price=90, cost_price=50,
            supplier=cls.supplier_a, tenant=cls.tenant_a,
        )
        cls.product_b = Product.objects.create(
            name='Product B', sku='SKU-B-INV', retail_price=200, wholesale_price=160,
            online_price=180, cost_price=100,
            supplier=cls.supplier_b, tenant=cls.tenant_b,
        )

    def test_user_a_product_list_excludes_user_b_products(self):
        self.login_a()
        response = self.client.get(reverse('inventory:product_list'))
        self.assertContains(response, 'Product A')
        self.assertNotContains(response, 'Product B')

    def test_product_list_displays_cost_and_retail_values_and_flags_cost_one(self):
        Product.objects.filter(pk=self.product_a.pk).update(quantity=9, cost_price=1)
        self.login_a()
        response = self.client.get(reverse('inventory:product_list'))

        self.assertContains(response, 'Cost Price')
        self.assertContains(response, 'Stock Value (Cost)')
        self.assertContains(response, 'Retail Value')
        self.assertContains(response, 'Cost not set')
        self.assertContains(response, 'KES 9.00')
        self.assertContains(response, 'KES 900.00')

    def test_product_import_requires_cost_and_skips_missing_or_nonpositive_cost(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.login_a()
        old_format = (
            'Name,SKU,Retail Price,Wholesale Price,Online Price,Quantity,Min Stock,Supplier\n'
            'Missing Cost,NO-COST,100,80,90,2,1,Supplier A\n'
        )
        response = self.client.post(
            reverse('inventory:product_import_csv'),
            {'csv_file': SimpleUploadedFile('products.csv', old_format.encode(), content_type='text/csv')},
        )
        self.assertRedirects(response, reverse('inventory:product_list'))
        self.assertFalse(Product.objects.filter(sku='NO-COST').exists())

        csv_data = (
            'Name,SKU,Cost Price,Retail Price,Wholesale Price,Online Price,Quantity,Min Stock,Supplier\n'
            'Zero Cost,ZERO-COST,0,100,80,90,2,1,Supplier A\n'
            'Valid Cost,VALID-COST,50,100,80,90,2,1,Supplier A\n'
        )
        response = self.client.post(
            reverse('inventory:product_import_csv'),
            {'csv_file': SimpleUploadedFile('products.csv', csv_data.encode(), content_type='text/csv')},
        )
        self.assertRedirects(response, reverse('inventory:product_list'))
        self.assertFalse(Product.objects.filter(sku='ZERO-COST').exists())
        self.assertEqual(Product.objects.get(sku='VALID-COST').cost_price, 50)

    def test_cost_report_lists_low_values_without_mutating_them(self):
        Product.objects.filter(pk=self.product_a.pk).update(cost_price=1)
        output = StringIO()
        call_command('list_unset_cost_prices', stdout=output)
        self.assertIn('SKU-A-INV', output.getvalue())
        self.assertIn('DRY RUN', output.getvalue())
        self.assertEqual(Product.objects.get(pk=self.product_a.pk).cost_price, 1)

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
