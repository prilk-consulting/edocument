// Copyright (c) 2025, Prilk Consulting BV and contributors
// For license information, please see license.txt

frappe.ui.form.on("EDocument", {
	refresh(frm) {
		// Show Generate XML button if source document exists
		if (frm.doc.edocument_source_document && frm.doc.edocument_profile) {
			frm.add_custom_button(
				__("Generate XML"),
				function () {
					frm.call({
						method: "generate_xml",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Generating XML..."),
						callback: function (r) {
							// Reload form to show updated status and error fields
							frm.reload_doc();
						},
					});
				},
				__("Actions")
			);
		}

		// Show Validate XML button if XML file exists (either uploaded or generated)
		if (frm.doc.edocument_profile) {
			// Check for uploaded XML file first (synchronous check)
			if (frm.doc.xml_file) {
				frm.add_custom_button(
					__("Validate XML"),
					function () {
						frm.call({
							method: "validate_xml",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Validating XML..."),
							callback: function (r) {
								// Reload form to show validation results in error field
								frm.reload_doc();
							},
						});
					},
					__("Actions")
				);
			} else if (frm.doc.edocument_source_document) {
				// Check for generated XML file (asynchronous check)
				frm.call({
					method: "_has_xml_file",
					doc: frm.doc,
					callback: function (r) {
						if (r.message) {
							frm.add_custom_button(
								__("Validate XML"),
								function () {
									frm.call({
										method: "validate_xml",
										doc: frm.doc,
										freeze: true,
										freeze_message: __("Validating XML..."),
										callback: function (r) {
											// Reload form to show validation results in error field
											frm.reload_doc();
										},
									});
								},
								__("Actions")
							);
						}
					},
				});
			}
		}

		// Show Create Document buttons for uploaded XML
		if (frm.doc.xml_file && frm.doc.edocument_profile) {
			// Button 1: Open document with prefilled data for review
			frm.add_custom_button(
				__("Create & Review Document"),
				function () {
					// Use open_mapped_doc to open document with prefilled data
					frappe.model.open_mapped_doc({
						method: "edocument.edocument.doctype.edocument.edocument.create_document",
						frm: frm,
						freeze_message: __("Parsing XML and preparing document..."),
					});
				},
				__("Actions")
			);

			// Button 2: Create and save document without opening
			frm.add_custom_button(
				__("Create Document"),
				function () {
					frm.call({
						method: "create_and_save_document",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Creating document from XML..."),
						callback: function (r) {
							if (r.message) {
								// Reload to show updated target document fields
								frm.reload_doc();
							}
						},
					});
				},
				__("Actions")
			);
		}
	},
});
