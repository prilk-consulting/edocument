# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Validator module for EDocument XML validation.
This module routes to profile-specific validators based on the EDocument Profile.

This module also provides common validation functions for XSD and Schematron
that can be used by all profiles.
"""

from pathlib import Path
from typing import Optional

import frappe
from frappe import _


def get_xml_validator(xml_bytes, edocument_profile):
	"""
	Get XML validator based on the profile.

	"""
	# Try to get validator from profile's validator_path if specified
	if edocument_profile.validator_path:
		try:
			validator_func = frappe.get_attr(edocument_profile.validator_path)
			return validator_func(xml_bytes, edocument_profile)
		except Exception as e:
			frappe.log_error(f"Error loading validator from path {edocument_profile.validator_path}: {e!s}")

	# Default: Use basic XML validator
	return validate_basic_xml(xml_bytes, edocument_profile)


def validate_basic_xml(xml_bytes, edocument_profile):
	"""
	Basic XML validator (placeholder implementation).

	"""
	# This is a placeholder implementation
	# You should implement actual XML validation based on your requirements
	# For example, you might want to:
	# 1. Use different validators for different profiles
	# 2. Validate XML structure and content
	# 3. Use common validation functions from this module

	try:
		# Basic XML structure validation
		from lxml import etree

		# Parse XML to check if it's well-formed
		parser = etree.XMLParser()
		etree.fromstring(xml_bytes, parser)

		# If validation passes
		return {"is_valid": True, "error": None}

	except etree.XMLSyntaxError as e:
		return {"is_valid": False, "error": f"XML syntax error: {e!s}"}
	except ImportError:
		# If lxml is not available, just check basic structure
		try:
			import xml.etree.ElementTree as ET

			ET.fromstring(xml_bytes)
			return {"is_valid": True, "error": None}
		except Exception as e:
			return {"is_valid": False, "error": f"XML validation error: {e!s}"}
	except Exception as e:
		return {"is_valid": False, "error": f"XML validation error: {e!s}"}


# ============================================================================
# Common XSD and Schematron Validation Functions
# These functions can be used by all profiles
# ============================================================================


def validate_xml_structure(xml_bytes: bytes) -> bytes:
	"""
	Validate XML structure (well-formedness).
	"""
	from lxml import etree

	try:
		parser = etree.XMLParser()
		root = etree.fromstring(xml_bytes, parser)
		# Return validated XML with pretty formatting
		return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
	except etree.XMLSyntaxError as e:
		error_msg = f"XML structure validation failed: {e!s}"
		frappe.log_error(error_msg, "XML Validation")
		raise ValueError(error_msg)
	except Exception as e:
		error_msg = f"XML parsing failed: {e!s}"
		frappe.log_error(error_msg, "XML Validation")
		raise ValueError(error_msg)


def validate_xml_against_xsd_file(xml_bytes: bytes, xsd_file_path: Path | str) -> bytes:
	"""
	Validate XML against an XSD schema file.
	"""
	from lxml import etree

	xsd_path = Path(xsd_file_path) if isinstance(xsd_file_path, str) else xsd_file_path

	if not xsd_path.exists():
		error_msg = f"XSD schema file not found: {xsd_path}"
		frappe.log_error(error_msg, "XSD Validation")
		raise FileNotFoundError(error_msg)

	try:
		# Load and compile XSD schema
		schema_doc = etree.parse(str(xsd_path))
		xsd_schema = etree.XMLSchema(schema_doc)

		# Parse and validate XML
		parser = etree.XMLParser(schema=xsd_schema)
		xml_root = etree.fromstring(xml_bytes, parser)

		# Return validated XML with pretty formatting
		return etree.tostring(xml_root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
	except etree.XMLSchemaError as e:
		error_msg = f"XSD validation failed: {e!s}"
		frappe.log_error(error_msg, "XSD Validation")
		raise ValueError(error_msg)
	except Exception as e:
		error_msg = f"XSD schema load or validation failed: {e!s}"
		frappe.log_error(error_msg, "XSD Validation")
		raise ValueError(error_msg)


def validate_xml_against_schematron_file(
	xml_bytes: bytes, xsl_file_path: Path | str
) -> tuple[list[str], list[str]]:
	"""
	Validate XML against a single Schematron XSL stylesheet.

	"""
	from lxml import objectify

	xsl_path = Path(xsl_file_path) if isinstance(xsl_file_path, str) else xsl_file_path

	if not xsl_path.exists():
		raise FileNotFoundError(f"XSL stylesheet not found: {xsl_path}")

	try:
		from saxonche import PySaxonProcessor
	except ImportError:
		raise ImportError("saxonche package is required for Schematron validation")

	xml_string = xml_bytes.decode("utf-8")

	# Run Schematron validation
	with PySaxonProcessor(license=False) as proc:
		xslt30_processor = proc.new_xslt30_processor()
		input_node = proc.parse_xml(xml_text=xml_string)
		executable = xslt30_processor.compile_stylesheet(stylesheet_file=str(xsl_path))
		report = executable.transform_to_string(xdm_node=input_node)

	# Parse SVRL report
	root = objectify.fromstring(report.encode("utf-8"))
	svrl_ns = {"svrl": "http://purl.oclc.org/dsdl/svrl"}

	# Errors: failed-assert WITHOUT flag="warning" (fatal or no flag)
	error_asserts = root.xpath(
		"//svrl:failed-assert[not(@flag='warning')]/svrl:text",
		namespaces=svrl_ns,
	)

	# Warnings: failed-assert WITH flag="warning" + all successful-report
	warning_asserts = root.xpath(
		"//svrl:failed-assert[@flag='warning']/svrl:text",
		namespaces=svrl_ns,
	)
	successful_reports = root.xpath(
		"//svrl:successful-report/svrl:text",
		namespaces=svrl_ns,
	)

	errors = [assertion.text.strip() for assertion in error_asserts if assertion.text]
	warnings = [w.text.strip() for w in warning_asserts if w.text]
	warnings.extend([r.text.strip() for r in successful_reports if r.text])

	return errors, warnings


def validate_xml_against_schematron_files(
	xml_bytes: bytes, xsl_file_paths: list[Path | str]
) -> tuple[list[str], list[str]]:
	"""
	Validate XML against multiple Schematron XSL stylesheets and combine results.

	"""
	all_errors = []
	all_warnings = []

	for xsl_file_path in xsl_file_paths:
		errors, warnings = validate_xml_against_schematron_file(xml_bytes, xsl_file_path)
		all_errors.extend(errors)
		all_warnings.extend(warnings)

	return all_errors, all_warnings
