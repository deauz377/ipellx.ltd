"""Give every existing product a home and an explanation.

Before this, a product's stock was a single number with no record of where it
was or how it got there. This creates a default Location per business, moves
each product's current quantity into a StockLevel there, and writes an opening
StockMovement so the ledger accounts for every unit already on hand.

Written to be idempotent: it skips any product that already has stock levels,
so a re-run cannot double anyone's inventory.
"""
from decimal import Decimal

from django.db import migrations

ZERO = Decimal('0')


def backfill(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    Location = apps.get_model('inventory', 'Location')
    Product = apps.get_model('inventory', 'Product')
    StockLevel = apps.get_model('inventory', 'StockLevel')
    StockMovement = apps.get_model('inventory', 'StockMovement')

    for tenant in Tenant.objects.all():
        products = Product.objects.filter(tenant=tenant)
        if not products.exists():
            continue

        location = Location.objects.filter(tenant=tenant, is_default=True).first()
        if location is None:
            location = Location.objects.create(
                tenant=tenant, name='Main Store', code='MAIN',
                kind='store', is_default=True, is_active=True,
            )

        for product in products:
            if StockLevel.objects.filter(product=product).exists():
                continue  # already migrated; never double up

            quantity = product.quantity or ZERO
            StockLevel.objects.create(
                tenant=tenant, product=product, location=location,
                batch=None, quantity=quantity,
            )
            # Even a zero opening balance gets a row, so the ledger explains
            # every product rather than only the ones that happened to have
            # stock on the day this ran.
            StockMovement.objects.create(
                tenant=tenant, product=product, location=location, batch=None,
                movement_type='opening', quantity_delta=quantity,
                quantity_before=ZERO, quantity_after=quantity,
                reason='Opening balance carried over when stock locations were introduced',
                reference_type='migration', reference_id='0010_backfill_stock_levels',
            )


def unbackfill(apps, schema_editor):
    """Reverse cleanly by removing only what this migration created, leaving
    Product.quantity (which it never modified) exactly as it was."""
    Location = apps.get_model('inventory', 'Location')
    StockLevel = apps.get_model('inventory', 'StockLevel')
    StockMovement = apps.get_model('inventory', 'StockMovement')

    StockMovement.objects.filter(
        reference_type='migration', reference_id='0010_backfill_stock_levels',
    ).delete()
    StockLevel.objects.all().delete()
    Location.objects.filter(code='MAIN', is_default=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_product_barcode_product_brand_product_image_url_and_more'),
        ('tenants', '0008_user_email_verified_user_verification_sent_at'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
