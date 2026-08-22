"""The same business must show the same stock figures to everyone.

Four screens report stock: the main dashboard, the CEO dashboard, the
Inventory Overview and Stock Control. They each used to work the numbers out
for themselves, and they disagreed -- one called a product "low" if it held
less than the catalogue average, another valued stock as the sum of every
price multiplied by the sum of every quantity. An Owner and a Storekeeper
comparing notes were reading different books.

These tests hold the four screens against one another. If a future change
gives any screen its own rule again, this file fails.
"""
from decimal import Decimal

from django.urls import reverse

from tenants.models import User
from tenants.tests import TEST_PASSWORD

from .models import Product
from .services import (
    low_stock_queryset, out_of_stock_queryset, receive_stock, stock_value,
)
from .tests_stock import StockServiceTestCase, make_product

ZERO = Decimal('0')


class FigureTestCase(StockServiceTestCase):
    """A catalogue with one product in each state that the figures care about."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # product_a comes from the parent fixture: minimum_stock 10, cost 70.
        cls.healthy = make_product(cls.tenant_a, name='Healthy Rice',
                                   cost_price=Decimal('50'), minimum_stock=Decimal('10'))
        cls.low = make_product(cls.tenant_a, name='Low Salt',
                               cost_price=Decimal('20'), minimum_stock=Decimal('10'))
        cls.custom_level = make_product(cls.tenant_a, name='Custom Level Flour',
                                        cost_price=Decimal('30'),
                                        minimum_stock=Decimal('2'),
                                        reorder_level=Decimal('25'))
        cls.empty = make_product(cls.tenant_a, name='Empty Sugar',
                                 cost_price=Decimal('40'), minimum_stock=Decimal('10'))
        cls.retired = make_product(cls.tenant_a, name='Retired Soap',
                                   cost_price=Decimal('15'), minimum_stock=Decimal('10'),
                                   is_active=False)

        cls.manager = User.objects.create_user(
            username='manager_fig', email='mgr_fig@example.com',
            password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.MANAGER, email_verified=True,
        )

    def setUp(self):
        super().setUp()
        receive_stock(product=self.healthy, quantity=100, location=self.main_a)
        receive_stock(product=self.low, quantity=4, location=self.main_a)
        receive_stock(product=self.custom_level, quantity=20, location=self.main_a)
        receive_stock(product=self.retired, quantity=8, location=self.main_a)
        # self.empty and self.product_a are deliberately left at zero.


class DefinitionTests(FigureTestCase):
    def test_low_stock_means_at_or_below_the_reorder_level(self):
        low = set(low_stock_queryset(self.tenant_a))
        self.assertIn(self.low, low)
        self.assertNotIn(self.healthy, low)

    def test_a_products_own_reorder_level_beats_the_minimum_stock_fallback(self):
        """20 on hand is comfortably above minimum_stock of 2, but below the
        reorder_level of 25 that was set for this product -- the specific
        setting has to win, or the field does nothing."""
        self.assertIn(self.custom_level, low_stock_queryset(self.tenant_a))

    def test_out_of_stock_is_not_also_counted_as_low_stock(self):
        low = set(low_stock_queryset(self.tenant_a))
        out = set(out_of_stock_queryset(self.tenant_a))
        self.assertIn(self.empty, out)
        self.assertNotIn(self.empty, low)
        self.assertEqual(low & out, set(), 'a product in both states doubles every alert')

    def test_retired_products_raise_no_reorder_alert(self):
        self.assertNotIn(self.retired, low_stock_queryset(self.tenant_a))
        self.assertNotIn(self.retired, out_of_stock_queryset(self.tenant_a))

    def test_stock_is_valued_at_cost_not_retail(self):
        """Valuing stock at what you hope to sell it for books profit that has
        not happened."""
        expected = sum(
            (p.quantity * p.cost_price
             for p in Product.objects.filter(tenant=self.tenant_a, is_active=True)),
            ZERO,
        )
        self.assertEqual(stock_value(self.tenant_a), expected)
        self.assertGreater(expected, ZERO, 'the fixture must actually hold stock')

    def test_the_valuation_is_a_sum_of_products_not_a_product_of_sums(self):
        """The old arithmetic was Sum(price) * Sum(quantity), which grows with
        the size of the catalogue rather than with what is on the shelf."""
        product_of_sums = (
            sum((p.cost_price for p in Product.objects.filter(
                tenant=self.tenant_a, is_active=True)), ZERO)
            * sum((p.quantity for p in Product.objects.filter(
                tenant=self.tenant_a, is_active=True)), ZERO)
        )
        self.assertNotEqual(stock_value(self.tenant_a), product_of_sums)

    def test_another_tenants_stock_is_never_counted(self):
        receive_stock(product=self.product_b, quantity=500, location=self.main_b)
        before = stock_value(self.tenant_a)
        receive_stock(product=self.product_b, quantity=500, location=self.main_b)
        self.assertEqual(stock_value(self.tenant_a), before)
        self.assertNotIn(self.product_b, low_stock_queryset(self.tenant_a))


class ScreensAgreeTests(FigureTestCase):
    """Load every screen that reports stock, as one user, and compare."""

    def setUp(self):
        super().setUp()
        self.assertTrue(self.client.login(username=self.user_a.username,
                                          password=TEST_PASSWORD))

    def _contexts(self):
        return {
            'main dashboard': self.client.get(reverse('dashboard_overview')).context,
            'CEO dashboard': self.client.get(reverse('ceo_dashboard')).context,
            'inventory overview': self.client.get(
                reverse('inventory:inventory_overview')).context,
            'stock control': self.client.get(
                reverse('inventory:command_centre')).context,
        }

    def test_every_screen_reports_the_same_stock_value(self):
        ctx = self._contexts()
        expected = stock_value(self.tenant_a)
        self.assertEqual(ctx['CEO dashboard']['inventory_value'], expected)
        self.assertEqual(ctx['inventory overview']['total_stock_value'], expected)
        self.assertEqual(ctx['stock control']['stock_value'], expected)

    def test_every_screen_reports_the_same_low_stock_count(self):
        ctx = self._contexts()
        expected = low_stock_queryset(self.tenant_a).count()
        self.assertEqual(ctx['main dashboard']['low_stock_count'], expected)
        self.assertEqual(ctx['CEO dashboard']['low_stock_count'], expected)
        self.assertEqual(ctx['inventory overview']['low_stock_products'], expected)
        self.assertEqual(len(ctx['stock control']['low_stock']), expected)

    def test_every_screen_names_the_same_low_stock_products(self):
        """Matching counts are not enough -- two screens can agree on how many
        while disagreeing on which.

        The dashboards show a short list rather than all of them, so enough
        low products are created here to make that truncation bite. Each
        screen must show the *most urgent* ones: the same ordering, cut at a
        different length, never a different set.
        """
        for i in range(8):
            extra = make_product(self.tenant_a, name=f'Scarce Item {i}',
                                 cost_price=Decimal('10'), minimum_stock=Decimal('50'))
            receive_stock(product=extra, quantity=Decimal(str(i + 1)),
                          location=self.main_a)

        canonical = list(low_stock_queryset(self.tenant_a))
        self.assertGreater(len(canonical), 8, 'the slices must actually truncate')

        ctx = self._contexts()
        for screen, key in [('main dashboard', 'low_stock_products'),
                            ('CEO dashboard', 'low_stock_products'),
                            ('inventory overview', 'low_stock_alerts'),
                            ('stock control', 'low_stock')]:
            with self.subTest(screen=screen):
                shown = list(ctx[screen][key])
                self.assertEqual(shown, canonical[:len(shown)])

    def test_the_main_dashboard_does_not_call_purchases_a_stock_value(self):
        """That key fed a tile labelled "Total Purchases"; naming it
        stock_value is how the four screens got out of step to begin with."""
        context = self.client.get(reverse('dashboard_overview')).context
        self.assertIn('total_purchases', context)

    def test_the_figures_hold_after_stock_actually_moves(self):
        from .services import issue_stock
        issue_stock(product=self.healthy, quantity=95, location=self.main_a,
                    user=self.user_a)

        ctx = self._contexts()
        self.assertIn(self.healthy, low_stock_queryset(self.tenant_a),
                      '5 left against a minimum of 10 is low')
        expected_value = stock_value(self.tenant_a)
        self.assertEqual(ctx['CEO dashboard']['inventory_value'], expected_value)
        self.assertEqual(ctx['inventory overview']['total_stock_value'], expected_value)
        self.assertEqual(ctx['stock control']['stock_value'], expected_value)
        self.assertEqual(ctx['main dashboard']['low_stock_count'],
                         len(ctx['stock control']['low_stock']))


class RoleAgreementTests(FigureTestCase):
    """Two people in the same business, on the same screen, see one number."""

    def test_owner_and_manager_see_the_same_stock_control_figures(self):
        seen = []
        for user in [self.user_a, self.manager]:
            self.client.login(username=user.username, password=TEST_PASSWORD)
            context = self.client.get(reverse('inventory:command_centre')).context
            seen.append((
                context['stock_value'],
                len(context['low_stock']),
                len(context['out_of_stock']),
                context['total_products'],
            ))
            self.client.logout()
        self.assertEqual(seen[0], seen[1])

    def test_the_owners_two_dashboards_agree_with_each_other(self):
        self.client.login(username=self.user_a.username, password=TEST_PASSWORD)
        main = self.client.get(reverse('dashboard_overview')).context
        ceo = self.client.get(reverse('ceo_dashboard')).context
        self.assertEqual(main['low_stock_count'], ceo['low_stock_count'])
        self.assertEqual(set(main['low_stock_products']),
                         set(ceo['low_stock_products']))
