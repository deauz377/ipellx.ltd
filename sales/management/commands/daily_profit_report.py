from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from django.core.mail import mail_admins
from django.conf import settings

from sales.utils import compute_daily_profit


class Command(BaseCommand):
    help = 'Compute daily profit and email a report to ADMINS (or recipients specified).'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format')
        parser.add_argument('--to', nargs='+', help='Email addresses to send the report to (overrides ADMINS)')

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

        subject = f"Daily Profit Report: {result['date']}"
        message = (
            f"Revenue: {result['revenue']}\n"
            f"Cost: {result['cost']}\n"
            f"Gross profit: {result['gross_profit']}\n"
            f"Expenses: {result['expenses']}\n"
            f"Net profit: {result['net_profit']}\n"
        )

        recipients = options.get('to')
        if recipients:
            # send directly to provided recipients
            from django.core.mail import send_mail

            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            send_mail(subject, message, from_email, recipients)
            self.stdout.write(f"Report emailed to: {', '.join(recipients)}")
        else:
            # mail to ADMINS via mail_admins
            mail_admins(subject, message)
            self.stdout.write('Report emailed to ADMINS')
