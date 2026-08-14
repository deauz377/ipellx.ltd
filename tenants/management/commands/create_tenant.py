from django.core.management.base import BaseCommand
from tenants.models import Tenant, User
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Create initial tenant and super admin'

    def handle(self, *args, **options):
        # Create tenant
        tenant, created = Tenant.objects.get_or_create(
            name='Default Tenant',
            defaults={
                'subdomain': 'default',
                'paid_until': timezone.now() + timedelta(days=30),
                'on_trial': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Tenant "{tenant.name}" created'))
        else:
            self.stdout.write(f'Tenant "{tenant.name}" already exists')

        # Create super admin
        if not User.objects.filter(is_super_admin=True).exists():
            user = User.objects.create_user(
                username='admin',
                email='admin@example.com',
                password='admin123',
                is_staff=True,
                is_superuser=True,
                tenant=tenant,
                is_super_admin=True
            )
            self.stdout.write(self.style.SUCCESS('Super admin created: admin/admin123'))
        else:
            self.stdout.write('Super admin already exists')