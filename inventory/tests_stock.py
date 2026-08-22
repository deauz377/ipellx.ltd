from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from sales.models import Invoice, InvoiceItem
from tenants.models import User
from tenants.tests import TEST_PASSWORD, TwoTenantTestCase

from .models import Location, Product, StockLevel, StockMovement
from .services import (
    StockError, adjust_stock, available_quantity, default_location,
    expiring_batches, issue_stock, receive_stock, reconcile, return_stock,
    transfer_stock,
)

ZERO = Decimal('0')


def make_product(tenant, name='Cooking Oil', sku=None, **kwargs):
    defaults = dict(
        tenant=tenant, name=name, sku=sku or f'SKU-{name}-{tenant.pk}',
        retail_price=Decimal('100'), wholesale_price=Decimal('90'),
        online_price=Decimal('110'), cost_price=Decimal('70'),
        minimum_stock=Decimal('10'),
    )
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


class StockServiceTestCase(TwoTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.main_a = Location.objects.create(
            tenant=cls.tenant_a, name='Main Store', kind='store', is_default=True,
        )
        cls.branch_a = Location.objects.create(
            tenant=cls.tenant_a, name='Branch Two', kind='branch',
        )
        cls.main_b = Location.objects.create(
            tenant=cls.tenant_b, name='B Store', kind='store', is_default=True,
        )
        cls.product_a = make_product(cls.tenant_a)
        cls.product_b = make_product(cls.tenant_b, name='B Oil')


class RecordMovementTests(StockServiceTestCase):
    def test_receiving_creates_level_movement_and_updates_cache(self):
        receive_stock(product=self.product_a, quantity=25, location=self.main_a,
                      user=self.user_a, reason='Opening delivery')

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('25'))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('25'))

        movement = StockMovement.objects.get(product=self.product_a)
        self.assertEqual(movement.movement_type, StockMovement.RECEIVE)
        self.assertEqual(movement.quantity_before, ZERO)
        self.assertEqual(movement.quantity_after, Decimal('25'))
        self.assertEqual(movement.quantity_delta, Decimal('25'))
        self.assertEqual(movement.user, self.user_a)
        self.assertTrue(reconcile(self.product_a))

    def test_issuing_reduces_and_records_before_and_after(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        issue_stock(product=self.product_a, quantity=8, location=self.main_a, user=self.user_a)

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('12'))
        sale = StockMovement.objects.filter(movement_type=StockMovement.SALE).get()
        self.assertEqual(sale.quantity_before, Decimal('20'))
        self.assertEqual(sale.quantity_after, Decimal('12'))
        self.assertEqual(sale.quantity_delta, Decimal('-8'))
        self.assertTrue(reconcile(self.product_a))

    def test_cannot_take_more_than_is_there(self):
        receive_stock(product=self.product_a, quantity=5, location=self.main_a)
        with self.assertRaises(StockError):
            issue_stock(product=self.product_a, quantity=6, location=self.main_a)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('5'), 'a refused sale must change nothing')

    def test_zero_and_negative_quantities_are_refused(self):
        for bad in (0, -3):
            with self.assertRaises(StockError):
                receive_stock(product=self.product_a, quantity=bad, location=self.main_a)

    def test_stock_never_leaks_between_locations(self):
        receive_stock(product=self.product_a, quantity=10, location=self.main_a)
        receive_stock(product=self.product_a, quantity=4, location=self.branch_a)

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('10'))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('4'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('14'), 'cache is the sum of both')

        # The branch cannot sell the main store's stock.
        with self.assertRaises(StockError):
            issue_stock(product=self.product_a, quantity=6, location=self.branch_a)

    def test_stock_never_leaks_between_businesses(self):
        receive_stock(product=self.product_a, quantity=10, location=self.main_a)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.quantity, ZERO)

        with self.assertRaises(StockError):
            # Another tenant's location must never accept this product.
            receive_stock(product=self.product_a, quantity=5, location=self.main_b)


