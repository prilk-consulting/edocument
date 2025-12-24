# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def _get_profile_settings(profile_name):
	"""Get EDocument Profile settings."""
	if not profile_name:
		return None
	return frappe.db.get_value(
		"EDocument Profile",
		profile_name,
		[
			"edocument_generation_on_save",
			"edocument_generation_on_submit",
			"ignore_validation_error_for_edocument_generation",
		],
		as_dict=True,
	)


def _create_edocument(doc, ignore_validation_error=False):
	"""Create EDocument for the given Sales Invoice.

	Args:
		doc: Sales Invoice document
		ignore_validation_error: If True, don't throw error on validation failure

	Returns:
		EDocument document or None if already exists
	"""
	# Check if EDocument already exists for this document
	existing_edocument = frappe.db.exists(
		"EDocument",
		{
			"edocument_source_type": doc.doctype,
			"edocument_source_document": doc.name,
		},
	)

	if existing_edocument:
		edocument = frappe.get_doc("EDocument", existing_edocument)
		# Check validation status if not ignoring errors
		if not ignore_validation_error and edocument.status == "Validation Failed":
			frappe.throw(
				_("EDocument {0} validation failed: {1}").format(
					frappe.bold(edocument.name), edocument.error or _("Unknown error")
				)
			)
		return edocument

	# Get country from company
	country = None
	if doc.company:
		country = frappe.db.get_value("Company", doc.company, "country")

	# Create EDocument record (this triggers XML generation and validation in before_save)
	edocument = frappe.get_doc(
		{
			"doctype": "EDocument",
			"edocument_source_type": doc.doctype,
			"edocument_source_document": doc.name,
			"edocument_profile": doc.edocument_profile,
			"country": country,
			"company": doc.company,
		}
	)

	# Set flag to block on validation error if not ignoring
	# This causes EDocument.before_save to throw an error before the document is created
	if not ignore_validation_error:
		frappe.flags.block_on_validation_error = True

	try:
		edocument.insert(ignore_permissions=True)
	finally:
		# Always clear the flag
		frappe.flags.block_on_validation_error = False

	# Note: EDocument.on_update will update the source document's edocument field

	if edocument.status == "Validation Successful":
		frappe.msgprint(
			_("EDocument {0} created and validated successfully").format(frappe.bold(edocument.name)),
			indicator="green",
			alert=True,
		)
	elif edocument.status == "Validation Failed":
		frappe.msgprint(
			_("EDocument {0} created with validation errors: {1}").format(
				frappe.bold(edocument.name), edocument.error or _("Unknown error")
			),
			indicator="orange",
			alert=True,
		)

	return edocument


def on_update(doc, method):
	"""Create EDocument when Sales Invoice is saved (if profile setting enabled)."""
	# Only process if edocument_profile is set
	if not doc.edocument_profile:
		return

	# Don't create EDocument on update if invoice is already submitted
	if doc.docstatus == 1:
		return

	# Get profile settings
	profile_settings = _get_profile_settings(doc.edocument_profile)
	if not profile_settings:
		return

	# Check if generation on save is enabled
	if not profile_settings.get("edocument_generation_on_save"):
		return

	ignore_validation_error = profile_settings.get("ignore_validation_error_for_edocument_generation")
	_create_edocument(doc, ignore_validation_error=ignore_validation_error)


def before_submit(doc, method):
	"""Create and validate EDocument before Sales Invoice is submitted.

	Blocks submission if EDocument validation fails (unless ignore_validation_error is set).
	"""
	# Only process if edocument_profile is set
	if not doc.edocument_profile:
		return

	# Get profile settings
	profile_settings = _get_profile_settings(doc.edocument_profile)
	if not profile_settings:
		return

	# Check if generation on submit is enabled
	if not profile_settings.get("edocument_generation_on_submit"):
		return

	ignore_validation_error = profile_settings.get("ignore_validation_error_for_edocument_generation")
	_create_edocument(doc, ignore_validation_error=ignore_validation_error)
