from django.db import models
from tenants.models import TenantModel

# Create your models here.

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


class Product(TenantModel):
    name = models.CharField(max_length=200)  # Placeholder for encryption
    sku = models.CharField(max_length=100, unique=True)  # Placeholder for encryption
    category = models.CharField(max_length=100, blank=True)

    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Cost/Buying price used to compute profit per item
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2)
    online_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Decimal, not integer -- goods sold by weight/volume (e.g. 2.5 kg of
    # rice, 1.5 litres of cooking oil) need fractional stock levels.
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=5)
    
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL,
                                 blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name