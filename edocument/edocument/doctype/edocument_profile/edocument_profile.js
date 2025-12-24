// Copyright (c) 2025, Prilk Consulting BV and contributors
// For license information, please see license.txt

frappe.ui.form.on("EDocument Profile", {
	refresh(frm) {
		if (frm.doc.name === "PEPPOL") {
			frm.add_custom_button(
				__("Import PEPPOL Codes"),
				function () {
					frappe.call({
						method: "edocument.edocument.profiles.peppol.setup_peppol_codes.setup_peppol_codes",
						freeze: true,
						freeze_message: __("Importing PEPPOL code lists..."),
						callback: function (r) {
							if (!r.exc) {
								frappe.msgprint(__("PEPPOL code lists imported successfully."));
							}
						},
					});
				},
				__("Actions")
			);
		}
	},
});
