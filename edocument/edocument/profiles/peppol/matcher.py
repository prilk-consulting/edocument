# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
PEPPOL Matcher Module

This module provides matching functionality for PEPPOL BIS Billing 3.0 invoices.
It extracts supplier, items, and purchase order data from XML and attempts to
match them against ERPNext master data.

If mismatches are found, a matching dialog is shown for manual mapping.

Entry point: match_peppol_xml(xml_bytes, edocument_profile, edocument=None) -> dict
Returns: {"is_matched": bool, "matching_data": dict, "dialog_config": dict, "matching_summary": str}

matcher_path: edocument.edocument.profiles.peppol.matcher.match_peppol_xml
"""

import json

import frappe
from frappe import _
from lxml import etree as ET

from edocument.edocument.profiles.peppol import (
	DOCUMENT_TYPE_ELEMENTS,
	UBL_NAMESPACES,
)
from edocument.edocument.validator import validate_xml_structure


def get_xml_text(element, xpath, namespaces=None) -> str | None:
	"""Helper function to extract text from XML element."""
	if element is None:
		return None
	result = element.find(xpath, namespaces or {})
	return result.text if result is not None and result.text else None


def _detect_document_type_from_xml(root) -> str:
	"""Detect UBL document type from XML root element."""
	try:
		if root.tag.endswith("}CreditNote"):
			return "CreditNote"
		elif root.tag.endswith("}DebitNote"):
			return "DebitNote"
		elif root.tag.endswith("}Invoice"):
			return "Invoice"
	except Exception:
		pass
	return "Invoice"


def extract_matching_candidates(xml_bytes: bytes) -> dict:
	"""
	Parse PEPPOL XML and extract supplier, items, and PO data for matching.

	Args:
		xml_bytes: The XML content as bytes

	Returns:
		dict: Extracted candidates
	"""
	# Validate and parse XML
	xml_bytes = validate_xml_structure(xml_bytes)
	root = ET.fromstring(xml_bytes)

	# Detect document type
	document_type = _detect_document_type_from_xml(root)
	document_elements = DOCUMENT_TYPE_ELEMENTS.get(document_type, DOCUMENT_TYPE_ELEMENTS["Invoice"])

	namespaces = UBL_NAMESPACES

	candidates = {
		"supplier": {},
		"items": [],
		"purchase_order": {},
	}

	# Extract supplier information
	seller_party = root.find(".//cac:AccountingSupplierParty/cac:Party", namespaces)
	if seller_party is not None:
		seller_name = get_xml_text(
			seller_party, ".//cac:PartyLegalEntity/cbc:RegistrationName", namespaces
		) or get_xml_text(seller_party, ".//cac:PartyName/cbc:Name", namespaces)

		seller_tax_id = get_xml_text(seller_party, ".//cac:PartyTaxScheme/cbc:CompanyID", namespaces)

		endpoint_elem = seller_party.find(".//cbc:EndpointID", namespaces)
		electronic_address = endpoint_elem.text if endpoint_elem is not None and endpoint_elem.text else None
		electronic_address_scheme = endpoint_elem.get("schemeID") if endpoint_elem is not None else None

		candidates["supplier"] = {
			"xml_name": seller_name,
			"xml_tax_id": seller_tax_id,
			"xml_electronic_address": electronic_address,
			"xml_electronic_address_scheme": electronic_address_scheme,
		}

	# Extract line items
	line_elem_name = document_elements["line"]
	quantity_elem_name = document_elements["quantity"]

	for idx, invoice_line in enumerate(root.findall(f".//cac:{line_elem_name}", namespaces)):
		item_candidate = {"line_index": idx}

		product_name = get_xml_text(invoice_line, ".//cac:Item/cbc:Name", namespaces)
		item_candidate["xml_name"] = product_name

		seller_product_id = get_xml_text(
			invoice_line, ".//cac:Item/cac:SellersItemIdentification/cbc:ID", namespaces
		)
		buyer_item_id = get_xml_text(
			invoice_line, ".//cac:Item/cac:BuyersItemIdentification/cbc:ID", namespaces
		)

		item_candidate["xml_seller_id"] = seller_product_id
		item_candidate["xml_buyer_id"] = buyer_item_id

		qty_elem = invoice_line.find(f".//cbc:{quantity_elem_name}", namespaces)
		if qty_elem is not None and qty_elem.text:
			try:
				item_candidate["qty"] = float(qty_elem.text)
			except (ValueError, TypeError):
				item_candidate["qty"] = None
			item_candidate["uom"] = qty_elem.get("unitCode")
		else:
			item_candidate["qty"] = None
			item_candidate["uom"] = None

		candidates["items"].append(item_candidate)

	# Extract purchase order reference
	order_reference = get_xml_text(root, ".//cac:OrderReference/cbc:ID", namespaces)
	buyer_reference = get_xml_text(root, ".//cbc:BuyerReference", namespaces)

	candidates["purchase_order"] = {
		"xml_order_reference": order_reference,
		"xml_buyer_reference": buyer_reference,
	}

	return candidates


def auto_match_entities(candidates: dict, existing_matching_data: dict | None = None) -> dict:
	"""
	Attempt automatic matching of extracted candidates against ERPNext master data.

	Args:
		candidates: Extracted candidates from extract_matching_candidates()
		existing_matching_data: Previously saved matching data (if any)

	Returns:
		dict: Matching results
	"""
	existing_matching_data = existing_matching_data or {}
	result = {
		"supplier": dict(candidates.get("supplier", {})),
		"items": [dict(item) for item in candidates.get("items", [])],
		"purchase_order": dict(candidates.get("purchase_order", {})),
	}

	# --- Match Supplier ---
	supplier_data = result["supplier"]
	existing_supplier = existing_matching_data.get("supplier", {})

	if existing_supplier.get("matched") and existing_supplier.get("match_method") == "manual":
		if frappe.db.exists("Supplier", existing_supplier["matched"]):
			supplier_data["matched"] = existing_supplier["matched"]
			supplier_data["match_method"] = "manual"
		else:
			supplier_data["matched"] = None
			supplier_data["match_method"] = None
	else:
		matched_supplier = None
		match_method = None

		if supplier_data.get("xml_name") and frappe.db.exists("Supplier", supplier_data["xml_name"]):
			matched_supplier = supplier_data["xml_name"]
			match_method = "name"

		if not matched_supplier and supplier_data.get("xml_tax_id"):
			matched_supplier = frappe.db.get_value(
				"Supplier", {"tax_id": supplier_data["xml_tax_id"]}, "name"
			)
			if matched_supplier:
				match_method = "tax_id"

		if not matched_supplier and supplier_data.get("xml_electronic_address"):
			matched_supplier = frappe.db.get_value(
				"Supplier",
				{"edocument_electronic_address": supplier_data["xml_electronic_address"]},
				"name",
			)
			if matched_supplier:
				match_method = "electronic_address"

		supplier_data["matched"] = matched_supplier
		supplier_data["match_method"] = match_method

	# --- Match Items ---
	existing_items = {item.get("line_index"): item for item in existing_matching_data.get("items", [])}
	matched_supplier = supplier_data.get("matched")

	for item in result["items"]:
		line_index = item["line_index"]
		existing_item = existing_items.get(line_index, {})

		if existing_item.get("matched") and existing_item.get("match_method") == "manual":
			if frappe.db.exists("Item", existing_item["matched"]):
				item["matched"] = existing_item["matched"]
				item["match_method"] = "manual"
			else:
				item["matched"] = None
				item["match_method"] = None
		else:
			matched_item = None
			match_method = None

			if item.get("xml_buyer_id") and frappe.db.exists("Item", item["xml_buyer_id"]):
				matched_item = item["xml_buyer_id"]
				match_method = "buyer_id"

			if not matched_item and item.get("xml_seller_id") and matched_supplier:
				matched_item = frappe.db.get_value(
					"Item Supplier",
					{"supplier": matched_supplier, "supplier_part_no": item["xml_seller_id"]},
					"parent",
				)
				if matched_item:
					match_method = "seller_id"

			item["matched"] = matched_item
			item["match_method"] = match_method

	# --- Match Purchase Order ---
	po_data = result["purchase_order"]
	existing_po = existing_matching_data.get("purchase_order", {})

	if existing_po.get("matched") and existing_po.get("match_method") == "manual":
		if frappe.db.exists("Purchase Order", existing_po["matched"]):
			po_data["matched"] = existing_po["matched"]
			po_data["match_method"] = "manual"
		else:
			po_data["matched"] = None
			po_data["match_method"] = None
	else:
		matched_po = None
		match_method = None

		if po_data.get("xml_order_reference") and frappe.db.exists(
			"Purchase Order", po_data["xml_order_reference"]
		):
			matched_po = po_data["xml_order_reference"]
			match_method = "order_reference"

		if not matched_po and po_data.get("xml_buyer_reference") and frappe.db.exists(
			"Purchase Order", po_data["xml_buyer_reference"]
		):
			matched_po = po_data["xml_buyer_reference"]
			match_method = "buyer_reference"

		po_data["matched"] = matched_po
		po_data["match_method"] = match_method

	return result


def match_peppol_xml(xml_bytes, edocument_profile, edocument=None) -> dict:
	"""
	Match PEPPOL XML entities against ERPNext master data.

	This is the main interface method called by the base matcher.
	Follows the same pattern as validate_peppol_xml.

	Args:
		xml_bytes: Raw XML content as bytes
		edocument_profile: EDocument Profile document
		edocument: EDocument document (optional, for existing matching_data)

	Returns:
		dict: {
			"is_matched": True/False,
			"matching_data": {...},
			"dialog_config": {...},
			"matching_summary": "..."
		}
	"""
	# Get existing matching data if any
	existing_matching_data = None
	if edocument and edocument.matching_data:
		try:
			existing_matching_data = json.loads(edocument.matching_data)
		except (json.JSONDecodeError, TypeError):
			pass

	# Extract candidates from XML
	candidates = extract_matching_candidates(xml_bytes)

	# Attempt auto-matching
	matching_data = auto_match_entities(candidates, existing_matching_data)

	# Check if all entities are matched
	supplier_matched = bool(matching_data["supplier"].get("matched"))
	items = matching_data.get("items", [])
	all_items_matched = all(item.get("matched") for item in items) if items else True

	# PO matching is optional - not required for is_matched
	# (PO reference in XML is informational, user can link manually if needed)

	# Determine if fully matched (supplier and items only, PO is optional)
	is_matched = supplier_matched and all_items_matched

	# Generate dialog config and summary
	dialog_config = _get_dialog_config(matching_data)
	matching_summary = _generate_matching_summary(matching_data)

	return {
		"is_matched": is_matched,
		"matching_data": matching_data,
		"dialog_config": dialog_config,
		"matching_summary": matching_summary,
	}


def _generate_matching_summary(matching_data: dict) -> str:
	"""Generate plain text summary of matching status."""
	supplier_data = matching_data.get("supplier", {})
	items_data = matching_data.get("items", [])
	po_data = matching_data.get("purchase_order", {})

	lines = []

	# Supplier summary
	supplier_xml = supplier_data.get("xml_name") or "-"
	supplier_matched = supplier_data.get("matched")
	supplier_method = supplier_data.get("match_method") or ""
	if supplier_matched:
		supplier_status = f"✓ {supplier_matched}"
		if supplier_method:
			supplier_status += f" ({supplier_method})"
	else:
		supplier_status = "✗ Not matched"

	lines.append(f"{_('Supplier')}: {supplier_xml} → {supplier_status}")

	# Items summary
	if items_data:
		matched_count = sum(1 for item in items_data if item.get("matched"))
		total_count = len(items_data)
		lines.append(f"\n{_('Items')}: {matched_count}/{total_count} {_('matched')}")

		for item in items_data:
			xml_name = item.get("xml_name") or "-"
			matched = item.get("matched")
			method = item.get("match_method") or ""
			if matched:
				status = f"✓ {matched}"
				if method:
					status += f" ({method})"
			else:
				status = "✗ Not matched"
			lines.append(f"  • {xml_name} → {status}")

	# Purchase Order summary (optional)
	po_ref = po_data.get("xml_order_reference") or po_data.get("xml_buyer_reference")
	if po_ref:
		po_matched = po_data.get("matched")
		if po_matched:
			po_status = f"✓ {po_matched}"
		else:
			po_status = "- Not linked"
		lines.append(f"\n{_('Purchase Order')}: {po_ref} → {po_status}")

	return "\n".join(lines)


def _get_dialog_config(matching_data: dict) -> dict:
	"""
	Get Frappe dialog configuration for the matching dialog.

	Returns complete Frappe-compatible field definitions that can be
	passed directly to frappe.ui.Dialog.

	Args:
		matching_data: Current matching data

	Returns:
		dict: Dialog configuration with title, fields, and validation rules
	"""
	supplier_data = matching_data.get("supplier", {})
	items_data = matching_data.get("items", [])
	po_data = matching_data.get("purchase_order", {})

	fields = []

	# --- Supplier Section ---
	fields.append({"fieldtype": "Section Break", "label": _("Supplier")})

	fields.append({
		"fieldtype": "Data",
		"fieldname": "xml_supplier_name",
		"label": _("XML Supplier Name"),
		"default": supplier_data.get("xml_name") or "-",
		"read_only": 1,
	})
	fields.append({"fieldtype": "Column Break"})
	fields.append({
		"fieldtype": "Data",
		"fieldname": "xml_supplier_tax_id",
		"label": _("XML Tax ID"),
		"default": supplier_data.get("xml_tax_id") or "-",
		"read_only": 1,
	})
	fields.append({"fieldtype": "Section Break"})
	fields.append({
		"fieldtype": "Link",
		"fieldname": "supplier",
		"label": _("Match to Supplier"),
		"options": "Supplier",
		"reqd": 1,
		"default": supplier_data.get("matched"),
	})

	# --- Items Section as Table ---
	if items_data:
		fields.append({"fieldtype": "Section Break", "label": _("Line Items")})

		# Build table data
		table_data = []
		for item in items_data:
			idx = item.get("line_index", 0)
			xml_name = item.get("xml_name") or "-"
			xml_seller_id = item.get("xml_seller_id") or "-"
			qty = item.get("qty") or "-"
			uom = item.get("uom") or ""
			matched = item.get("matched")

			table_data.append({
				"line_no": idx + 1,
				"xml_product": xml_name,
				"seller_id": xml_seller_id,
				"qty": f"{qty} {uom}".strip(),
				"matched_item": matched,
			})

		fields.append({
			"fieldtype": "Table",
			"fieldname": "items",
			"label": _("Items"),
			"cannot_add_rows": True,
			"cannot_delete_rows": True,
			"in_place_edit": True,
			"data": table_data,
			"fields": [
				{"fieldtype": "Int", "fieldname": "line_no", "label": "#", "in_list_view": 1, "read_only": 1, "columns": 1},
				{"fieldtype": "Data", "fieldname": "xml_product", "label": _("XML Product"), "in_list_view": 1, "read_only": 1, "columns": 3},
				{"fieldtype": "Data", "fieldname": "seller_id", "label": _("Seller ID"), "in_list_view": 1, "read_only": 1, "columns": 2},
				{"fieldtype": "Data", "fieldname": "qty", "label": _("Qty"), "in_list_view": 1, "read_only": 1, "columns": 1},
				{"fieldtype": "Link", "fieldname": "matched_item", "label": _("Match to Item"), "options": "Item", "in_list_view": 1, "reqd": 1, "columns": 3},
			],
		})

	# --- Purchase Order Section ---
	po_ref = po_data.get("xml_order_reference") or po_data.get("xml_buyer_reference")
	if po_ref:
		fields.append({"fieldtype": "Section Break", "label": _("Purchase Order")})

		fields.append({
			"fieldtype": "Data",
			"fieldname": "xml_po_reference",
			"label": _("XML Order Reference"),
			"default": po_data.get("xml_order_reference") or po_data.get("xml_buyer_reference") or "-",
			"read_only": 1,
		})
		fields.append({"fieldtype": "Section Break"})
		fields.append(
			{
				"fieldtype": "Link",
				"fieldname": "purchase_order",
				"label": _("Match to Purchase Order"),
				"options": "Purchase Order",
				"reqd": 1,
				"default": po_data.get("matched"),
			}
		)

	# --- Summary Section ---
	fields.append({"fieldtype": "Section Break", "label": _("Summary")})
	summary = _generate_matching_summary(matching_data)
	fields.append({
		"fieldtype": "Long Text",
		"fieldname": "matching_summary",
		"label": _("Matching Status"),
		"default": summary,
		"read_only": 1,
	})

	return {
		"title": _("Match Invoice Data"),
		"fields": fields,
		"primary_action_label": _("Save"),
	}


