from django.contrib import admin
from .models import Product, Supplier

# Register your models here.
admin.site.register(Supplier)
admin.site.register(Product)