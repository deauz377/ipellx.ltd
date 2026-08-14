from django.contrib import admin
from .models import Customer, CreditRecord

# Register your models here.
admin.site.register(Customer)
admin.site.register(CreditRecord)
