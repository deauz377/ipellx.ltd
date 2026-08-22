"""Screen-level tests for the stock control UI.

These are deliberately shallow-but-wide: every stock URL is loaded at least
once so a missing template, a bad {% url %} or a renamed context variable
fails here rather than in front of a storekeeper. The narrow, deep tests of
what the numbers actually do live in tests_stock.py and tests_workflows.py.
"""
from decimal import Decimal

from django.urls import reverse

from tenants.models import User
from tenants.tests import TEST_PASSWORD

from .models import (
    GoodsReceipt, GoodsReceiptLine, Location, StockCount, StockTransfer,
)
from .services import available_quantity, receive_stock
from .tests_stock import StockServiceTestCase

ZERO = Decimal('0')

# Read-only screens: safe for anyone entitled to look at stock.
READ_URLS = [
    'inventory:command_centre',
    'inventory:movement_history',
    'inventory:stock_by_location',
    'inventory:receipt_list',
    'inventory:transfer_list',
    'inventory:count_list',
]

# Screens that exist to change stock, or to set up what stock hangs off.
WRITE_URLS = [
    'inventory:location_list',
    'inventory:location_create',
    'inventory:receipt_create',
    'inventory:transfer_create',
    'inventory:count_start',
]


class StockViewTestCase(StockServiceTestCase):
    """Adds the extra roles the stock screens distinguish between."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.storekeeper = User.objects.create_user(
            username='storekeeper_a', email='store_a@example.com',
            password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.INVENTORY_MANAGER, email_verified=True,
        )
        cls.accountant = User.objects.create_user(
            username='accountant_a', email='acc_a@example.com',
            password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.ACCOUNTANT, email_verified=True,
        )
        cls.seller = User.objects.create_user(
            username='seller_a', email='sell_a@example.com',
            password=TEST_PASSWORD, tenant=cls.tenant_a,
            role=User.Role.SALES_STAFF, email_verified=True,
        )

    def login(self, user):
        self.assertTrue(self.client.login(username=user.username, password=TEST_PASSWORD))


class ScreenRendersTests(StockViewTestCase):
    """Catches TemplateDoesNotExist, NoReverseMatch and context typos."""

    def test_every_stock_screen_renders_for_the_inventory_manager(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        self.login(self.storekeeper)
        for name in READ_URLS + WRITE_URLS:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_detail_screens_render(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        self.login(self.storekeeper)

        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a, received_by=self.storekeeper,
        )
        GoodsReceiptLine.objects.create(
            tenant=self.tenant_a, receipt=receipt, product=self.product_a,
            quantity_ordered=Decimal('5'), quantity_received=Decimal('5'),
            unit_cost=Decimal('60'),
        )
        count = StockCount.objects.create(
            tenant=self.tenant_a, location=self.main_a, started_by=self.storekeeper,
        )

        for url in [
            reverse('inventory:receipt_detail', args=[receipt.pk]),
            reverse('inventory:receipt_confirm', args=[receipt.pk]),
            reverse('inventory:receipt_cancel', args=[receipt.pk]),
            reverse('inventory:count_detail', args=[count.pk]),
            reverse('inventory:location_edit', args=[self.main_a.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_command_centre_shows_a_product_that_needs_reordering(self):
        # minimum_stock is 10 in the fixture, so 2 on hand is low.
        receive_stock(product=self.product_a, quantity=2, location=self.main_a)
        self.login(self.storekeeper)
        response = self.client.get(reverse('inventory:command_centre'))
        self.assertIn(self.product_a, response.context['low_stock'])
        self.assertContains(response, self.product_a.name)

    def test_movement_history_filters_by_product(self):
        other = self.product_a.__class__.objects.create(
            tenant=self.tenant_a, name='Sugar', sku='SKU-SUGAR-A',
            retail_price=Decimal('100'), wholesale_price=Decimal('90'),
            online_price=Decimal('110'), cost_price=Decimal('70'),
        )
        receive_stock(product=self.product_a, quantity=5, location=self.main_a)
        receive_stock(product=other, quantity=5, location=self.main_a)

        self.login(self.storekeeper)
        response = self.client.get(reverse('inventory:movement_history'),
                                   {'product': self.product_a.pk})
        # Asserted on the rows, not the page text: every product also appears
        # in the filter dropdown, so 'Sugar' is legitimately in the HTML.
        shown = {m.product for m in response.context['movements']}
        self.assertEqual(shown, {self.product_a})


class NavigationTests(StockViewTestCase):
    """The sidebar tells Inventory from Stock Control by one substring, so
    that grouping has to hold. A stock route added outside stock/ would
    silently light up the wrong menu entry."""

    def test_every_stock_route_lives_under_the_stock_prefix(self):
        for name in READ_URLS + WRITE_URLS:
            with self.subTest(url=name):
                self.assertIn('/inventory/stock/', reverse(name))

    def test_catalogue_routes_stay_outside_the_stock_prefix(self):
        for name in ['inventory:inventory_overview', 'inventory:product_list',
                     'inventory:supplier_list', 'inventory:product_create']:
            with self.subTest(url=name):
                self.assertNotIn('/inventory/stock/', reverse(name))

    def test_the_sidebar_offers_stock_control_to_the_storekeeper(self):
        self.login(self.storekeeper)
        response = self.client.get(reverse('inventory:command_centre'))
        self.assertContains(response, reverse('inventory:command_centre'))
        self.assertContains(response, 'Stock Control')

    def test_the_sidebar_hides_stock_control_from_sales_staff(self):
        self.login(self.seller)
        response = self.client.get(reverse('inventory:product_list'))
        self.assertNotContains(response, 'Stock Control')


class StockPermissionTests(StockViewTestCase):
    def test_sales_staff_cannot_reach_the_stock_screens(self):
        """Selling requires knowing what is available, not the right to change
        it -- availability already shows on the sales screens."""
        self.login(self.seller)
        for name in READ_URLS + WRITE_URLS:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_accountant_may_look_but_not_touch(self):
        self.login(self.accountant)
        for name in READ_URLS:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for name in WRITE_URLS:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_read_only_screens_hide_the_action_buttons(self):
        self.login(self.accountant)
        response = self.client.get(reverse('inventory:command_centre'))
        self.assertFalse(response.context['can_edit'])
        self.assertNotContains(response, 'Receive Stock')

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for name in READ_URLS + WRITE_URLS:
            with self.subTest(url=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login', response['Location'])

    def test_owner_still_gets_in(self):
        self.login(self.user_a)
        self.assertEqual(self.client.get(reverse('inventory:command_centre')).status_code, 200)

    def test_existing_product_screens_are_now_guarded_too(self):
        """These were open to any logged-in user before this phase."""
        self.login(self.seller)
        for name in ['inventory:product_create', 'inventory:supplier_create',
                     'inventory:product_import_csv']:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)


class StockTenantIsolationTests(StockViewTestCase):
    """Another tenant's stock paperwork must not be reachable by pk."""

    def test_cannot_open_another_tenants_receipt_count_or_location(self):
        other_receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_b, location=self.main_b, received_by=self.user_b,
        )
        other_count = StockCount.objects.create(
            tenant=self.tenant_b, location=self.main_b, started_by=self.user_b,
        )
        self.login(self.storekeeper)
        for url in [
            reverse('inventory:receipt_detail', args=[other_receipt.pk]),
            reverse('inventory:receipt_confirm', args=[other_receipt.pk]),
            reverse('inventory:count_detail', args=[other_count.pk]),
            reverse('inventory:location_edit', args=[self.main_b.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_listings_never_leak_another_tenants_rows(self):
        receive_stock(product=self.product_b, quantity=99, location=self.main_b)
        self.login(self.storekeeper)
        for name in ['inventory:movement_history', 'inventory:stock_by_location']:
            with self.subTest(url=name):
                self.assertNotContains(self.client.get(reverse(name)), self.product_b.name)

    def test_receipt_form_only_offers_this_tenants_products(self):
        self.login(self.storekeeper)
        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a, received_by=self.storekeeper,
        )
        form = self.client.get(
            reverse('inventory:receipt_detail', args=[receipt.pk])).context['line_form']
        self.assertIn(self.product_a, form.fields['product'].queryset)
        self.assertNotIn(self.product_b, form.fields['product'].queryset)


class StockActionTests(StockViewTestCase):
    def setUp(self):
        super().setUp()
        receive_stock(product=self.product_a, quantity=50, location=self.main_a)
        self.login(self.storekeeper)

    def _transfer(self):
        return StockTransfer.objects.create(
            tenant=self.tenant_a, product=self.product_a, quantity=Decimal('10'),
            source=self.main_a, destination=self.branch_a, requested_by=self.storekeeper,
        )

    def test_a_get_request_can_never_move_stock(self):
        """URLs get prefetched, crawled and mistyped. Only a POST may act."""
        transfer = self._transfer()
        for action in ['approve', 'dispatch', 'receive', 'cancel']:
            with self.subTest(action=action):
                self.client.get(reverse('inventory:transfer_action',
                                        args=[transfer.pk, action]))
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.PENDING)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('50'))

    def test_the_full_transfer_journey_through_the_screens(self):
        transfer = self._transfer()
        for action in ['approve', 'dispatch']:
            self.client.post(reverse('inventory:transfer_action', args=[transfer.pk, action]))

        # Dispatched but not yet received: gone from source, not yet arrived.
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('40'))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), ZERO)

        self.client.post(reverse('inventory:transfer_action', args=[transfer.pk, 'receive']))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('10'))

    def test_an_unknown_action_changes_nothing(self):
        transfer = self._transfer()
        self.client.post(reverse('inventory:transfer_action', args=[transfer.pk, 'teleport']))
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.PENDING)

    def test_confirming_a_delivery_from_the_screen_brings_stock_in(self):
        response = self.client.post(reverse('inventory:receipt_create'), {
            'location': self.main_a.pk, 'invoice_number': 'INV-9',
        })
        receipt = GoodsReceipt.objects.get(invoice_number='INV-9')
        self.assertRedirects(response, reverse('inventory:receipt_detail', args=[receipt.pk]))

        self.client.post(reverse('inventory:receipt_detail', args=[receipt.pk]), {
            'product': self.product_a.pk, 'quantity_ordered': '12',
            'quantity_received': '12', 'quantity_rejected': '0', 'unit_cost': '60',
        })
        self.assertEqual(receipt.lines.count(), 1)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('50'),
                         'a draft delivery must not touch stock')

        self.client.post(reverse('inventory:receipt_confirm', args=[receipt.pk]))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('62'))

    def test_a_line_cannot_be_added_to_a_confirmed_delivery(self):
        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a, received_by=self.storekeeper,
        )
        GoodsReceiptLine.objects.create(
            tenant=self.tenant_a, receipt=receipt, product=self.product_a,
            quantity_ordered=Decimal('4'), quantity_received=Decimal('4'),
            unit_cost=Decimal('60'),
        )
        self.client.post(reverse('inventory:receipt_confirm', args=[receipt.pk]))

        self.client.post(reverse('inventory:receipt_detail', args=[receipt.pk]), {
            'product': self.product_a.pk, 'quantity_ordered': '99',
            'quantity_received': '99', 'quantity_rejected': '0', 'unit_cost': '60',
        })
        self.assertEqual(receipt.lines.count(), 1)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('54'))

    def test_saving_a_count_records_findings_without_changing_stock(self):
        self.client.post(reverse('inventory:count_start'), {'location': self.main_a.pk})
        count = StockCount.objects.get(location=self.main_a)
        line = count.lines.get(product=self.product_a)
        self.assertEqual(line.system_quantity, Decimal('50'))

        self.client.post(reverse('inventory:count_detail', args=[count.pk]), {
            'physical_%s' % line.pk: '46',
            'reason_%s' % line.pk: 'damage',
            'note_%s' % line.pk: 'Two crates crushed',
        })
        line.refresh_from_db()
        self.assertEqual(line.physical_quantity, Decimal('46'))
        self.assertEqual(line.variance, Decimal('-4'))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('50'),
                         'counting is not adjusting -- approval is')

        self.client.post(reverse('inventory:count_action', args=[count.pk, 'submit']))
        self.client.post(reverse('inventory:count_action', args=[count.pk, 'approve']))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('46'))

    def test_a_rejected_count_leaves_stock_alone(self):
        self.client.post(reverse('inventory:count_start'), {'location': self.main_a.pk})
        count = StockCount.objects.get(location=self.main_a)
        line = count.lines.get(product=self.product_a)
        self.client.post(reverse('inventory:count_detail', args=[count.pk]),
                         {'physical_%s' % line.pk: '5'})
        self.client.post(reverse('inventory:count_action', args=[count.pk, 'submit']))
        self.client.post(reverse('inventory:count_action', args=[count.pk, 'reject']),
                         {'reason': 'That variance is not believable, recount'})

        count.refresh_from_db()
        self.assertEqual(count.status, StockCount.REJECTED)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('50'))

    def test_a_blank_count_line_stays_uncounted_rather_than_becoming_zero(self):
        """An empty box means "not counted yet", never "there are none" --
        reading it as zero would wipe out the shelf on approval."""
        self.client.post(reverse('inventory:count_start'), {'location': self.main_a.pk})
        count = StockCount.objects.get(location=self.main_a)
        line = count.lines.get(product=self.product_a)
        self.client.post(reverse('inventory:count_detail', args=[count.pk]),
                         {'physical_%s' % line.pk: ''})
        line.refresh_from_db()
        self.assertIsNone(line.physical_quantity)

        self.client.post(reverse('inventory:count_action', args=[count.pk, 'submit']))
        self.client.post(reverse('inventory:count_action', args=[count.pk, 'approve']))
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('50'))

    def test_the_accountant_cannot_post_an_action_even_knowing_the_url(self):
        transfer = self._transfer()
        self.client.logout()
        self.login(self.accountant)
        response = self.client.post(
            reverse('inventory:transfer_action', args=[transfer.pk, 'approve']))
        self.assertEqual(response.status_code, 403)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.PENDING)


class LocationScreenTests(StockViewTestCase):
    def test_adding_a_location_attaches_it_to_the_right_tenant(self):
        self.login(self.storekeeper)
        self.client.post(reverse('inventory:location_create'), {
            'name': 'Lorry Park Store', 'code': 'LPS', 'kind': 'store', 'is_active': 'on',
        })
        location = Location.objects.get(name='Lorry Park Store')
        self.assertEqual(location.tenant, self.tenant_a)

    def test_the_location_list_shows_what_is_held_at_each_one(self):
        receive_stock(product=self.product_a, quantity=17, location=self.branch_a)
        self.login(self.storekeeper)
        response = self.client.get(reverse('inventory:location_list'))
        held = {loc.name: loc.on_hand for loc in response.context['locations']}
        self.assertEqual(held['Branch Two'], Decimal('17'))
        self.assertEqual(held['Main Store'], ZERO)
