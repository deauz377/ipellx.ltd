from django.db import models
from tenants.models import TenantModel

# Create your models here.

class Customer(TenantModel):
    name = models.CharField(max_length=200)  # Placeholder for encryption
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(
        blank=True,
        help_text='Free-form relationship notes -- preferences, history, anything worth remembering.',
    )

    def __str__(self):
        return self.name

    def recalculate_balance(self):
        """Recomputes balance from scratch (sum of unpaid invoice
        balances), rather than incrementing/decrementing it at each call
        site -- so it can never drift out of sync.

        Uses Invoice._base_manager, not Invoice.objects, because this is
        also called from contexts with no real tenant in scope (e.g. the
        M-Pesa webhook callback, which runs with no logged-in user) --
        Invoice.objects would filter by whatever tenant that anonymous
        request happens to resolve to, silently computing the balance
        from zero of this customer's actual invoices.
        """
        from django.db.models import F, Sum
        from sales.models import Invoice

        outstanding = Invoice._base_manager.filter(customer=self).aggregate(
            outstanding=Sum(F('total') - F('paid'))
        )['outstanding'] or 0
        self.balance = outstanding
        self.save(update_fields=['balance'])

class CreditRecord(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice = models.ForeignKey('sales.Invoice', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.BooleanField(default=False)
    due_date = models.DateField()

    def __str__(self):
        return f"Credit for {self.customer.name} - {self.amount}"

