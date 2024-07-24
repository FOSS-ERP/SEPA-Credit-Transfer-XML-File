frappe.pages['payment-run'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Payment Run',
		single_column: true
	});
	
	page.company = page.add_field({
		fieldname: 'company',
        label: __('Company'),
        fieldtype:'Link',
        options:'Company',
		default:"Vesta Si Sweden AB"
	})
	page.due_date = page.add_field({
		fieldname: 'due_date',
        label: __('Due Date'),
        fieldtype:'Date',
		default:'Today',
		onchange:()=>{
			frappe.payment_run.run(page);
		}
	})

	page.payment_type_field = page.add_field({
        fieldname: 'payment_type',
        label: __('Payment Type'),
        fieldtype:'Select',
        default:"SEPA (EUR)",
        options:"SEPA (EUR)\nCross Border Payments (USD)\nCross Border Payments (EUR)\nCross Border Payments (OTHER)",
        onchange: () => {
            getfindSelected()
			togglecurrency(page)
            frappe.payment_run.run(page);
        }
    });
	page.bank_account = page.add_field({
        fieldname: 'account',
        label: __('Bank Account'),
        fieldtype:'Link',
        options: "Bank Account",
		onchange: () => {
            getfindSelected()
        }
    });

	frappe.payment_run.make(page);
	frappe.payment_run.run(page);
	
}

frappe.payment_run = {
	make: (page) => {
		var me = frappe.payment_run;
        me.page = page;
        me.body = $('<div></div>').appendTo(me.page.main);
        let data = '';
        $(frappe.render_template('payment_run', data)).appendTo(me.body);
		$(".create-payment").on('click', function() {
			let checked = findSelected()
			if (checked.length > 0) {
                var invoices = [];
                for (var i = 0; i < checked.length; i++) {
                    invoices.push(checked[i].name);
                }
				frappe.call({
					method:"sepa_payment.sepa_payment.page.payment_run.payment_run.get_invoices",
					args:{
						invoices : invoices,
						payment_type : page.payment_type_field.get_value(),
						bank_account : page.bank_account.get_value()
					},
					callback:r=>{
						if(!r.message){
							frappe.msgprint("Payment entries are being created. This process may take a few moments.<br><br>Please check payment entry List")
						}else{
							frappe.msgprint(r.message)
						}
						page.main.find(".btn-create").addClass("hide");
                        page.main.find(".btn-refresh").removeClass("hide");
					}
				})

			}
		})
		page.main.find(".btn-refresh").on('click', function() {
            location.reload(); 
        });
	},
	run: (page , orderby="ASC") => {
		togglecurrency(page)
		frappe.call({
			method:"sepa_payment.sepa_payment.page.payment_run.payment_run.get_purchase_invoice",
			args:{
				orderby : orderby,
				payment_type : page.payment_type_field.get_value(),
				due_date: page.due_date.get_value(),
				bank_account : page.bank_account.get_value()
			},
			callback:(r)=>{
				var parent = page.main.find(".purchase_invoice_table").empty();
				if (r.message.invoices.length > 0) {
					$(frappe.render_template('purchase_invoice_table', r.message)).appendTo(parent);
					document.getElementById('selectedCountDisplay').innerText = `0 / ${r.message.invoices.length}`;
				} else {
					$('<p class="text-muted">' + __("No Purchase invoice to be unpaid found with status Submited") + '</p>').appendTo(parent);
				}
				$(".descending").on('click', function() {
					frappe.payment_run.run(page,orderby = "DESC");
				})
				$(".ascending").on('click', function() {
					frappe.payment_run.run(page,orderby = "ASC");
				})
			}
		})
	}
}

function selectunselect() {
	// Get the state of the "select all" checkbox
	var selectAllCheckbox = document.querySelector('.selectall');
	var isChecked = selectAllCheckbox.checked;

	// Get all checkboxes in the table with the class 'inputcheck'
	var checkboxes = document.querySelectorAll('.inputcheck');

	// Set the checked state of all checkboxes based on the "select all" checkbox
	checkboxes.forEach(function(checkbox) {
		checkbox.checked = isChecked;
	});
	getfindSelected()
}
function findSelected(){
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
function getfindSelected() {
	// Get all checkboxes in the table with the class 'inputcheck'
	var checkboxes = document.querySelectorAll('.inputcheck');
	// Count the number of checked checkboxes
	var total_row = 0;
	var selectedCount = 0;
	checkboxes.forEach(function(checkbox) {
		total_row++;
		if (checkbox.checked) {
			selectedCount++;
		}
	});

	// Alternatively, you could display this count in the UI
	document.getElementById('selectedCountDisplay').innerText = `${selectedCount} / ${total_row}`;

}

function togglecurrency(page){
    var element = document.querySelector('[data-fieldname="account"]');
	console.log(element)
    if (page.payment_type_field.get_value() == 'Cross Border Payments (OTHER)'){
        element.hidden = false;
    }else{
        element.hidden = true;
    }
}