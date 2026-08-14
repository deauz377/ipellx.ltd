from django.db import models
from django.utils import timezone
from tenants.models import TenantModel
from inventory.models import Product

# Create your models here.

class Invoice(TenantModel):
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT)
    date = models.DateTimeField(auto_now_add=True)
    discount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoices_created',
    )
    # Historical DBs contained a non-null `delete_reason` column; keep a
    # matching field here with a safe default so inserts don't fail.
    delete_reason = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f"Invoice #{self.id} - {self.customer.name}"

    @property
    def balance(self):
        return self.total - self.paid

class Order(TenantModel):
    ORDER_TYPE_CHOICES = [
        ('customer', 'Customer Order'),
        ('supplier', 'Supplier Order'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('cancelled', 'Cancelled'),
    ]

    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='customer')
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, null=True, blank=True)
    supplier = models.ForeignKey('inventory.Supplier', on_delete=models.PROTECT, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        if self.order_type == 'supplier' and self.supplier:
            return f"Purchase Order #{self.id} - {self.supplier.name}"
        return f"Order #{self.id} - {self.customer.name if self.customer else 'Unknown'}"

    @property
    def partner_name(self):
        return self.supplier.name if self.order_type == 'supplier' and self.supplier else self.customer.name if self.customer else 'Unknown'

class InvoiceItem(TenantModel):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Snapshot of the product's cost price at the moment this item was
    # sold, so historical profit stays accurate even if the product's
    # current cost_price changes later.
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.qty} x {self.product.name}"

class OrderItem(TenantModel):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.qty} x {self.product.name}"

    @property
    def line_total(self):
        return self.qty * self.price

class DailySalesEntry(TenantModel):
    """A simple free-text sales ledger line — for recording sales that
    aren't necessarily tied to a catalogued Product (e.g. informal
    items, bulk goods sold by weight, one-off items)."""
    UNIT_CHOICES = [
        ('pcs', 'Pieces'),
        ('kg', 'Kg'),
        ('g', 'Grams'),
        ('litre', 'Litre'),
        ('ml', 'ml'),
        ('pack', 'Pack'),
        ('box', 'Box'),
        ('dozen', 'Dozen'),
        ('bag', 'Bag'),
        ('other', 'Other'),
    ]
    date = models.DateField(default=timezone.now)
    particulars = models.CharField(max_length=255, help_text="What was sold")
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='pcs')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    notes = models.TextField(blank=True)
    # Some databases have an `is_deleted` column; keep it with a default
    # to avoid NOT NULL constraint failures on inserts.
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='daily_sales_entries_created',
    )

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Daily sales entries'

    def save(self, *args, **kwargs):
        self.total = (self.quantity or 0) * (self.unit_price or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.particulars} ({self.total})"


class ProfitEntry(TenantModel):
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255, help_text="What generated the profit entry")
    revenue = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Profit entries'

    def save(self, *args, **kwargs):
        self.profit = (self.revenue or 0) - (self.cost or 0) - (self.expenses or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.description} ({self.profit})"


class Payment(TenantModel):
    METHOD_CHOICES = [
        ('cash','Cash'),
        ('mpesa','M-Pesa'),
        ('bank','Bank'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.method} payment of {self.amount}"