class FefoTests(StockServiceTestCase):
    def test_nearest_expiry_is_consumed_first(self):
        today = timezone.localdate()
        self.product_a.tracks_expiry = True
        self.product_a.save(update_fields=['tracks_expiry'])

        receive_stock(product=self.product_a, quantity=10, location=self.main_a,
                      batch_number='LATE', expiry_date=today + timedelta(days=30))
        receive_stock(product=self.product_a, quantity=6, location=self.main_a,
                      batch_number='SOON', expiry_date=today + timedelta(days=3))

        issue_stock(product=self.product_a, quantity=8, location=self.main_a)

        levels = {
            lv.batch.batch_number: lv.quantity
            for lv in StockLevel.objects.filter(product=self.product_a).select_related('batch')
        }
        self.assertEqual(levels['SOON'], ZERO, 'the batch expiring soonest empties first')
        self.assertEqual(levels['LATE'], Decimal('8'), 'only the remainder comes from the later batch')
        self.assertTrue(reconcile(self.product_a))

    def test_expiry_required_when_the_product_tracks_it(self):
        self.product_a.tracks_expiry = True
        self.product_a.save(update_fields=['tracks_expiry'])
        with self.assertRaises(StockError):
            receive_stock(product=self.product_a, quantity=5, location=self.main_a)

    def test_expiring_batches_only_lists_stock_still_on_hand(self):
        today = timezone.localdate()
        self.product_a.tracks_expiry = True
        self.product_a.save(update_fields=['tracks_expiry'])
        receive_stock(product=self.product_a, quantity=4, location=self.main_a,
                      batch_number='NEAR', expiry_date=today + timedelta(days=2))

        self.assertEqual(expiring_batches(self.tenant_a, within_days=7).count(), 1)
        issue_stock(product=self.product_a, quantity=4, location=self.main_a)
        self.assertEqual(
            expiring_batches(self.tenant_a, within_days=7).count(), 0,
            'a lot that has been sold is not something anyone needs to act on',
        )


class AdjustAndTransferTests(StockServiceTestCase):
    def test_stock_count_records_the_variance_rather_than_overwriting(self):
        receive_stock(product=self.product_a, quantity=100, location=self.main_a)
        adjust_stock(product=self.product_a, location=self.main_a, new_quantity=96,
                     user=self.user_a, reason='spoilage')

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('96'))
        adjustment = StockMovement.objects.filter(movement_type=StockMovement.ADJUSTMENT).get()
        self.assertEqual(adjustment.quantity_delta, Decimal('-4'))
        self.assertEqual(adjustment.quantity_before, Decimal('100'))
        self.assertEqual(adjustment.quantity_after, Decimal('96'))
        self.assertEqual(adjustment.reason, 'spoilage')
        self.assertTrue(reconcile(self.product_a))

    def test_counting_the_same_number_records_nothing(self):
        receive_stock(product=self.product_a, quantity=50, location=self.main_a)
        before = StockMovement.objects.count()
        self.assertIsNone(
            adjust_stock(product=self.product_a, location=self.main_a, new_quantity=50)
        )
        self.assertEqual(StockMovement.objects.count(), before)

    def test_transfer_moves_stock_as_a_matched_pair(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        transfer_stock(product=self.product_a, quantity=12, source=self.main_a,
                       destination=self.branch_a, user=self.user_a)

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('18'))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('12'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('30'), 'a transfer moves stock, it does not create it')
        self.assertTrue(reconcile(self.product_a))

    def test_transfer_of_more_than_is_available_moves_nothing(self):
        receive_stock(product=self.product_a, quantity=5, location=self.main_a)
        with self.assertRaises(StockError):
            transfer_stock(product=self.product_a, quantity=9,
                           source=self.main_a, destination=self.branch_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('5'))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), ZERO)

    def test_cannot_transfer_to_the_same_place_or_another_business(self):
        receive_stock(product=self.product_a, quantity=5, location=self.main_a)
        with self.assertRaises(StockError):
            transfer_stock(product=self.product_a, quantity=1,
                           source=self.main_a, destination=self.main_a)
        with self.assertRaises(StockError):
            transfer_stock(product=self.product_a, quantity=1,
                           source=self.main_a, destination=self.main_b)


