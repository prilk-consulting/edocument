## EDocument

Create and import PEPPOL-compliant e-documents with ERPNext.

This app provides a flexible framework for generating and parsing electronic documents, with full support for **PEPPOL BIS Billing 3.0** using UBL 2.1 XML format.

### Features

- **PEPPOL BIS Billing 3.0 Support**: Full implementation of PEPPOL BIS Billing 3.0 specification
- **UBL 2.1 XML Generation**: Generate compliant UBL 2.1 XML for invoices and credit notes
- **Multiple Document Types**: Support for Invoice and CreditNote
- **XML Validation**: XSD schema validation and Schematron business rule validation
- **Code List Management**: Automatic code list handling for PEPPOL standards
- **Profile-Based Architecture**: Extensible profile system for different e-document standards
- **Import/Export**: Import incoming PEPPOL invoices and export outgoing invoices

---

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/prilk-consulting/edocument --branch develop
bench install-app edocument
```

Please use a branch that matches the major version of ERPNext you are using. For example, `version-15` or `version-16`. If you are a developer contributing new features, you'll want to use the `develop` branch instead.

## Dependencies

This app requires the following Python packages (automatically installed):

- **saxonche** (~=12.5.0): XSLT 3.0 processor for Schematron validation
- **lxml** (>=4.9.3,<6.0.0): XML parsing and XSD validation

These dependencies are specified in `pyproject.toml` and will be installed automatically when you install the app.

## Setup

### Code Lists

E-documents rely on common codes that describe the content of the document. E.g. "C62" is used for the UOM "One" and "ZZZ" is used for a mutually agreed mode of payment.

Common codes are part of a code list. You'll need to import the code lists and map the codes you need to the corresponding ERPNext entities. Please use the "Import Genericode" button in **Code List** and paste the URL linked below.  

Code List | Mapped DocType | Default Value
----------|----------------|--------------
[UNTDID 4461 Payment means code](https://www.xrepository.de/api/xrepository/urn:xoev-de:xrechnung:codeliste:untdid.4461_3:technischerBestandteilGenericode) | Payment Terms Template, Mode of Payment | ZZZ
[Codes for Units of Measure Used in International Trade](https://www.xrepository.de/api/xrepository/urn:xoev-de:kosit:codeliste:rec20_3:technischerBestandteilGenericode) | UOM | C62
[Codes for Duty Tax and Fee Categories](https://www.xrepository.de/api/xrepository/urn:xoev-de:kosit:codeliste:untdid.5305_3:technischerBestandteilGenericode) | Item Tax Template, Account, Tax Category, Sales Taxes and Charges Template | S
[Electronic Address Scheme](https://www.xrepository.de/api/xrepository/urn:xoev-de:kosit:codeliste:eas_5:technischerBestandteilGenericode) | Company, Customer, Supplier | EM

For example, let's say your standard **Payment Terms Template** is "Bank Transfer, 30 days". You'll need to find the suitable **Common Code** for bank transfers within the **Code List** "UNTDID.4461". In this case, the code is "58". Then you add a row to the _Applies To_ table, select "Payment Terms Template" as the _Link Document Type_ and "Bank Transfer, 30 days" as the _Link Name_. If you now create an Invoice with this **Payment Terms Template**, the e-document will contain the code "58" for the payment means.

The retrieval of codes goes from the most specific to the most general. E.g. for determining the VAT type of a line item, we first look for a code using the specific item's _Item Tax Template_ and _Income Account_, then fall back to the code for the invoice's _Tax Category_ or _Sales Taxes and Charges Template_.

### PEPPOL Code Lists

For PEPPOL profiles, additional code lists are required. These can be imported using the "Import Genericode" button in **Code List**:

Code List | Purpose
----------|--------
PEPPOL Payment Means Code | Payment methods for PEPPOL invoices
PEPPOL Unit of Measure Code | Units of measure for PEPPOL line items
PEPPOL Tax Category Code | Tax categories for PEPPOL invoices
PEPPOL Country Code | Country codes for addresses
PEPPOL Electronic Address Identifier Scheme | Electronic address schemes for PEPPOL participants

These code lists are automatically set up when you install the app. You can verify and update mappings in the **Code List** doctype.

The PEPPOL code lists are sourced from the [PEPPOL BIS Billing 3.0 repository](https://github.com/OpenPEPPOL/peppol-bis-invoice-3/tree/master/structure/codelist) and are included in the app's `edocument/profiles/peppol/peppol-bis-invoice-3/structure/codelist/` folder.

The UBL 2.1 XSD schemas are sourced from the [OASIS UBL 2.1 specification](http://docs.oasis-open.org/ubl/UBL-2.1.html) and are included in the app's `edocument/profiles/peppol/UBL-2.1/xsd/` folder.

### Electronic Address

If you send your invoice via PEPPOL, you might need to specify your and your customer's electronic addresses. This is done by setting the _Electronic Address Scheme_ and _Electronic Address_ fields in the **Company**, **Customer** and **Supplier** master data.

Please make sure to import the **Electronic Address Scheme** code list first.

If not specified, email addresses are used as electronic addresses for outgoing invoices. For the Customer, we use the _Contact Email_ or _Buyer Address_ > _Email ID_. For the Company, we use the _Seller Contact_ > _Email ID_ or _Company_ > _Email_.

### Bank Details

If you want your e-document to contain bank details, you need to set up a **Mode of Payment** of type "Bank", link the company's corresponding **Account** and create a **Bank Account** for the same account with IBAN and BIC (SWIFT number).

Then, you can map a **Common Code** from **Code List** "UNTDID.4461", e.g. "Credit Transfer" (30) or "SEPA Credit Transfer" (58), to the **Mode of Payment**.

Please note that the e-document standard only supports one payment means per invoice, so you should not specify multiple **Modes of Payment** in the same invoice.

## Usage

### EDocument Profile

Before using the app, you need to create an **EDocument Profile** that defines which profile to use (e.g., PEPPOL) and the generator/parser paths.

1. Go to **EDocument Profile** doctype
2. Create a new profile (e.g., "PEPPOL")
3. Set the profile identifier values:
   - **Identifier Namespace**: `urn:oasis:names:specification:ubl:schema:xsd:Invoice-2`
   - **Identifier Element Name**: `CustomizationID`
   - **Identifier Value**: `urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0`
4. Set the generator and parser paths:
   - **Generator Path**: `edocument.edocument.profiles.peppol.generator.create_peppol_xml`
   - **Parser Path**: `edocument.edocument.profiles.peppol.parser.parse_peppol_xml`
   - **Validator Path**: `edocument.edocument.profiles.peppol.validator.validate_peppol_xml`

### Sales Invoice

To create an outgoing e-document, you need to create an **EDocument** record:

1. Go to **EDocument** doctype
2. Create a new document
3. Set the **Source Type** (e.g., "Sales Invoice")
4. Set the **Source Document** (the Sales Invoice name)
5. Select the **EDocument Profile** (e.g., "PEPPOL")
6. Click **Generate XML** - this will create the PEPPOL XML and attach it to the document
7. The XML is automatically validated against XSD and Schematron rules
8. Click **Validate XML** - this will validate the PEPPOL XML.

The following fields of the **Sales Invoice** are currently considered for the e-document:

- Invoice type (credit note, corrected invoice, commercial invoice)
- Invoice number
- Invoice date
- Due date (only for invoices, not credit notes)
- Currency
- Company information (name, address, tax ID, electronic address)
- Customer information (name, address, tax ID, electronic address)
- Items (name, description, quantity, rate, net amount, tax rate)
- Taxes (rate, amount, taxable amount)
- Payment means (bank account with IBAN and BIC)
- Payment terms
- Totals (line extension amount, tax exclusive amount, tax inclusive amount, payable amount)
- Document-level discounts and allowances

### Credit Notes

Credit notes are automatically detected when a Sales Invoice has `is_return = 1`. The app will:

- Use `CreditNote` as the root XML element (instead of `Invoice`)
- Use `CreditNoteTypeCode` instead of `InvoiceTypeCode`
- Use `CreditNoteLine` instead of `InvoiceLine`
- Exclude `DueDate` (credit notes don't have due dates)
- Include `BillingReference` to reference the original invoice
- Use the CreditNote XSD schema for validation

### Purchase Invoice (Import)

To import an incoming e-document:

1. Go to **EDocument** doctype
2. Create a new document
3. Upload the XML file
4. The app will automatically:
   - Detect the document type (Invoice, CreditNote, etc.)
   - Detect the profile (PEPPOL)
   - Validate the XML against XSD and Schematron rules
   - Parse the XML and create a Purchase Invoice

The following fields are imported from the e-document:

- Invoice ID
- Issue Date
- Currency
- Seller (Supplier) information
- Buyer (Company) information
- Items (product name, description, quantity, rate, tax rate)
- Taxes (basis amount, rate, calculated amount)
- Payment terms
- Payment means (IBAN, BIC)
- Monetary totals

## Validation

The app performs comprehensive validation of generated and imported XML:

1. **XML Syntax Validation**: Ensures the XML is well-formed
2. **XSD Validation**: Validates the XML against the UBL 2.1 XSD schema (Invoice or CreditNote)
3. **Schematron Validation**: Validates business rules using PEPPOL Schematron files

Validation results are displayed in the **EDocument** record:
- **Status**: Valid/Invalid
- **Error**: Any validation errors
- **Warnings**: Any validation warnings

### External Validation

For PEPPOL invoices (UBL 2.1), you can use the [PEPPOL Validation Service](https://peppol.helger.com/public/locale-en_US/menuitem-validation) or your PEPPOL service provider's validation tools.

## Architecture

The app follows a modular, profile-based architecture:

### Core Components

- **`generator.py`**: Converts ERPNext invoice data to UBL 2.1 XML
- **`parser.py`**: Parses UBL 2.1 XML and creates ERPNext documents
- **`validator.py`**: XSD and Schematron validation
- **`profiles/`**: Profile-specific implementations (PEPPOL, etc.)

### Profile System

The app uses a profile-based system that allows different e-document standards to be implemented:

- **PEPPOL Profile**: Full PEPPOL BIS Billing 3.0 implementation
- **Extensible**: Easy to add new profiles (e.g., country-specific CIUS)

Each profile defines:
- Generator function (creates XML from ERPNext data)
- Parser function (creates ERPNext data from XML)
- Validator function (validates XML)
- Profile identifier (for automatic detection)

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/edocument
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## License

Copyright (C) 2025 Prilk Consulting BV

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
