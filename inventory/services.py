"""The only sanctioned way to change stock.

Every stock change goes through `record_movement`, which in one atomic step:
locks the affected StockLevel row, applies the delta, refreshes the
Product.quantity cache, and writes a StockMovement recording who did it, why,
and the before/after quantities.

Nothing else in the codebase may assign Product.quantity or StockLevel.quantity
directly. Before this module existed, stock was mutated inline in two views
with raw F() expressions and a third view forgot to do it at all -- which is
how deleting an invoice could increase stock that had never been deducted.
Funnelling everything through one function is what makes that class of bug
impossible rather than merely fixed once.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Batch, Location, Product, StockLevel, StockMovement

ZERO = Decimal('0')


class StockError(Exception):
    """Raised when a stock operation cannot be completed. Callers should catch
    this and show the message -- it is written to be read by a shopkeeper."""


def default_location(tenant):
    """The location stock lands in when the caller does not name one.

    Falls back to any active location, then creates one, so a tenant can never
    be left unable to record stock because of missing setup.
    """
    if tenant is None:
        raise StockError('Cannot record stock without a business.')

    location = Location.objects.filter(tenant=tenant, is_default=True).first()
    if location is None:
        location = Location.objects.filter(tenant=tenant, is_active=True).order_by('pk').first()
    if location is None:
        location = Location.objects.create(
            tenant=tenant, name='Main Store', kind='store', is_default=True,
        )
    return location


def _refresh_product_cache(product):
    """Recompute Product.quantity from the StockLevel rows that own the truth.

    Recomputed by aggregate rather than incremented, so the cache cannot drift
    away from the levels even if something goes wrong upstream.
    """
    total = StockLevel.objects.filter(product=product).aggregate(t=Sum('quantity'))['t'] or ZERO
    # update() rather than save() to avoid firing signals and to keep this a
    # single statement inside the surrounding transaction.
    type(product).objects.filter(pk=product.pk).update(quantity=total)
    product.quantity = total
    return total


@transaction.atomic
def record_movement(*, product, location=None, batch=None, delta, movement_type,
                    user=None, reason='', reference_type='', reference_id='',
                    allow_negative=False):
    """Apply `delta` to one (product, location, batch) and log it.

    Returns the created StockMovement. Raises StockError if the change would
    take that specific bucket negative, unless `allow_negative` is set -- a
    correction after a bad count is the only legitimate reason to.
    """
    if delta is None:
        raise StockError('No quantity given.')
    delta = Decimal(str(delta))
    if delta == ZERO:
        raise StockError('Quantity must not be zero.')

    tenant = product.tenant
    location = location or default_location(tenant)

    if location.tenant_id != product.tenant_id:
        # Belt and braces: a location from another business would silently
        # move stock between tenants.
        raise StockError('That location belongs to a different business.')
    if batch is not None and batch.product_id != product.pk:
        raise StockError('That batch belongs to a different product.')

    level, _created = StockLevel.objects.select_for_update().get_or_create(
        product=product, location=location, batch=batch,
        defaults={'tenant': tenant, 'quantity': ZERO},
    )

    before = level.quantity
    after = before + delta
    if after < ZERO and not allow_negative:
        where = location.name
        raise StockError(
            f'Not enough {product.name} at {where}: {before} available, {abs(delta)} requested.'
        )

    level.quantity = after
    level.save(update_fields=['quantity', 'updated_at'])
    _refresh_product_cache(product)

    return StockMovement.objects.create(
        tenant=tenant, product=product, location=location, batch=batch,
        movement_type=movement_type, quantity_delta=delta,
        quantity_before=before, quantity_after=after,
        reason=reason, user=user,
        reference_type=reference_type, reference_id=str(reference_id or ''),
    )


def receive_stock(*, product, quantity, location=None, user=None, batch_number='',
                  expiry_date=None, cost_price=None, reason='', reference_type='',
                  reference_id=''):
    """Bring stock in, creating a Batch when the product tracks expiry.

    A batch is created whenever a batch number or expiry is supplied, even for
    products not marked as tracking expiry -- recording what was actually
    received is never wrong.
    """
    quantity = Decimal(str(quantity))
    if quantity <= ZERO:
        raise StockError('Received quantity must be greater than zero.')

    batch = None
    if batch_number or expiry_date or product.tracks_expiry:
        if product.tracks_expiry and not expiry_date:
            raise StockError(f'{product.name} is tracked by expiry, so an expiry date is required.')
        batch = Batch.objects.create(
            tenant=product.tenant, product=product,
            batch_number=batch_number, expiry_date=expiry_date,
            cost_price=cost_price if cost_price is not None else product.cost_price,
        )

    return record_movement(
        product=product, location=location, batch=batch, delta=quantity,
        movement_type=StockMovement.RECEIVE, user=user,
        reason=reason, reference_type=reference_type, reference_id=reference_id,
    )


def available_quantity(product, location=None):
    """How much of a product is on hand, optionally at one location."""
    levels = StockLevel.objects.filter(product=product)
    if location is not None:
        levels = levels.filter(location=location)
    return levels.aggregate(t=Sum('quantity'))['t'] or ZERO


def issue_stock(*, product, quantity, location=None, user=None,
                movement_type=StockMovement.SALE, reason='',
                reference_type='', reference_id=''):
    """Take stock out, consuming batches by First Expiry First Out.

    Returns the list of movements created -- one per batch drawn from, since a
    single sale may span several lots.
    """
    quantity = Decimal(str(quantity))
    if quantity <= ZERO:
        raise StockError('Issued quantity must be greater than zero.')

    tenant = product.tenant
    location = location or default_location(tenant)

    on_hand = available_quantity(product, location)
    if on_hand < quantity:
        raise StockError(
            f'Not enough {product.name} at {location.name}: {on_hand} available, {quantity} requested.'
        )

    movements = []
    remaining = quantity

    with transaction.atomic():
        # FEFO: nearest expiry first, then oldest received. Batchless stock is
        # taken last, so dated lots are always cleared before undated ones.
        levels = list(
            StockLevel.objects.select_for_update()
            .filter(product=product, location=location, quantity__gt=ZERO)
            .select_related('batch')
            .order_by(
                models_expiry_ordering(),
                'batch__expiry_date',
                'batch__received_at',
                'pk',
            )
        )

        for level in levels:
            if remaining <= ZERO:
                break
            take = min(level.quantity, remaining)
            movements.append(record_movement(
                product=product, location=location, batch=level.batch, delta=-take,
                movement_type=movement_type, user=user, reason=reason,
                reference_type=reference_type, reference_id=reference_id,
            ))
            remaining -= take

        if remaining > ZERO:
            # Should be unreachable given the pre-check, but a concurrent sale
            # could have taken stock between the check and the lock.
            raise StockError(
                f'Not enough {product.name} at {location.name} to complete this.'
            )

    return movements


def models_expiry_ordering():
    """Order batchless stock last without relying on database NULL ordering,
    which differs between SQLite (dev) and PostgreSQL (production)."""
    from django.db.models import Case, IntegerField, Value, When
    return Case(
        When(batch__isnull=True, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    ).asc()


def return_stock(*, product, quantity, location=None, user=None, reason='',
                 reference_type='', reference_id=''):
    """Put stock back after a sale is reversed (an invoice deleted, a return).

    Goes back as unbatched stock deliberately: which lot a returned item came
    from is not knowable from the sale record, and inventing a batch would put
    a false expiry date on real stock.
    """
    quantity = Decimal(str(quantity))
    if quantity <= ZERO:
        raise StockError('Returned quantity must be greater than zero.')
    return record_movement(
        product=product, location=location, batch=None, delta=quantity,
        movement_type=StockMovement.SALE_REVERSAL, user=user, reason=reason,
        reference_type=reference_type, reference_id=reference_id,
    )


def adjust_stock(*, product, location, new_quantity, user=None, reason='',
                 reference_type='stock_count', reference_id=''):
    """Set a location's stock for a product to a counted figure.

    Records the difference as a single adjustment movement rather than
    overwriting the number, so a stock count leaves an explanation behind
    instead of a silent change.
    """
    new_quantity = Decimal(str(new_quantity))
    if new_quantity < ZERO:
        raise StockError('Counted quantity cannot be negative.')

    current = available_quantity(product, location)
    delta = new_quantity - current
    if delta == ZERO:
        return None

    return record_movement(
        product=product, location=location, batch=None, delta=delta,
        movement_type=StockMovement.ADJUSTMENT, user=user,
        reason=reason or 'Stock count adjustment',
        reference_type=reference_type, reference_id=reference_id,
        allow_negative=True,
    )


@transaction.atomic
def transfer_stock(*, product, quantity, source, destination, user=None, reason='',
                   reference_type='transfer', reference_id=''):
    """Move stock between two locations as a matched out/in pair.

    Both halves happen or neither does, so stock cannot evaporate in transit.
    """
    if source.pk == destination.pk:
        raise StockError('Source and destination must be different locations.')
    if source.tenant_id != destination.tenant_id:
        raise StockError('Cannot transfer between different businesses.')

    out_movements = issue_stock(
        product=product, quantity=quantity, location=source, user=user,
        movement_type=StockMovement.TRANSFER_OUT, reason=reason,
        reference_type=reference_type, reference_id=reference_id,
    )
    in_movement = record_movement(
        product=product, location=destination, batch=None,
        delta=Decimal(str(quantity)), movement_type=StockMovement.TRANSFER_IN,
        user=user, reason=reason,
        reference_type=reference_type, reference_id=reference_id,
    )
    return out_movements, in_movement


def write_off(*, product, quantity, location=None, user=None,
              movement_type=StockMovement.DAMAGE, reason=''):
    """Remove stock that is damaged or expired -- lost, not sold."""
    return issue_stock(
        product=product, quantity=quantity, location=location, user=user,
        movement_type=movement_type, reason=reason, reference_type='write_off',
    )


def reconcile(product):
    """True when the cache, the levels and the ledger all agree for a product.

    Used by tests and by an ops check: if these ever disagree, something wrote
    stock without going through this module.
    """
    levels_total = StockLevel.objects.filter(product=product).aggregate(
        t=Sum('quantity'))['t'] or ZERO
    ledger_total = StockMovement.objects.filter(product=product).aggregate(
        t=Sum('quantity_delta'))['t'] or ZERO
    product.refresh_from_db(fields=['quantity'])
    return product.quantity == levels_total == ledger_total


def expiring_batches(tenant, within_days=30, location=None):
    """Batches with stock still on hand, expiring within `within_days`.

    Only batches that still hold stock are returned -- an expired lot already
    sold or written off is not something anyone needs to act on.
    """
    today = timezone.localdate()
    cutoff = today + timezone.timedelta(days=within_days)
    levels = StockLevel.objects.filter(
        tenant=tenant, quantity__gt=ZERO,
        batch__isnull=False, batch__expiry_date__lte=cutoff,
    ).select_related('batch', 'product', 'location')
    if location is not None:
        levels = levels.filter(location=location)
    return levels.order_by('batch__expiry_date')


# ---------------------------------------------------------------------------
# Shared figures
# ---------------------------------------------------------------------------
# Every screen that shows a stock number reads it from here.
#
# They used to each carry their own rule, and the same business showed a
# different answer depending on who was looking: the Inventory Overview called
# a product "low" if it held less than the catalogue average (so roughly half
# the catalogue was always low) and valued stock as the sum of all prices times
# the sum of all quantities, which is not a valuation of anything; the main
# dashboard's "stock value" was actually the running total of supplier orders;
# only the CEO dashboard had the arithmetic right. An Owner and a Storekeeper
# comparing notes would have been reading three different sets of books.

def stock_products(tenant):
    """The product set every stock figure is measured over.

    Retired products are left out: you do not reorder something you have
    stopped selling, and counting it would make the alerts unactionable.
    """
    return Product.objects.filter(tenant=tenant, is_active=True)


def _with_threshold(queryset):
    # reorder_level is the newer per-product setting; minimum_stock is the
    # original field and stays the fallback, so products predating the
    # inventory upgrade keep the level they were set up with.
    return queryset.annotate(threshold=Coalesce('reorder_level', 'minimum_stock'))


def low_stock_queryset(tenant):
    """On hand, but at or below the reorder level.

    Out-of-stock is deliberately excluded: it is a separate and more urgent
    state, and counting a product in both would double every alert.
    """
    return _with_threshold(stock_products(tenant)).filter(
        quantity__gt=ZERO, quantity__lte=F('threshold'),
    ).order_by('quantity')


def out_of_stock_queryset(tenant):
    return stock_products(tenant).filter(quantity__lte=ZERO).order_by('name')


def stock_value(tenant):
    """What the goods on hand cost to buy.

    Cost price, not retail: valuing stock at what you hope to sell it for
    books profit that has not happened yet.
    """
    return stock_products(tenant).aggregate(
        v=Sum(F('quantity') * F('cost_price'),
              output_field=DecimalField(max_digits=18, decimal_places=2)),
    )['v'] or ZERO
