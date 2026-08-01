import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	"""Add a custom field on Email Queue used to correlate Resend webhook events.

	Resend returns its own email id (a UUID) for each message we send. We store
	it on the originating Email Queue row so that inbound webhook events
	(delivered / bounced / opened / ...) can be matched back to the right row.
	"""
	create_custom_fields(
		{
			"Email Queue": [
				{
					"fieldname": "resend_email_id",
					"label": "Resend Email ID",
					"fieldtype": "Data",
					"insert_after": "message_id",
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"translatable": 0,
				}
			]
		},
		ignore_validate=True,
	)
