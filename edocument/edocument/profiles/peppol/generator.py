# Copyright (c) 2025, Prilk Consulting BV and contributors
"""
PEPPOL Generator

This module provides UBL 2.1 XML generation for PEPPOL BIS Billing 3.0
compliant invoices from ERPNext data.
"""

from datetime import datetime

import frappe
from frappe.utils.data import flt
from lxml import etree as ET

from edocument.edocument.profiles.peppol import (
	DOCUMENT_TYPE_ELEMENTS,
	DOCUMENT_TYPE_MAPPING,
	DOCUMENT_TYPE_NAMESPACES,
	PEPPOL_CUSTOMIZATION_ID,
	PEPPOL_PROFILE_ID,
	UBL_NAMESPACES,
	VATEX_CODES,
	VATEX_REASON_TEXTS,
	duty_tax_fee_category_codes,
	payment_means_codes,
	uom_codes,
)


class PEPPOLGenerator:
	# Generates PEPPOL BIS Billing 3.0 compliant UBL 2.1 XML documents

	namespaces = UBL_NAMESPACES

	def __init__(self, invoice):
		# Initialize PEPPOL generator with invoice object
		if not invoice:
			raise ValueError("Invoice is required for PEPPOL generation")

		self.invoice = invoice
		self.xml_bytes = None

		self.seller_address = None
		if invoice.company_address:
			self.seller_address = frappe.get_doc("Address", invoice.company_address)

		self.buyer_address = None
		if invoice.customer_address:
			self.buyer_address = frappe.get_doc("Address", invoice.customer_address)

		self.shipping_address = None
		if invoice.shipping_address_name:
			self.shipping_address = frappe.get_doc("Address", invoice.shipping_address_name)

		self.seller_contact = None
		if invoice.get("company_contact_person"):
			self.seller_contact = frappe.get_doc("Contact", invoice.company_contact_person)

		self.buyer_contact = None
		if invoice.contact_person:
			self.buyer_contact = frappe.get_doc("Contact", invoice.contact_person)

		# Determine document type (Invoice, CreditNote, DebitNote, etc.)
		self.document_type = self._get_document_type()
		self.document_elements = DOCUMENT_TYPE_ELEMENTS.get(
			self.document_type, DOCUMENT_TYPE_ELEMENTS["Invoice"]
		)

	def _get_document_type(self) -> str:
		"""
		Determine the UBL document type from the invoice.

		Returns:
		    str: Document type ('Invoice', 'CreditNote', 'DebitNote', etc.)
		"""
		invoice_type_code = self.get_invoice_type_code(self.invoice)
		# Map invoice type code to UBL document type
		document_type = DOCUMENT_TYPE_MAPPING.get(invoice_type_code, "Invoice")
		return document_type

	def _has_out_of_scope_items(self) -> bool:
		"""Check if any invoice line has VAT category 'O' (Out of Scope).

		Per PEPPOL BR-O-02: invoices with O items shall not contain VAT identifiers.
		"""
		for item in self.invoice.items:
			if self.get_vat_category_code(self.invoice, item=item) == "O":
				return True
		return False

	def _is_intra_community_invoice(self) -> bool:
		"""Check if the invoice is an intra-community supply.

		An invoice is intra-community if any item has VAT category K.

		Returns:
		    bool: True if this is an intra-community invoice
		"""
		for item in self.invoice.items:
			if self.get_vat_category_code(self.invoice, item=item) == "K":
				return True
		return False

	def create_einvoice(self):
		# Create the PEPPOL XML document
		try:
			if not self.invoice:
				raise ValueError("No invoice provided to PEPPOLGenerator")

			self._initialize_document()

			self._set_header()
			self._set_seller()
			self._set_buyer()
			self._add_delivery()
			self._add_payment_means()
			self._add_allowances_charges()
			self._add_tax_totals()
			self._set_totals()
			self._add_line_items()

			self.xml_bytes = self.finalize_xml_document(self.root)

		except Exception as e:
			frappe.logger().error(f"PEPPOL generation failed: {e!s}")
			import traceback

			frappe.logger().error(f"PEPPOL traceback: {traceback.format_exc()}")
			raise

	def _initialize_document(self):
		# Initialize the UBL 2.1 Invoice XML document
		self.root = self.initialize_peppol_xml()

	def _set_header(self):
		# Set document header information
		if not hasattr(self, "root") or self.root is None:
			return

		ubl_version = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}UBLVersionID")
		ubl_version.text = "2.1"

		customization_id = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}CustomizationID")
		customization_id.text = PEPPOL_CUSTOMIZATION_ID

		profile_id = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}ProfileID")
		profile_id.text = PEPPOL_PROFILE_ID

		doc_id = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}ID")
		doc_id.text = self.invoice.name

		issue_date = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}IssueDate")
		issue_date.text = self.format_date(self.invoice.posting_date)

		# DueDate is only for Invoice, not for CreditNote or DebitNote
		if self.invoice.due_date and self.document_type == "Invoice":
			due_date = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}DueDate")
			due_date.text = self.format_date(self.invoice.due_date)

		# Use document-specific type code element (InvoiceTypeCode, CreditNoteTypeCode, etc.)
		invoice_type_code = self.get_invoice_type_code(self.invoice)
		type_code_elem = ET.SubElement(
			self.root, f"{{{self.namespaces['cbc']}}}{self.document_elements['type_code']}"
		)
		type_code_elem.text = invoice_type_code

		currency_code = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}DocumentCurrencyCode")
		currency_code.text = self.invoice.currency

		# Add BuyerReference with PO number if po_no exists
		if self.invoice.po_no:
			buyer_ref = ET.SubElement(self.root, f"{{{self.namespaces['cbc']}}}BuyerReference")
			buyer_ref.text = self.invoice.po_no

		# Add OrderReference if po_no exists
		if self.invoice.po_no:
			order_ref = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}OrderReference")
			order_id = ET.SubElement(order_ref, f"{{{self.namespaces['cbc']}}}ID")
			order_id.text = self.invoice.po_no

		# Add BillingReference for credit notes (references the original invoice)
		# NL-R-001: For Netherlands suppliers, credit notes MUST have BillingReference
		if self.document_type == "CreditNote" and self.invoice.return_against:
			billing_ref = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}BillingReference")
			invoice_doc_ref = ET.SubElement(
				billing_ref, f"{{{self.namespaces['cac']}}}InvoiceDocumentReference"
			)
			invoice_id = ET.SubElement(invoice_doc_ref, f"{{{self.namespaces['cbc']}}}ID")
			invoice_id.text = self.invoice.return_against

			# Optionally add IssueDate of the original invoice
			try:
				original_invoice_date = frappe.db.get_value(
					"Sales Invoice", self.invoice.return_against, "posting_date"
				)
				if original_invoice_date:
					invoice_issue_date = ET.SubElement(
						invoice_doc_ref, f"{{{self.namespaces['cbc']}}}IssueDate"
					)
					invoice_issue_date.text = self.format_date(original_invoice_date)
			except Exception:
				pass  # If date lookup fails, continue without it

	def _set_seller(self):
		# Set seller/supplier information
		if not hasattr(self, "root") or self.root is None:
			return

		supplier_party = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}AccountingSupplierParty")
		party = ET.SubElement(supplier_party, f"{{{self.namespaces['cac']}}}Party")

		company = frappe.get_doc("Company", self.invoice.company)

		electronic_address = self.get_seller_electronic_address(company, self.seller_contact)
		if electronic_address:
			endpoint = ET.SubElement(party, f"{{{self.namespaces['cbc']}}}EndpointID")
			endpoint.text = electronic_address["value"]
			endpoint.set("schemeID", electronic_address["scheme_id"])

		party_id = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyIdentification")
		id_elem = ET.SubElement(party_id, f"{{{self.namespaces['cbc']}}}ID")
		id_elem.text = company.name

		party_name = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyName")
		name_elem = ET.SubElement(party_name, f"{{{self.namespaces['cbc']}}}Name")
		name_elem.text = company.company_name or company.name

		if self.seller_address:
			postal_address = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PostalAddress")

			street = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}StreetName")
			street.text = self.seller_address.address_line1 or ""

			if self.seller_address.address_line2:
				additional_street = ET.SubElement(
					postal_address, f"{{{self.namespaces['cbc']}}}AdditionalStreetName"
				)
				additional_street.text = self.seller_address.address_line2

			city = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}CityName")
			city.text = self.seller_address.city or ""

			postal_zone = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}PostalZone")
			postal_zone.text = self.seller_address.pincode or ""

			country = ET.SubElement(postal_address, f"{{{self.namespaces['cac']}}}Country")
			country_code = ET.SubElement(country, f"{{{self.namespaces['cbc']}}}IdentificationCode")
			if self.seller_address.country:
				country_code.text = (
					frappe.db.get_value("Country", self.seller_address.country, "code") or "DE"
				).upper()
			else:
				country_code.text = "DE"

		# BR-O-02: Omit VAT identifiers if any item is Out of Scope
		if self.invoice.company_tax_id and not self._has_out_of_scope_items():
			tax_scheme = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyTaxScheme")
			company_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}CompanyID")
			company_id.text = self.invoice.company_tax_id

			scheme = ET.SubElement(tax_scheme, f"{{{self.namespaces['cac']}}}TaxScheme")
			scheme_id = ET.SubElement(scheme, f"{{{self.namespaces['cbc']}}}ID")
			scheme_id.text = "VAT"

		legal_entity = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyLegalEntity")
		registration_name = ET.SubElement(legal_entity, f"{{{self.namespaces['cbc']}}}RegistrationName")
		registration_name.text = company.company_name or company.name

		# Add Contact information if available
		if self.seller_contact:
			contact = ET.SubElement(party, f"{{{self.namespaces['cac']}}}Contact")
			if self.seller_contact.first_name or self.seller_contact.last_name:
				contact_name = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}Name")
				contact_name.text = (
					f"{self.seller_contact.first_name or ''} {self.seller_contact.last_name or ''}".strip()
				)
			if self.seller_contact.email_id:
				contact_email = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}ElectronicMail")
				contact_email.text = self.seller_contact.email_id
		elif company.email:
			contact = ET.SubElement(party, f"{{{self.namespaces['cac']}}}Contact")
			contact_email = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}ElectronicMail")
			contact_email.text = company.email

	def _set_buyer(self):
		# Set buyer/customer information
		if not hasattr(self, "root") or self.root is None:
			return

		customer_party = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}AccountingCustomerParty")

		customer = frappe.get_doc("Customer", self.invoice.customer)

		party = ET.SubElement(customer_party, f"{{{self.namespaces['cac']}}}Party")

		# customer already loaded above
		electronic_address = self.get_buyer_electronic_address(
			customer, self.invoice, self.buyer_contact, self.buyer_address
		)
		if electronic_address:
			endpoint = ET.SubElement(party, f"{{{self.namespaces['cbc']}}}EndpointID")
			endpoint.text = electronic_address["value"]
			endpoint.set("schemeID", electronic_address["scheme_id"])

		party_id = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyIdentification")
		id_elem = ET.SubElement(party_id, f"{{{self.namespaces['cbc']}}}ID")
		id_elem.text = customer.name

		party_name = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyName")
		name_elem = ET.SubElement(party_name, f"{{{self.namespaces['cbc']}}}Name")
		name_elem.text = customer.customer_name or customer.name

		if self.buyer_address:
			postal_address = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PostalAddress")

			street = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}StreetName")
			street.text = self.buyer_address.address_line1 or ""

			if self.buyer_address.address_line2:
				additional_street = ET.SubElement(
					postal_address, f"{{{self.namespaces['cbc']}}}AdditionalStreetName"
				)
				additional_street.text = self.buyer_address.address_line2

			city = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}CityName")
			city.text = self.buyer_address.city or ""

			postal_zone = ET.SubElement(postal_address, f"{{{self.namespaces['cbc']}}}PostalZone")
			postal_zone.text = self.buyer_address.pincode or ""

			country = ET.SubElement(postal_address, f"{{{self.namespaces['cac']}}}Country")
			country_code = ET.SubElement(country, f"{{{self.namespaces['cbc']}}}IdentificationCode")
			if self.buyer_address.country:
				country_code.text = (
					frappe.db.get_value("Country", self.buyer_address.country, "code") or "DE"
				).upper()
			else:
				country_code.text = "DE"

		# BR-O-02: Omit VAT identifiers if any item is Out of Scope
		if self.invoice.tax_id and not self._has_out_of_scope_items():
			tax_scheme = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyTaxScheme")
			company_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}CompanyID")
			company_id.text = self.invoice.tax_id

			scheme = ET.SubElement(tax_scheme, f"{{{self.namespaces['cac']}}}TaxScheme")
			scheme_id = ET.SubElement(scheme, f"{{{self.namespaces['cbc']}}}ID")
			scheme_id.text = "VAT"

		legal_entity = ET.SubElement(party, f"{{{self.namespaces['cac']}}}PartyLegalEntity")
		registration_name = ET.SubElement(legal_entity, f"{{{self.namespaces['cbc']}}}RegistrationName")
		registration_name.text = customer.customer_name or customer.name

		# Add Contact information if available
		if self.buyer_contact:
			contact = ET.SubElement(party, f"{{{self.namespaces['cac']}}}Contact")
			if self.buyer_contact.first_name or self.buyer_contact.last_name:
				contact_name = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}Name")
				contact_name.text = (
					f"{self.buyer_contact.first_name or ''} {self.buyer_contact.last_name or ''}".strip()
				)
			if self.buyer_contact.email_id:
				contact_email = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}ElectronicMail")
				contact_email.text = self.buyer_contact.email_id
		elif self.invoice.contact_email:
			contact = ET.SubElement(party, f"{{{self.namespaces['cac']}}}Contact")
			contact_email = ET.SubElement(contact, f"{{{self.namespaces['cbc']}}}ElectronicMail")
			contact_email.text = self.invoice.contact_email

	def _add_delivery(self):
		"""Add Delivery element for intra-community and cross-border invoices.

		Required by:
		- BR-IC-11: Intra-community supply must have ActualDeliveryDate or InvoicePeriod
		- BR-IC-12: Intra-community supply must have Delivery country code

		For IC invoices, adds:
		- ActualDeliveryDate (BT-72): Uses posting_date or delivery_date from invoice
		- DeliveryLocation/Address/Country (BT-80): Country where goods were delivered
		"""
		if not hasattr(self, "root") or self.root is None:
			return

		# Check if this is an intra-community invoice or has shipping address
		is_ic = self._is_intra_community_invoice()

		# Only add Delivery for IC invoices or when shipping address is present
		if not is_ic and not self.shipping_address:
			return

		delivery = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}Delivery")

		# ActualDeliveryDate (BT-72) - Required for IC invoices (BR-IC-11)
		# Use delivery_date if available, otherwise posting_date
		delivery_date = getattr(self.invoice, "delivery_date", None) or self.invoice.posting_date
		if delivery_date:
			actual_delivery_date = ET.SubElement(delivery, f"{{{self.namespaces['cbc']}}}ActualDeliveryDate")
			actual_delivery_date.text = self.format_date(delivery_date)

		# DeliveryLocation with Country (BT-80) - Required for IC invoices (BR-IC-12)
		# Use shipping address if available, otherwise buyer address
		delivery_address = self.shipping_address or self.buyer_address
		if delivery_address and delivery_address.country:
			delivery_location = ET.SubElement(delivery, f"{{{self.namespaces['cac']}}}DeliveryLocation")
			address = ET.SubElement(delivery_location, f"{{{self.namespaces['cac']}}}Address")
			country = ET.SubElement(address, f"{{{self.namespaces['cac']}}}Country")
			country_code_elem = ET.SubElement(country, f"{{{self.namespaces['cbc']}}}IdentificationCode")
			country_code_elem.text = (
				frappe.db.get_value("Country", delivery_address.country, "code") or "DE"
			).upper()

	def _add_line_items(self):
		# Add invoice line items
		if not hasattr(self, "root") or self.root is None:
			return

		for item in self.invoice.items:
			self._add_line_item(self.root, item)

	def _add_line_item(self, root: ET.Element, item):
		# Add a single line item using document-specific element names
		line_elem_name = self.document_elements["line"]  # InvoiceLine, CreditNoteLine, DebitNoteLine
		quantity_elem_name = self.document_elements[
			"quantity"
		]  # InvoicedQuantity, CreditedQuantity, DebitedQuantity

		line_elem = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}{line_elem_name}")

		line_id = ET.SubElement(line_elem, f"{{{self.namespaces['cbc']}}}ID")
		line_id.text = str(item.idx)

		# Normalize signs for PEPPOL compliance
		qty = flt(item.qty, item.precision("qty"))
		item_amount = flt(item.amount, item.precision("amount"))
		item_rate = flt(item.rate, item.precision("rate"))

		if self.document_type == "CreditNote":
			# Credit notes: all values positive (document type implies reversal)
			qty = abs(qty)
			item_amount = abs(item_amount)
			item_rate = abs(item_rate)
		elif item_amount < 0:
			# Invoice deduction line: move negative from rate/price to quantity
			qty = -abs(qty)
			item_rate = abs(item_rate)

		quantity = ET.SubElement(line_elem, f"{{{self.namespaces['cbc']}}}{quantity_elem_name}")
		quantity.text = str(qty)
		quantity.set("unitCode", self.map_unit_code(item.uom))

		# Update references from invoice_line to line_elem
		invoice_line = line_elem

		line_amount = ET.SubElement(invoice_line, f"{{{self.namespaces['cbc']}}}LineExtensionAmount")
		# Round through flt (the site's configured rounding), not f"{x:.2f}", so the line amount
		# matches the document LineExtensionAmount (BT-106), which is also flt-rounded — otherwise
		# the two disagree and BR-CO-10 fails on sub-cent (3-decimal) amounts.
		line_amount.text = f"{flt(item_amount, 2):.2f}"
		line_amount.set("currencyID", self.invoice.currency)

		item_elem = ET.SubElement(invoice_line, f"{{{self.namespaces['cac']}}}Item")

		description = ET.SubElement(item_elem, f"{{{self.namespaces['cbc']}}}Description")
		item_description = item.description or item.item_name
		if frappe.utils.is_html(item_description):
			from frappe.core.utils import html2text

			item_description = html2text(item_description).strip()
		description.text = item_description

		name = ET.SubElement(item_elem, f"{{{self.namespaces['cbc']}}}Name")
		name.text = item.item_name

		tax_category = ET.SubElement(item_elem, f"{{{self.namespaces['cac']}}}ClassifiedTaxCategory")

		category_code = self.get_vat_category_code(self.invoice, item=item)
		category_id = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}ID")
		category_id.text = category_code

		# BR-O-05: O lines shall not contain VAT rate; BR-E-05: E lines require rate = 0
		if category_code != "O":
			item_tax_rate = self._get_item_tax_rate(item) if category_code not in ("E",) else 0
			tax_percent = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}Percent")
			tax_percent.text = str(flt(item_tax_rate or 0, 2))

		tax_scheme = ET.SubElement(tax_category, f"{{{self.namespaces['cac']}}}TaxScheme")
		scheme_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}ID")
		scheme_id.text = "VAT"

		price = ET.SubElement(invoice_line, f"{{{self.namespaces['cac']}}}Price")
		price_amount = ET.SubElement(price, f"{{{self.namespaces['cbc']}}}PriceAmount")
		price_precision = item.precision("rate") or 2
		price_amount.text = f"{item_rate:.{price_precision}f}"
		price_amount.set("currencyID", self.invoice.currency)

	def _add_tax_totals(self):
		# Add tax total section (TaxTotal) with tax breakdown
		if not hasattr(self, "root") or self.root is None:
			return

		tax_total = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}TaxTotal")

		# Use invoice.total_taxes_and_charges for total TaxAmount (already correctly calculated after discount)
		# Credit notes: use abs() since PEPPOL CreditNote expects positive values
		total_tax = flt(self.invoice.total_taxes_and_charges, 2)
		if self.document_type == "CreditNote":
			total_tax = abs(total_tax)
		tax_amount = ET.SubElement(tax_total, f"{{{self.namespaces['cbc']}}}TaxAmount")
		tax_amount.text = f"{total_tax:.2f}"
		tax_amount.set("currencyID", self.invoice.currency)

		# Group taxes by (category_code, rate)
		# O items are not subject to VAT - no rate needed; E items require rate=0
		tax_groups = {}
		for item in self.invoice.items:
			category_code = self.get_vat_category_code(self.invoice, item=item)

			# O is not subject to VAT - no rate; E is exempt with rate=0
			if category_code == "O":
				rate = None
			elif category_code == "E":
				rate = 0
			else:
				rate = self._get_item_tax_rate(item) or 0

			key = (category_code, rate)

			if key not in tax_groups:
				tax_groups[key] = {"taxable_amount": 0, "tax_amount": 0}

			net_amount = flt(item.net_amount)
			if self.document_type == "CreditNote":
				net_amount = abs(net_amount)
			item_tax_amount = net_amount * (rate or 0) / 100
			tax_groups[key]["tax_amount"] += item_tax_amount
			tax_groups[key]["taxable_amount"] += net_amount

		# Add TaxSubtotal for each (category, rate) group
		for (category_code, rate), data in tax_groups.items():
			tax_subtotal = ET.SubElement(tax_total, f"{{{self.namespaces['cac']}}}TaxSubtotal")

			taxable_amount = ET.SubElement(tax_subtotal, f"{{{self.namespaces['cbc']}}}TaxableAmount")
			taxable_amount.text = f"{flt(data['taxable_amount'], 2):.2f}"
			taxable_amount.set("currencyID", self.invoice.currency)

			tax_amount = ET.SubElement(tax_subtotal, f"{{{self.namespaces['cbc']}}}TaxAmount")
			tax_amount.text = f"{flt(data['tax_amount'], 2):.2f}"
			tax_amount.set("currencyID", self.invoice.currency)

			tax_category = ET.SubElement(tax_subtotal, f"{{{self.namespaces['cac']}}}TaxCategory")

			category_id = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}ID")
			category_id.text = category_code

			# BR-48: O (Not subject to VAT) has no rate; all others require Percent
			if category_code != "O":
				tax_percent = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}Percent")
				tax_percent.text = str(flt(rate or 0, 2))

			if category_code in ["E", "AE", "G", "O", "K"]:
				# Add TaxExemptionReasonCode (VATEX code)
				exemption_code = self._get_exemption_reason_code(category_code)
				if exemption_code:
					exemption_reason_code = ET.SubElement(
						tax_category, f"{{{self.namespaces['cbc']}}}TaxExemptionReasonCode"
					)
					exemption_reason_code.text = exemption_code

				# Add TaxExemptionReason (text description)
				exemption_text = self._get_exemption_reason_text(category_code)
				if exemption_text:
					exemption_reason = ET.SubElement(
						tax_category, f"{{{self.namespaces['cbc']}}}TaxExemptionReason"
					)
					exemption_reason.text = exemption_text

			tax_scheme = ET.SubElement(tax_category, f"{{{self.namespaces['cac']}}}TaxScheme")
			scheme_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}ID")
			scheme_id.text = "VAT"

	def _add_payment_means(self):
		# Add payment means information
		if not hasattr(self, "root") or self.root is None:
			return

		# Check if we have any payment information
		has_payment_info = self.invoice.payment_terms_template or (
			self.invoice.payment_schedule
			and any(term.mode_of_payment for term in self.invoice.payment_schedule)
		)

		# Skip PaymentMeans if no payment information is available
		# PaymentMeans has cardinality 0..n in Peppol BIS Billing 3.0, making it optional
		if not has_payment_info:
			return

		# Add PaymentMeans
		payment_means = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}PaymentMeans")

		# Payment Means Code
		# Use CommonCodeRetriever to get code from Payment Terms Template or Mode of Payment
		# Validation will enforce NL-R-008 rule
		payment_code = ET.SubElement(payment_means, f"{{{self.namespaces['cbc']}}}PaymentMeansCode")
		payment_means_code_value = payment_means_codes.get(
			[("Payment Terms Template", self.invoice.payment_terms_template)]
			+ [("Mode of Payment", term.mode_of_payment) for term in self.invoice.payment_schedule]
		)
		payment_code.text = payment_means_code_value

		# PaymentID: Use invoice name
		payment_id = ET.SubElement(payment_means, f"{{{self.namespaces['cbc']}}}PaymentID")
		payment_id.text = self.invoice.name

		# Payee Financial Account
		# BR-61: Required for PaymentMeansCode 30 (SEPA), 58 (Local), 59 (Non-SEPA international)
		iban = None
		bic = None

		if self.document_type == "Invoice":
			# For Invoices: Get bank details from payment_schedule mode_of_payment
			modes_of_payment = {
				ps.mode_of_payment for ps in self.invoice.payment_schedule if ps.mode_of_payment
			}
			for mode_of_payment in modes_of_payment:
				iban, bic = self._get_bank_details(mode_of_payment, self.invoice.company)
				if iban:
					break  # Use first valid bank account found
		elif self.document_type == "CreditNote":
			# For Credit Notes: Get default company bank account
			default_bank_account = frappe.db.get_value(
				"Bank Account",
				{"company": self.invoice.company, "is_company_account": 1, "is_default": 1, "disabled": 0},
				"name",
			)
			if default_bank_account:
				iban, bank = frappe.db.get_value("Bank Account", default_bank_account, ["iban", "bank"])
				if iban:
					bic = frappe.db.get_value("Bank", bank, "swift_number") if bank else None

		# Add PayeeFinancialAccount if IBAN is found
		if iban:
			payee_financial_account = ET.SubElement(
				payment_means, f"{{{self.namespaces['cac']}}}PayeeFinancialAccount"
			)

			# PayeeFinancialAccount ID: Use IBAN
			financial_account_id = ET.SubElement(payee_financial_account, f"{{{self.namespaces['cbc']}}}ID")
			financial_account_id.text = iban

			# FinancialInstitutionBranch: Use BIC/SWIFT from Bank doctype
			if bic:
				financial_institution_branch = ET.SubElement(
					payee_financial_account, f"{{{self.namespaces['cac']}}}FinancialInstitutionBranch"
				)
				financial_institution_branch_id = ET.SubElement(
					financial_institution_branch, f"{{{self.namespaces['cbc']}}}ID"
				)
				financial_institution_branch_id.text = bic

	def _get_bank_details(self, mode_of_payment: str, company: str) -> tuple[str | None, str | None]:
		"""
		Get bank details (IBAN and BIC) for a mode of payment.

		Args:
		    mode_of_payment: Name of the Mode of Payment
		    company: Company name

		Returns:
		    Tuple of (IBAN, BIC) or (None, None) if not found
		"""
		empty_tuple = (None, None)

		# Check if Mode of Payment type is "Bank"
		if frappe.db.get_value("Mode of Payment", mode_of_payment, "type") != "Bank":
			return empty_tuple

		# Get account from Mode of Payment Account
		account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
		)
		if not account:
			return empty_tuple

		# Get Bank Account doctype name (using is_company_account=1 and disabled=0)
		bank_account_name = frappe.db.get_value(
			"Bank Account", {"account": account, "company": company, "is_company_account": 1, "disabled": 0}
		)
		if not bank_account_name:
			return empty_tuple

		# Get IBAN and Bank from Bank Account
		iban, bank = frappe.db.get_value("Bank Account", bank_account_name, ["iban", "bank"])
		if not iban:
			return empty_tuple

		# Get BIC/SWIFT from Bank doctype
		bic = frappe.db.get_value("Bank", bank, "swift_number") if bank else None

		return (iban, bic or None)

	def _add_allowances_charges(self):
		# Add document-level allowances and charges
		if not hasattr(self, "root") or self.root is None:
			return

		# Handle document-level discounts (AllowanceCharge with ChargeIndicator=false)
		discount_amount = flt(self.invoice.total, 2) - flt(self.invoice.net_total, 2)
		if self.document_type == "CreditNote":
			discount_amount = abs(discount_amount)
		if discount_amount > 0:
			# There's a document-level discount
			allowance_charge = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}AllowanceCharge")

			# ChargeIndicator: false for discounts (allowances)
			charge_indicator = ET.SubElement(allowance_charge, f"{{{self.namespaces['cbc']}}}ChargeIndicator")
			charge_indicator.text = "false"

			# AllowanceChargeReason: Use discount description or default
			reason_text = "Additional Discount"
			if self.invoice.discount_amount and self.invoice.additional_discount_percentage:
				reason_text = f"Discount ({self.invoice.additional_discount_percentage}%)"
			reason = ET.SubElement(allowance_charge, f"{{{self.namespaces['cbc']}}}AllowanceChargeReason")
			reason.text = reason_text

			# MultiplierFactorNumeric: Calculate percentage (Amount / BaseAmount * 100)
			inv_total = (
				abs(flt(self.invoice.total, 2))
				if self.document_type == "CreditNote"
				else flt(self.invoice.total, 2)
			)
			if inv_total > 0:
				multiplier = (discount_amount / inv_total) * 100
				multiplier_factor = ET.SubElement(
					allowance_charge, f"{{{self.namespaces['cbc']}}}MultiplierFactorNumeric"
				)
				multiplier_factor.text = str(flt(multiplier, 6))  # 6 decimal places as in example

			# Amount: The discount amount
			amount = ET.SubElement(allowance_charge, f"{{{self.namespaces['cbc']}}}Amount")
			amount.text = f"{flt(discount_amount, 2):.2f}"
			amount.set("currencyID", self.invoice.currency)

			# BaseAmount: The amount before discount (invoice.total)
			base_amount = ET.SubElement(allowance_charge, f"{{{self.namespaces['cbc']}}}BaseAmount")
			base_amount.text = f"{inv_total:.2f}"
			base_amount.set("currencyID", self.invoice.currency)

			# Tax Category (BR-32: always required on AllowanceCharge)
			# Get the first non-Actual tax rate (usually VAT)
			tax_rate = 0
			sample_tax = None
			for tax in self.invoice.taxes:
				if tax.charge_type != "Actual" and tax.rate:
					tax_rate = tax.rate
					sample_tax = tax
					break

			tax_category = ET.SubElement(allowance_charge, f"{{{self.namespaces['cac']}}}TaxCategory")

			category_code = self.get_vat_category_code(self.invoice, tax=sample_tax)

			category_id = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}ID")
			category_id.text = category_code

			tax_percent = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}Percent")
			tax_percent.text = str(flt(tax_rate, 2))

			tax_scheme = ET.SubElement(tax_category, f"{{{self.namespaces['cac']}}}TaxScheme")
			scheme_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}ID")
			scheme_id.text = "VAT"

		# Handle document-level charges (AllowanceCharge with ChargeIndicator=true)
		for tax in self.invoice.taxes:
			if tax.charge_type == "Actual" and tax.tax_amount != 0:
				allowance_charge = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}AllowanceCharge")

				charge_indicator = ET.SubElement(
					allowance_charge, f"{{{self.namespaces['cbc']}}}ChargeIndicator"
				)
				charge_indicator.text = "true"

				if tax.description:
					reason = ET.SubElement(
						allowance_charge, f"{{{self.namespaces['cbc']}}}AllowanceChargeReason"
					)
					reason.text = tax.description

				# Amount
				charge_amt = (
					abs(flt(tax.tax_amount, 2))
					if self.document_type == "CreditNote"
					else flt(tax.tax_amount, 2)
				)
				amount = ET.SubElement(allowance_charge, f"{{{self.namespaces['cbc']}}}Amount")
				amount.text = f"{charge_amt:.2f}"
				amount.set("currencyID", self.invoice.currency)

				# Tax Category (BR-32: always required on AllowanceCharge)
				tax_category = ET.SubElement(allowance_charge, f"{{{self.namespaces['cac']}}}TaxCategory")

				category_code = self.get_vat_category_code(self.invoice, tax=tax)

				category_id = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}ID")
				category_id.text = category_code

				tax_percent = ET.SubElement(tax_category, f"{{{self.namespaces['cbc']}}}Percent")
				tax_percent.text = str(flt(tax.rate or 0, 2))

				tax_scheme = ET.SubElement(tax_category, f"{{{self.namespaces['cac']}}}TaxScheme")
				scheme_id = ET.SubElement(tax_scheme, f"{{{self.namespaces['cbc']}}}ID")
				scheme_id.text = "VAT"

	def _set_totals(self):
		# Set monetary totals using ERPNext values directly
		if not hasattr(self, "root") or self.root is None:
			return

		# Add LegalMonetaryTotal section
		legal_total = ET.SubElement(self.root, f"{{{self.namespaces['cac']}}}LegalMonetaryTotal")

		# For credit notes, ERPNext stores negative totals but PEPPOL requires positive values
		is_credit = self.document_type == "CreditNote"
		inv_total = abs(flt(self.invoice.total, 2)) if is_credit else flt(self.invoice.total, 2)
		inv_net_total = abs(flt(self.invoice.net_total, 2)) if is_credit else flt(self.invoice.net_total, 2)
		inv_grand_total = (
			abs(flt(self.invoice.grand_total, 2)) if is_credit else flt(self.invoice.grand_total, 2)
		)

		# Line Extension Amount (BT-106) - Sum of Invoice line net amount (BEFORE discount)
		# Use invoice.total which is the sum of all item.amount values
		line_total = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}LineExtensionAmount")
		line_total.text = f"{inv_total:.2f}"
		line_total.set("currencyID", self.invoice.currency)

		# Tax Exclusive Amount (BT-109) - Invoice total amount without VAT
		# This equals LineExtensionAmount - AllowanceTotalAmount = net_total (after discount, before tax)
		tax_exclusive_amount = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}TaxExclusiveAmount")
		tax_exclusive_amount.text = f"{inv_net_total:.2f}"
		tax_exclusive_amount.set("currencyID", self.invoice.currency)

		# Tax Inclusive Amount (BT-112) = Tax Exclusive + total VAT. Derive it from the rounded
		# parts instead of reading grand_total, so it still reconciles when the invoice carries
		# sub-cent (3-decimal) amounts whose independent 2-decimal roundings no longer add up
		# (BR-CO-15).
		total_tax = flt(self.invoice.total_taxes_and_charges, 2)
		if is_credit:
			total_tax = abs(total_tax)
		tax_inclusive = flt(inv_net_total + total_tax, 2)
		tax_inclusive_amount = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}TaxInclusiveAmount")
		tax_inclusive_amount.text = f"{tax_inclusive:.2f}"
		tax_inclusive_amount.set("currencyID", self.invoice.currency)

		# Allowance Total Amount (BT-107) - Sum of allowances on document level (discount)
		# Calculate as difference between total (before discount) and net_total (after discount)
		allowance_amount = inv_total - inv_net_total
		allowance_total = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}AllowanceTotalAmount")
		allowance_total.text = f"{flt(allowance_amount, 2):.2f}"
		allowance_total.set("currencyID", self.invoice.currency)

		# Charge Total Amount (BT-108) - Sum of charges on document level
		# Must come AFTER AllowanceTotalAmount per XSD schema order
		actual_charge_total = sum(tax.tax_amount for tax in self.invoice.taxes if tax.charge_type == "Actual")
		if is_credit:
			actual_charge_total = abs(actual_charge_total)
		if actual_charge_total:
			charge_total = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}ChargeTotalAmount")
			charge_total.text = f"{flt(actual_charge_total, 2):.2f}"
			charge_total.set("currencyID", self.invoice.currency)
		else:
			# Always add ChargeTotalAmount (set to 0.00 if no charges)
			charge_total = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}ChargeTotalAmount")
			charge_total.text = "0.00"
			charge_total.set("currencyID", self.invoice.currency)

		# Prepaid Amount (BT-113) - already-paid portion, measured against the rounded total due
		# (what the customer actually owes) so partially-paid invoices with a rounding adjustment
		# still balance; falls back to grand_total when Round Off is disabled (rounded_total = 0).
		prepaid_value = 0.0
		if not is_credit:
			rounded_total = flt(self.invoice.rounded_total, 2) or flt(self.invoice.grand_total, 2)
			prepaid_value = flt(rounded_total - flt(self.invoice.outstanding_amount, 2), 2)
			if prepaid_value > 0:
				prepaid_amount = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}PrepaidAmount")
				prepaid_amount.text = f"{prepaid_value:.2f}"
				prepaid_amount.set("currencyID", self.invoice.currency)
			else:
				prepaid_value = 0.0

		# Payable Amount (BT-115) - the real amount due
		if is_credit:
			payable_value = inv_grand_total
		else:
			payable_value = flt(self.invoice.outstanding_amount, 2)

		# Payable Rounding Amount (BT-114) - residual that reconciles the derived tax-inclusive
		# total with the amount due (BR-CO-16: Payable = TaxInclusive - Prepaid + Rounding). On a
		# sub-cent invoice this carries the <=1 cent gap. Must come after PrepaidAmount and before
		# PayableAmount per the UBL XSD order; emitted only when non-zero.
		rounding_amount = flt(payable_value - (tax_inclusive - prepaid_value), 2)
		if rounding_amount:
			payable_rounding = ET.SubElement(
				legal_total, f"{{{self.namespaces['cbc']}}}PayableRoundingAmount"
			)
			payable_rounding.text = f"{rounding_amount:.2f}"
			payable_rounding.set("currencyID", self.invoice.currency)

		payable_amount = ET.SubElement(legal_total, f"{{{self.namespaces['cbc']}}}PayableAmount")
		payable_amount.text = f"{payable_value:.2f}"
		payable_amount.set("currencyID", self.invoice.currency)

	def initialize_peppol_xml(self) -> ET.Element:
		# Initialize the PEPPOL XML document with root element and namespaces
		nsmap = {
			None: self.namespaces["ubl"],  # Default namespace for root element (will be overridden)
			"cbc": self.namespaces["cbc"],
			"cac": self.namespaces["cac"],
		}

		# Get document-specific namespace and root element name
		document_ns = DOCUMENT_TYPE_NAMESPACES.get(self.document_type, DOCUMENT_TYPE_NAMESPACES["Invoice"])
		root_element_name = self.document_elements["root"]  # Invoice, CreditNote, DebitNote

		# Set the default namespace for the root element
		nsmap[None] = document_ns

		# Create root element with appropriate namespace
		root = ET.Element(f"{{{document_ns}}}{root_element_name}", nsmap=nsmap)

		return root

	def finalize_xml_document(self, root: ET.Element) -> bytes:
		# Format XML and return as bytes
		return ET.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True)

	def format_date(self, date):
		# Format date to YYYY-MM-DD string
		if not date:
			return None

		try:
			if isinstance(date, str):
				for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
					try:
						parsed_date = datetime.strptime(date, fmt)
						return parsed_date.strftime("%Y-%m-%d")
					except ValueError:
						continue
				return date

			if hasattr(date, "strftime"):
				return date.strftime("%Y-%m-%d")

			return str(date)

		except Exception as e:
			frappe.logger().error(f"Error formatting date {date} (type: {type(date)}): {e!s}")
			return str(date) if date else None

	def _get_item_tax_rate(self, item) -> float | None:
		# Get the tax rate for an item from the item tax template and the taxes table
		if item.item_tax_template:
			tax_template = frappe.get_doc("Item Tax Template", item.item_tax_template)
			applicable_accounts = [tax.account_head for tax in self.invoice.taxes if tax.account_head]

			for item_tax in tax_template.taxes:
				if item_tax.tax_type in applicable_accounts:
					return item_tax.tax_rate

		tax_rates = [
			invoice_tax.rate
			for invoice_tax in self.invoice.taxes
			if invoice_tax.charge_type == "On Net Total"
		]
		return tax_rates[0] if len(tax_rates) == 1 else None

	def get_seller_electronic_address(self, company, seller_contact=None) -> dict[str, str] | None:
		# Get seller electronic address
		if company.edocument_electronic_address_scheme and company.edocument_electronic_address:
			scheme_id = frappe.db.get_value(
				"Common Code", company.edocument_electronic_address_scheme, "common_code"
			)
			if scheme_id:
				return {"value": company.edocument_electronic_address, "scheme_id": scheme_id}

		electronic_address = None
		if seller_contact and seller_contact.email_id:
			electronic_address = seller_contact.email_id
		else:
			electronic_address = company.email

		if electronic_address:
			return {"value": electronic_address, "scheme_id": "EM"}

		return None

	def get_buyer_electronic_address(
		self, customer, invoice, buyer_contact=None, buyer_address=None
	) -> dict[str, str] | None:
		# Get buyer electronic address
		if customer.edocument_electronic_address_scheme and customer.edocument_electronic_address:
			scheme_id = frappe.db.get_value(
				"Common Code", customer.edocument_electronic_address_scheme, "common_code"
			)
			if scheme_id:
				return {"value": customer.edocument_electronic_address, "scheme_id": scheme_id}

		electronic_address = None
		if invoice.contact_email:
			electronic_address = invoice.contact_email
		elif buyer_address and buyer_address.email_id:
			electronic_address = buyer_address.email_id

		if electronic_address:
			return {"value": electronic_address, "scheme_id": "EM"}

		return None

	def get_invoice_type_code(self, invoice) -> str:
		# Determine the appropriate PEPPOL invoice type code
		invoice_type_code = "380"

		try:
			if hasattr(invoice, "is_return") and invoice.is_return:
				invoice_type_code = "381"
			elif hasattr(invoice, "amended_from") and invoice.amended_from:
				# 384 (Corrected Invoice) only allowed when both parties are German
				if self._both_parties_german():
					invoice_type_code = "384"
		except Exception:
			pass

		return invoice_type_code

	def _both_parties_german(self) -> bool:
		# Check if both seller and buyer are German organizations
		try:
			seller_code = ""
			if self.seller_address and self.seller_address.country:
				seller_code = (
					frappe.db.get_value("Country", self.seller_address.country, "code") or ""
				).upper()
			buyer_code = ""
			if self.buyer_address and self.buyer_address.country:
				buyer_code = (
					frappe.db.get_value("Country", self.buyer_address.country, "code") or ""
				).upper()
			return seller_code == "DE" and buyer_code == "DE"
		except Exception:
			return False

	def map_unit_code(self, erpnext_unit: str) -> str:
		# Map ERPNext unit codes to PEPPOL standard unit codes using CommonCodeRetriever
		if not erpnext_unit:
			return uom_codes.default_code or "C62"

		return uom_codes.get([("UOM", erpnext_unit)]) or uom_codes.default_code or "C62"

	def get_vat_category_code(self, invoice, item=None, tax=None) -> str:
		# Get VAT category code using CommonCodeRetriever
		lookup_records = []

		if item:
			lookup_records.extend(
				[
					("Item", getattr(item, "item_code", None)),
					("Item Tax Template", getattr(item, "item_tax_template", None)),
					("Account", getattr(item, "income_account", None)),
				]
			)

		if tax:
			# For tax-level VAT category (BT-118)
			lookup_records.extend(
				[
					("Account", getattr(tax, "account_head", None)),
				]
			)

		lookup_records.extend(
			[
				("Tax Category", getattr(invoice, "tax_category", None)),
				("Sales Taxes and Charges Template", getattr(invoice, "taxes_and_charges", None)),
			]
		)

		lookup_records = [(doctype, name) for doctype, name in lookup_records if name]

		# Check for explicit mapping only; fallback logic handles defaults below
		category_code = duty_tax_fee_category_codes.get_code(lookup_records)

		if category_code:
			return category_code

		# Auto-detect Z (zero-rated) for 0% rates when no explicit mapping exists
		tax_rate = None
		if item:
			tax_rate = self._get_item_tax_rate(item)
		elif tax:
			tax_rate = getattr(tax, "rate", None)

		# 0% VAT line exists → Zero-rated (safe assumption, doesn't require exemption text)
		if tax_rate is not None and flt(tax_rate) == 0:
			return "Z"

		# Default to S (standard) for everything else
		return duty_tax_fee_category_codes.default_code or "S"

	def _get_exemption_reason_code(self, category_code: str) -> str:
		"""Get VATEX exemption reason code for PEPPOL validation.

		Returns the standardized VATEX code for non-standard VAT categories.
		"""
		return VATEX_CODES.get(category_code, "")

	def _get_exemption_reason_text(self, category_code: str) -> str:
		"""Get exemption reason text for PEPPOL validation.

		Categories E, AE, G, O, K require either TaxExemptionReasonCode or TaxExemptionReason
		per PEPPOL BIS business rules (BR-E-10, BR-AE-10, BR-G-10, BR-O-10, BR-IC-10).
		"""
		return VATEX_REASON_TEXTS.get(category_code, "")

	def get_xml_bytes(self) -> bytes:
		# Return the XML as bytes
		if not self.xml_bytes:
			raise ValueError("No XML generated. Call create_einvoice() first.")
		return self.xml_bytes


def generate_peppol_xml(source_doc, edocument_profile):
	"""
	Generate PEPPOL XML from source document.

	This function matches the EDocument generator interface:
	- Takes (source_doc, edocument_profile) as parameters
	- Returns bytes (XML content)

	Args:
		source_doc: The source document (e.g., Sales Invoice, Purchase Invoice)
		edocument_profile: The EDocument Profile document

	Returns:
		bytes: The generated PEPPOL XML as bytes
	"""
	# Validate that source document is a Sales Invoice
	if source_doc.doctype != "Sales Invoice":
		frappe.throw(f"PEPPOL generator only supports Sales Invoice, got {source_doc.doctype}")

	# Initialize PEPPOL generator
	generator = PEPPOLGenerator(source_doc)

	# Create the PEPPOL XML document
	generator.create_einvoice()

	# Return XML as bytes
	return generator.get_xml_bytes()
