// Copyright (c) 2025, Prilk Consulting BV and contributors
// For license information, please see license.txt

frappe.ui.form.on("EDocument", {
	refresh(frm) {
		setup_action_buttons(frm);
	},
});

function setup_action_buttons(frm) {
	// Generate XML - for outgoing documents
	if (frm.doc.edocument_source_document && frm.doc.edocument_profile) {
		frm.add_custom_button(__("Generate XML"), () => {
			frm.call({
				method: "generate_xml",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Generating XML..."),
				callback: () => frm.reload_doc(),
			});
		}, __("Actions"));
	}

	// XML-dependent buttons
	if (!frm.doc.edocument_profile) return;

	frm.call({
		method: "_has_xml_file",
		doc: frm.doc,
		callback: (r) => {
			if (!r.message && !frm.doc.xml_file) return;

			frm.add_custom_button(__("Preview EDocument"), () => show_preview(frm), __("Actions"));
			frm.add_custom_button(__("Validate XML"), () => validate_xml(frm), __("Actions"));
			frm.add_custom_button(__("Match Document"), () => match_document(frm), __("Actions"));
			frm.add_custom_button(__("Create Document"), () => create_document(frm), __("Actions"));
			frm.add_custom_button(__("Review and Create Document"), () => review_and_create(frm), __("Actions"));

			// Auto-load preview on form load
			show_preview(frm);
		},
	});
}

function show_preview(frm) {
	frm.call({
		method: "generate_preview",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Generating preview..."),
		callback: (r) => {
			if (!r.message) return;
			frm.get_field("edocument_preview")?.set_value(r.message);
			frm.get_field("edocument_preview")?.$wrapper?.css({
				width: "100%",
				padding: "15px",
				background: "#fff",
				border: "1px solid #e0e0e0",
				borderRadius: "4px",
				marginTop: "10px",
			});
		},
	});
}

function validate_xml(frm) {
	frm.call({
		method: "validate_xml",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Validating XML..."),
		callback: () => frm.reload_doc(),
	});
}

function create_document(frm) {
	frm.call({
		method: "create_and_save_document",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Creating document from XML..."),
		callback: (r) => { if (r.message) frm.reload_doc(); },
	});
}

function match_document(frm) {
	frm.call({
		method: "get_matching_status",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Checking matching status..."),
		callback: (r) => {
			if (!r.message?.has_matcher) {
				frappe.msgprint(__("No matcher configured for this profile."));
				return;
			}
			show_matching_dialog(frm, r.message.matching_data, r.message.dialog_config);
		},
	});
}

function review_and_create(frm) {
	frappe.model.open_mapped_doc({
		method: "edocument.edocument.doctype.edocument.edocument.create_document",
		frm: frm,
		freeze_message: __("Parsing XML and preparing document..."),
	});
}

function show_matching_dialog(frm, matching_data, config) {
	const dialog = new frappe.ui.Dialog({
		title: config.title,
		size: "large",
		fields: config.fields,
		primary_action_label: __("Save"),
		primary_action: () => save_matching(frm, dialog, matching_data),
	});
	dialog.show();
}

function save_matching(frm, dialog, original_data) {
	const data = JSON.parse(JSON.stringify(original_data));
	const values = dialog.get_values();

	// Update supplier
	if (data.supplier) {
		data.supplier.matched = values.supplier || null;
		if (values.supplier && values.supplier !== original_data.supplier?.matched) {
			data.supplier.match_method = "manual";
		}
	}

	// Update items from table
	const items_table = values.items || [];
	for (let i = 0; i < (data.items || []).length; i++) {
		const table_row = items_table[i];
		const original_matched = original_data.items?.[i]?.matched;
		if (table_row) {
			data.items[i].matched = table_row.matched_item || null;
			if (table_row.matched_item && table_row.matched_item !== original_matched) {
				data.items[i].match_method = "manual";
			}
		}
	}

	// Update purchase order
	if (data.purchase_order) {
		data.purchase_order.matched = values.purchase_order || null;
		if (values.purchase_order && values.purchase_order !== original_data.purchase_order?.matched) {
			data.purchase_order.match_method = "manual";
		}
	}

	frm.call({
		method: "save_matching_data",
		doc: frm.doc,
		args: { matching_data: data },
		freeze: true,
		freeze_message: __("Saving..."),
		callback: (r) => {
			if (r.message?.success) {
				dialog.hide();
				frm.reload_doc();
			}
		},
	});
}
