# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Parser module for EDocument XML parsing.
This module routes to profile-specific parsers based on the EDocument Profile.

This module handles XML parsing to create Purchase Invoices from imported XML files.
"""

import frappe
from frappe import _


def get_xml_parser(xml_bytes, edocument_profile):
	"""
	Get XML parser based on the profile.

	The parser is determined by:
	1. Check if edocument_profile has a parser_path field
	2. If not found, fall back to basic parser

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document

	Returns:
		dict: Document data dictionary with 'doctype' field ready to be used with frappe.get_doc()
	"""
	# Try to get parser from profile's parser_path if specified
	if hasattr(edocument_profile, "parser_path") and edocument_profile.parser_path:
		try:
			parser_func = frappe.get_attr(edocument_profile.parser_path)
			return parser_func(xml_bytes, edocument_profile)
		except Exception as e:
			frappe.log_error(f"Error loading parser from path {edocument_profile.parser_path}: {e!s}")
			# Fall through to basic parser if loading fails

	# Default: Use basic XML parser
	return parse_basic_xml(xml_bytes, edocument_profile)


def parse_basic_xml(xml_bytes, edocument_profile):
	"""
	Basic XML parser (placeholder implementation).
	This should be replaced with actual profile-specific parsers.

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document

	Returns:
		dict: Document data dictionary with 'doctype' field (e.g., Purchase Invoice, Sales Invoice, etc.)
	"""
	# This is a placeholder implementation
	# You should implement actual XML parsing based on your requirements
	# For example, you might want to:
	# 1. Use different parsers for different profiles
	# 2. Parse XML based on profile-specific structure
	# 3. Map XML elements to document fields
	# 4. Return a dict with 'doctype' field specifying the document type

	frappe.throw(
		_("No parser configured for profile {0}. Please set parser_path in EDocument Profile.").format(
			edocument_profile.name
		)
	)
