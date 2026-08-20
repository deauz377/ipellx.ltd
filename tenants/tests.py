from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Tenant, User

TEST_PASSWORD = 'TestPass123!'


def create_tenant_and_owner(subdomain, tenant_name=None, username=None, role=User.Role.OWNER):
    """Shared fixture helper: one tenant plus one verified, login-ready user
    owning it. Every field that matters for isolation tests (tenant,
    role, email_verified) is explicit -- never left to a default that
    could silently change and invalidate what a test is asserting."""
    tenant_name = tenant_name or f'{subdomain} Ltd'
    username = username or subdomain.replace('-', '_')
    tenant = Tenant.objects.create(
        name=tenant_name,
        subdomain=subdomain,
        paid_until=timezone.now() + timedelta(days=30),
        on_trial=True,
    )
    user = User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password=TEST_PASSWORD,
        tenant=tenant,
        role=role,
        email_verified=True,
    )
    return tenant, user


class TwoTenantTestCase(TestCase):
    """Base class for cross-tenant isolation tests: two completely
    independent tenants, each with one Owner. Subclasses create their own
    per-app fixture objects under tenant_a/tenant_b (always passing
    tenant= explicitly -- see create_tenant_and_owner's docstring) and
    assert that logging in as user_a can never reach anything under
    tenant_b, by any route: URL pk, POST data, or a list/search view."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a, cls.user_a = create_tenant_and_owner('tenant-a-iso-test', 'Tenant A Ltd', 'owner_a')
        cls.tenant_b, cls.user_b = create_tenant_and_owner('tenant-b-iso-test', 'Tenant B Ltd', 'owner_b')

    def login_a(self):
        self.client.login(username='owner_a', password=TEST_PASSWORD)

    def login_b(self):
        self.client.login(username='owner_b', password=TEST_PASSWORD)


from django.test import Client

from .middleware import get_current_tenant


class AnonymousTenantResolutionTests(TestCase):
    """Regression test for the removed 'default' tenant fallback in
    TenantMiddleware.process_request() -- an anonymous request must never
    resolve to ANY tenant, even one that legitimately has
    subdomain='default' (as this platform's own first tenant does in
    production)."""

    def test_anonymous_request_never_resolves_a_tenant_even_with_a_default_subdomain(self):
        Tenant.objects.create(
            name='Has The Default Subdomain', subdomain='default',
            paid_until=timezone.now() + timedelta(days=30), on_trial=True,
        )
        # A real request (not a direct middleware call) so this exercises
        # the exact code path a browser hits -- host defaults to
        # 'testserver' for Django's test client, matching how no real
        # subdomain routing exists in production either.
        Client().get('/login/')
        self.assertIsNone(get_current_tenant())
