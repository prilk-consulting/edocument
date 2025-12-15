// Copyright (c) 2025, Prilk Consulting BV and contributors
// For license information, please see license.txt

frappe.ui.form.on("EDocument", {
	refresh(frm) {
		// Generate XML button - for outgoing documents with source
		if (frm.doc.edocument_source_document && frm.doc.edocument_profile) {
			frm.add_custom_button(__("Generate XML"), () => {
				frm.call({
					method: "generate_xml",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Generating XML..."),
					callback: () => frm.reload_doc()
				});
			}, __("Actions"));
		}


		// XML-dependent buttons - check for XML files first
		if (frm.doc.edocument_profile) {
			frm.call({
				method: "_has_xml_file",
				doc: frm.doc,
				callback: (r) => {
					if (r.message || frm.doc.xml_file) {
						// Preview EDocument button - only when XML exists
						frm.add_custom_button(__("Preview EDocument"), () => {
							frm.call({
								method: "generate_preview",
								doc: frm.doc,
								freeze: true,
								freeze_message: __("Generating preview..."),
								callback: (r) => {
									if (r.message) {
										frm.get_field("edocument_preview")?.set_value(r.message);
										frm.get_field("edocument_preview")?.$wrapper?.css({
											"width": "100%", "max-width": "100%", "overflow-x": "auto",
											"padding": "15px", "background-color": "#fff",
											"border": "1px solid #e0e0e0", "border-radius": "4px", "margin-top": "10px"
										}).find("> div").css({ "width": "100%", "max-width": "100%" });
									}
								},
								error: (r) => frappe.msgprint(__("Error generating preview: {0}", [r.message]))
							});
						}, __("Actions"));

						// Validate XML button
						frm.add_custom_button(__("Validate XML"), () => {
							frm.call({
								method: "validate_xml",
								doc: frm.doc,
								freeze: true,
								freeze_message: __("Validating XML..."),
								callback: () => frm.reload_doc()
							});
						}, __("Actions"));

						// Create Document buttons
						frm.add_custom_button(__("Create & Review Document"), () => {
							frappe.model.open_mapped_doc({
								method: "edocument.edocument.doctype.edocument.edocument.create_document",
								frm: frm,
								freeze_message: __("Parsing XML and preparing document..."),
							});
						}, __("Actions"));

						frm.add_custom_button(__("Create Document"), () => {
							frm.call({
								method: "create_and_save_document",
								doc: frm.doc,
								freeze: true,
								freeze_message: __("Creating document from XML..."),
								callback: (r) => { if (r.message) frm.reload_doc(); }
							});
						}, __("Actions"));
					}
				}
			});
		}
	},
});
