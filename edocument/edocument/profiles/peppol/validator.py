# Copyright (c) 2025, Prilk Consulting BV and contributors
"""
PEPPOL Validator

This module provides UBL 2.1 XML validation for PEPPOL BIS Billing 3.0
compliant invoices from ERPNext data.

This validator determines PEPPOL-specific schema paths and uses
common validation functions from edocument.edocument.validator.
"""

from pathlib import Path

import frappe

# Import document type constants
from edocument.edocument.profiles.peppol import (
	DOCUMENT_TYPE_NAMESPACES,
	DOCUMENT_TYPE_XSD_FILES,
)

# Import common validation functions
from edocument.edocument.validator import (
	validate_xml_against_schematron_files,
	validate_xml_against_xsd_file,
	validate_xml_structure,
)


def _detect_document_type_from_xml(xml_bytes: bytes) -> str:
	"""
	Detect UBL document type from XML root element.

	Args:
		xml_bytes: XML content as bytes

	Returns:
		str: Document type ('Invoice', 'CreditNote', 'DebitNote', etc.) or 'Invoice' as default
	"""
	try:
		from lxml import etree as ET

		root = ET.fromstring(xml_bytes)

		# Check root element tag against known document type namespaces
		for doc_type, namespace in DOCUMENT_TYPE_NAMESPACES.items():
			expected_tag = f"{{{namespace}}}{doc_type}"
			if root.tag == expected_tag or root.tag.endswith(f"}}{doc_type}"):
				return doc_type

		# Fallback: check by element name suffix
		if root.tag.endswith("}CreditNote"):
			return "CreditNote"
		elif root.tag.endswith("}DebitNote"):
			return "DebitNote"
		elif root.tag.endswith("}Invoice"):
			return "Invoice"
	except Exception:
		pass

	# Default to Invoice if detection fails
	return "Invoice"


def _get_peppol_xsd_path(xml_bytes: bytes | None = None) -> Path:
	"""
	Get the path to the PEPPOL XSD schema file.

	Detects the document type (Invoice, CreditNote, DebitNote, etc.) from XML
	and returns the appropriate XSD. If xml_bytes is not provided, defaults to Invoice XSD.

	Args:
		xml_bytes: Optional XML bytes to detect document type

	Returns:
		Path: Path to the XSD schema file
	"""
	schema_dir = Path(__file__).parent / "UBL-2.1" / "xsdrt" / "maindoc"

	# Detect document type from XML if provided
	if xml_bytes:
		document_type = _detect_document_type_from_xml(xml_bytes)
		xsd_filename = DOCUMENT_TYPE_XSD_FILES.get(document_type, DOCUMENT_TYPE_XSD_FILES["Invoice"])
		return schema_dir / xsd_filename

	# Default to Invoice XSD
	return schema_dir / DOCUMENT_TYPE_XSD_FILES["Invoice"]


def _get_peppol_xsl_paths() -> list[Path]:
	"""
	Get the paths to the PEPPOL Schematron XSL stylesheet files.

	Returns:
		list[Path]: List of paths to XSL stylesheet files
	"""
	# Use pre-compiled XSL files from schematron directory
	# These are SchXslt-compiled XSL files that handle context correctly
	schematron_dir = Path(__file__).parent.parent.parent / "schematron"
	return [
		schematron_dir / "CEN-EN16931-UBL.xsl",
		schematron_dir / "PEPPOL-EN16931-UBL.xsl",
	]


def validate_peppol_xml(xml_bytes, edocument_profile):
	"""
	Validate PEPPOL XML against XSD and Schematron.
	"""
	result = {"is_valid": True, "error": None, "warnings": []}

	# Validate XML structure
	try:
		xml_bytes = validate_xml_structure(xml_bytes)
	except ValueError as e:
		result["is_valid"] = False
		result["error"] = str(e)
		return result

	# Validate against XSD schema
	# Get PEPPOL-specific XSD path (detects CreditNote vs Invoice)
	xsd_path = _get_peppol_xsd_path(xml_bytes)
	try:
		xml_bytes = validate_xml_against_xsd_file(xml_bytes, xsd_path)
	except ValueError as e:
		result["is_valid"] = False
		result["error"] = f"XSD validation failed: {e!s}"
		return result
	except FileNotFoundError as e:
		result["warnings"].append(f"XSD schema file not found: {e!s}")
	except Exception as e:
		result["warnings"].append(f"XSD validation skipped: {e!s}")

	# Validate against Schematron
	# Get PEPPOL-specific XSL paths
	xsl_paths = _get_peppol_xsl_paths()
	try:
		errors, warnings = validate_xml_against_schematron_files(xml_bytes, xsl_paths)
		# Debug: Log validation results
		if errors:
			frappe.log_error(
				f"Schematron validation errors for EDocument:\n{chr(10).join(errors)}",
				"Schematron Validation Debug",
			)
		if warnings:
			frappe.log_error(
				f"Schematron validation warnings for EDocument:\n{chr(10).join(warnings)}",
				"Schematron Validation Debug",
			)
		if errors:
			result["is_valid"] = False
			result["error"] = "\n".join(errors)
		result["warnings"].extend(warnings)
	except FileNotFoundError as e:
		result["warnings"].append(f"XSL stylesheet file not found: {e!s}")
	except ImportError as e:
		result["warnings"].append(f"Schematron validation skipped: {e!s}")
	except Exception as e:
		result["warnings"].append(f"Schematron validation skipped: {e!s}")

	return result
