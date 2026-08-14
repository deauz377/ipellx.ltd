from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0007_dailysalesentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceitem",
            name="cost_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
