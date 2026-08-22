"""Workflow models: receiving, transfers and stock counts.

Kept in their own module rather than swelling models.py, and re-exported from
there so `inventory.models.StockTransfer` still works and Django's app
registry finds them normally.

The shared principle across all three: nothing changes stock until a human
confirms it. A draft receipt, a requested transfer and an unapproved count
are all just paperwork -- only the confirm/receive/approve step calls
inventory.services, which is still the single doorway to the ledger.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from tenants.models import TenantModel

ZERO = Decimal('0')


class GoodsReceipt(TenantModel):
    """A delivery being booked in: Supplier -> PO -> Delivery -> Receive -> Confirm.

    Stock only moves on confirm, so a receipt can be captured at the gate and
    corrected before it touches inventory.
    """

    DRAFT = 'draft'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (DRAFT, 'Draft'),
        (CONFIRMED, 'Confirmed'),
        (CANCELLED, 'Cancelled'),
    ]

    supplier = models.ForeignKey(
        'inventory.Supplier', on_delete=models.PROTECT, null=True, blank=True,
        related_name='goods_receipts',
    )
    # The existing purchase order, if this delivery came from one. sales.Order
    # with order_type='supplier' is this ERP's purchase order -- no new PO
    # model is introduced.
    purchase_order = models.ForeignKey(
        'sales.Order', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='goods_receipts',
    )
    invoice_number = models.CharField(max_length=64, blank=True)
    location = models.ForeignKey(
        'inventory.Location', on_delete=models.PROTECT, related_name='goods_receipts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    notes = models.TextField(blank=True)

    received_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    confirmed_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.supplier.name if self.supplier else 'Unknown supplier'
        return f'Receipt #{self.pk} from {who}'

    @property
    def is_editable(self):
        return self.status == self.DRAFT

    @property
    def total_received(self):
        return sum((line.quantity_received for line in self.lines.all()), ZERO)

    @property
    def total_cost(self):
        return sum(
            (line.quantity_received * line.unit_cost for line in self.lines.all()), ZERO,
        )


class GoodsReceiptLine(TenantModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='+')
    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2)
    # Recorded but never added to stock -- rejected goods go back to the
    # supplier, so counting them would inflate inventory.
    quantity_rejected = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    batch_number = models.CharField(max_length=64, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f'{self.product.name} x {self.quantity_received}'


class StockTransfer(TenantModel):
    """Stock moving between two locations, with an approval trail.

    Stock leaves the source when the transfer is marked in transit and lands
    at the destination when it is received -- so goods on a lorry are neither
    sellable at the source nor countable at the destination, which is the
    whole reason the intermediate state exists.
    """

    PENDING = 'pending'
    APPROVED = 'approved'
    IN_TRANSIT = 'in_transit'
    RECEIVED = 'received'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (IN_TRANSIT, 'In Transit'),
        (RECEIVED, 'Received'),
        (CANCELLED, 'Cancelled'),
    ]
    OPEN_STATUSES = (PENDING, APPROVED, IN_TRANSIT)

    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='transfers')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.ForeignKey(
        'inventory.Location', on_delete=models.PROTECT, related_name='transfers_out',
    )
    destination = models.ForeignKey(
        'inventory.Location', on_delete=models.PROTECT, related_name='transfers_in',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    notes = models.CharField(max_length=255, blank=True)

    requested_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    approved_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    received_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.quantity} x {self.product.name}: {self.source} -> {self.destination}'

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES


class StockCount(TenantModel):
    """A stock take at one location.

    Counting never changes stock by itself: lines record what was found, and
    only approval turns the differences into adjustment movements. That is
    what stops a miscount silently rewriting inventory.
    """

    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (DRAFT, 'Counting'),
        (SUBMITTED, 'Awaiting approval'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]

    location = models.ForeignKey(
        'inventory.Location', on_delete=models.PROTECT, related_name='stock_counts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    notes = models.TextField(blank=True)

    started_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    submitted_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    approved_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    rejection_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Count #{self.pk} at {self.location.name} ({self.get_status_display()})'

    @property
    def is_editable(self):
        return self.status == self.DRAFT

    @property
    def total_variance(self):
        return sum((line.variance for line in self.lines.all()), ZERO)

    @property
    def lines_with_variance(self):
        return [line for line in self.lines.all() if line.variance != ZERO]


class StockCountLine(TenantModel):
    REASON_CHOICES = [
        ('', 'Not stated'),
        ('damaged', 'Damaged'),
        ('spoilage', 'Spoilage'),
        ('theft', 'Theft'),
        ('counting_error', 'Counting error'),
        ('unknown_loss', 'Unknown loss'),
        ('other', 'Other'),
    ]

    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='+')
    # Snapshotted when the count starts, so the variance is measured against
    # what the system claimed at that moment rather than a number that has
    # since moved underneath the person counting.
    system_quantity = models.DecimalField(max_digits=12, decimal_places=2)
    physical_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['product__name']

    def __str__(self):
        return f'{self.product.name}: {self.system_quantity} -> {self.physical_quantity}'

    @property
    def is_counted(self):
        return self.physical_quantity is not None

    @property
    def variance(self):
        if self.physical_quantity is None:
            return ZERO
        return self.physical_quantity - self.system_quantity
