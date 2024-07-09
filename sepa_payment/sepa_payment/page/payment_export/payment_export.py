# -*- coding: utf-8 -*-
# Copyright (c) 2017-2018, libracore (https://www.libracore.com) and contributors
# License: AGPL v3. See LICENCE

from __future__ import unicode_literals
import html
import time
from collections import defaultdict
from datetime import datetime
from itertools import groupby
import frappe
from frappe import _, throw
from frappe.utils import flt, get_link_to_form, getdate, now, nowdate, get_url
from sepa_payment.sepa_payment.page.payment_export.cross_border_payment import get_cross_border_xml_file


@frappe.whitelist()
def generate_xml_file(payments,  posting_date, company, payment_type, bank_account = None):
	if payment_type != "SEPA (EUR)":
		content, transaction_count, control_sum = get_cross_border_xml_file(payments, company, posting_date, payment_type, bank_account)
		# gen_payment_export_log(content, transaction_count, control_sum, payments, currency=None)
	else:
		current_time = now()
		original_date = datetime.strptime(str(current_time), '%Y-%m-%d %H:%M:%S.%f')
		formatted_date = original_date.strftime('%Y-%m-%d %H-%M-%S')
		formatted_date = formatted_date.replace(' ','-')
		content = genrate_file_for_sepa(payments, posting_date)
	return content , formatted_date
	

@frappe.whitelist()
def get_payments(company, payment_type):
	payments = frappe.db.sql(
		f""" Select pe.name, pe.posting_date, pe.paid_amount, pe.party, pe.party_name, ba.iban,pe.total_allocated_amount,
			pe.paid_from, pe.paid_to_account_currency, per.reference_doctype, per.reference_name
			From `tabPayment Entry` as pe
			Left Join `tabPayment Entry Reference` as per ON per.parent = pe.name
			left join `tabBank Account` as ba ON ba.party_type = pe.party_type and ba.party = pe.party
			Where pe.docstatus = 0 and pe.payment_type = "Pay" and pe.xml_file_generated = 0 and ba.iban is not null
			and pe.paid_from_account_currency = 'EUR' and pe.company = '{company}'
			order by posting_date
		""",
		as_dict=1,
	)

	submitted_entry = frappe.db.sql(""" Select pe.name, pe.posting_date, pe.paid_amount, pe.party, pe.party_name, pe.paid_from, pe.paid_to_account_currency, per.reference_doctype,
									per.reference_name, pe.received_amount
									From `tabPayment Entry` as pe 
									Left Join `tabPayment Entry Reference` as per ON per.parent = pe.name
									Where pe.docstatus = 1 and pe.payment_type = "Pay" and pe.party_type = "Supplier" and pe.xml_file_generated = 0 and pe.custom_include_in_xml_file = 1
									order by posting_date
									""",as_dict = 1)
	
	payments = payments + submitted_entry

	payments_ = []

	key_func = lambda k: k["name"]

	INFO = sorted(payments, key=key_func)

	for key, value in groupby(INFO, key_func):
		ref_name_list = []
		for d in list(value):
			ref_name_list.append(d.get("reference_name"))
		d.update({"reference_name": ref_name_list})
		payments_.append(d)
	total_paid_amount = 0
	for row in payments_:
		total_paid_amount += row.paid_amount

	_payments = []
	list_of_amount = []

	for row in payments_:
		payment = frappe.get_doc('Payment Entry', row.name)
		if payment_type == "SEPA (EUR)" and frappe.db.get_value('Supplier', row.party, 'payment_type') == 'SEPA (EUR)':
				flag = False
				for d in row.reference_name:
					currency = frappe.db.get_value(row.reference_doctype, d, 'currency')
					if currency == "EUR":
						flag = True
				if flag:
					_payments.append(row)
					list_of_amount.append(row.paid_amount)
		if payment_type == "Cross Border Payments (USD)" and frappe.db.get_value('Supplier', row.party, 'payment_type') == 'Cross Border Payments (USD)':
				row.update({"paid_amount" : row.received_amount})
				_payments.append(row)
				list_of_amount.append(row.received_amount)
		if payment_type == "Cross Border Payments (EUR)" and frappe.db.get_value('Supplier', row.party, 'payment_type') == 'Cross Border Payments (EUR)':
				row.update({"paid_amount" : row.received_amount})
				_payments.append(row)
				list_of_amount.append(row.received_amount)
		if payment_type == "Cross Border Payments (OTHER)" and frappe.db.get_value('Supplier', row.party, 'payment_type') == 'Cross Border Payments (OTHER)':
				row.update({"paid_amount" : row.received_amount})
				_payments.append(row)
				list_of_amount.append(row.received_amount)
	
	return {"payments": _payments, "total_paid_amount": total_paid_amount, "time":now()}


