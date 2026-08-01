import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


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
