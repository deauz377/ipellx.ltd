"""Selling from a specific location.

Before this, a sale always drew from the tenant's default location while the
screen showed stock across every location. Two consequences:

  - a seller at a branch was told "50 available" for goods sitting at head
    office, and the sale was refused on submit;
  - nothing recorded where goods left from, so deleting an invoice returned
    them to the default location. Stock teleported between branches, and
    because the tenant-wide total stayed correct, reconcile() could not see it.

Single-location businesses -- which is all of them today -- must be completely
unaffected, so that is tested too.
"""
from decimal import Decimal

from django.urls import reverse

from customers.models import Customer
from inventory.services import available_quantity, receive_stock
from inventory.tests_stock import StockServiceTestCase
from tenants.models import User
from tenants.tests import TEST_PASSWORD

from .models import Invoice, InvoiceItem

ZERO = Decimal('0')


class SaleLocationTestCase(StockServiceTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.seller = User.objects.create_user(
            username='seller_loc', email='seller_loc@example.com',
            password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.SALES_STAFF, email_verified=True,
        )
        cls.customer = Customer.objects.create(tenant=cls.tenant_a, name='Mama Mboga')

    def login(self, user=None):
        user = user or self.user_a
        self.assertTrue(self.client.login(username=user.username, password=TEST_PASSWORD))

    def quick_sale_post(self, product, qty, location=None, **extra):
        data = {
            'payment_method': 'cash',
            'discount': '0',
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-product': product.pk,
            'form-0-qty': str(qty),
            'form-0-channel': 'retail',
        }
        if location is not None:
            data['location'] = location.pk
        data.update(extra)
        return self.client.post(reverse('sales:quick_sale'), data)


class SellingFromTheRightPlaceTests(SaleLocationTestCase):
    def test_a_sale_takes_stock_from_the_chosen_location_only(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        receive_stock(product=self.product_a, quantity=30, location=self.branch_a)
        self.login()

        self.quick_sale_post(self.product_a, 10, location=self.branch_a)

        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('20'))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('30'),
                         'the other location must be untouched')

    def test_the_line_records_where_the_goods_left_from(self):
        receive_stock(product=self.product_a, quantity=30, location=self.branch_a)
        self.login()
        self.quick_sale_post(self.product_a, 5, location=self.branch_a)

        item = InvoiceItem.objects.get(product=self.product_a)
        self.assertEqual(item.location, self.branch_a)

    def test_stock_held_elsewhere_cannot_be_sold_from_this_till(self):
        """The whole point: 30 exist, but not here."""
        receive_stock(product=self.product_a, quantity=30, location=self.branch_a)
        self.login()

        response = self.quick_sale_post(self.product_a, 5, location=self.main_a)

        self.assertEqual(Invoice.objects.count(), 0)
        self.assertContains(response, 'Main Store')
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('30'))

    def test_the_refusal_names_the_location_and_the_real_figure(self):
        receive_stock(product=self.product_a, quantity=2, location=self.main_a)
        receive_stock(product=self.product_a, quantity=40, location=self.branch_a)
        self.login()

        response = self.quick_sale_post(self.product_a, 5, location=self.main_a)
        body = response.content.decode()
        self.assertIn('Main Store', body)
        self.assertNotIn('42', body.split('Main Store')[1][:80],
                         'the message must not quote the tenant-wide total')


class ReturnsGoBackWhereTheyCameFromTests(SaleLocationTestCase):
    def test_deleting_a_branch_sale_returns_stock_to_that_branch(self):
        """The teleport bug: stock used to come back to the default location,
        leaving the tenant-wide total correct so nothing flagged it."""
        receive_stock(product=self.product_a, quantity=50, location=self.branch_a)
        self.login()
        self.quick_sale_post(self.product_a, 20, location=self.branch_a)
        invoice = Invoice.objects.get()

        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('30'))

        self.client.post(reverse('sales:invoice_delete', args=[invoice.pk]))

        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('50'),
                         'stock must return to the branch it left')
        self.assertEqual(available_quantity(self.product_a, self.main_a), ZERO,
                         'and must not appear at head office')

    def test_a_sale_and_its_deletion_leave_every_location_exactly_as_before(self):
        receive_stock(product=self.product_a, quantity=25, location=self.main_a)
        receive_stock(product=self.product_a, quantity=25, location=self.branch_a)
        before = {
            'main': available_quantity(self.product_a, self.main_a),
            'branch': available_quantity(self.product_a, self.branch_a),
        }
        self.login()
        self.quick_sale_post(self.product_a, 7, location=self.branch_a)
        invoice = Invoice.objects.get()
        self.client.post(reverse('sales:invoice_delete', args=[invoice.pk]))

        self.assertEqual(available_quantity(self.product_a, self.main_a), before['main'])
        self.assertEqual(available_quantity(self.product_a, self.branch_a), before['branch'])


