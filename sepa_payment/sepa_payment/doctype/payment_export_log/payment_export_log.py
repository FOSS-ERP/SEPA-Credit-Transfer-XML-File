# Copyright (c) 2024, Viral Kansodiya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json
from frappe.utils import flt, get_link_to_form, getdate, now, nowdate, get_url

class PaymentExportLog(Document):
    def on_update(self):
        flag = True
        for row in self.logs:
            if row.status != "Submitted":
                flag = False
        if flag:
            self.db_set('status', "Submitted")


@frappe.whitelist()
def submit_all_payment_entry(self : dict):
    doc = json.loads(self)
    skipped = []
    log = frappe.get_doc('Payment Export Log', doc.get('name'))
    for row in log.logs:
        if not row.ignore_to_submit_payment_entry:
            payment_doc = frappe.get_doc('Payment Entry', row.get('payment_entry'))
            try:
                payment_doc.submit()
                frappe.db.set_value("Payment Transaction Log", row.get('name'), 'status', payment_doc.status)
            except:
                skipped.append(payment_doc.name)
    if skipped:
        message = "Error While submitting payment entry<br>"
        for d in skipped:
            message += "<p>{0}</p><br>".format(get_link_to_form('Payment Entry', d))
        frappe.msgprint(message)
    else:
        frappe.db.set_value('Payment Export Log', doc.get('name'), 'status', 'Submitted')
        frappe.msgprint('Payment entries have been submitted successfully.')



#On submit of the payment entry

def payment_entry_submit():
    if self.party_type == "Supplier" and self.payment_type == "Pay":
        if not (self.xml_file_generated):
            frappe.throw("XML file is not generated for this payment entry <b>{0}</b>.".format(self.name))
        data =  frappe.db.sql(f'''
                Select parent From `tabPayment Transaction Log` 
                Where payment_entry = "{self.name}"
            ''', as_dict =1)
        if len(data):
            pel_doc = frappe.get_doc('Payment Export Log', data[0].parent)
            for row in pel_doc.logs:
                if row.payment_entry == self.name:
                    frappe.db.set_value(row.doctype , row.name, 'status', 'Submitted')