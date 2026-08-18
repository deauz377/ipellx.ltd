from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sales.models import PaymentAuditLog, PaymentRequest
from sales.utils import build_pay_url, send_payment_request_reminder

# Matches sales/views.py's REMINDER_COOLDOWN -- kept as a separate
# constant rather than importing from views (a management command
# shouldn't depend on the view layer), but the two must be changed
# together if this value ever does.
REMINDER_COOLDOWN = timedelta(hours=24)


class Command(BaseCommand):
    help = (
        'Sends reminders for payment requests whose scheduled_reminder_at has '
        'passed, via whichever of WhatsApp/SMS is configured. Intended to run '
        'on a schedule (see the /cron/send-payment-reminders/ endpoint and '
        'vercel.json) rather than by hand, though it is safe to run manually too.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        due = PaymentRequest.objects.filter(
            status__in=['pending', 'sent', 'partial'],
            scheduled_reminder_at__isnull=False,
            scheduled_reminder_at__lte=now,
        )

        sent_count = 0
        skipped_count = 0

        for payment_request in due:
            invoice = payment_request.invoice

            if invoice.balance <= 0:
                payment_request.status = 'paid'
                payment_request.save(update_fields=['status'])
                continue

            if payment_request.last_reminder_sent_at and now - payment_request.last_reminder_sent_at < REMINDER_COOLDOWN:
                skipped_count += 1
                continue

            pay_url = build_pay_url(payment_request)
            sent_via = send_payment_request_reminder(payment_request, pay_url)

            if sent_via:
                payment_request.last_reminder_sent_at = now
                payment_request.reminder_count += 1
                payment_request.save(update_fields=['last_reminder_sent_at', 'reminder_count'])
                PaymentAuditLog.objects.create(
                    invoice=invoice, payment_request=payment_request, action='reminder_sent',
                    tenant=payment_request.tenant, metadata={'channels': sent_via, 'source': 'cron'},
                )
                sent_count += 1
            else:
                skipped_count += 1

        self.stdout.write(f'Reminders sent: {sent_count}. Skipped (cooldown or unsent): {skipped_count}.')
