from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from customers.models import Customer
from .models import Invoice


class SalesInvoiceDetailViewTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='sales-user', password='secret123')
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name='Test Customer', phone='0712345678')
        self.invoice = Invoice.objects.create(customer=self.customer, total=1000.00, paid=0.00)

    def test_invoice_detail_page_renders(self):
        response = self.client.get(reverse('sales:invoice_detail', kwargs={'pk': self.invoice.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invoice #')
