"""State transitions for receiving, transfers and stock counts.

Each function is the *only* way its workflow touches stock, and each one goes
through inventory.services rather than writing quantities itself -- so the
ledger and the audit trail stay complete no matter which screen the change
came from.

The recurring rule: paperwork is free, stock movement is not. Drafting a
receipt, requesting a transfer or counting a shelf changes nothing. Only
confirm / dispatch / receive / approve move stock, and each is guarded so it
cannot run twice.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    GoodsReceipt, StockCount, StockCountLine, StockMovement, StockTransfer,
)
from .services import (
    StockError, available_quantity, receive_stock, record_movement,
)

ZERO = Decimal('0')


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------

@transaction.atomic
def confirm_receipt(receipt, user=None):
    """Book a delivery into stock.

    Guarded against double-confirmation, which would otherwise be the easiest
    way to double a business's inventory: refreshing a confirm URL.
    """
    locked = GoodsReceipt.objects.select_for_update().get(pk=receipt.pk)
    if locked.status != GoodsReceipt.DRAFT:
        raise StockError('This delivery has already been dealt with.')

    lines = list(locked.lines.select_related('product'))
    if not lines:
        raise StockError('Add at least one line before confirming a delivery.')

    for line in lines:
        if line.quantity_received <= ZERO:
            continue  # a line rejected in full brings nothing in
        receive_stock(
            product=line.product, quantity=line.quantity_received,
            location=locked.location, user=user,
            batch_number=line.batch_number, expiry_date=line.expiry_date,
            cost_price=line.unit_cost or None,
            reason=f'Delivery {locked.invoice_number or locked.pk}',
            reference_type='goods_receipt', reference_id=locked.pk,
        )

    locked.status = GoodsReceipt.CONFIRMED
    locked.confirmed_by = user
    locked.confirmed_at = timezone.now()
    locked.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
    return locked


@transaction.atomic
def cancel_receipt(receipt, user=None):
    """Discard a draft delivery. Confirmed deliveries cannot be cancelled --
    the stock is already on the shelf, so the correction is a stock count or a
    write-off, both of which leave a record.

    The status is re-read under lock rather than trusting the instance handed
    in: a caller holding an object from before a confirm would otherwise see a
    stale 'draft' and be allowed to cancel a delivery already in stock.
    """
    locked = GoodsReceipt.objects.select_for_update().get(pk=receipt.pk)
    if locked.status != GoodsReceipt.DRAFT:
        raise StockError('Only a draft delivery can be cancelled.')
    locked.status = GoodsReceipt.CANCELLED
    locked.save(update_fields=['status'])
    return locked


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

@transaction.atomic
def approve_transfer(transfer, user=None):
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.PENDING:
        raise StockError('Only a pending transfer can be approved.')
    locked.status = StockTransfer.APPROVED
    locked.approved_by = user
    locked.save(update_fields=['status', 'approved_by'])
    return locked


@transaction.atomic
def dispatch_transfer(transfer, user=None):
    """Send the goods: stock leaves the source now.

    Deliberately not credited to the destination yet -- goods on a lorry are
    not sellable at either end, and pretending otherwise is how the same units
    get sold twice.
    """
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.APPROVED:
        raise StockError('Approve the transfer before dispatching it.')

    on_hand = available_quantity(locked.product, locked.source)
    if on_hand < locked.quantity:
        raise StockError(
            f'Not enough {locked.product.name} at {locked.source.name}: '
            f'{on_hand} available, {locked.quantity} requested.'
        )

    record_movement(
        product=locked.product, location=locked.source, batch=None,
        delta=-locked.quantity, movement_type=StockMovement.TRANSFER_OUT,
        user=user, reason=f'Transfer to {locked.destination.name}',
        reference_type='transfer', reference_id=locked.pk,
    )
    locked.status = StockTransfer.IN_TRANSIT
    locked.dispatched_at = timezone.now()
    locked.save(update_fields=['status', 'dispatched_at'])
    return locked


@transaction.atomic
def receive_transfer(transfer, user=None):
    """Book the goods in at the far end, completing the move."""
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status != StockTransfer.IN_TRANSIT:
        raise StockError('Only a transfer that is in transit can be received.')

    record_movement(
        product=locked.product, location=locked.destination, batch=None,
        delta=locked.quantity, movement_type=StockMovement.TRANSFER_IN,
        user=user, reason=f'Transfer from {locked.source.name}',
        reference_type='transfer', reference_id=locked.pk,
    )
    locked.status = StockTransfer.RECEIVED
    locked.received_by = user
    locked.received_at = timezone.now()
    locked.save(update_fields=['status', 'received_by', 'received_at'])
    return locked


@transaction.atomic
def cancel_transfer(transfer, user=None, reason=''):
    """Cancel a transfer, returning stock to the source if it already left.

    A transfer cancelled in transit must put the goods back, otherwise the
    units simply vanish from the business.
    """
    locked = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.status in (StockTransfer.RECEIVED, StockTransfer.CANCELLED):
        raise StockError('This transfer can no longer be cancelled.')

    if locked.status == StockTransfer.IN_TRANSIT:
        record_movement(
            product=locked.product, location=locked.source, batch=None,
            delta=locked.quantity, movement_type=StockMovement.TRANSFER_IN,
            user=user, reason=reason or 'Transfer cancelled in transit',
            reference_type='transfer', reference_id=locked.pk,
        )

    locked.status = StockTransfer.CANCELLED
    locked.notes = (locked.notes + ' ' + reason).strip()[:255]
    locked.save(update_fields=['status', 'notes'])
    return locked


# ---------------------------------------------------------------------------
# Stock counts
# ---------------------------------------------------------------------------

def start_count(*, tenant, location, user=None, products=None):
    """Open a stock take, snapshotting what the system currently believes.

    The snapshot matters: without it the variance would be measured against a
    number that may have moved while the shelf was being counted.
    """
    from .models import Product

    count = StockCount.objects.create(
        tenant=tenant, location=location, started_by=user, status=StockCount.DRAFT,
    )
    if products is None:
        products = Product.objects.filter(tenant=tenant, is_active=True)

    for product in products:
        StockCountLine.objects.create(
            tenant=tenant, count=count, product=product,
            system_quantity=available_quantity(product, location),
        )
    return count


@transaction.atomic
def submit_count(count, user=None):
    locked = StockCount.objects.select_for_update().get(pk=count.pk)
    if locked.status != StockCount.DRAFT:
        raise StockError('This count has already been submitted.')
    if not any(line.is_counted for line in locked.lines.all()):
        raise StockError('Enter at least one physical count first.')
    locked.status = StockCount.SUBMITTED
    locked.submitted_by = user
    locked.submitted_at = timezone.now()
    locked.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    return locked


@transaction.atomic
def approve_count(count, user=None):
    """Turn the counted differences into adjustment movements.

    This is the only point at which a count changes stock, and each line
    becomes its own movement carrying the counter's stated reason -- so a
    shortfall is always explained rather than silently absorbed.
    """
    locked = StockCount.objects.select_for_update().get(pk=count.pk)
    if locked.status != StockCount.SUBMITTED:
        raise StockError('Only a submitted count can be approved.')

    for line in locked.lines.select_related('product'):
        if not line.is_counted or line.variance == ZERO:
            continue
        record_movement(
            product=line.product, location=locked.location, batch=None,
            delta=line.variance, movement_type=StockMovement.ADJUSTMENT,
            user=user,
            reason=line.get_reason_display() if line.reason else 'Stock count adjustment',
            reference_type='stock_count', reference_id=locked.pk,
            # A count is the authority on what is physically there, so it may
            # correct a negative that earlier bad data produced.
            allow_negative=True,
        )

    locked.status = StockCount.APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    locked.save(update_fields=['status', 'approved_by', 'approved_at'])
    return locked


@transaction.atomic
def reject_count(count, user=None, reason=''):
    """Reject a submitted count without touching stock -- the whole point of
    requiring approval."""
    locked = StockCount.objects.select_for_update().get(pk=count.pk)
    if locked.status != StockCount.SUBMITTED:
        raise StockError('Only a submitted count can be rejected.')
    locked.status = StockCount.REJECTED
    locked.approved_by = user
    locked.rejection_reason = reason
    locked.save(update_fields=['status', 'approved_by', 'rejection_reason'])
    return locked
