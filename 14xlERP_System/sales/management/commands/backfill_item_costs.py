"""
One-time backfill for InvoiceItem.cost_price on items created before that
field existed. Those rows default to 0, which would make old sales look
like 100% profit with no cost at all.

This fills them in using each product's CURRENT cost_price -- the best
available estimate, since the true cost at the original time of sale
was never recorded. It only touches items where cost_price is still 0,
so it's safe to run more than once and won't overwrite anything already
snapshotted correctly by a real sale going forward.

Usage:
    python manage.py backfill_item_costs
"""
from django.core.management.base import BaseCommand
from sales.models import InvoiceItem


class Command(BaseCommand):
    help = "Backfills cost_price on old InvoiceItem rows using each product's current cost_price"

    def handle(self, *args, **options):
        items = InvoiceItem.objects.filter(cost_price=0).select_related('product')

        updated = 0
        skipped = 0
        for item in items:
            if item.product.cost_price:
                item.cost_price = item.product.cost_price
                item.save(update_fields=['cost_price'])
                updated += 1
            else:
                # Product itself has no cost_price set either -- nothing
                # to backfill from, leave as 0.
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Backfilled {updated} invoice item(s)."
        ))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"Skipped {skipped} item(s) whose product also has no cost_price set -- "
                f"add a cost price to those products first, then re-run this command."
            ))
