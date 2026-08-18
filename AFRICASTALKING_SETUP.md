# Setting up SMS payment requests/reminders

The code side of this is already built and live: payment requests and
reminders on an invoice (`sales/templates/sales/invoice_detail.html`) can
send via SMS, backed by `sales/sms.py`. Until the two things below are
done, sending shows "SMS isn't set up for this deployment yet" rather
than silently failing or pretending to send.

This is account setup on Africa's Talking's side, not something code can
do for you — it ties to your business identity and (for production
volume) a registered sender ID.

## 1. An Africa's Talking account

1. Go to [africastalking.com](https://africastalking.com) and create an
   account. A **sandbox** app is created automatically and is free to use
   for testing — it can only send to phone numbers you've explicitly
   registered as test numbers in the sandbox simulator, not to real
   customers.
2. For real customers, create a **live** app from the dashboard. Africa's
   Talking requires some business verification and (for Kenya) a small
   top-up before live SMS can be sent — unlike the WhatsApp/M-Pesa
   integrations already in this app, there's no separate approval step
   for message content; plain SMS doesn't require pre-approved templates.
3. Optionally register a **Sender ID** (a short alphanumeric name shown
   as the sender instead of a long shared number) — this needs separate
   approval from Africa's Talking and can take a few days. Without one,
   messages send from a shared shortcode.

## 2. Environment variables

Once you have an app (sandbox or live), set these wherever the app is
deployed (same place as `SECRET_KEY` and `DATABASE_URL`):

| Variable | Where to find it |
|---|---|
| `AT_USERNAME` | Africa's Talking dashboard → your app's username. Use the literal value `sandbox` while testing against the sandbox environment |
| `AT_API_KEY` | Africa's Talking dashboard → Settings → API Key, generated per-app |
| `AT_SENDER_ID` | Your approved Sender ID from step 1, if you registered one. Leave unset to send from Africa's Talking's shared shortcode |

`sales/sms.py` picks the sandbox vs. live API host automatically based on
whether `AT_USERNAME` is exactly `sandbox`.

## Testing before customers see anything

In the Africa's Talking dashboard, under the sandbox app's **Simulator**,
add your own phone number as a test recipient (international format, e.g.
`254712345678`, not `0712345678` — normalized automatically by
`sales.mpesa.normalize_phone()`, reused here). Send a payment request or
reminder to a test invoice with that number on the customer record and
confirm it arrives.

## Cost

Africa's Talking charges per SMS segment, with rates that vary by
destination network and change over time — check
[Africa's Talking's current pricing](https://africastalking.com/pricing)
for Kenya-specific rates before relying on this at real message volume.
