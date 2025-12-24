# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
PEPPOL Detector

This module detects EDocument field values from incoming PEPPOL UBL 2.1 XML.
It extracts company and other relevant fields by matching against ERPNext master data.
"""

import frappe
from lxml import etree as ET

from edocument.edocument.profiles.peppol import UBL_NAMESPACES
from edocument.edocument.validator import validate_xml_structure


def detect_edocument_fields(xml_bytes):
	"""
	Detect EDocument field values from incoming PEPPOL XML.

	Extracts:
	- company: from buyer's EndpointID or name
	- country: from seller's country
	- edocument_target_type: based on document type (Invoice → Purchase Invoice)

	Args:
		xml_bytes: Raw XML content as bytes

	Returns:
		dict: Field values to populate on EDocument
	"""
	try:
		xml_bytes = validate_xml_structure(xml_bytes)
		root = ET.fromstring(xml_bytes)

		result = {}

		# Detect company from buyer information
		company = _detect_company_from_buyer(root)
		if company:
			result["company"] = company

		# Detect country from seller information
		country = _detect_country_from_seller(root)
		if country:
			result["country"] = country

		# Detect target document type
		target_type = _detect_target_doctype(root)
		if target_type:
			result["edocument_target_type"] = target_type

		return result

	except Exception as e:
		frappe.log_error(
			f"Failed to detect EDocument fields from PEPPOL XML: {e!s}",
			"PEPPOL Field Detection Error"
		)
		return {}


def _detect_company_from_buyer(root):
	"""
	Detect ERPNext Company from buyer (AccountingCustomerParty) in PEPPOL XML.

	Matching strategies:
	1. Match EndpointID against Company.edocument_electronic_address
	2. Match buyer name against Company name

	Args:
		root: Parsed XML root element

	Returns:
		str | None: Company name if matched, None otherwise
	"""
	buyer_party = root.find(".//cac:AccountingCustomerParty/cac:Party", UBL_NAMESPACES)
	if buyer_party is None:
		return None

	# Strategy 1: Match by EndpointID against edocument_electronic_address
	buyer_endpoint = buyer_party.find(".//cbc:EndpointID", UBL_NAMESPACES)
	if buyer_endpoint is not None and buyer_endpoint.text:
		endpoint_value = buyer_endpoint.text.strip()
		company = frappe.db.get_value(
			"Company",
			{"edocument_electronic_address": endpoint_value},
			"name"
		)
		if company:
			return company

	# Strategy 2: Match by buyer name
	buyer_name = _get_buyer_name(buyer_party)
	if buyer_name and frappe.db.exists("Company", buyer_name):
		return buyer_name

	return None


def _get_buyer_name(buyer_party):
	"""Extract buyer name from Party element."""
	# Try PartyLegalEntity/RegistrationName first
	reg_name = buyer_party.find(".//cac:PartyLegalEntity/cbc:RegistrationName", UBL_NAMESPACES)
	if reg_name is not None and reg_name.text:
		return reg_name.text.strip()

	# Fallback to PartyName/Name
	party_name = buyer_party.find(".//cac:PartyName/cbc:Name", UBL_NAMESPACES)
	if party_name is not None and party_name.text:
		return party_name.text.strip()

	return None


def _detect_country_from_seller(root):
	"""
	Detect country from seller (AccountingSupplierParty) in PEPPOL XML.

	Args:
		root: Parsed XML root element

	Returns:
		str | None: Country name if found, None otherwise
	"""
	seller_party = root.find(".//cac:AccountingSupplierParty/cac:Party", UBL_NAMESPACES)
	if seller_party is None:
		return None

	# Get country code from PostalAddress
	country_code_elem = seller_party.find(".//cac:PostalAddress/cac:Country/cbc:IdentificationCode", UBL_NAMESPACES)
	if country_code_elem is not None and country_code_elem.text:
		country_code = country_code_elem.text.strip()
		# Look up country name from code
		country = frappe.db.get_value("Country", {"code": country_code}, "name")
		if country:
			return country

	return None


def _detect_target_doctype(root):
	"""
	Detect target ERPNext doctype from PEPPOL XML document type.

	For incoming documents:
	- Invoice (380, 384) → Purchase Invoice
	- CreditNote (381) → Purchase Invoice (with is_return=1)

	Args:
		root: Parsed XML root element

	Returns:
		str | None: Target doctype name if detected, None otherwise
	"""
	# Check root element to determine document type
	root_tag = ET.QName(root.tag).localname

	if root_tag == "Invoice":
		return "Purchase Invoice"
	elif root_tag == "CreditNote":
		return "Purchase Invoice"  # Credit notes become return Purchase Invoices
	elif root_tag == "DebitNote":
		return "Purchase Invoice"

	return None
