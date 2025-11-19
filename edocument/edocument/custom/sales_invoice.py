# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def on_submit(doc, method):
	"""Create an EDocument record when Sales Invoice is submitted."""
	# Only create EDocument if edocument_profile is set
	if not doc.edocument_profile:
		return

	# Check if EDocument already exists for this Sales Invoice
	existing_edocument = frappe.db.exists(
		"EDocument",
		{
			"edocument_source_type": "Sales Invoice",
			"edocument_source_document": doc.name,
		},
	)

	if existing_edocument:
		return

	# Get country from company
	country = None
	if doc.company:
		country = frappe.db.get_value("Company", doc.company, "country")

	# Create EDocument record
	edocument = frappe.get_doc(
		{
			"doctype": "EDocument",
			"edocument_source_type": "Sales Invoice",
			"edocument_source_document": doc.name,
			"edocument_profile": doc.edocument_profile,
			"country": country,
		}
	)
	edocument.insert(ignore_permissions=True)
	
	frappe.msgprint(
		_("EDocument {0} created successfully").format(
			frappe.bold(edocument.name)
		),
		indicator="green",
		alert=True,
	)

