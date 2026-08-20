from django.db import models
from tenants.models import TenantModel

# Create your models here.

class Expense(TenantModel):
    CATEGORY_CHOICES = [
        ('rent', 'Rent'),
        ('salaries', 'Salaries & Wages'),
        ('transport', 'Transport'),
        ('utilities', 'Utilities'),
        # Added for the budgeting app, which needs one Expense category per
        # budget category to compute "amount spent" -- 'utilities' is kept
        # (existing rows still use it) alongside the two more specific
        # options below for anyone who wants that level of detail going
        # forward.
        ('electricity', 'Electricity'),
        ('water', 'Water'),
        ('marketing', 'Marketing'),
        ('gas_fuel', 'Gas/Fuel'),
        ('maintenance', 'Maintenance'),
        ('food_production', 'Food/Production'),
        ('other', 'Other'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)  # Placeholder for encryption
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    def __str__(self):
        return f"{self.category} - {self.amount}"
