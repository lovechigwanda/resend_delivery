# Resend Delivery

Route outgoing Frappe/ERPNext email through [Resend](https://resend.com), using
API keys you paste in yourself. Inspired by
[frappe/email_delivery_service](https://github.com/frappe/email_delivery_service)
(which is Mailgun + Frappe Cloud only), reworked so it:

- Uses **Resend** instead of Mailgun, talking to Resend's HTTP API directly.
- Works on **any** Frappe site, not just Frappe Cloud — there's no
  dependency on Frappe Cloud's `press` API or a Frappe-Cloud-issued
  site_config secret.
- Lets you define **multiple named sending identities** ("Resend Accounts"),
  each with its own API key, instead of one global key per site. Outgoing
  mail is routed to the right key by matching the "From" address.
- Bring-your-own-key: you paste in a Resend API key you generated yourself,
  stored encrypted in the Password field.
- Verifies Resend's webhook signatures (Svix HMAC) instead of a bare shared
  secret string.
- Has a built-in "Send Test Email" button so you can confirm a key/domain
  works before relying on it.

## How it works

Frappe supports an `override_email_send` hook: instead of using SMTP, every
outgoing Email Queue recipient is handed to a function of your choosing.
This app implements that function (`resend_delivery/controller.py`), which:

1. Looks at the outgoing "From" address and finds a matching **Resend
   Account** record (falling back to whichever one is marked "Use as
   Default").
2. Converts Frappe's rendered MIME message into the JSON shape Resend's
   `/emails` endpoint expects (subject, html, text, attachments) — Resend's
   API is JSON, not a raw MIME upload like Mailgun's.
3. POSTs it to `https://api.resend.com/emails` using that account's API key.
4. Records the returned Resend email id on the Email Queue row, and updates
   status.

A webhook endpoint (`/api/method/resend_delivery.api.resend_webhook`) then
receives `email.delivered` / `email.bounced` / `email.complained` /
`email.opened` / `email.clicked` events from Resend and reflects them back
onto Email Queue / Communication.

## Installation

```bash
bench get-app resend_delivery <repo-url>
bench --site your-site.local install-app resend_delivery
```

## Setup

1. In Resend, verify the domain(s) you'll send from, and create an API key
   (Sending access is enough).
2. In Frappe, go to **Resend Account** (new) and create one record per
   sending identity, e.g.:
   - **Account Name**: `Support Team`
   - **Sender Email**: `support@yourdomain.com` (must be on a Resend-verified domain)
   - **Sender Display Name**: `Acme Support` (optional, shown as the From name)
   - **Resend API Key**: paste the key from Resend
   - **Use as Default**: check this on (at most) one account, as the
     fallback for senders that don't match any specific account
3. Click **Send Test Email** to confirm it works before saving/relying on it.
4. Optional but recommended: in Resend, add a Webhook pointed at the
   **Webhook URL** shown on the Resend Account form, subscribe to the
   `email.*` events you care about, and paste the signing secret
   (`whsec_...`) back into **Webhook Signing Secret** so events are
   signature-verified.

That's it — once at least one enabled Resend Account exists, all outgoing
mail from Frappe is sent through Resend.

## Notes / limitations

- Resend's API takes an explicit `to` per request; since Frappe already
  dispatches this hook once per recipient (mirroring SMTP envelope
  behaviour), each recipient gets sent individually with `to` set to just
  their address. The original message's `Cc` header is preserved as a
  custom header for reference, but Resend's own recipient/Cc handling is
  not used.
- If no Resend Account matches the sender and none is marked default, the
  send fails loudly (Email Queue status `Error`) rather than silently
  falling back to SMTP — configure a default account to avoid surprises.
- Requires Frappe v15+ (uses `frappe.get_cached_doc`).

## License

MIT