class SingleLocationBusinessesAreUnaffectedTests(SaleLocationTestCase):
    """Every tenant in production has exactly one location. Nothing about
    selling may change for them."""

    def setUp(self):
        super().setUp()
        # Remove the second location so this tenant looks like a real one.
        self.branch_a.delete()

    def test_a_sale_submitted_without_a_location_still_works(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        self.login()

        self.quick_sale_post(self.product_a, 6)  # no location in the POST

        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('14'))

    def test_the_line_still_records_the_only_location_there_is(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        self.login()
        self.quick_sale_post(self.product_a, 6)
        self.assertEqual(InvoiceItem.objects.get().location, self.main_a)

    def test_the_selector_is_hidden_when_there_is_no_choice_to_make(self):
        self.login()
        response = self.client.get(reverse('sales:quick_sale'))
        self.assertTrue(response.context['form'].single_location)
        self.assertNotContains(response, 'Selling from')

    def test_the_selector_appears_once_a_second_location_exists(self):
        from inventory.models import Location
        Location.objects.create(tenant=self.tenant_a, name='Second Shop', kind='branch')
        self.login()
        response = self.client.get(reverse('sales:quick_sale'))
        self.assertFalse(response.context['form'].single_location)
        self.assertContains(response, 'Selling from')


class InvoiceLineLocationTests(SaleLocationTestCase):
    def test_adding_an_invoice_line_draws_from_the_chosen_location(self):
        receive_stock(product=self.product_a, quantity=40, location=self.branch_a)
        self.login()
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer,
                                         total=ZERO, created_by=self.user_a)

        self.client.post(reverse('sales:invoice_item_add', args=[invoice.pk]), {
            'product': self.product_a.pk, 'qty': '9', 'price': '100',
            'sale_channel': 'retail', 'location': self.branch_a.pk,
        })

        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('31'))
        self.assertEqual(invoice.items.get().location, self.branch_a)

    def test_an_invoice_line_cannot_draw_from_an_empty_location(self):
        receive_stock(product=self.product_a, quantity=40, location=self.branch_a)
        self.login()
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer,
                                         total=ZERO, created_by=self.user_a)

        self.client.post(reverse('sales:invoice_item_add', args=[invoice.pk]), {
            'product': self.product_a.pk, 'qty': '9', 'price': '100',
            'sale_channel': 'retail', 'location': self.main_a.pk,
        })

        self.assertEqual(invoice.items.count(), 0, 'no line without the stock to back it')
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('40'))

    def test_the_form_only_offers_this_tenants_locations(self):
        self.login()
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer,
                                         total=ZERO, created_by=self.user_a)
        form = self.client.get(
            reverse('sales:invoice_item_add', args=[invoice.pk])).context['form']
        self.assertIn(self.main_a, form.fields['location'].queryset)
        self.assertNotIn(self.main_b, form.fields['location'].queryset)


class QuickSaleAvailabilityDataTests(SaleLocationTestCase):
    def test_the_product_dropdown_carries_stock_per_location(self):
        """What the seller sees has to be what the till can actually sell."""
        receive_stock(product=self.product_a, quantity=12, location=self.main_a)
        receive_stock(product=self.product_a, quantity=7, location=self.branch_a)
        self.login()

        formset = self.client.get(reverse('sales:quick_sale')).context['formset']
        data = formset.forms[0].fields['product'].widget.product_data[str(self.product_a.pk)]
        by_location = data['stock_by_location']

        self.assertEqual(by_location[str(self.main_a.pk)], '12.00')
        self.assertEqual(by_location[str(self.branch_a.pk)], '7.00')

    def test_another_tenants_stock_never_reaches_the_dropdown(self):
        receive_stock(product=self.product_b, quantity=99, location=self.main_b)
        self.login()
        formset = self.client.get(reverse('sales:quick_sale')).context['formset']
        product_data = formset.forms[0].fields['product'].widget.product_data
        self.assertNotIn(str(self.product_b.pk), product_data)
