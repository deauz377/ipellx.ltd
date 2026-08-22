from decimal import Decimal

from django.db import models

from tenants.models import TenantModel


class Supplier(TenantModel):
    name = models.CharField(max_length=200)  # Placeholder for encryption
    contact = models.CharField(max_length=100, blank=True)
    # Separate from `contact` (which is free text -- could be a person's
    # name, an email, anything) because WhatsApp alerts need a real,
    # validated phone number in international format.
    phone = models.CharField(
        max_length=20, blank=True,
        help_text='WhatsApp number in international format, e.g. 254712345678',
    )

    def __str__(self):
        return self.name


class Location(TenantModel):
    """A physical place stock can sit: a shop, a store room, a warehouse.

    Stock is held per (product, location, batch), so this is what stops two
    branches' stock being added together and spent twice.
    """

    KIND_CHOICES = [
        ('store', 'Shop / Retail Store'),
        ('warehouse', 'Warehouse'),
        ('branch', 'Branch'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, blank=True, help_text='Short code, e.g. NRB-01')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='store')
    address = models.CharField(max_length=255, blank=True)
    # The place stock lands when nothing more specific is chosen. Exactly one
    # per tenant is created by the data migration so no stock is ever
    # location-less; enforced in save() rather than a DB constraint because
    # "one true default per tenant" is not expressible as a unique_together.
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default and self.tenant_id:
            Location.objects.filter(tenant_id=self.tenant_id, is_default=True).exclude(
                pk=self.pk,
            ).update(is_default=False)


class Product(TenantModel):
    UNIT_CHOICES = [
        ('pcs', 'Pieces'),
        ('kg', 'Kilograms'),
        ('g', 'Grams'),
        ('l', 'Litres'),
        ('ml', 'Millilitres'),
        ('box', 'Boxes'),
        ('crate', 'Crates'),
        ('bag', 'Bags'),
        ('tray', 'Trays'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)  # Placeholder for encryption
    sku = models.CharField(max_length=100, unique=True)  # Placeholder for encryption
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.CharField(max_length=100, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='pcs')

    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Cost/Buying price used to compute profit per item
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2)
    online_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Decimal, not integer -- goods sold by weight/volume (e.g. 2.5 kg of
    # rice, 1.5 litres of cooking oil) need fractional stock levels.
    #
    # This is a CACHE of the sum of this product's StockLevel rows across every
    # location and batch. It is kept because the dashboard's stock-value
    # aggregate, the low-stock queries and the sales stock check all read it
    # directly, and turning it into a property would break those. It must only
    # ever be written by inventory.services -- never assigned directly.
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=5)
    maximum_stock = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Falling to this level triggers a reorder. Defaults to the minimum stock level.',
    )

    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL,
                                 blank=True, null=True)

    # A URL/path rather than an ImageField: ImageField requires Pillow, which
    # is not installed and would add weight to the serverless bundle for one
    # optional field. Matches hr.Employee.profile_image_url's approach.
    image_url = models.CharField(
        max_length=500, blank=True, help_text='URL or file path to a product photo',
    )
    # Drives whether receiving demands a batch and expiry date. Off by default
    # so existing non-perishable products are unaffected.
    tracks_expiry = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def effective_reorder_level(self):
        return self.reorder_level if self.reorder_level is not None else self.minimum_stock

    @property
    def is_low_stock(self):
        return self.quantity <= self.effective_reorder_level

    @property
    def is_out_of_stock(self):
        return self.quantity <= 0

    @property
    def recommended_order_quantity(self):
        """How much to buy to get back to a sensible level: up to maximum_stock
        if one is set, otherwise twice the reorder level. Never negative."""
        target = self.maximum_stock if self.maximum_stock is not None else (
            self.effective_reorder_level * 2
        )
        shortfall = target - self.quantity
        return shortfall if shortfall > 0 else Decimal('0')

    @property
    def stock_value(self):
        return self.quantity * self.cost_price


class Batch(TenantModel):
    """A received lot of one product, with its own expiry and cost.

    Expiry is nullable so non-perishable goods can use the same machinery
    without pretending to have a shelf life.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=64, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiry_date', 'received_at']

    def __str__(self):
        label = self.batch_number or f'Batch {self.pk}'
        return f'{self.product.name} - {label}'

    @property
    def is_expired(self):
        from django.utils import timezone
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    def days_to_expiry(self):
        from django.utils import timezone
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days


class StockLevel(TenantModel):
    """How much of one product sits in one location, optionally in one batch.

    This is the truth about what is where. Product.quantity is a cache of the
    sum of these rows.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_levels')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='stock_levels')
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, null=True, blank=True, related_name='stock_levels',
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One row per place-a-thing-can-be. Without this, two rows for the same
        # product/location/batch could drift apart and both look correct.
        unique_together = [('product', 'location', 'batch')]
        ordering = ['product__name', 'location__name']

    def __str__(self):
        return f'{self.product.name} @ {self.location.name}: {self.quantity}'


class StockMovement(TenantModel):
    """Append-only ledger of every stock change -- and the audit trail.

    These are one model rather than two because the audit record the brief
    asks for (user, action, product, previous quantity, new quantity,
    difference, reason, date/time, location, related transaction) is exactly
    what a movement row already holds. Keeping them separate would mean two
    things to write and two places for them to disagree.

    Rows are never edited or deleted in normal operation: a mistake is
    corrected by recording a compensating movement, so history stays intact.
    """

    RECEIVE = 'receive'
    SALE = 'sale'
    SALE_REVERSAL = 'sale_reversal'
    TRANSFER_OUT = 'transfer_out'
    TRANSFER_IN = 'transfer_in'
    ADJUSTMENT = 'adjustment'
    DAMAGE = 'damage'
    EXPIRY = 'expiry'
    PRODUCTION_IN = 'production_in'
    PRODUCTION_OUT = 'production_out'
    OPENING = 'opening'

    MOVEMENT_TYPE_CHOICES = [
        (OPENING, 'Opening balance'),
        (RECEIVE, 'Stock received'),
        (SALE, 'Sold'),
        (SALE_REVERSAL, 'Sale reversed'),
        (TRANSFER_OUT, 'Transferred out'),
        (TRANSFER_IN, 'Transferred in'),
        (ADJUSTMENT, 'Adjustment'),
        (DAMAGE, 'Damaged'),
        (EXPIRY, 'Expired'),
        (PRODUCTION_IN, 'Produced'),
        (PRODUCTION_OUT, 'Consumed in production'),
    ]

    # Why stock was adjusted during a count. Mirrors the brief's list.
    REASON_CHOICES = [
        ('damaged', 'Damaged'),
        ('spoilage', 'Spoilage'),
        ('theft', 'Theft'),
        ('counting_error', 'Counting error'),
        ('unknown_loss', 'Unknown loss'),
        ('other', 'Other'),
    ]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='movements')
    batch = models.ForeignKey(
        Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements',
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)

    # Signed: negative takes stock out, positive puts it in.
    quantity_delta = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_before = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_after = models.DecimalField(max_digits=12, decimal_places=2)

    reason = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Deliberately a loose reference rather than a ContentType FK: the related
    # object may live in sales, purchasing or a module that does not exist yet,
    # and a hard FK to each would couple inventory to all of them.
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        direction = '+' if self.quantity_delta >= 0 else ''
        return f'{self.product.name}: {direction}{self.quantity_delta} ({self.get_movement_type_display()})'

    @property
    def is_increase(self):
        return self.quantity_delta > 0
