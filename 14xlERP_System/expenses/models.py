from django.db import models
from tenants.models import TenantModel

# Create your models here.

class Expense(TenantModel):
    CATEGORY_CHOICES = [
        ('rent','Rent'),
        ('salaries','Salaries'),
        ('transport','Transport'),
        ('utilities','Utilities'),
        ('other','Other'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)  # Placeholder for encryption
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    def __str__(self):
        return f"{self.category} - {self.amount}"
