import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0006_invoice_tenant_invoiceitem_tenant_order_tenant_and_more'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySalesEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('particulars', models.CharField(help_text='What was sold', max_length=255)),
                ('unit', models.CharField(choices=[('pcs', 'Pieces'), ('kg', 'Kg'), ('g', 'Grams'), ('litre', 'Litre'), ('ml', 'ml'), ('pack', 'Pack'), ('box', 'Box'), ('dozen', 'Dozen'), ('bag', 'Bag'), ('other', 'Other')], default='pcs', max_length=20)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('total', models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=12)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='tenants.tenant')),
            ],
            options={
                'verbose_name_plural': 'Daily sales entries',
                'ordering': ['-date', '-created_at'],
            },
        ),
    ]
