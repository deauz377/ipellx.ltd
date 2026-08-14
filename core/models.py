from django.db import models
from tenants.models import TenantModel

# Create your models here.

class Business(TenantModel):
    name = models.CharField(max_length=200)  # Placeholder for encryption
    address = models.TextField(blank=True)  # Placeholder for encryption
    phone = models.CharField(max_length=50, blank=True)  # Placeholder for encryption
    # Additional fields like logo, tax ID, etc.

    def __str__(self):
        return self.name

