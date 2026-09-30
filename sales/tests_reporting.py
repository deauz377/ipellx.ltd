"""Regression tests for sales/reporting.py's product figures.

Guards against stock value collapsing to the same number as quantity (which
happens if cost_price is ever dropped from the calculation, defaulted to 1,
or swapped for quantity by mistake).
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from customers.models import Customer
from inventory.services import receive_stock
from inventory.tests_stock import StockServiceTestCase, make_product

from .models import Invoice, InvoiceItem
from .reporting import business_day_summary, product_performance, product_totals

ZERO = Decimal('0')


class StockValueIsNotQuantityTests(StockServiceTestCase):
    """product.stock_value must be quantity * cost_price, never quantity alone."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # cost_price deliberately != 1 and != quantity, so a bug that returns
        # quantity or quantity*1 instead of quantity*cost_price is caught.
        cls.product = make_product(
            cls.tenant_a, name='Valued Rice', cost_price=Decimal('45.50'),
        )
        receive_stock(product=cls.product, quantity=Decimal('30'), location=cls.main_a)
        cls.product.refresh_from_db()

    def test_product_stock_value_property_is_quantity_times_cost_price(self):
        self.assertEqual(self.product.quantity, Decimal('30'))
        self.assertEqual(self.product.stock_value, Decimal('30') * Decimal('45.50'))
        self.assertNotEqual(self.product.stock_value, self.product.quantity)

    def test_product_performance_row_reports_the_same_stock_value(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        rows = product_performance(self.tenant_a, today, week_start, month_start)
        row = next(r for r in rows if r['product'].pk == self.product.pk)

        self.assertEqual(row['stock_value'], Decimal('30') * Decimal('45.50'))
        self.assertNotEqual(row['stock_value'], self.product.quantity)

    def test_stock_value_scales_with_cost_price_not_just_quantity(self):
        """Two products with equal quantity but different cost_price must
        not report the same stock value -- proves quantity alone isn't
        being used as a stand-in for value."""
        cheap = make_product(self.tenant_a, name='Cheap Salt', cost_price=Decimal('5'))
        pricey = make_product(self.tenant_a, name='Pricey Saffron', cost_price=Decimal('500'))
        receive_stock(product=cheap, quantity=Decimal('30'), location=self.main_a)
        receive_stock(product=pricey, quantity=Decimal('30'), location=self.main_a)
        cheap.refresh_from_db()
        pricey.refresh_from_db()

        self.assertEqual(cheap.quantity, pricey.quantity)
        self.assertNotEqual(cheap.stock_value, pricey.stock_value)
        self.assertEqual(pricey.stock_value, cheap.stock_value * 100)


class ProductPerformanceCogsUsesSaleSnapshotTests(StockServiceTestCase):
    """COGS must come from InvoiceItem.cost_price (the price paid at sale
    time), not the product's current cost_price, so a later cost change
    doesn't rewrite historical profit."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer = Customer.objects.create(name='Regular Customer', tenant=cls.tenant_a)
        cls.product = make_product(cls.tenant_a, name='Sold Oil', cost_price=Decimal('70'))
        receive_stock(product=cls.product, quantity=Decimal('50'), location=cls.main_a)
        cls.invoice = Invoice.objects.create(
            tenant=cls.tenant_a, customer=cls.customer, total=Decimal('1000'),
        )
        cls.item = InvoiceItem.objects.create(
            tenant=cls.tenant_a, invoice=cls.invoice, product=cls.product,
            qty=Decimal('10'), price=Decimal('100'), cost_price=Decimal('70'),
            location=cls.main_a,
        )

    def test_product_totals_cogs_matches_sold_quantity_times_snapshot_cost(self):
        today = timezone.localdate()
        totals = {r['product_id']: r for r in product_totals(self.tenant_a, today, today)}
        row = totals[self.product.pk]

        self.assertEqual(row['units_sold'], Decimal('10'))
        self.assertEqual(row['revenue'], Decimal('1000'))
        self.assertEqual(row['cogs'], Decimal('700'))

    def test_product_totals_cogs_survives_a_later_cost_price_change(self):
        self.product.cost_price = Decimal('999')
        self.product.save(update_fields=['cost_price'])

        today = timezone.localdate()
        totals = {r['product_id']: r for r in product_totals(self.tenant_a, today, today)}
        row = totals[self.product.pk]

        self.assertEqual(row['cogs'], Decimal('700'))
        self.assertNotEqual(row['cogs'], row['units_sold'] * self.product.cost_price)

    def test_business_day_summary_reports_matching_revenue_and_cogs(self):
        today = timezone.localdate()
        summary = business_day_summary(self.tenant_a, today)

        self.assertEqual(summary['financial_summary']['revenue'], Decimal('1000'))
        self.assertEqual(summary['financial_summary']['cogs'], Decimal('700'))
        self.assertEqual(summary['financial_summary']['gross_profit'], Decimal('300'))
