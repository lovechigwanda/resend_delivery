from urllib.parse import quote

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, get_url, validate_email_address


class ResendAccount(Document):
	def validate(self):
		self.sender_email = (self.sender_email or "").strip().lower()
		validate_email_address(self.sender_email, throw=True)

		if self.sender_display_name:
			self.sender_display_name = self.sender_display_name.strip()

		self._enforce_single_default()
		self._set_webhook_url()

	def on_update(self):
		# Make sure Frappe has a default outgoing Email Account so its mail
		# pipeline accepts outgoing email; Resend does the real sending. A
		# provisioning hiccup must never block saving the account itself.
		if self.enabled:
			try:
				from resend_delivery.install import ensure_outgoing_email_account

				ensure_outgoing_email_account(self.sender_email)
			except Exception:
				frappe.log_error(
					title="resend_delivery: could not provision outgoing Email Account"
				)

	def _enforce_single_default(self):
		"""At most one account may be marked as the default."""
		if not self.use_as_default:
			return

		others = frappe.get_all(
			"Resend Account",
			filters={"use_as_default": 1, "name": ["!=", self.name]},
			pluck="name",
		)
		# Silently demote the previous default so the newest choice wins,
		# rather than blocking the save.
		for name in others:
			frappe.db.set_value("Resend Account", name, "use_as_default", 0)

	def _set_webhook_url(self):
		"""Absolute URL a Resend webhook should target for this account."""
		self.webhook_url = "{base}/api/method/resend_delivery.api.resend_webhook?account={name}".format(
			base=get_url(),
			name=quote(self.name or ""),
		)

	@frappe.whitelist()
	def send_test_email(self, recipient: str | None = None):
		"""Send a small test message through this account's Resend key.

		Runs synchronously (not via the Email Queue) so the caller gets an
		immediate success/failure for the key + domain combination.
		"""
		from resend_delivery.controller import send_via_resend

		recipient = (recipient or self.sender_email or "").strip()
		validate_email_address(recipient, throw=True)

		if not self.enabled:
			frappe.throw(_("Enable this account before sending a test email."))

		html = _(
			"<p>This is a test email from <b>{0}</b> sent through Resend.</p>"
			"<p>If you are reading this, the API key and sending domain are working.</p>"
		).format(escape_html(self.account_name))

		resend_id = send_via_resend(
			self,
			to=recipient,
			subject=_("Resend Delivery test email"),
			html=html,
			text="This is a test email sent through Resend. Your API key and domain are working.",
		)
		return {"id": resend_id, "recipient": recipient}
