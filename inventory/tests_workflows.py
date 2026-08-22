from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .models import (
    GoodsReceipt, GoodsReceiptLine, StockCount, StockMovement, StockTransfer,
)
from .services import StockError, available_quantity, receive_stock, reconcile
from .tests_stock import StockServiceTestCase, make_product
from .workflow_services import (
    approve_count, approve_transfer, cancel_receipt, cancel_transfer,
    confirm_receipt, dispatch_transfer, receive_transfer, reject_count,
    start_count, submit_count,
)

ZERO = Decimal('0')


class GoodsReceiptTests(StockServiceTestCase):
    def _draft(self, quantity=Decimal('40'), rejected=ZERO, **line_kwargs):
        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a,
            invoice_number='INV-77', received_by=self.user_a,
        )
        GoodsReceiptLine.objects.create(
            tenant=self.tenant_a, receipt=receipt, product=self.product_a,
            quantity_ordered=quantity, quantity_received=quantity,
            quantity_rejected=rejected, unit_cost=Decimal('60'), **line_kwargs
        )
        return receipt

    def test_drafting_a_delivery_changes_no_stock(self):
        self._draft()
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, ZERO, 'paperwork alone must not move stock')

    def test_confirming_brings_stock_in(self):
        receipt = self._draft(quantity=Decimal('40'))
        confirm_receipt(receipt, user=self.user_a)

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('40'))
        movement = StockMovement.objects.get(reference_type='goods_receipt')
        self.assertEqual(movement.movement_type, StockMovement.RECEIVE)
        self.assertEqual(movement.user, self.user_a)
        self.assertTrue(reconcile(self.product_a))

    def test_confirming_twice_cannot_double_stock(self):
        """Refreshing a confirm URL would otherwise be the easiest way to
        double a business's inventory."""
        receipt = self._draft(quantity=Decimal('40'))
        confirm_receipt(receipt, user=self.user_a)
        with self.assertRaises(StockError):
            confirm_receipt(receipt, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('40'))

    def test_rejected_goods_are_recorded_but_never_stocked(self):
        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a, received_by=self.user_a,
        )
        GoodsReceiptLine.objects.create(
            tenant=self.tenant_a, receipt=receipt, product=self.product_a,
            quantity_ordered=Decimal('50'), quantity_received=Decimal('45'),
            quantity_rejected=Decimal('5'), unit_cost=Decimal('60'),
        )
        confirm_receipt(receipt, user=self.user_a)
        self.assertEqual(
            available_quantity(self.product_a, self.main_a), Decimal('45'),
            'only accepted goods reach the shelf',
        )

    def test_receiving_with_expiry_creates_a_batch(self):
        expiry = timezone.localdate() + timedelta(days=20)
        receipt = self._draft(quantity=Decimal('12'), batch_number='LOT-9', expiry_date=expiry)
        confirm_receipt(receipt, user=self.user_a)

        movement = StockMovement.objects.get(reference_type='goods_receipt')
        self.assertIsNotNone(movement.batch)
        self.assertEqual(movement.batch.batch_number, 'LOT-9')
        self.assertEqual(movement.batch.expiry_date, expiry)

    def test_empty_delivery_cannot_be_confirmed(self):
        receipt = GoodsReceipt.objects.create(
            tenant=self.tenant_a, location=self.main_a, received_by=self.user_a,
        )
        with self.assertRaises(StockError):
            confirm_receipt(receipt, user=self.user_a)

    def test_confirmed_delivery_cannot_be_cancelled(self):
        receipt = self._draft()
        confirm_receipt(receipt, user=self.user_a)
        with self.assertRaises(StockError):
            cancel_receipt(receipt, user=self.user_a)

    def test_cancelling_a_draft_leaves_stock_alone(self):
        receipt = self._draft()
        # The transition returns the authoritative row it locked and updated;
        # the instance passed in stays as the caller last saw it, which is why
        # callers use the return value rather than re-reading their own copy.
        cancelled = cancel_receipt(receipt, user=self.user_a)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, ZERO)
        self.assertEqual(cancelled.status, GoodsReceipt.CANCELLED)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, GoodsReceipt.CANCELLED)


