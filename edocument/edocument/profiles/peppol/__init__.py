# Copyright (c) 2025, Prilk Consulting BV and contributors
"""
PEPPOL Module

This module provides PEPPOL BIS Billing 3.0 compliant UBL 2.1 XML generation,
validation, and parsing functionality.
"""

# UBL 2.1 standard namespaces (shared constant)
UBL_NAMESPACES = {
	"ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
	"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
	"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}

# PEPPOL BIS Billing 3.0 Constants
PEPPOL_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PEPPOL_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# UBL 2.1 Document Types
# Maps invoice type codes to UBL document types
# UNCL1001 codes: 380=Invoice, 381=Credit Note, 383=Debit Note, 384=Corrected Invoice
DOCUMENT_TYPE_MAPPING = {
	"380": "Invoice",  # Commercial invoice
	"384": "Invoice",  # Corrected invoice (still uses Invoice root)
	"381": "CreditNote",  # Credit note
	"383": "DebitNote",  # Debit note (for future support)
}

# UBL 2.1 Document Type Namespaces
DOCUMENT_TYPE_NAMESPACES = {
	"Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
	"CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
	"DebitNote": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2",
}

# UBL 2.1 Document Type XSD Files
DOCUMENT_TYPE_XSD_FILES = {
	"Invoice": "UBL-Invoice-2.1.xsd",
	"CreditNote": "UBL-CreditNote-2.1.xsd",
	"DebitNote": "UBL-DebitNote-2.1.xsd",
}

# Element names for different document types
DOCUMENT_TYPE_ELEMENTS = {
	"Invoice": {
		"root": "Invoice",
		"type_code": "InvoiceTypeCode",
		"line": "InvoiceLine",
		"quantity": "InvoicedQuantity",
	},
	"CreditNote": {
		"root": "CreditNote",
		"type_code": "CreditNoteTypeCode",
		"line": "CreditNoteLine",
		"quantity": "CreditedQuantity",
	},
	"DebitNote": {
		"root": "DebitNote",
		"type_code": "DebitNoteTypeCode",
		"line": "DebitNoteLine",
		"quantity": "DebitedQuantity",
	},
}

# Global code retrievers for PEPPOL standardized codes (shared across generator and import)
from edocument.edocument.common_codes import CommonCodeRetriever

duty_tax_fee_category_codes = CommonCodeRetriever(["urn:peppol:id:codelist:UNCL5305"], "S")
uom_codes = CommonCodeRetriever(["urn:peppol:id:codelist:UNECERec20"], "C62")
payment_means_codes = CommonCodeRetriever(["urn:peppol:id:codelist:UNCL4461"], "ZZZ")
country_codes = CommonCodeRetriever(["urn:peppol:id:codelist:ISO3166-1_Alpha2"], "DE")
currency_codes = CommonCodeRetriever(["urn:peppol:id:codelist:ISO4217"], "EUR")
electronic_address_schemes = CommonCodeRetriever(["urn:peppol:id:codelist:eas"], "EM")
