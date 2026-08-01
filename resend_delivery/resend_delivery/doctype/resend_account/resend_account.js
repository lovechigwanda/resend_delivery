frappe.ui.form.on("Resend Account", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Send Test Email"), () => {
				frappe.prompt(
					[
						{
							fieldname: "recipient",
							label: __("Send test email to"),
							fieldtype: "Data",
							options: "Email",
							reqd: 1,
							default: frm.doc.sender_email,
						},
					],
					(values) => {
						frappe.dom.freeze(__("Sending test email..."));
						frm
							.call("send_test_email", { recipient: values.recipient })
							.then((r) => {
								frappe.dom.unfreeze();
								if (r && r.message) {
									frappe.show_alert({
										message: __("Test email sent to {0} (Resend id {1})", [
											r.message.recipient,
											r.message.id,
										]),
										indicator: "green",
									});
								}
							})
							.catch(() => frappe.dom.unfreeze());
					},
					__("Send Test Email"),
					__("Send")
				);
			});
		}
	},
});
