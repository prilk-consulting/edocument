# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

import frappe


def on_update(doc, method):
	"""Update EDocument target fields when Purchase Invoice is saved with edocument reference."""
	if not doc.edocument:
		return

	# Check if EDocument exists
	if not frappe.db.exists("EDocument", doc.edocument):
		return

	# Update EDocument with target document information if not already set
	edocument_target = frappe.db.get_value(
		"EDocument", doc.edocument, ["edocument_target_type", "edocument_target_document"], as_dict=True
	)

	if not edocument_target.edocument_target_type or not edocument_target.edocument_target_document:
		frappe.db.set_value(
			"EDocument",
			doc.edocument,
			{
				"edocument_target_type": doc.doctype,
				"edocument_target_document": doc.name,
			},
			update_modified=False,
		)
