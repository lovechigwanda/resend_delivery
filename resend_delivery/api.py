"""Inbound Resend webhook endpoint.

Resend signs webhook deliveries with Svix HMAC (headers ``svix-id``,
``svix-timestamp``, ``svix-signature``). We verify the signature against the
signing secret stored on a Resend Account before reflecting the event back onto
the originating Email Queue / Communication.
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _

# Reject events whose timestamp is outside this window (replay protection).
TIMESTAMP_TOLERANCE_SECONDS = 5 * 60

# Resend event type -> Email Queue status
_QUEUE_STATUS = {
	"email.sent": "Sent",
	"email.delivered": "Sent",
	"email.bounced": "Error",
	"email.delivery_delayed": "Sending",
}

# Resend event type -> Communication.delivery_status
_COMM_STATUS = {
	"email.sent": "Sent",
	"email.delivered": "Sent",
	"email.opened": "Opened",
	"email.clicked": "Clicked",
	"email.bounced": "Bounced",
	"email.complained": "Marked As Spam",
}


@frappe.whitelist(allow_guest=True)
def resend_webhook(account=None):
	body = frappe.request.data or b""
	if isinstance(body, str):
		body = body.encode("utf-8")

	verified_account = _verify_signature(body, frappe.request.headers, account)
	if not verified_account:
		frappe.local.response.http_status_code = 401
		return {"status": "invalid signature"}

	try:
		event = json.loads(body.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		frappe.local.response.http_status_code = 400
		return {"status": "invalid payload"}

	_process_event(event)
	return {"status": "ok"}


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def _verify_signature(body: bytes, headers, account_name=None):
	"""Return the name of the account whose secret validates the signature.

	Returns ``None`` when no configured secret verifies the payload.
	"""
	svix_id = headers.get("svix-id") or headers.get("webhook-id")
	svix_ts = headers.get("svix-timestamp") or headers.get("webhook-timestamp")
	svix_sig = headers.get("svix-signature") or headers.get("webhook-signature")
	if not (svix_id and svix_ts and svix_sig):
		return None

	try:
		if abs(time.time() - int(svix_ts)) > TIMESTAMP_TOLERANCE_SECONDS:
			return None
	except (TypeError, ValueError):
		return None

	signed_content = f"{svix_id}.{svix_ts}.".encode("utf-8") + body
	provided = _signature_values(svix_sig)
	if not provided:
		return None

	for name, secret in _candidate_secrets(account_name):
		expected = _compute_signature(secret, signed_content)
		if not expected:
			continue
		for candidate in provided:
			if hmac.compare_digest(candidate, expected):
				return name

	return None


def _signature_values(header_value):
	"""Extract the base64 signatures from a (possibly space-separated) header.

	Each entry looks like ``v1,<base64sig>``; unversioned values are accepted too.
	"""
	values = []
	for token in header_value.split(" "):
		token = token.strip()
		if not token:
			continue
		values.append(token.split(",", 1)[1] if "," in token else token)
	return values


def _compute_signature(secret, signed_content: bytes):
	key = secret
	if key.startswith("whsec_"):
		key = key[len("whsec_") :]
	try:
		key_bytes = base64.b64decode(key)
	except (ValueError, TypeError):
		return None
	digest = hmac.new(key_bytes, signed_content, hashlib.sha256).digest()
	return base64.b64encode(digest).decode("ascii")


def _candidate_secrets(account_name):
	"""Yield ``(account_name, secret)`` pairs to try, most specific first."""
	if account_name:
		secret = _get_secret(account_name)
		if secret:
			yield account_name, secret
			return

	for name in frappe.get_all("Resend Account", filters={"enabled": 1}, pluck="name"):
		secret = _get_secret(name)
		if secret:
			yield name, secret


def _get_secret(account_name):
	try:
		doc = frappe.get_cached_doc("Resend Account", account_name)
	except frappe.DoesNotExistError:
		return None
	try:
		return doc.get_password("webhook_signing_secret")
	except Exception:
		return None


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------


def _process_event(event):
	event_type = event.get("type") or ""
	data = event.get("data") or {}
	email_id = data.get("email_id") or data.get("id")
	if not email_id:
		return

	queue_name = frappe.db.get_value("Email Queue", {"resend_email_id": email_id}, "name")
	if not queue_name:
		return

	updates = {}
	status = _QUEUE_STATUS.get(event_type)
	if status:
		updates["status"] = status
	if event_type == "email.bounced":
		updates["error"] = _bounce_text(data)
	if updates:
		frappe.db.set_value("Email Queue", queue_name, updates)

	comm_status = _COMM_STATUS.get(event_type)
	if comm_status:
		communication = frappe.db.get_value("Email Queue", queue_name, "communication")
		if communication:
			frappe.db.set_value(
				"Communication", communication, "delivery_status", comm_status, update_modified=False
			)

	frappe.db.commit()


def _bounce_text(data):
	bounce = data.get("bounce") or {}
	if isinstance(bounce, dict):
		message = bounce.get("message") or bounce.get("subType") or bounce.get("type")
		if message:
			return _("Bounced by Resend: {0}").format(message)
	return _("Bounced by Resend.")