class SalesIntegrationTests(StockServiceTestCase):
    """The bug this phase exists to fix.

    Adding a line to an invoice never deducted stock, while deleting the
    invoice put stock back -- so every delete invented inventory that had
    never left the shelf.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer = Customer.objects.create(tenant=cls.tenant_a, name='Walk-in')

    def test_adding_an_invoice_line_now_deducts_stock(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer, total=0)

        self.login_a()
        response = self.client.post(
            reverse('sales:invoice_item_add', kwargs={'invoice_pk': invoice.pk}),
            {'product': self.product_a.pk, 'qty': '3', 'price': '100', 'sale_channel': 'retail'},
        )
        self.assertEqual(response.status_code, 302)

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('17'))
        self.assertTrue(
            StockMovement.objects.filter(
                movement_type=StockMovement.SALE, reference_type='invoice',
            ).exists()
        )

    def test_deleting_an_invoice_returns_exactly_what_was_taken(self):
        """The regression itself: stock must land back on its original value,
        never above it."""
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer, total=0)

        self.login_a()
        self.client.post(
            reverse('sales:invoice_item_add', kwargs={'invoice_pk': invoice.pk}),
            {'product': self.product_a.pk, 'qty': '5', 'price': '100', 'sale_channel': 'retail'},
        )
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('15'))

        self.client.post(reverse('sales:invoice_delete', kwargs={'pk': invoice.pk}))

        self.product_a.refresh_from_db()
        self.assertEqual(
            self.product_a.quantity, Decimal('20'),
            'deleting an invoice must restore stock exactly, not inflate it',
        )
        self.assertTrue(reconcile(self.product_a))

    def test_an_invoice_line_beyond_available_stock_is_refused(self):
        receive_stock(product=self.product_a, quantity=2, location=self.main_a)
        invoice = Invoice.objects.create(tenant=self.tenant_a, customer=self.customer, total=0)

        self.login_a()
        response = self.client.post(
            reverse('sales:invoice_item_add', kwargs={'invoice_pk': invoice.pk}),
            {'product': self.product_a.pk, 'qty': '9', 'price': '100', 'sale_channel': 'retail'},
        )
        self.assertEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('2'))
        self.assertFalse(
            InvoiceItem.objects.filter(invoice=invoice).exists(),
            'the line and the deduction succeed or fail together',
        )

    def test_quick_sale_deducts_once_and_only_once(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        self.login_a()
        self.client.post(reverse('sales:quick_sale'), {
            'customer': '', 'payment_method': 'cash', 'amount_received': '', 'discount': '0',
            'form-TOTAL_FORMS': '6', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-product': str(self.product_a.pk), 'form-0-channel': 'retail',
            'form-0-qty': '4', 'form-0-price': '100',
            **{f'form-{i}-{f}': '' for i in range(1, 6)
               for f in ('product', 'channel', 'qty', 'price')},
        })
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('26'), 'deducted exactly once')
        self.assertEqual(
            StockMovement.objects.filter(movement_type=StockMovement.SALE).count(), 1,
        )
        self.assertTrue(reconcile(self.product_a))


class ProductHelperTests(StockServiceTestCase):
    def test_low_stock_and_reorder_helpers(self):
        product = make_product(self.tenant_a, name='Rice', sku='RICE-1',
                               minimum_stock=Decimal('10'), maximum_stock=Decimal('50'))
        receive_stock(product=product, quantity=4, location=self.main_a)
        product.refresh_from_db()

        self.assertTrue(product.is_low_stock)
        self.assertFalse(product.is_out_of_stock)
        self.assertEqual(product.recommended_order_quantity, Decimal('46'))
        self.assertEqual(product.stock_value, Decimal('4') * product.cost_price)

    def test_reorder_level_falls_back_to_minimum_stock(self):
        product = make_product(self.tenant_a, name='Sugar', sku='SUGAR-1',
                               minimum_stock=Decimal('8'), reorder_level=None)
        self.assertEqual(product.effective_reorder_level, Decimal('8'))

    def test_default_location_is_created_when_missing(self):
        tenant = self.tenant_b
        Location.objects.filter(tenant=tenant).delete()
        location = default_location(tenant)
        self.assertEqual(location.tenant, tenant)
        self.assertTrue(Location.objects.filter(tenant=tenant).exists())


class AuditTrailTests(StockServiceTestCase):
    def test_every_change_leaves_a_readable_record(self):
        receive_stock(product=self.product_a, quantity=50, location=self.main_a, user=self.user_a)
        issue_stock(product=self.product_a, quantity=5, location=self.main_a,
                    user=self.user_a, reason='5 chickens sold')

        movements = StockMovement.objects.filter(product=self.product_a).order_by('pk')
        self.assertEqual(movements.count(), 2)

        sale = movements.last()
        self.assertEqual(sale.user, self.user_a)
        self.assertEqual(sale.quantity_before, Decimal('50'))
        self.assertEqual(sale.quantity_after, Decimal('45'))
        self.assertEqual(sale.reason, '5 chickens sold')
        self.assertEqual(sale.location, self.main_a)
        self.assertIsNotNone(sale.created_at)

    def test_movements_are_scoped_to_their_business(self):
        receive_stock(product=self.product_a, quantity=5, location=self.main_a)
        receive_stock(product=self.product_b, quantity=7, location=self.main_b)

        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant_a).count(), 1,
        )
        self.assertFalse(
            StockMovement.objects.filter(tenant=self.tenant_a, product=self.product_b).exists()
        )


class ReturnStockTests(StockServiceTestCase):
    def test_returned_stock_comes_back_unbatched(self):
        """Which lot a returned item came from is not knowable from the sale
        record, so inventing a batch would put a false expiry on real stock."""
        today = timezone.localdate()
        self.product_a.tracks_expiry = True
        self.product_a.save(update_fields=['tracks_expiry'])
        receive_stock(product=self.product_a, quantity=10, location=self.main_a,
                      batch_number='B1', expiry_date=today + timedelta(days=10))
        issue_stock(product=self.product_a, quantity=4, location=self.main_a)

        return_stock(product=self.product_a, quantity=4, location=self.main_a)

        unbatched = StockLevel.objects.get(
            product=self.product_a, location=self.main_a, batch__isnull=True,
        )
        self.assertEqual(unbatched.quantity, Decimal('4'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('10'))
        self.assertTrue(reconcile(self.product_a))
