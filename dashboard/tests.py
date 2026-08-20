from django.urls import reverse

from customers.models import Customer
from sales.models import Invoice
from tenants.tests import TwoTenantTestCase


class DashboardTenantIsolationTests(TwoTenantTestCase):
    """Part 19 #26 -- the dashboard has no per-ID URL to manipulate (its
    numbers come entirely from request.user.tenant), so what matters here
    is that its KPIs never blend in another tenant's figures."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        customer_a = Customer.objects.create(name='Customer A', tenant=cls.tenant_a)
        customer_b = Customer.objects.create(name='Customer B', tenant=cls.tenant_b)
        Invoice.objects.create(customer=customer_a, total=1000, tenant=cls.tenant_a)
        Invoice.objects.create(customer=customer_b, total=999999, tenant=cls.tenant_b)

    def test_user_a_dashboard_excludes_user_b_sales_figures(self):
        self.login_a()
        response = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(response.status_code, 200)
        # Tenant B's much larger invoice total must never appear on Tenant
        # A's dashboard -- proves sales_month etc. are actually scoped by
        # the logged-in user's own tenant, not accidentally summed globally.
        self.assertNotContains(response, '999,999')
        self.assertNotContains(response, 'Customer B')
