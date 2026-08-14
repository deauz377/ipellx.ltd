from django.db import models
from tenants.models import TenantModel

# Create your models here.

class Customer(TenantModel):
    name = models.CharField(max_length=200)  # Placeholder for encryption
    phone = models.CharField(max_length=20, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.name

class CreditRecord(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice = models.ForeignKey('sales.Invoice', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.BooleanField(default=False)
    due_date = models.DateField()

    def __str__(self):
        return f"Credit for {self.customer.name} - {self.amount}"

