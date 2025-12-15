# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Preview module for EDocument XML preview.
This module routes to profile-specific preview functions based on the EDocument Profile.

This module handles XML to HTML transformation for preview using XSLT.
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_xml_preview(xml_bytes=None, edocument_profile=None):
	"""
	Get XML preview (HTML transformation) based on the profile.

	Args:
	    xml_bytes: Optional XML content as bytes. If not provided, will be fetched from current document
	    edocument_profile: Optional EDocument Profile document. If not provided, will be fetched from current document

	Returns:
	    str: HTML string for preview
	"""
	# Handle xml_bytes - if it's passed as a string (from JavaScript), decode it
	if xml_bytes and isinstance(xml_bytes, str):
		xml_bytes = xml_bytes.encode("utf-8")

	# Handle edocument_profile - if it's a string (profile name), get the document
	if edocument_profile and isinstance(edocument_profile, str) and edocument_profile.strip():
		try:
			edocument_profile = frappe.get_doc("EDocument Profile", edocument_profile)
			frappe.log_error(f"Loaded EDocument Profile: {edocument_profile.name}")
		except Exception as e:
			frappe.log_error(f"Could not load EDocument Profile '{edocument_profile}': {e}")
			edocument_profile = None
	elif edocument_profile and not isinstance(edocument_profile, str):
		# Already a document object
		pass
	else:
		frappe.log_error(f"Invalid edocument_profile: {edocument_profile} (type: {type(edocument_profile)})")

	# If no xml_bytes provided, get from current document
	if xml_bytes is None:
		docname = frappe.form_dict.get("docname")
		doctype = frappe.form_dict.get("doctype")
		if docname and doctype:
			current_doc = frappe.get_doc(doctype, docname)
			xml_bytes = current_doc._get_xml_from_attached_files()

	# If no profile provided, get from current document
	if edocument_profile is None:
		docname = frappe.form_dict.get("docname")
		doctype = frappe.form_dict.get("doctype")
		if docname and doctype:
			try:
				current_doc = frappe.get_doc(doctype, docname)
				if current_doc.edocument_profile:
					edocument_profile = frappe.get_doc("EDocument Profile", current_doc.edocument_profile)
			except Exception as e:
				frappe.log_error(f"Could not load document {doctype} {docname}: {e}")

	# Try to get preview function from profile's preview_path if specified
	if edocument_profile and hasattr(edocument_profile, "preview_path") and edocument_profile.preview_path:
		try:
			preview_func = frappe.get_attr(edocument_profile.preview_path)
			return preview_func(xml_bytes, edocument_profile)
		except Exception as e:
			frappe.log_error(f"Error loading preview from path {edocument_profile.preview_path}: {e!s}")

	# Default: Use basic preview (placeholder)
	return preview_basic_xml(xml_bytes, edocument_profile)


def preview_basic_xml(xml_bytes, edocument_profile):
	"""
	Basic XML preview (placeholder implementation).
	This should be replaced with actual profile-specific preview functions.

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document

	Returns:
		str: HTML string for preview
	"""
	frappe.throw(
		_(
			"No preview function configured for profile {0}. Please set preview_path in EDocument Profile or implement profile-specific preview."
		).format(edocument_profile.name)
	)
