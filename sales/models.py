import secrets

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
    due_date = models.DateField(null=True, blank=True)
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

    @property
    def payment_status(self):
        """Derived, never stored -- so it can't drift from paid/total."""
        if self.paid <= 0:
            return 'pending'
        if self.paid < self.total:
            return 'partial'
        return 'paid'

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

    # Set when a WhatsApp alert is sent to the supplier for this order.
    # 'not_configured' / 'no_phone' / 'failed' / 'sent' -- surfaced on the
    # order detail page so an Owner isn't left guessing whether the
    # supplier actually got notified.
    supplier_notified_at = models.DateTimeField(null=True, blank=True)
    supplier_notification_status = models.CharField(max_length=20, blank=True)

    def __str__(self):
        if self.order_type == 'supplier' and self.supplier:
            return f"Purchase Order #{self.id} - {self.supplier.name}"
        return f"Order #{self.id} - {self.customer.name if self.customer else 'Unknown'}"

    @property
    def partner_name(self):
        return self.supplier.name if self.order_type == 'supplier' and self.supplier else self.customer.name if self.customer else 'Unknown'

class InvoiceItem(TenantModel):
    CHANNEL_CHOICES = [
        ('retail', 'Retail'),
        ('wholesale', 'Wholesale'),
        ('online', 'Online'),
    ]

    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    # Decimal, not integer -- matches Product.quantity, so goods sold by
    # weight/volume can be sold in fractional amounts too.
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Which of the product's three price tiers this line was actually sold
    # at. Independent of `price` itself, which can still be hand-overridden
    # per line -- this is what makes a later "sales by channel" report
    # possible, since price alone can't distinguish a discounted retail
    # sale from a wholesale one.
    sale_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='retail')
    # Snapshot of the product's cost price at the moment this item was
    # sold, so historical profit stays accurate even if the product's
    # current cost_price changes later.
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.qty} x {self.product.name}"

class OrderItem(TenantModel):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    # Decimal, matching Product.quantity -- see InvoiceItem.qty.
    qty = models.DecimalField(max_digits=10, decimal_places=2)
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


class PaymentRequest(TenantModel):
    """A request for money against an invoice -- the "ticket" behind the
    shareable customer-facing payment link. Distinct from Payment: this
    represents asking for money, not money received. amount_due is a
    snapshot for display/audit only -- the public payment page always
    re-derives the real amount from invoice.balance at request time,
    since amount_due goes stale the moment any other payment lands
    against the invoice."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payment_requests')
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    instructions = models.TextField(blank=True, default='')
    # Unguessable by design -- this token, not login, is what secures the
    # public payment page. unique=True is defense-in-depth; the 256 bits
    # of entropy from token_urlsafe(32) is the actual guarantee.
    token = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    created_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment_requests_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.PositiveIntegerField(default=0)
    scheduled_reminder_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment request for Invoice #{self.invoice_id} ({self.get_status_display()})"


class Payment(TenantModel):
    METHOD_CHOICES = [
        ('cash','Cash'),
        ('mpesa','M-Pesa'),
        ('bank','Bank'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]
    # A Payment row only ever represents money actually confirmed received
    # -- see MpesaTransaction's docstring below for the same invariant on
    # the M-Pesa side. 'confirmed'/'refunded' are the only states that
    # belong here; pending/failed/cancelled attempts live on
    # MpesaTransaction.status and PaymentRequest.status instead, never here.
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('refunded', 'Refunded'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    # SET_NULL, not CASCADE -- cancelling/deleting the request that led to
    # this payment must never delete money that was actually received.
    payment_request = models.ForeignKey(
        PaymentRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments',
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    recorded_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments_recorded',
    )
    notes = models.TextField(blank=True, default='')
    refunded_at = models.DateTimeField(null=True, blank=True)
    refunded_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments_refunded',
    )
    refund_reason = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f"{self.method} payment of {self.amount}"


class MpesaTransaction(TenantModel):
    """One STK Push attempt against an invoice. Deliberately separate from
    Payment: STK Push is asynchronous (Safaricom confirms or rejects it
    seconds to minutes later, via a webhook, and the customer can also
    just cancel the prompt on their phone) so nothing here should count
    as money received -- and invoice.paid should never move -- until the
    callback actually confirms success. A Payment row only gets created
    at that point, by mpesa_callback()."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='mpesa_transactions')
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Safaricom's IDs for correlating the later callback to this attempt.
    checkout_request_id = models.CharField(max_length=100, unique=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    result_description = models.CharField(max_length=255, blank=True)
    initiated_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mpesa_transactions_initiated',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"M-Pesa {self.checkout_request_id} - {self.status}"


class PaymentAuditLog(TenantModel):
    """Who did what, to which payment/request, and when -- a compliance
    trail for financial data. Nothing here is ever mutated after creation."""
    ACTION_CHOICES = [
        ('request_created', 'Payment Request Created'),
        ('request_sent', 'Payment Request Sent'),
        ('reminder_sent', 'Reminder Sent'),
        ('payment_recorded', 'Payment Recorded'),
        ('payment_confirmed', 'Payment Confirmed (M-Pesa callback)'),
        ('payment_refunded', 'Payment Refunded'),
        ('stk_push_initiated', 'STK Push Initiated'),
        ('request_cancelled', 'Payment Request Cancelled'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payment_audit_logs')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    payment_request = models.ForeignKey(
        PaymentRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs',
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    # Null actor = a system/webhook action (e.g. the M-Pesa callback), not
    # a logged-in user -- mirrors MpesaTransaction.initiated_by's own
    # null=True for exactly the same "no user on the other end" case.
    actor = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} - Invoice #{self.invoice_id}"

