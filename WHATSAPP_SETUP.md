# Setting up WhatsApp supplier alerts

The code side of this is already built and live: every supplier purchase
order has a **Notify Supplier** button (`sales/order_detail.html`), backed
by `sales/whatsapp.py`. Until the three things below are done, clicking it
shows "WhatsApp isn't set up for this deployment yet" rather than silently
failing or pretending to send.

None of this can be done from code — it's account setup on Meta's side,
and it's yours to do (or delegate) since it ties to your business identity
and phone number.

## 1. Meta Business Account + WhatsApp Business Platform

1. Go to [business.facebook.com](https://business.facebook.com) and create
   (or use an existing) Meta Business Account.
2. In [developers.facebook.com](https://developers.facebook.com), create an
   App, add the **WhatsApp** product to it.
3. Meta gives you a **test phone number** for free to start — good enough
   to verify everything works before registering your real business number.
4. To send to real suppliers (not just pre-approved test recipients), you
   need to register and verify your actual business WhatsApp number. This
   involves phone verification (a code sent by call or SMS) and, for
   production volume, Meta's business verification process — this step can
   take anywhere from minutes to a few days depending on how much
   verification Meta asks for.

## 2. An approved message template

Business-initiated WhatsApp messages (i.e. you messaging a supplier who
hasn't messaged you first) **must** use a pre-approved template — free-form
text only works within 24 hours of the other side messaging first, which
doesn't fit "alert a supplier about a new PO."

In Meta Business Manager, under WhatsApp Manager → Message Templates,
create a template with a body that takes **4 text parameters in this
order** (matching what `sales/whatsapp.py` sends):

```
Hello from {{1}}. New purchase order #{{2}}: {{3}}. Total: {{4}}.
Please confirm you can fulfil this order.
```

Submit it for review. Templates are usually approved within a few hours,
sometimes up to 24.

If you want different wording, edit the `parameters` list in
`send_supplier_order_alert()` (`sales/whatsapp.py`) to match — the order
and count must line up exactly with your approved template's `{{1}}`,
`{{2}}`, etc.

## 3. Environment variables

Once you have a phone number and an approved template, set these wherever
the app is deployed (same place as `SECRET_KEY` and `DATABASE_URL`):

| Variable | Where to find it |
|---|---|
| `WHATSAPP_API_TOKEN` | Meta App Dashboard → WhatsApp → API Setup → a temporary token to start, a permanent one once you set up a System User for production |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta App Dashboard → WhatsApp → API Setup — a numeric ID, **not** the phone number itself |
| `WHATSAPP_TEMPLATE_NAME` | The template name you created in step 2. Defaults to `purchase_order_alert` if unset |

## Testing before suppliers see anything

Meta's test number can message a handful of verified recipient numbers
for free, before any business verification is needed. Add your own
number as a test recipient in the Meta dashboard, put it on a test
Supplier record (in international format, e.g. `254712345678`, not
`0712345678`), and click **Notify Supplier** on a test purchase order.

## Cost

WhatsApp Business API pricing is per-conversation (a 24-hour window),
not per-message, and Meta's published rates vary by country and change
over time — check [Meta's current WhatsApp pricing page](https://developers.facebook.com/docs/whatsapp/pricing/)
for Kenya-specific rates before relying on this at real order volume.
