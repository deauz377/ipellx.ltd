from django.core.management.base import BaseCommand

from inventory.models import Product


class Command(BaseCommand):
    help = 'List products with cost prices at or below KES 1; does not change data.'

    def handle(self, *args, **options):
        products = Product.objects.filter(cost_price__lte=1).order_by('sku')
        self.stdout.write('DRY RUN - no product data will be changed')
        self.stdout.write('SKU\tNAME\tCOST PRICE\tQUANTITY')
        for product in products.iterator():
            self.stdout.write(
                f'{product.sku}\t{product.name}\t'
                f'KES {product.cost_price:.2f}\t{product.quantity}'
            )
        self.stdout.write(f'{products.count()} product(s) need cost-price review.')