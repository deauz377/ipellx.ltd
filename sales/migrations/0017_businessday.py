# Generated manually because this workspace does not include a Python runtime.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0016_backfill_invoiceitem_location'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_date', models.DateField(db_index=True)),
                ('status', models.CharField(choices=[('open', 'Open'), ('closed', 'Closed')], default='open', max_length=10)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('reopened_at', models.DateTimeField(blank=True, null=True)),
                ('closing_notes', models.TextField(blank=True, default='')),
                ('closing_summary', models.JSONField(blank=True, default=dict)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('reopened_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='tenants.tenant')),
            ],
            options={'ordering': ['-business_date']},
        ),
        migrations.AddConstraint(
            model_name='businessday',
            constraint=models.UniqueConstraint(fields=('tenant', 'business_date'), name='sales_businessday_tenant_date'),
        ),
    ]