# adds Windows-compatible line endings (to make the xml look nice)
def make_line(line):
	return line + "\r\n"


@frappe.whitelist()
def genrate_file_for_sepa(payments, posting_date):
	payments = eval(payments)
	payments = list(filter(None, payments))

	message_root = get_message_root()

	group_header = get_group_header_content(payments, message_root)

	content, transaction_count, control_sum = get_payment_info(
		payments, group_header, posting_date
	)

	gen_payment_export_log(
		content, transaction_count, control_sum, payments, currency=None
	)

	return content


def get_message_root():
	# create xml header
	content = make_line('<?xml version="1.0" encoding="UTF-8"?>')
	# define xml template reference
	content += make_line(
		'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03 pain.001.001.03.xsd">'
	)
	# transaction holder
	content += make_line("<CstmrCdtTrfInitn>")
	return content


def get_group_header_content(payments, message_root):
	content = message_root
	content += make_line("      <GrpHdr>")
	content += make_line(
		"          <MsgId>{0}</MsgId>".format(time.strftime("%Y%m%d%H%M%S"))
	)
	content += make_line(
		"          <CreDtTm>{0}</CreDtTm>".format(time.strftime("%Y-%m-%dT%H:%M:%S"))
	)
	transaction_count = 0
	transaction_count_identifier = "<!-- $COUNT -->"
	content += make_line(
		"          <NbOfTxs>{0}</NbOfTxs>".format(transaction_count_identifier)
	)
	control_sum = 0.0
	control_sum_identifier = "<!-- $CONTROL_SUM -->"
	content += make_line(
		"          <CtrlSum>{0}</CtrlSum>".format(control_sum_identifier)
	)
	content += make_line("          <InitgPty>")
	content += make_line(
		"              <Nm>{0}</Nm>".format(get_company_name(payments[0]))
	)

	company = get_company_name(payments[0])
	initiating_party_org_id = frappe.db.get_value(
		"Company", company, "initiating_party_org_id"
	)
	if not initiating_party_org_id:
		frappe.throw(
			"Please update a valid <b>Initiating Party Org Id</b> in company {}".format(
				get_link_to_form("Company", company)
			)
		)
	content += make_line("              <Id>")
	content += make_line("                  <OrgId>")
	content += make_line("                      <Othr>")
	content += make_line(
		f"                          <Id>{initiating_party_org_id}</Id>"
	)
	content += make_line("                          <SchmeNm>")
	content += make_line("                              <Cd>BANK</Cd>")
	content += make_line("                          </SchmeNm>")
	content += make_line("                      </Othr>")
	content += make_line("                  </OrgId>")
	content += make_line("              </Id>")
	content += make_line("          </InitgPty>")
	content += make_line("      </GrpHdr>")

	return content


