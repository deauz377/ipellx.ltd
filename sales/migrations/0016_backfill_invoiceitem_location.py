"""Point existing invoice lines at the location they actually came from.

Every sale written before multi-location selling drew from the tenant's
default location, because that is the only place issue_stock() could take
from. Recording that explicitly means invoice_delete() never has to guess,
and a null location from here on is a genuine anomaly rather than "old row".
"""
from django.db import migrations


def backfill(apps, schema_editor):
    InvoiceItem = apps.get_model('sales', 'InvoiceItem')
    Location = apps.get_model('inventory', 'Location')

    # One default per tenant, resolved once rather than per line.
    defaults = {}
    for location in Location.objects.filter(is_default=True):
        defaults.setdefault(location.tenant_id, location.pk)

    for item in InvoiceItem.objects.filter(location__isnull=True).iterator():
        location_id = defaults.get(item.tenant_id)
        if location_id is not None:
            InvoiceItem.objects.filter(pk=item.pk).update(location_id=location_id)


def unbackfill(apps, schema_editor):
    # Reversible: the column goes back to null, which is where it started.
    InvoiceItem = apps.get_model('sales', 'InvoiceItem')
    InvoiceItem.objects.update(location=None)


class Migration(migrations.Migration):
    dependencies = [
        ('sales', '0015_invoiceitem_location'),
        ('inventory', '0011_goodsreceipt_goodsreceiptline_stockcount_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
