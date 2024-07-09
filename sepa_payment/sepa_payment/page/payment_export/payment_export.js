frappe.pages['payment-export'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Payment Export',
		single_column: true
	});
	frappe.payment_export.make(page);

	page.company_field = page.add_field({
		fieldname: 'company',
		label: __('Company'),
		fieldtype:'Link',
		options:'Company',
		default: frappe.defaults.get_user_default("Company"),
	});

	page.posting_date_field = page.add_field({
		fieldname: 'posting_date',
		label: __('Required Execution Date'),
		fieldtype:'Date',
		default:"Today"
	});
	page.payment_type_field = page.add_field({
		fieldname: 'payment_type',
		label: __('Payment Type'),
		fieldtype:'Select',
		default:"SEPA (EUR)",
		options:"SEPA (EUR)\nCross Border Payments (USD)\nCross Border Payments (EUR)\nCross Border Payments (OTHER)",
		onchange: () => {
			frappe.payment_export.run(page);
			getfindSelected()
			togglebankaccount(page)
		}
	});
	page.bank_account_field = page.add_field({
		fieldname: 'account',
		label: __('Bank Account'),
		fieldtype:'Link',
		options: "Bank Account",
	});
	page.set_secondary_action('Refresh', () => refresh())
	frappe.payment_export.run(page);
	getfindSelected()
}
frappe.payment_export = {
	start: 0,
	make: function(page) {
		var me = frappe.payment_export;
		me.page = page;
		me.body = $('<div></div>').appendTo(me.page.main);
		var data = "";
		$(frappe.render_template('payment_export', data)).appendTo(me.body);

		// attach button handlers
		this.page.main.find(".btn-create-file").on('click', function() {
			// find selected payments
			var checkedPayments = findSelected();
			if (checkedPayments.length > 0) {
				var payments = [];
				for (var i = 0; i < checkedPayments.length; i++) {
					payments.push(checkedPayments[i].name);
				}

				// generate payment file
				frappe.call({
					method: 'sepa_payment.sepa_payment.page.payment_export.payment_export.generate_xml_file',
					args: {
						'payments': payments,
						"posting_date": page.posting_date_field.get_value(),
						'company': page.company_field.get_value(),
						'payment_type':page.payment_type_field.get_value(),
						'bank_account': page.bank_account_field.get_value()
					},
					callback: function(r) {
						if (r.message) {
							
							var parent = page.main.find(".insert-log-messages").empty();
							download(`payments${r.message[1]}.xml`, r.message[0]);
							frappe.payment_export.run(page);
						}
					}
				});               

			} else {
				frappe.msgprint( __("Please select at least one payment."), __("Information") );
			}
		});
		this.page.main.find(".btn-validate").on('click', function() {
			frappe.call({
				method: "sepa_payment.sepa_payment.page.payment_export.payment_export.validate_master_data",
				args: {
					'company': page.company_field.get_value()
				},
				callback:function(r){
					console.log(r.message)
					if(!r.message.length){
						frappe.msgprint("No errors found.")
					}
					let html = `<table class="table" width="100%">
									<tbody>`
					r.message.forEach(element =>{
						html += `<tr><td><b>${element.party}</b></td><td><b>${element.msg}</b></td></tr>`
					})
					html += `</tbody>
						</table>`
					var logs = page.main.find(".missing_data").empty();
					$(html).appendTo(logs);
					frappe.msgprint(html)
				}
			})
		})
	},
	run: function(page) {
		// populate payment entries
		togglebankaccount(page)
		frappe.call({
			method: 'sepa_payment.sepa_payment.page.payment_export.payment_export.get_payments',
			args: {
				"posting_date": page.posting_date_field.get_value(),
				"company":page.company_field.get_value(),
				'payment_type':page.payment_type_field.get_value()
			 },
			callback: function(r) {
				if (r.message) {
					var parent = page.main.find(".payment-table").empty();
					if (r.message.payments.length > 0) {
						$(frappe.render_template('payment_export_table', r.message)).appendTo(parent);
					} else {
						$('<p class="text-muted">' + __("No payment entries to be paid found with status draft") + '</p>').appendTo(parent);
					}
					getfindSelected()
				}
			}
		});
	}
}

function download(filename, content) {
  var element = document.createElement('a');
  element.setAttribute('href', 'data:application/octet-stream;charset=utf-8,' + encodeURIComponent(content));
  element.setAttribute('download', filename);

  element.style.display = 'none';
  document.body.appendChild(element);

  element.click();

  document.body.removeChild(element);
}

function findSelected() {
	var inputs = document.getElementsByTagName("input");
	var checkboxes = [];
	var checked = [];
	for (var i = 0; i < inputs.length; i++) {
	  if (inputs[i].type == "checkbox" && inputs[i].classList.contains("inputcheck")) {
		checkboxes.push(inputs[i]);
		if (inputs[i].checked) {
		  checked.push(inputs[i]);
		}
	  }
	}
	return checked;
}
function refresh(){
	location.reload();
}
function getfindSelected() {

	var inputs = document.getElementsByTagName("input");
	var checked = [];
	var a = 0
	var total_selected = 0
	for (var i = 0; i < inputs.length; i++) {

		if (inputs[i].classList.contains("inputcheck")) {
			checked.push(inputs[i])
		  var isChecked = inputs[i].checked;

		  if (isChecked) {
			var checkid = inputs[i].id.replace('chk','')
			frappe.model.get_value('Payment Entry' , checkid , 'paid_amount' , (r) => {
				total_selected = r.paid_amount + total_selected
				if(i == inputs.length){
					var selected_entry = document.getElementById('total_selected_amount')
					selected_entry.innerHTML = `<b>Total Amount of Selected Entries</b>: <b>EUR ${total_selected}</b>`
				}
			})
			a++;
		  }
		}
	}
	if(a==0){
		var selected_entry = document.getElementById('total_selected_amount')
		selected_entry.innerHTML = `<b>Total Amount of Selected Entries</b>: ${a}`
	}
	if(checked.length || a){
		document.getElementById("update_selected").innerText = `${a}/${checked.length} Selected`
	}

}
function selectunselect(){

	var inputCheck = document.querySelector('.selectall');
	var indexerCheckboxes = document.querySelectorAll('.inputcheck');


	indexerCheckboxes.forEach(function(indexerCheckbox) {
		indexerCheckbox.checked = inputCheck.checked;
	});

	getfindSelected()
}

function togglebankaccount(page){
	var element = document.querySelector('[data-fieldname="account"]');
	if (page.payment_type_field.get_value() != 'SEPA (EUR)'){
		element.hidden = false;                                                                                                      
	}else{
		element.hidden = true;
	}
}