def get_payment_info(payments, group_header, posting_date):
	content = group_header
	content += make_line("      <PmtInf>")
	content += make_line("          <PmtInfId>{0}</PmtInfId>".format(payments[0]))
	content += make_line("          <PmtMtd>TRF</PmtMtd>")
	content += make_line("          <BtchBookg>false</BtchBookg>")
	transaction_count = 0
	transaction_count_identifier = "<!-- $COUNT -->"
	content += make_line(
		"          <NbOfTxs>{0}</NbOfTxs>".format(transaction_count_identifier)
	)
	control_sum = 0.0
	control_sum_identifier = "<!-- $CONTROL_SUM -->"
	content += make_line(
		"          <CtrlSum>{0}</CtrlSum>".format(control_sum_identifier)
	)

	content += make_line("          <PmtTpInf>")
	content += make_line("              <SvcLvl>")
	content += make_line("                  <Cd>SEPA</Cd>")
	content += make_line("              </SvcLvl>")
	content += make_line("          </PmtTpInf>")

	required_execution_date = posting_date
	content += make_line(
		"          <ReqdExctnDt>{0}</ReqdExctnDt>".format(required_execution_date)
	)

	content += make_line("          <Dbtr>")
	company_name = get_company_name(payments[0])
	debtor_org_id = frappe.db.get_value("Company", company_name, "debtor_org_id")
	if not debtor_org_id:
		frappe.throw(
			"Please update a valid <b>Debtor Org Id</b> in company {}".format(
				get_link_to_form("Company", company_name)
			)
		)
	content += make_line("              <Nm>{0}</Nm>".format(company_name))
	content += make_line("              <Id>")
	content += make_line("                  <OrgId>")
	content += make_line("                      <Othr>")
	content += make_line("                          <Id>{}</Id>".format(debtor_org_id))
	content += make_line("                          <SchmeNm>")
	content += make_line("                              <Cd>BANK</Cd>")
	content += make_line("                          </SchmeNm>")
	content += make_line("                      </Othr>")
	content += make_line("                  </OrgId>")
	content += make_line("              </Id>")
	content += make_line("              <CtryOfRes>SE</CtryOfRes>")
	content += make_line("          </Dbtr>")

	content += make_line("          <DbtrAcct>")
	content += make_line("              <Id>")
	iban = get_company_iban(company_name)
	content += make_line("                  <IBAN>{0}</IBAN>".format(iban.get("iban")))
	content += make_line("              </Id>")
	content += make_line("              <Ccy>EUR</Ccy>")
	content += make_line("          </DbtrAcct>")

	content += make_line("          <DbtrAgt>")
	content += make_line(
		"          <!-- Note: For IBAN only on Debtor side use Othr/Id: NOTPROVIDED - see below -->"
	)
	content += make_line("              <FinInstnId>")
	if iban.get("branch_code") or iban.get("swift_number"):
		content += make_line(
			"          <BIC>{0}</BIC>".format(
				iban.get("swift_number")
				if iban.get("swift_number")
				else iban.get("branch_code")
			)
		)
	else:
		content += make_line("                  <Othr>")
		content += make_line("                      <Id>NOTPROVIDED</Id>")
		content += make_line("                  </Othr>")
	content += make_line("              </FinInstnId>")
	content += make_line("          </DbtrAgt>")

	content += make_line("          <ChrgBr>SLEV</ChrgBr>")
	for payment in payments:
		frappe.db.set_value("Payment Entry", payment, "xml_file_generated", 1)
		payment_record = frappe.get_doc("Payment Entry", payment)

		content += make_line("          <CdtTrfTxInf>")
		content += make_line("              <PmtId>")
		content += make_line("                  <InstrId>{}</InstrId>".format(payment))
		content += make_line(
			"                  <EndToEndId>{}</EndToEndId>".format(
				payment.replace("-", "")
			)
		)
		content += make_line("              </PmtId>")
		content += make_line("              <Amt>")
		content += make_line(
			'                  <InstdAmt Ccy="{0}">{1:.2f}</InstdAmt>'.format(
				payment_record.paid_from_account_currency,
				payment_record.total_allocated_amount,
			)
		)
		content += make_line("              </Amt>")
		content += make_line(
			"              <!-- Note: Creditor Agent should not be used at all for IBAN only on Creditor side -->"
		)
		content += make_line("              <Cdtr>")

		name = frappe.db.get_value("Supplier", payment_record.party, "supplier_name")
		if "&" in name:
			new_name = name.replace("& ", "")
			if new_name == name:
				new_name = name.replace("&", " ")
			name = new_name
		content += make_line("                  <Nm>{0}</Nm>".format(name))
		content += make_line("              </Cdtr>")
		content += make_line("              <CdtrAcct>")
		content += make_line("                  <Id>")
		iban_code = get_supplier_iban_no(payment_record.party)
		content += make_line(
			"                      <IBAN>{0}</IBAN>".format(iban_code.strip() or "")
		)
		content += make_line("                  </Id>")
		content += make_line("              </CdtrAcct>")
		content += make_line("              <RmtInf>")
		sup_invoice_no = []
		for row in payment_record.references:
			bill_no = frappe.db.get_value(
				"Purchase Invoice",
				payment_record.references[0].reference_name,
				"bill_no",
			)
			if bill_no:
				sup_invoice_no.append(bill_no)
		if sup_invoice_no:
			sup_invoice_no = " ,".join(sup_invoice_no)

		content += make_line(
			"                  <Ustrd>{0}</Ustrd>".format(
				sup_invoice_no if sup_invoice_no else ""
			)
		)
		content += make_line("              </RmtInf>")
		content += make_line("          </CdtTrfTxInf>")
		transaction_count += 1
		control_sum += payment_record.paid_amount
	content += make_line("      </PmtInf>")
	content += make_line("  </CstmrCdtTrfInitn>")
	content += make_line("</Document>")
	content = content.replace(
		transaction_count_identifier, "{0}".format(transaction_count)
	)
	content = content.replace(control_sum_identifier, "{:.2f}".format(control_sum))

	return content, transaction_count, control_sum


