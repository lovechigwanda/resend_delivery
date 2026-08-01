app_name = "resend_delivery"
app_title = "Resend Delivery"
app_publisher = "lovechigwanda"
app_description = (
	"Send outgoing Frappe emails through Resend (resend.com) using per-account API keys."
)
app_email = "lschigwanda@gmail.com"
app_license = "MIT"

# Apps this app depends on
required_apps = ["frappe"]

# Route every outgoing Email Queue recipient through Resend instead of SMTP.
# Frappe calls this as: send(email_queue_doc, sender, recipient, message_bytes)
override_email_send = ["resend_delivery.controller.send"]

# Ensure the custom field used to correlate webhook events exists both on a
# fresh install and after migrating an existing site.
after_install = "resend_delivery.install.after_install"
after_migrate = "resend_delivery.install.after_install"
