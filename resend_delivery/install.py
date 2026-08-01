import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Name of the shell Email Account this app provisions so Frappe's mail pipeline
# is satisfied. Resend does the real sending; this account is never connected to.
PLACEHOLDER_EMAIL_ACCOUNT = "Resend Delivery"


def after_install():
	"""Add a custom field used to correlate Resend webhook events.

	Resend returns its own email id (a UUID) for each message we send. The
	``override_email_send`` hook fires once per recipient, so each recipient
	gets a distinct Resend id — we store it on the Email Queue Recipient (child)
	row, not the parent, so inbound webhook events (delivered / bounced /
	opened / ...) can be matched back to the exact recipient.
	"""
	create_custom_fields(
		{
			"Email Queue Recipient": [
				{
					"fieldname": "resend_email_id",
					"label": "Resend Email ID",
					"fieldtype": "Data",
					"insert_after": "recipient",
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"translatable": 0,
				}
			]
		},
		ignore_validate=True,
	)


def ensure_outgoing_email_account(email_id):
	"""Guarantee Frappe has a default outgoing Email Account.

	Frappe refuses to enqueue mail unless it can resolve a default outgoing
	Email Account, and that check runs *before* our ``override_email_send`` hook
	ever executes. Resend still performs the actual delivery — this account is a
	placeholder shell whose SMTP server (``localhost``) is never contacted,
	because the override path never opens an SMTP connection.

	Respects any existing default outgoing account and is safe to call
	repeatedly (idempotent). Returns the name of the account in effect, or
	``None`` if nothing was created.
	"""
	# A default outgoing account is already configured (real or placeholder) —
	# never override the user's own mail setup.
	existing = frappe.db.get_value(
		"Email Account", {"enable_outgoing": 1, "default_outgoing": 1}, "name"
	)
	if existing:
		return existing

	# Our placeholder exists but isn't currently the default — promote it.
	if frappe.db.exists("Email Account", PLACEHOLDER_EMAIL_ACCOUNT):
		frappe.db.set_value(
			"Email Account",
			PLACEHOLDER_EMAIL_ACCOUNT,
			{"enable_outgoing": 1, "default_outgoing": 1},
		)
		return PLACEHOLDER_EMAIL_ACCOUNT

	if not email_id:
		return None

	account = frappe.get_doc(
		{
			"doctype": "Email Account",
			"email_account_name": PLACEHOLDER_EMAIL_ACCOUNT,
			"email_id": email_id,
			"enable_incoming": 0,
			"enable_outgoing": 1,
			"default_outgoing": 1,
			# localhost makes Frappe skip its save-time SMTP connection test, and
			# the override path means it is never dialed at send time either.
			"smtp_server": "localhost",
			"smtp_port": 25,
			"use_tls": 0,
			"use_ssl_for_outgoing": 0,
			"no_smtp_authentication": 1,
		}
	)
	account.flags.ignore_permissions = True
	account.insert(ignore_permissions=True)

	frappe.msgprint(
		_(
			"Created a placeholder default outgoing Email Account "
			"(<b>{0}</b>) so Frappe will accept outgoing mail. Resend performs "
			"the actual delivery — this account's SMTP server is never used."
		).format(PLACEHOLDER_EMAIL_ACCOUNT),
		indicator="green",
		alert=True,
	)
	return account.name