class StockTransferWorkflowTests(StockServiceTestCase):
    def _transfer(self, quantity=Decimal('10')):
        return StockTransfer.objects.create(
            tenant=self.tenant_a, product=self.product_a, quantity=quantity,
            source=self.main_a, destination=self.branch_a, requested_by=self.user_a,
        )

    def test_full_lifecycle_moves_stock_exactly_once(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        transfer = self._transfer(Decimal('10'))

        approve_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('30'),
                         'approval alone must not move stock')

        dispatch_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('20'))
        self.assertEqual(available_quantity(self.product_a, self.branch_a), ZERO,
                         'goods in transit belong to neither end')

        receive_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('10'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('30'),
                         'a transfer moves stock, it does not create or destroy it')
        self.assertTrue(reconcile(self.product_a))

    def test_cannot_dispatch_before_approval(self):
        receive_stock(product=self.product_a, quantity=30, location=self.main_a)
        transfer = self._transfer()
        with self.assertRaises(StockError):
            dispatch_transfer(transfer, user=self.user_a)

    def test_cannot_dispatch_more_than_the_source_holds(self):
        receive_stock(product=self.product_a, quantity=4, location=self.main_a)
        transfer = self._transfer(Decimal('9'))
        approve_transfer(transfer, user=self.user_a)
        with self.assertRaises(StockError):
            dispatch_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('4'))

    def test_cancelling_in_transit_returns_the_goods(self):
        """Otherwise the units simply vanish from the business."""
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        transfer = self._transfer(Decimal('8'))
        approve_transfer(transfer, user=self.user_a)
        dispatch_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('12'))

        cancel_transfer(transfer, user=self.user_a, reason='Lorry broke down')
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('20'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.quantity, Decimal('20'))
        self.assertTrue(reconcile(self.product_a))

    def test_cancelling_before_dispatch_moves_nothing(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        transfer = self._transfer()
        cancel_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('20'))

    def test_received_transfer_cannot_be_cancelled(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        transfer = self._transfer(Decimal('5'))
        approve_transfer(transfer, user=self.user_a)
        dispatch_transfer(transfer, user=self.user_a)
        receive_transfer(transfer, user=self.user_a)
        with self.assertRaises(StockError):
            cancel_transfer(transfer, user=self.user_a)

    def test_receiving_twice_cannot_duplicate_stock(self):
        receive_stock(product=self.product_a, quantity=20, location=self.main_a)
        transfer = self._transfer(Decimal('5'))
        approve_transfer(transfer, user=self.user_a)
        dispatch_transfer(transfer, user=self.user_a)
        receive_transfer(transfer, user=self.user_a)
        with self.assertRaises(StockError):
            receive_transfer(transfer, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('5'))


class StockCountWorkflowTests(StockServiceTestCase):
    def _counted(self, system=Decimal('100'), physical=Decimal('96'), reason='spoilage'):
        receive_stock(product=self.product_a, quantity=system, location=self.main_a)
        count = start_count(tenant=self.tenant_a, location=self.main_a, user=self.user_a)
        line = count.lines.get(product=self.product_a)
        line.physical_quantity = physical
        line.reason = reason
        line.save()
        return count, line

    def test_counting_snapshots_the_system_figure(self):
        receive_stock(product=self.product_a, quantity=100, location=self.main_a)
        count = start_count(tenant=self.tenant_a, location=self.main_a, user=self.user_a)
        line = count.lines.get(product=self.product_a)
        self.assertEqual(line.system_quantity, Decimal('100'))
        self.assertFalse(line.is_counted)
        self.assertEqual(line.variance, ZERO)

    def test_variance_is_calculated_but_stock_is_untouched_until_approval(self):
        count, line = self._counted(Decimal('100'), Decimal('96'))
        self.assertEqual(line.variance, Decimal('-4'))
        self.assertEqual(
            available_quantity(self.product_a, self.main_a), Decimal('100'),
            'counting alone must never change stock',
        )

        submit_count(count, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('100'),
                         'submitting is still not approving')

        approve_count(count, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('96'))

        adjustment = StockMovement.objects.get(reference_type='stock_count')
        self.assertEqual(adjustment.quantity_delta, Decimal('-4'))
        self.assertEqual(adjustment.quantity_before, Decimal('100'))
        self.assertEqual(adjustment.quantity_after, Decimal('96'))
        self.assertEqual(adjustment.reason, 'Spoilage')
        self.assertTrue(reconcile(self.product_a))

    def test_rejecting_a_count_changes_nothing(self):
        count, _line = self._counted(Decimal('100'), Decimal('40'))
        submit_count(count, user=self.user_a)
        rejected = reject_count(count, user=self.user_a, reason='Recount required')

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('100'))
        self.assertEqual(rejected.status, StockCount.REJECTED)
        self.assertEqual(rejected.rejection_reason, 'Recount required')
        count.refresh_from_db()
        self.assertEqual(count.status, StockCount.REJECTED)
        self.assertFalse(StockMovement.objects.filter(reference_type='stock_count').exists())

    def test_a_surplus_is_recorded_as_readily_as_a_shortfall(self):
        count, line = self._counted(Decimal('50'), Decimal('53'), reason='counting_error')
        self.assertEqual(line.variance, Decimal('3'))
        submit_count(count, user=self.user_a)
        approve_count(count, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('53'))

    def test_uncounted_lines_are_left_alone(self):
        receive_stock(product=self.product_a, quantity=10, location=self.main_a)
        other = make_product(self.tenant_a, name='Untouched', sku='UNTOUCHED-1')
        receive_stock(product=other, quantity=7, location=self.main_a)

        count = start_count(tenant=self.tenant_a, location=self.main_a, user=self.user_a)
        line = count.lines.get(product=self.product_a)
        line.physical_quantity = Decimal('8')
        line.save()

        submit_count(count, user=self.user_a)
        approve_count(count, user=self.user_a)

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('8'))
        self.assertEqual(available_quantity(other, self.main_a), Decimal('7'),
                         'a product nobody counted must not be zeroed')

    def test_cannot_submit_without_counting_anything(self):
        receive_stock(product=self.product_a, quantity=10, location=self.main_a)
        count = start_count(tenant=self.tenant_a, location=self.main_a, user=self.user_a)
        with self.assertRaises(StockError):
            submit_count(count, user=self.user_a)

    def test_cannot_approve_a_count_that_was_never_submitted(self):
        count, _ = self._counted()
        with self.assertRaises(StockError):
            approve_count(count, user=self.user_a)

    def test_approving_twice_cannot_apply_the_variance_again(self):
        count, _ = self._counted(Decimal('100'), Decimal('96'))
        submit_count(count, user=self.user_a)
        approve_count(count, user=self.user_a)
        with self.assertRaises(StockError):
            approve_count(count, user=self.user_a)
        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('96'))

    def test_count_only_covers_its_own_location(self):
        receive_stock(product=self.product_a, quantity=10, location=self.main_a)
        receive_stock(product=self.product_a, quantity=6, location=self.branch_a)

        count = start_count(tenant=self.tenant_a, location=self.branch_a, user=self.user_a)
        line = count.lines.get(product=self.product_a)
        self.assertEqual(line.system_quantity, Decimal('6'), 'counts the branch, not the whole business')

        line.physical_quantity = Decimal('5')
        line.save()
        submit_count(count, user=self.user_a)
        approve_count(count, user=self.user_a)

        self.assertEqual(available_quantity(self.product_a, self.main_a), Decimal('10'),
                         'the other location is untouched')
        self.assertEqual(available_quantity(self.product_a, self.branch_a), Decimal('5'))
