# Copyright (c) 2025, Prilk Consulting BV and contributors
"""
PEPPOL Preview

This module provides HTML preview for PEPPOL BIS Billing 3.0
compliant UBL 2.1 XML documents using the official PEPPOL stylesheet.
"""

from pathlib import Path

import frappe
from frappe import _


def preview_peppol_xml(xml_bytes, edocument_profile):
	"""
	Transform PEPPOL UBL XML to HTML using official PEPPOL stylesheet.

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document

	Returns:
		str: HTML string for preview
	"""
	xml_string = xml_bytes.decode("utf-8") if isinstance(xml_bytes, bytes) else xml_bytes

	# Get official PEPPOL stylesheet path
	xslt_path = _get_peppol_stylesheet_path()

	# Transform XML to HTML using saxonche
	try:
		from saxonche import PySaxonProcessor
	except ImportError:
		frappe.throw(_("saxonche package is required for XML preview"))

	with PySaxonProcessor(license=False) as proc:
		xslt30_processor = proc.new_xslt30_processor()
		input_node = proc.parse_xml(xml_text=xml_string)
		executable = xslt30_processor.compile_stylesheet(stylesheet_file=str(xslt_path))
		html = executable.transform_to_string(xdm_node=input_node)

	return html


def _get_peppol_stylesheet_path():
	"""Get the path to the official PEPPOL stylesheet."""
	# Path: edocument/edocument/profiles/peppol/peppol-bis-invoice-3/stylesheet/stylesheet-ubl.xslt
	xslt_path = (
		Path(__file__).parent
		/ "peppol-bis-invoice-3"
		/ "stylesheet"
		/ "stylesheet-ubl.xslt"
	)

	if not xslt_path.exists():
		frappe.throw(_("PEPPOL stylesheet not found at: {0}").format(str(xslt_path)))

	return xslt_path

