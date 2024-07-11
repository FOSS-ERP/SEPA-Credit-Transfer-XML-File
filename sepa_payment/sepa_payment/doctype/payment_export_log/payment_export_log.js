// Copyright (c) 2024, Viral Kansodiya and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Export Log', {
	refresh: frm => {
		if(frm.doc.status != 'Submitted'){
			frm.add_custom_button(
				__("Submit Payment Entry"),
				function () {
					frappe.call({
						method : "sepa_payment.sepa_payment.doctype.payment_export_log.payment_export_log.submit_all_payment_entry",
						args : {
							self : frm.doc
						}
					})
				},
			).addClass("btn btn-primary");;
		}
	}
});
