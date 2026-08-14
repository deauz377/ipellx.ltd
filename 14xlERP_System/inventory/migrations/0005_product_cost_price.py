from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_product_tenant_supplier_tenant_alter_product_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cost_price",
            field=models.DecimalField(default=0, max_digits=10, decimal_places=2),
        ),
    ]