def get_supplier_iban_no(party):
	iban = frappe.db.sql(
		f"""
		Select iban, name From `tabBank Account` where party_type = 'Supplier' and party = '{party}' and iban is not null
	""",
		as_dict=1,
	)
	if not iban:
		frappe.throw("Please create bank account for supplier <b>{0}</b>".format(party))
	if iban:
		if not iban[0].get("iban"):
			frappe.throw(
				"Please update a iban number in bank account <b>{0}</b>".format(
					get_link_to_form("Bank Account", iban[0].get("name"))
				)
			)
		return iban[0].iban
	return ""


def get_company_name(payment_entry):
	return frappe.get_value("Payment Entry", payment_entry, "company")


def get_company_iban(company_name):
	iban = frappe.db.sql(
		f"""
		Select ba.iban, ba.name, ba.bank, b.swift_number, ba.branch_code
		From `tabBank Account` as ba
		Left Join `tabBank` as b On b.name = ba.bank
		where is_company_account = 1 and company = '{company_name}'
	 """,
		as_dict=1,
	)

	if not iban:
		frappe.throw(
			"Please create bank account for company <b>{0}</b>".format(company_name)
		)
	if iban:
		if not iban[0].get("iban"):
			frappe.throw(
				"Please update a iban number in bank account <b>{0}</b>".format(
					get_link_to_form("Bank Account", iban[0].get("name"))
				)
			)
		return iban[0]
	return ""


def gen_payment_export_log(
	content, total_no_of_payments, total_paid_amount, payments, currency=None
):
	doc = frappe.new_doc("Payment Export Log")
	doc.file_creation_time = now()
	doc.user = frappe.session.user
	doc.currency = currency
	doc.total_paid_amount = total_paid_amount
	doc.total_no_of_payments = total_no_of_payments
	doc.content = content
	doc.flags.ignore_permissions = 1
	for row in payments:
		pay_doc = frappe.get_doc("Payment Entry", row)
		doc.append(
			"logs",
			{
				"payment_entry": row,
				"supplier": pay_doc.party,
				"paid_amount": pay_doc.paid_amount,
				"status": pay_doc.status,
			},
		)

	doc.save()
	frappe.msgprint(
		"Payment Export Log :- {}".format(
			get_link_to_form("Payment Export Log", doc.name)
		)
	)


@frappe.whitelist()
def validate_master_data(company):
	payment = frappe.db.sql(
		f""" Select pe.name, pe.posting_date, pe.paid_amount, pe.party, pe.party_name, ba.iban, ba.bban, ba.name as bank_account,pe.party_type,
								pe.paid_from, pe.paid_to_account_currency, per.reference_doctype, per.reference_name
								From `tabPayment Entry` as pe
								Left Join `tabPayment Entry Reference` as per ON per.parent = pe.name
								left join `tabBank Account` as ba ON ba.party_type = pe.party_type and ba.party = pe.party
								Where pe.docstatus = 0 and pe.payment_type = "Pay" and pe.xml_file_generated = 0
								and pe.paid_from_account_currency = 'EUR' and pe.company = '{company}'
								order by posting_date
							""",
		as_dict=1,
	)
	master_data = []

	for row in payment:
		if row.bank_account and not (row.iban or row.bban) :
			url = ""
			url = get_url()
			url += url + f"/apps/bank-account/{row.bank_account}"
			master_data.append(
				{
					"doctype": row.party_type,
					"party": row.party,
					"msg": f"Iban Code or Bban Code is missing for the transaction , Update in the Bank Account <a href ='{url}'>bank account</a> ",
				}
			)
		if not row.bank_account:
			master_data.append(
				{
					"doctype": row.party_type,
					"party": row.party,
					"msg": "<b>Bank Account</b> details is missing",
				}
			)

	return master_data
