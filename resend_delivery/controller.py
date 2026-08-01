"""Route outgoing Frappe email through Resend's HTTP API.

Frappe invokes :func:`send` for every outgoing Email Queue recipient (via the
``override_email_send`` hook) instead of using SMTP. We look up the matching
Resend Account for the sender, convert the rendered MIME message into the JSON
shape Resend's ``/emails`` endpoint expects, and POST it with that account's
API key.
"""

import base64
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr

import frappe
import requests
from frappe import _

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 30


def send(email_queue, sender, recipient, message):
	"""``override_email_send`` entry point.

	Called by Frappe as ``send(email_queue_doc, sender, recipient, message)``
	once per recipient. ``message`` is the rendered MIME message (bytes).
	"""
	account = _get_account_for_sender(sender)

	if isinstance(message, str):
		message = message.encode("utf-8")
	mime = message_from_bytes(message)

	payload = _build_payload(account, recipient, mime)
	resend_id = send_payload(account, payload)

	_record_result(email_queue, resend_id)


def send_via_resend(account, to, subject, html=None, text=None):
	"""Convenience helper used by the "Send Test Email" button.

	Builds a minimal payload and sends it synchronously through ``account``.
	Returns the Resend email id.
	"""
	payload = {
		"from": _format_from(account),
		"to": [to],
		"subject": subject or "",
	}
	if html:
		payload["html"] = html
	if text:
		payload["text"] = text
	if not html and not text:
		payload["text"] = " "
	return send_payload(account, payload)


def send_payload(account, payload):
	"""POST a fully-formed payload to Resend and return the created email id."""
	api_key = account.get_password("api_key")
	if not api_key:
		frappe.throw(_("Resend Account {0} has no API key configured.").format(account.name))

	try:
		resp = requests.post(
			RESEND_API_URL,
			json=payload,
			headers={
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json",
			},
			timeout=REQUEST_TIMEOUT,
		)
	except requests.RequestException as exc:
		frappe.throw(_("Could not reach Resend: {0}").format(str(exc)))

	if resp.status_code // 100 != 2:
		frappe.throw(_("Resend rejected the message: {0}").format(_error_text(resp)))

	try:
		return (resp.json() or {}).get("id")
	except ValueError:
		return None


# ---------------------------------------------------------------------------
# Account routing
# ---------------------------------------------------------------------------


def _get_account_for_sender(sender):
	"""Find the Resend Account that should send mail from ``sender``.

	Matches on the sender's email address, falling back to the account flagged
	``Use as Default``. Raises (marking the Email Queue row Error) if neither
	exists, rather than silently falling back to SMTP.
	"""
	addr = (parseaddr(sender or "")[1] or (sender or "")).strip().lower()

	name = frappe.db.get_value(
		"Resend Account", {"sender_email": addr, "enabled": 1}, "name"
	)
	if not name:
		name = frappe.db.get_value(
			"Resend Account", {"use_as_default": 1, "enabled": 1}, "name"
		)
	if not name:
		frappe.throw(
			_(
				"No enabled Resend Account matches sender {0}, and no default "
				"account is configured."
			).format(addr or sender)
		)

	return frappe.get_cached_doc("Resend Account", name)


# ---------------------------------------------------------------------------
# MIME -> Resend JSON conversion
# ---------------------------------------------------------------------------


def _build_payload(account, recipient, mime: Message):
	html, text, attachments = _extract_parts(mime)

	payload = {
		"from": _format_from(account),
		"to": [recipient],
		"subject": _decode(mime.get("Subject")) or "",
	}
	if html:
		payload["html"] = html
	if text:
		payload["text"] = text
	# Resend requires at least one body.
	if not html and not text:
		payload["text"] = " "

	reply_to = _decode(mime.get("Reply-To"))
	if reply_to:
		payload["reply_to"] = reply_to

	headers = {}
	# The original Cc is preserved for reference only; Resend still sends to the
	# single envelope recipient this hook was called with.
	cc = _decode(mime.get("Cc"))
	if cc:
		headers["X-Original-Cc"] = cc
	for header in ("In-Reply-To", "References"):
		value = _decode(mime.get(header))
		if value:
			headers[header] = value
	if headers:
		payload["headers"] = headers

	if attachments:
		payload["attachments"] = attachments

	return payload


def _extract_parts(mime: Message):
	"""Return ``(html, text, attachments)`` extracted from a MIME message."""
	html = None
	text = None
	attachments = []

	if not mime.is_multipart():
		body = _decode_body(mime)
		if mime.get_content_type() == "text/html":
			return body, None, attachments
		return None, body, attachments

	for part in mime.walk():
		if part.is_multipart():
			continue

		content_type = part.get_content_type()
		disposition = str(part.get("Content-Disposition") or "").lower()
		filename = part.get_filename()
		is_attachment = bool(filename) or "attachment" in disposition or "inline" in disposition

		if not is_attachment and content_type == "text/html":
			html = _decode_body(part)
		elif not is_attachment and content_type == "text/plain":
			text = _decode_body(part)
		elif is_attachment:
			attachment = _build_attachment(part, filename)
			if attachment:
				attachments.append(attachment)

	return html, text, attachments


def _build_attachment(part: Message, filename):
	payload = part.get_payload(decode=True)
	if payload is None:
		return None

	content_id = (part.get("Content-ID") or "").strip().strip("<>")
	attachment = {
		"filename": _decode(filename) or content_id or "attachment",
		"content": base64.b64encode(payload).decode("ascii"),
	}
	if content_id:
		attachment["content_id"] = content_id
	return attachment


def _decode_body(part: Message):
	payload = part.get_payload(decode=True)
	if payload is None:
		return None
	charset = part.get_content_charset() or "utf-8"
	try:
		return payload.decode(charset, errors="replace")
	except (LookupError, TypeError):
		return payload.decode("utf-8", errors="replace")


def _decode(value):
	"""Decode an RFC 2047 encoded header into a plain string."""
	if not value:
		return None
	try:
		return str(make_header(decode_header(value)))
	except Exception:
		return str(value)


def _format_from(account):
	if account.sender_display_name:
		return f"{account.sender_display_name} <{account.sender_email}>"
	return account.sender_email


# ---------------------------------------------------------------------------
# Writeback
# ---------------------------------------------------------------------------


def _record_result(email_queue, resend_id):
	"""Store the Resend id and move the row to ``Sending``.

	Final delivery is confirmed asynchronously by the webhook; until then the
	message is in flight, so ``Sending`` (not ``Sent``) is the correct status.
	"""
	if resend_id:
		try:
			email_queue.db_set("resend_email_id", resend_id, commit=False)
		except Exception:
			# Custom field missing (install/migrate not run yet) — non-fatal.
			frappe.log_error(title="resend_delivery: could not store resend_email_id")

	try:
		email_queue.db_set("status", "Sending", commit=True)
	except Exception:
		frappe.db.set_value("Email Queue", email_queue.name, "status", "Sending")
		frappe.db.commit()


def _error_text(resp):
	try:
		data = resp.json()
	except ValueError:
		return (resp.text or "")[:500] or f"HTTP {resp.status_code}"

	if isinstance(data, dict):
		message = data.get("message") or data.get("error") or data.get("name")
		if message:
			return f"{message} (HTTP {resp.status_code})"
	return f"HTTP {resp.status_code}"
