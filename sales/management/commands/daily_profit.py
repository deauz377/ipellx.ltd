from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from sales.utils import compute_daily_profit


class Command(BaseCommand):
    help = 'Compute daily profit for a given date (YYYY-MM-DD). Defaults to today.'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format')

    def handle(self, *args, **options):
        date_str = options.get('date')
        if date_str:
            target_date = parse_date(date_str)
            if target_date is None:
                self.stderr.write('Invalid date format. Use YYYY-MM-DD')
                return
        else:
            from datetime import date as _date

            target_date = _date.today()

        result = compute_daily_profit(target_date)
        self.stdout.write(f"Date: {result['date']}")
        self.stdout.write(f"Revenue: {result['revenue']}")
        self.stdout.write(f"Cost: {result['cost']}")
        self.stdout.write(f"Gross profit: {result['gross_profit']}")
        self.stdout.write(f"Expenses: {result['expenses']}")
        self.stdout.write(f"Net profit: {result['net_profit']}")
