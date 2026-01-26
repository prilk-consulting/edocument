# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
PEPPOL Parser

This module provides UBL 2.1 XML parsing for PEPPOL BIS Billing 3.0
compliant invoices to create Purchase Invoices from ERPNext data.

This parser parses PEPPOL XML and returns a Purchase Invoice dict structure.
"""

import frappe
from erpnext import get_default_company
from frappe import _
from frappe.utils.data import flt
from lxml import etree as ET

from edocument.edocument.profiles.peppol import (
	DOCUMENT_TYPE_ELEMENTS,
	DOCUMENT_TYPE_NAMESPACES,
	UBL_NAMESPACES,
)
from edocument.edocument.validator import validate_xml_structure


def get_xml_text(element, xpath, namespaces=None) -> str | None:
	"""Helper function to extract text from XML element."""
	if element is None:
		return None
	result = element.find(xpath, namespaces or {})
	return result.text if result is not None and result.text else None


def flt_or_none(value) -> float | None:
	"""Convert value to float or return None."""
	if value is None or value == "":
		return None
	try:
		return float(value)
	except (ValueError, TypeError):
		return None


def _detect_document_type_from_xml(root) -> str:
	"""
	Detect UBL document type from XML root element.

	Args:
		root: XML root element

	Returns:
		str: Document type ('Invoice', 'CreditNote', 'DebitNote', etc.) or 'Invoice' as default
	"""
	try:
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


def parse_peppol_xml(xml_bytes, edocument_profile, edocument=None):
	"""
	Parse PEPPOL UBL 2.1 XML and return Purchase Invoice dict structure.
	Supports Invoice, CreditNote, and DebitNote documents.

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document
		edocument: Optional EDocument instance (for accessing matching_data)

	Returns:
		dict: Purchase Invoice data dictionary with 'doctype' field ready to be used with frappe.get_doc()
	"""
	import json

	# Validate XML structure first
	try:
		xml_bytes = validate_xml_structure(xml_bytes)
		root = ET.fromstring(xml_bytes)
	except ValueError as e:
		frappe.throw(_("The uploaded file does not contain valid XML data: {0}").format(str(e)))

	# Get matching data if available
	matching_data = None
	if edocument and edocument.matching_data:
		try:
			matching_data = json.loads(edocument.matching_data)
		except (json.JSONDecodeError, TypeError):
			pass

	# Detect document type (Invoice, CreditNote, DebitNote)
	document_type = _detect_document_type_from_xml(root)
	document_elements = DOCUMENT_TYPE_ELEMENTS.get(document_type, DOCUMENT_TYPE_ELEMENTS["Invoice"])

	namespaces = UBL_NAMESPACES

	# Initialize Purchase Invoice dict
	pi_data = {"doctype": "Purchase Invoice", "items": [], "taxes": [], "payment_schedule": []}

	# Set is_return flag for credit notes (Purchase Invoice return)
	if document_type == "CreditNote":
		pi_data["is_return"] = 1

	try:
		# Parse basic invoice information
		invoice_id = get_xml_text(root, ".//cbc:ID", namespaces)
		issue_date = get_xml_text(root, ".//cbc:IssueDate", namespaces)
		# DueDate is only for Invoice, not for CreditNote or DebitNote
		due_date = None
		if document_type == "Invoice":
			due_date = get_xml_text(root, ".//cbc:DueDate", namespaces)
		currency = get_xml_text(root, ".//cbc:DocumentCurrencyCode", namespaces)
		buyer_reference = get_xml_text(root, ".//cbc:BuyerReference", namespaces)

		# For credit notes, check for BillingReference (original invoice reference)
		if document_type == "CreditNote":
			billing_ref_id = get_xml_text(
				root, ".//cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID", namespaces
			)
			if billing_ref_id:
				# Set return_against if the original invoice exists
				if frappe.db.exists("Purchase Invoice", billing_ref_id):
					pi_data["return_against"] = billing_ref_id

		pi_data["bill_no"] = invoice_id
		pi_data["bill_date"] = issue_date
		pi_data["due_date"] = due_date
		pi_data["currency"] = currency

		# Parse seller (supplier) information - use matching_data if available
		matched_supplier = None
		if matching_data and matching_data.get("supplier", {}).get("matched"):
			matched_supplier = matching_data["supplier"]["matched"]

		seller_data = parse_peppol_seller(root, namespaces, matched_supplier=matched_supplier)
		pi_data["supplier"] = seller_data.get("supplier")
		pi_data["supplier_name"] = seller_data.get("name")

		# Parse buyer (company) information
		buyer_data = parse_peppol_buyer(root, namespaces)
		pi_data["company"] = buyer_data.get("company") or get_default_company()

		# Check for Purchase Order - use matching_data if available
		matched_po = None
		if matching_data and matching_data.get("purchase_order", {}).get("matched"):
			matched_po = matching_data["purchase_order"]["matched"]

		if matched_po:
			pi_data["purchase_order"] = matched_po
		else:
			# Fallback to auto-detect from OrderReference or BuyerReference
			order_reference = get_xml_text(root, ".//cac:OrderReference/cbc:ID", namespaces)
			buyer_reference = get_xml_text(root, ".//cbc:BuyerReference", namespaces)

			# Use OrderReference first, fallback to BuyerReference
			po_reference = order_reference or buyer_reference
			if po_reference and frappe.db.exists("Purchase Order", po_reference):
				pi_data["purchase_order"] = po_reference

		# Build matched items lookup from matching_data
		matched_items = {}
		if matching_data and matching_data.get("items"):
			for item in matching_data["items"]:
				if item.get("matched"):
					matched_items[item["line_index"]] = item["matched"]

		# Parse line items (pass document_elements for generic parsing)
		pi_data["items"] = parse_peppol_line_items(
			root,
			namespaces,
			pi_data.get("purchase_order"),
			pi_data.get("supplier"),
			document_elements,
			matched_items=matched_items,
		)

		# Parse taxes
		pi_data["taxes"] = parse_peppol_taxes(root, namespaces)

		# Post-process: guess missing values
		guess_missing_values(pi_data)

		# Parse payment terms
		payment_schedule = parse_peppol_payment_terms(root, namespaces, due_date)
		if payment_schedule:
			pi_data["payment_schedule"] = payment_schedule

		# Parse monetary totals
		monetary_data = parse_peppol_monetary_totals(root, namespaces)
		pi_data.update(monetary_data)

		# Parse billing period
		billing_period = parse_peppol_billing_period(root, namespaces)
		if billing_period.get("from_date"):
			pi_data["from_date"] = billing_period["from_date"]
		if billing_period.get("to_date"):
			pi_data["to_date"] = billing_period["to_date"]

		return pi_data

	except Exception as e:
		frappe.log_error(f"PEPPOL Parsing Error: {e!s}", "EDocument PEPPOL Parsing")
		raise


def parse_peppol_seller(root, namespaces, matched_supplier=None):
	"""
	Parse seller (supplier) information from PEPPOL XML.

	Args:
		root: XML root element
		namespaces: Namespace dictionary
		matched_supplier: Pre-matched supplier from matching_data (takes precedence)
	"""
	seller_party = root.find(".//cac:AccountingSupplierParty/cac:Party", namespaces)
	if seller_party is None:
		return {"supplier": matched_supplier, "name": None}

	# Seller name
	seller_name = get_xml_text(
		seller_party, ".//cac:PartyLegalEntity/cbc:RegistrationName", namespaces
	) or get_xml_text(seller_party, ".//cac:PartyName/cbc:Name", namespaces)

	# Seller tax ID
	seller_tax_id = get_xml_text(seller_party, ".//cac:PartyTaxScheme/cbc:CompanyID", namespaces)

	# Use matched supplier if provided, otherwise try to find
	supplier = matched_supplier
	if not supplier:
		if seller_name and frappe.db.exists("Supplier", seller_name):
			supplier = seller_name
		elif seller_tax_id:
			supplier = frappe.db.get_value("Supplier", {"tax_id": seller_tax_id}, "name")

	return {"supplier": supplier, "name": seller_name, "tax_id": seller_tax_id}


def parse_peppol_buyer(root, namespaces):
	"""Parse buyer (company) information from PEPPOL XML."""
	buyer_party = root.find(".//cac:AccountingCustomerParty/cac:Party", namespaces)
	if buyer_party is None:
		return {"company": None, "name": None}

	# Buyer name
	buyer_name = get_xml_text(
		buyer_party, ".//cac:PartyLegalEntity/cbc:RegistrationName", namespaces
	) or get_xml_text(buyer_party, ".//cac:PartyName/cbc:Name", namespaces)

	# Try to find company
	company = None
	if buyer_name and frappe.db.exists("Company", buyer_name):
		company = buyer_name

	return {"company": company, "name": buyer_name}


def parse_peppol_line_items(
	root, namespaces, purchase_order=None, supplier=None, document_elements=None, matched_items=None
):
	"""
	Parse line items from PEPPOL XML.
	Supports InvoiceLine, CreditNoteLine, and DebitNoteLine.

	Args:
		root: XML root element
		namespaces: Namespace dictionary
		purchase_order: Optional purchase order for item matching
		supplier: Optional supplier for item matching
		document_elements: Document type element names (from DOCUMENT_TYPE_ELEMENTS)
		matched_items: Dict mapping line_index to matched item_code from matching_data

	Returns:
		list: List of item dictionaries
	"""
	if document_elements is None:
		document_elements = DOCUMENT_TYPE_ELEMENTS["Invoice"]

	matched_items = matched_items or {}
	items = []

	# Use document-specific line element name (InvoiceLine, CreditNoteLine, DebitNoteLine)
	line_elem_name = document_elements["line"]
	quantity_elem_name = document_elements["quantity"]

	for idx, invoice_line in enumerate(root.findall(f".//cac:{line_elem_name}", namespaces)):
		item = {"doctype": "Purchase Invoice Item"}

		# Product name/description
		product_name = get_xml_text(invoice_line, ".//cac:Item/cbc:Name", namespaces)
		product_description = get_xml_text(invoice_line, ".//cac:Item/cbc:Description", namespaces)

		if product_name:
			if len(product_name) > 140:
				item["item_name"] = product_name[:140]
				item["description"] = product_name + (
					" | " + product_description if product_description else ""
				)
			else:
				item["item_name"] = product_name
				item["description"] = product_description or product_name

		# Product IDs
		seller_product_id = get_xml_text(
			invoice_line, ".//cac:Item/cac:SellersItemIdentification/cbc:ID", namespaces
		)
		buyer_item_id = get_xml_text(
			invoice_line, ".//cac:Item/cac:BuyersItemIdentification/cbc:ID", namespaces
		)

		# Store seller product ID for later item code guessing
		if seller_product_id:
			item["seller_product_id"] = seller_product_id

		# Use matched item from matching_data if available
		item_code = matched_items.get(idx)
		if not item_code:
			# Try to find item by buyer item ID
			if buyer_item_id and frappe.db.exists("Item", buyer_item_id):
				item_code = buyer_item_id

		item["item_code"] = item_code

		# Quantity and UOM (use document-specific quantity element name)
		qty_elem = invoice_line.find(f".//cbc:{quantity_elem_name}", namespaces)
		if qty_elem is not None and qty_elem.text:
			item["qty"] = flt_or_none(qty_elem.text)
			unit_code = qty_elem.get("unitCode")
			if unit_code:
				# Store unit_code for later UOM guessing
				item["unit_code"] = unit_code

		# Price and rate calculation
		price_text = get_xml_text(invoice_line, ".//cac:Price/cbc:PriceAmount", namespaces)
		base_qty_text = get_xml_text(invoice_line, ".//cac:Price/cbc:BaseQuantity", namespaces)
		line_total_text = get_xml_text(invoice_line, ".//cbc:LineExtensionAmount", namespaces)

		if price_text:
			# PriceAmount is the unit price, BaseQuantity is what that price applies to (default 1)
			# rate = PriceAmount / BaseQuantity
			net_rate = float(price_text)
			base_qty = float(base_qty_text) if base_qty_text else 1.0
			item["rate"] = net_rate / base_qty if base_qty else net_rate

		# Line total
		if line_total_text:
			item["amount"] = flt_or_none(line_total_text)

		# Tax rate (for reference, actual tax is in taxes table)
		tax_category = invoice_line.find(".//cac:Item/cac:ClassifiedTaxCategory", namespaces)
		if tax_category is not None:
			tax_rate_text = get_xml_text(tax_category, ".//cbc:Percent", namespaces)
			if tax_rate_text:
				item["tax_rate"] = flt_or_none(tax_rate_text)

		# Purchase Order detail (if purchase order exists)
		if purchase_order:
			item["purchase_order"] = purchase_order

		# Set po_detail if provided (will be set by guess_po_details later)
		item["po_detail"] = None

		items.append(item)

	return items


def parse_peppol_taxes(root, namespaces):
	"""Parse taxes from PEPPOL XML."""
	taxes = []
	tax_total = root.find(".//cac:TaxTotal", namespaces)
	if tax_total is None:
		return taxes

	for tax_subtotal in tax_total.findall(".//cac:TaxSubtotal", namespaces):
		tax = {"doctype": "Purchase Taxes and Charges", "charge_type": "Actual"}

		# Tax basis
		taxable_amount = get_xml_text(tax_subtotal, ".//cbc:TaxableAmount", namespaces)
		if taxable_amount:
			tax["taxable_amount"] = flt_or_none(taxable_amount)

		# Tax rate
		tax_category = tax_subtotal.find(".//cac:TaxCategory", namespaces)
		if tax_category is not None:
			tax_percent = get_xml_text(tax_category, ".//cbc:Percent", namespaces)
			if tax_percent:
				tax["rate"] = flt_or_none(tax_percent)

			# Tax account (try to find from tax category)
			# This is a simplified approach - you may need to map tax categories to accounts
			tax["account_head"] = None  # Will need to be set based on your tax setup

		# Tax amount
		tax_amount = get_xml_text(tax_subtotal, ".//cbc:TaxAmount", namespaces)
		if tax_amount:
			tax["tax_amount"] = flt_or_none(tax_amount)

		taxes.append(tax)

	return taxes


def parse_peppol_payment_terms(root, namespaces, default_due_date=None):
	"""Parse payment terms from PEPPOL XML."""
	payment_schedule = []

	for payment_term in root.findall(".//cac:PaymentTerms", namespaces):
		# Check if it's a simple due date
		amount_text = get_xml_text(payment_term, ".//cbc:Amount", namespaces)
		if not amount_text:
			# Simple due date - skip (will use default_due_date)
			continue

		# Complex payment term with amount
		schedule_item = {"doctype": "Payment Schedule"}

		payment_due_date = get_xml_text(payment_term, ".//cbc:PaymentDueDate", namespaces)
		if payment_due_date:
			schedule_item["due_date"] = payment_due_date
		elif default_due_date:
			schedule_item["due_date"] = default_due_date

		if amount_text:
			schedule_item["payment_amount"] = flt_or_none(amount_text)

		# Description
		description = get_xml_text(payment_term, ".//cbc:Note", namespaces)
		if description:
			schedule_item["description"] = description

		# Discount terms (if any)
		discount_basis_date = get_xml_text(
			payment_term, ".//cac:PaymentDiscountTerms/cbc:BasisDate", namespaces
		)
		if discount_basis_date:
			schedule_item["discount_date"] = discount_basis_date

		discount_percent = get_xml_text(
			payment_term, ".//cac:PaymentDiscountTerms/cbc:CalculationPercent", namespaces
		)
		if discount_percent:
			schedule_item["discount_type"] = "Percentage"
			schedule_item["discount"] = flt_or_none(discount_percent)

		discount_amount = get_xml_text(payment_term, ".//cac:PaymentDiscountTerms/cbc:Amount", namespaces)
		if discount_amount:
			schedule_item["discount_type"] = "Amount"
			schedule_item["discount"] = flt_or_none(discount_amount)

		payment_schedule.append(schedule_item)

	# If no payment terms found, add default one
	if not payment_schedule and default_due_date:
		payment_schedule.append({"doctype": "Payment Schedule", "due_date": default_due_date})

	return payment_schedule


def parse_peppol_monetary_totals(root, namespaces):
	"""Parse monetary totals from PEPPOL XML."""
	monetary_total = root.find(".//cac:LegalMonetaryTotal", namespaces)
	if monetary_total is None:
		return {}

	return {
		"base_net_total": flt_or_none(get_xml_text(monetary_total, ".//cbc:LineExtensionAmount", namespaces)),
		"base_grand_total": flt_or_none(get_xml_text(monetary_total, ".//cbc:PayableAmount", namespaces)),
		"grand_total": flt_or_none(get_xml_text(monetary_total, ".//cbc:PayableAmount", namespaces)),
		"rounded_total": flt_or_none(get_xml_text(monetary_total, ".//cbc:PayableAmount", namespaces)),
	}


def parse_peppol_billing_period(root, namespaces):
	"""Parse billing period from PEPPOL XML."""
	period = root.find(".//cac:InvoicePeriod", namespaces)
	if period is None:
		return {}

	return {
		"from_date": get_xml_text(period, ".//cbc:StartDate", namespaces),
		"to_date": get_xml_text(period, ".//cbc:EndDate", namespaces),
	}


def parse_peppol_bank_details(root, namespaces):
	"""Parse bank details from PEPPOL XML."""
	payment_means = root.find(".//cac:PaymentMeans", namespaces)
	if payment_means is None:
		return {}

	financial_account = payment_means.find(".//cac:PayeeFinancialAccount", namespaces)
	if financial_account is None:
		return {}

	bank_data = {}

	# IBAN
	iban = get_xml_text(financial_account, ".//cbc:ID", namespaces)
	if iban:
		bank_data["payee_iban"] = iban

	# Account name (for EN16931 and above)
	account_name = get_xml_text(financial_account, ".//cbc:Name", namespaces)
	if account_name:
		bank_data["payee_account_name"] = account_name

	# BIC (Bank Identifier Code) - PEPPOL-compliant structure: FinancialInstitutionBranch/ID
	financial_institution_branch = financial_account.find(".//cac:FinancialInstitutionBranch", namespaces)
	if financial_institution_branch is not None:
		bic = get_xml_text(financial_institution_branch, ".//cbc:ID", namespaces)
		if bic:
			bank_data["payee_bic"] = bic

	return bank_data


def guess_missing_values(pi_data):
	"""Guess missing values for Purchase Invoice."""
	# Guess supplier if not found
	if not pi_data.get("supplier") and pi_data.get("supplier_name"):
		if frappe.db.exists("Supplier", pi_data["supplier_name"]):
			pi_data["supplier"] = pi_data["supplier_name"]

	# Guess company if not found
	if not pi_data.get("company"):
		pi_data["company"] = get_default_company()

	# Guess UOM and item codes for items
	for item in pi_data.get("items", []):
		# Guess UOM from unit_code
		if not item.get("uom") and item.get("unit_code"):
			try:
				from erpnext.edi.doctype.code_list.code_list import get_docnames_for

				from edocument.edocument.profiles.peppol import uom_codes

				uom_list = get_docnames_for(uom_codes.code_lists[0], "UOM", item["unit_code"])
				if uom_list:
					item["uom"] = uom_list[0]
			except Exception:
				pass

		# If UOM still not found, try to get from item
		if not item.get("uom") and item.get("item_code"):
			try:
				stock_uom, purchase_uom = frappe.db.get_value(
					"Item", item["item_code"], ["stock_uom", "purchase_uom"]
				)
				item["uom"] = purchase_uom or stock_uom
			except Exception:
				pass

		# Guess item code from seller product ID
		if not item.get("item_code") and item.get("seller_product_id") and pi_data.get("supplier"):
			try:
				item_code = frappe.db.get_value(
					"Item Supplier",
					{"supplier": pi_data["supplier"], "supplier_part_no": item["seller_product_id"]},
					"parent",
				)
				if item_code:
					item["item_code"] = item_code
			except Exception:
				pass

		# Remove temporary fields (if they exist)
		if "seller_product_id" in item:
			item.pop("seller_product_id")
		if "unit_code" in item:
			item.pop("unit_code")

	# Guess Purchase Order details for items
	guess_po_details(pi_data)

	# Set purchase_order on items if PO exists (parser should provide complete data)
	if pi_data.get("purchase_order"):
		for item in pi_data.get("items", []):
			if not item.get("purchase_order"):
				item["purchase_order"] = pi_data["purchase_order"]

	# Guess tax accounts for taxes (simplified - you may need to map based on your tax setup)
	for tax in pi_data.get("taxes", []):
		if not tax.get("account_head") and tax.get("rate"):
			# Try to find a default tax account based on rate
			# This is a simplified approach - you may need to customize this
			try:
				# Get default tax account from company settings or tax template
				# For now, leave it empty - user will need to set it manually
				pass
			except Exception:
				pass


def guess_po_details(pi_data):
	"""Guess Purchase Order details for items."""
	if not pi_data.get("purchase_order"):
		# Clear po_detail for all items if no PO
		for item in pi_data.get("items", []):
			item["po_detail"] = None
		return

	# Get Purchase Order
	try:
		purchase_order = frappe.get_doc("Purchase Order", pi_data["purchase_order"])
	except Exception:
		# PO doesn't exist or can't be loaded
		for item in pi_data.get("items", []):
			item["po_detail"] = None
		return

	# Create a list of PO items with unbilled amounts
	po_items = []
	for po_row in purchase_order.items:
		po_items.append(
			{
				"name": po_row.name,
				"item_code": po_row.item_code,
				"unbilled_amount": flt(po_row.amount) - flt(po_row.billed_amt),
			}
		)

	# Match PI items to PO items
	for pi_item in pi_data.get("items", []):
		# Skip if po_detail already set and valid
		if pi_item.get("po_detail"):
			try:
				if frappe.db.exists(
					"Purchase Order Item", {"name": pi_item["po_detail"], "parent": pi_data["purchase_order"]}
				):
					continue
			except Exception:
				pass

		# Try to match by item code and unbilled amount
		pi_item_code = pi_item.get("item_code")
		pi_amount = flt(pi_item.get("amount") or pi_item.get("rate", 0) * flt(pi_item.get("qty", 0)))

		matched = False
		for po_item in po_items:
			if po_item["item_code"] == pi_item_code and po_item["unbilled_amount"] >= pi_amount:
				pi_item["po_detail"] = po_item["name"]
				po_item["unbilled_amount"] -= pi_amount
				matched = True
				break

		if not matched:
			pi_item["po_detail"] = None
