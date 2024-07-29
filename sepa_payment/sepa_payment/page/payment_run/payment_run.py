# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import json
from functools import reduce
from erpnext.accounts.doctype.payment_entry.payment_entry import (
	set_party_type, 
	apply_early_payment_discount,
	update_accounting_dimensions,
	set_party_account_currency, 
	set_party_account,
	get_bank_cash_account,
	set_payment_type,
	set_paid_amount_and_received_amount,
	set_grand_total_and_outstanding_amount
	)
import frappe
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate, nowdate
from frappe.utils.data import comma_and, fmt_money
from pypika import Case
from pypika.functions import Coalesce, Sum

import erpnext
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_dimensions
from erpnext.accounts.doctype.bank_account.bank_account import (
	get_bank_account_details,
	get_party_bank_account,
)
from erpnext.accounts.party import get_party_account
from erpnext.setup.utils import get_exchange_rate

@frappe.whitelist()
def get_purchase_invoice(orderby, payment_type, due_date=None, payable_account=None, bank_account=None ):
	settings = frappe.get_doc("Payment Run Setting")
	
	if due_date:    
		data = frappe.db.sql(f"""
				Select 
				pi.name, 
				pi.bill_no, 
				pi.grand_total, 
				pi.outstanding_amount as panding_amount, 
				pi.supplier_name, 
				pi.due_date,
				pi.supplier,
				pi.currency,
				su.payment_type,
				pi.status,
				per.parent as payment_entry,
				per.total_amount,
				per.outstanding_amount,
				per.docstatus
				From `tabPurchase Invoice` as pi
				Left Join `tabSupplier` as su On su.name = pi.supplier
				left join `tabPayment Entry Reference` as per ON per.reference_name = pi.name and per.reference_doctype = "Purchase Invoice"
				Where pi.docstatus = 1 and pi.outstanding_amount > 0 and pi.due_date <= '{due_date}' 
				Order By pi.due_date {orderby}
		""",as_dict=1)
		invoices = []

		for row in data:
			if row.payment_entry and row.docstatus == 0:
				row.update({"docstatus" : "Draft"})
			if row.payment_entry and row.docstatus == 1:
				row.update({"docstatus" : "Submitted"})
			if row.status in ['Unpaid','Overdue']:
				if payment_type == row.payment_type:
					invoices.append(row)
			if row.status == 'Partly Paid':
				if payment_type == row.payment_type:
					invoices.append(row)
		if payment_type in ["SEPA (EUR)", "Cross Border Payments (EUR)"]:
			currency = "EUR"
		if payment_type == "Domestic (Swedish) Payments (SEK)":
			currency = "SEK"
		if payment_type == "Cross Border Payments (USD)":
			currency = "USD"
		if payment_type == "Cross Border Payments (OTHER)":
			if not bank_account:
				invoices = []
				return {"invoices" : invoices, 'currency':"SEK"}
			doc = frappe.get_doc("Bank Account", bank_account)
			currency = frappe.db.get_value("Account", doc.account , "account_currency")

		return {"invoices" : invoices, 'currency':currency}

@frappe.whitelist()
def get_invoices(invoices, payment_type, bank_account=None):
	if payment_type in ["SEPA (EUR)", "Cross Border Payments (EUR)"]:
		currency = "EUR"
	if payment_type == "Domestic (Swedish) Payments (SEK)":
		currency = "SEK"
	if payment_type == "Cross Border Payments (USD)":
		currency = "USD"
	if payment_type == "Cross Border Payments (OTHER)":
		doc = frappe.get_doc("Bank Account", bank_account)
		currency = frappe.db.get_value("Account", doc.account , "account_currency")
		account_paid_from = doc.account
	invoices = eval(invoices)
	invoices = list(filter(None, invoices))
	settings = frappe.get_doc("Payment Run Setting")
	for row in settings.payment_account:
		if row.currency == currency and not bank_account:
			account_paid_from = row.account_paid_from
			break
	Error = []
	frappe.enqueue(create_payment_entry_in_background, invoices=invoices,account_paid_from=account_paid_from, queue="long")

def create_payment_entry_in_background(invoices=[] , account_paid_from=None):
	Error = []
	for row in invoices:
		doc = get_payment_entry('Purchase Invoice', row, account_paid_from = account_paid_from)
		try:
			doc.save()
		except Exception as e:
			Error.append(row)
			frappe.log_error(e)


