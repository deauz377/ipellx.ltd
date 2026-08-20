import getpass

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta

from tenants.models import Tenant, User


class Command(BaseCommand):
    help = (
        'Create a new tenant/business plus its owning super-admin user, for '
        'operator use only (e.g. bootstrapping a fresh environment). Prompts '
        'for a real password rather than using a hardcoded one -- the '
        'previous version of this command created a "Default Tenant" '
        '(subdomain \'default\') and an admin/admin123 superuser '
        'unconditionally, which is exactly the shared/anonymous-account '
        'pattern this platform must not have. Real customer signups go '
        'through core.views.signup(), which this command does not replace.'
    )

    def add_arguments(self, parser):
        parser.add_argument('business_name', help='Name of the new tenant/business.')
        parser.add_argument('username', help='Username for the owning super-admin.')
        parser.add_argument('email', help='Email for the owning super-admin.')

    def handle(self, *args, **options):
        business_name = options['business_name']
        username = options['username']
        email = options['email']

        if Tenant.objects.filter(name__iexact=business_name).exists():
            raise CommandError(f'A tenant named "{business_name}" already exists.')
        if User.objects.filter(username=username).exists():
            raise CommandError(f'A user named "{username}" already exists.')

        password = getpass.getpass('Password for the new super-admin: ')
        if not password:
            raise CommandError('A password is required.')

        base_subdomain = slugify(business_name)[:80] or 'business'
        subdomain = base_subdomain
        suffix = 1
        while Tenant.objects.filter(subdomain=subdomain).exists():
            suffix += 1
            subdomain = f'{base_subdomain}-{suffix}'

        tenant = Tenant.objects.create(
            name=business_name,
            subdomain=subdomain,
            paid_until=timezone.now() + timedelta(days=30),
            on_trial=True,
        )
        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=True,
            is_superuser=True,
            tenant=tenant,
            role=User.Role.OWNER,
            is_super_admin=True,
            email_verified=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Tenant "{tenant.name}" (subdomain "{tenant.subdomain}") and super-admin "{username}" created.'
        ))