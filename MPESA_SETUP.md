# Setting up M-Pesa STK Push payments

The code is already built and live: every invoice with a balance due
shows a **Pay with M-Pesa** form (`sales/templates/sales/invoice_detail.html`),
backed by `sales/mpesa.py`. Until the steps below are done, submitting it
shows "M-Pesa isn't set up for this deployment yet" instead of silently
failing or pretending to send a prompt.

This is account setup on Safaricom's side — it ties to your business
registration and bank settlement details, so it has to be you (or
someone you delegate) who does it.

## 1. Daraja developer account

1. Go to [developer.safaricom.co.ke](https://developer.safaricom.co.ke)
   and create an account.
2. Create a new App. This gives you a **Consumer Key** and **Consumer
   Secret** for the sandbox — enough to test everything below before
   any real money or business registration is involved.

## 2. A paybill or till number

- **For testing**: Safaricom's sandbox provides a shared test shortcode
  (commonly `174379`) with a published test Passkey — the Daraja docs
  under "Lipa Na M-Pesa Online" have the current values. No business
  registration needed for this.
- **For production**: you need your own paybill or till number, which
  means either an existing one from your bank/Safaricom relationship, or
  applying for a new one. This step involves real paperwork and Safaricom
  approval — it's the slowest part of this whole setup, budget days, not
  hours.

## 3. The callback URL

Safaricom POSTs the payment result to `MPESA_CALLBACK_URL` — it must be a
real, publicly reachable **HTTPS** URL. This is the one piece that
genuinely cannot be tested from `python manage.py runserver` on your own
machine without a tunnel (ngrok, Cloudflare Tunnel, etc.), since
Safaricom's servers need to reach it over the public internet.

Once deployed, this is:
```
https://<your-domain>/sales/mpesa/callback/
```

This route is deliberately exempt from login — Safaricom's servers aren't
a logged-in user — but it verifies the request against a specific pending
transaction it already knows about (the `CheckoutRequestID` from step 4),
so an unrelated POST to this URL doesn't do anything.

## 4. Environment variables

| Variable | Where to find it |
|---|---|
| `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` | Your Daraja App page |
| `MPESA_SHORTCODE` | The paybill/till number (sandbox test number while testing) |
| `MPESA_PASSKEY` | Daraja App page, under "Lipa Na M-Pesa Online" — sandbox has a published test passkey |
| `MPESA_ENVIRONMENT` | `sandbox` while testing, `production` only once the real shortcode is live |
| `MPESA_CALLBACK_URL` | The public URL from step 3 |

## How the flow actually works

1. Someone clicks **Send Payment Prompt** on an invoice. The app calls
   Safaricom, which immediately returns a `CheckoutRequestID` — this is
   just an acknowledgement that the request was accepted, **not** that
   anyone has paid anything yet.
2. The customer's phone shows an M-Pesa PIN prompt. They approve, decline,
   or the prompt times out (about 60–90 seconds) with no action.
3. Safaricom POSTs the actual result to your callback URL, seconds to a
   couple of minutes later. **Only this step** creates a real payment
   record and reduces the invoice's balance — nothing before it does.

If a customer's prompt times out and the callback never fires as
"success", the invoice correctly stays unpaid. There's no need to
manually clean anything up — it just shows as a "Pending" or "Failed"
row in the M-Pesa attempts list on the invoice page.

## Testing before it's real

Daraja's sandbox lets you complete the full flow — including the
callback — against Safaricom's test environment, using their published
test phone number and PIN, with no real money moving and no business
registration required. Do this before touching production credentials.