def get_payment_entry(
	dt,
	dn,
	party_amount=None,
	bank_account=None,
	bank_amount=None,
	party_type=None,
	payment_type=None,
	reference_date=None,
	account_paid_from = None
):
	doc = frappe.get_doc(dt, dn)
	over_billing_allowance = frappe.db.get_single_value("Accounts Settings", "over_billing_allowance")
	if dt in ("Sales Order", "Purchase Order") and flt(doc.per_billed, 2) >= (100.0 + over_billing_allowance):
		frappe.throw(_("Can only make payment against unbilled {0}").format(_(dt)))

	if not party_type:
		party_type = set_party_type(dt)

	party_account = set_party_account(dt, dn, doc, party_type)
	party_account_currency = set_party_account_currency(dt, party_account, doc)

	if not payment_type:
		payment_type = set_payment_type(dt, doc)

	grand_total, outstanding_amount = set_grand_total_and_outstanding_amount(
		party_amount, dt, party_account_currency, doc
	)
	
	# bank or cash
	bank = get_bank_cash_account(doc, bank_account)
	
	# if default bank or cash account is not set in company master and party has default company bank account, fetch it
	if party_type in ["Customer", "Supplier"] and not bank:
		party_bank_account = get_party_bank_account(party_type, doc.get(scrub(party_type)))
		if party_bank_account:
			account = frappe.db.get_value("Bank Account", party_bank_account, "account")
			bank = get_bank_cash_account(doc, account)
	
	bank = frappe.get_doc("Account",account_paid_from)
	paid_amount, received_amount = set_paid_amount_and_received_amount(
		dt, party_account_currency, bank, outstanding_amount, payment_type, bank_amount, doc
	)

	reference_date = getdate(reference_date)
	paid_amount, received_amount, discount_amount, valid_discounts = apply_early_payment_discount(
		paid_amount, received_amount, doc, party_account_currency, reference_date
	)

	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = payment_type
	pe.company = doc.company
	pe.cost_center = doc.get("cost_center")
	pe.posting_date = nowdate()
	pe.reference_date = reference_date
	pe.mode_of_payment = doc.get("mode_of_payment")
	pe.party_type = party_type
	pe.party = doc.get(scrub(party_type))
	pe.contact_person = doc.get("contact_person")
	pe.contact_email = doc.get("contact_email")
	pe.ensure_supplier_is_not_blocked()
	settings = frappe.get_doc("Payment Run Setting")
	for row in settings.payment_account:
		if row.currency == doc.currency:
			account_paid_from = row.account_paid_from
			break
	pe.paid_from = account_paid_from
	pe.paid_from_account_currency = doc.currency
	pe.paid_to = party_account if payment_type == "Pay" else bank.account

	pe.paid_from_account_currency = (
		doc.currency
	)
	pe.paid_to_account_currency = doc.currency
	pe.paid_amount = paid_amount
	pe.received_amount = received_amount
	pe.letter_head = doc.get("letter_head")

	if dt in ["Purchase Order", "Sales Order", "Sales Invoice", "Purchase Invoice"]:
		pe.project = doc.get("project") or reduce(
			lambda prev, cur: prev or cur, [x.get("project") for x in doc.get("items")], None
		)  # get first non-empty project from items

	if pe.party_type in ["Customer", "Supplier"]:
		bank_account = get_party_bank_account(pe.party_type, pe.party)
		pe.set("bank_account", bank_account)
		pe.set_bank_account_data()

	# only Purchase Invoice can be blocked individually
	if doc.doctype == "Purchase Invoice" and doc.invoice_is_blocked():
		frappe.msgprint(_("{0} is on hold till {1}").format(doc.name, doc.release_date))
	else:
		if doc.doctype in (
			"Sales Invoice",
			"Purchase Invoice",
			"Purchase Order",
			"Sales Order",
		) and frappe.get_cached_value(
			"Payment Terms Template",
			{"name": doc.payment_terms_template},
			"allocate_payment_based_on_payment_terms",
		):
			for reference in get_reference_as_per_payment_terms(
				doc.payment_schedule, dt, dn, doc, grand_total, outstanding_amount, party_account_currency
			):
				pe.append("references", reference)
		else:
			if dt == "Dunning":
				pe.append(
					"references",
					{
						"reference_doctype": "Sales Invoice",
						"reference_name": doc.get("sales_invoice"),
						"bill_no": doc.get("bill_no"),
						"due_date": doc.get("due_date"),
						"total_amount": doc.get("outstanding_amount"),
						"outstanding_amount": doc.get("outstanding_amount"),
						"allocated_amount": doc.get("outstanding_amount"),
					},
				)
				pe.append(
					"references",
					{
						"reference_doctype": dt,
						"reference_name": dn,
						"bill_no": doc.get("bill_no"),
						"due_date": doc.get("due_date"),
						"total_amount": doc.get("dunning_amount"),
						"outstanding_amount": doc.get("dunning_amount"),
						"allocated_amount": doc.get("dunning_amount"),
					},
				)
			else:
				pe.append(
					"references",
					{
						"reference_doctype": dt,
						"reference_name": dn,
						"bill_no": doc.get("bill_no"),
						"due_date": doc.get("due_date"),
						"total_amount": grand_total,
						"outstanding_amount": outstanding_amount,
						"allocated_amount": outstanding_amount,
					},
				)

	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.set_missing_ref_details()

	update_accounting_dimensions(pe, doc)

	if party_account and bank:
		pe.set_exchange_rate(ref_doc=doc)
		pe.set_amounts()

		if discount_amount:
			base_total_discount_loss = 0
			if frappe.db.get_single_value("Accounts Settings", "book_tax_discount_loss"):
				base_total_discount_loss = split_early_payment_discount_loss(pe, doc, valid_discounts)

			set_pending_discount_loss(
				pe, doc, discount_amount, base_total_discount_loss, party_account_currency
			)

		pe.set_difference_amount()

	return pe