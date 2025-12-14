# Copyright (c) 2025, Prilk Consulting BV and contributors
"""
PEPPOL Code List Setup Script

This script imports PEPPOL standardized code lists into ERPNext and creates mappings
between ERPNext objects and PEPPOL codes.

"""

from pathlib import Path

import frappe
from lxml import etree


@frappe.whitelist()
def setup_peppol_codes():
	"""Main function to set up PEPPOL code lists."""

	frappe.logger().info("Starting PEPPOL code list setup...")

	# Import all PEPPOL code lists
	import_peppol_code_lists()

	# Create mappings between ERPNext objects and codes
	create_erpnext_mappings()

	frappe.logger().info("PEPPOL code list setup completed!")

	# Debug output
	code_lists = frappe.get_all("Code List", fields=["name", "title"])
	common_codes_count = frappe.db.count("Common Code")

	frappe.logger().info(f"Created {len(code_lists)} Code Lists:")
	for cl in code_lists:
		frappe.logger().info(f"  - {cl.name}: {cl.title}")

	frappe.logger().info(f"Created {common_codes_count} Common Code documents")


def import_peppol_code_lists():
	"""Import PEPPOL code lists from XML files."""

	# PEPPOL code list configurations with default codes
	code_list_configs = {
		"urn:peppol:id:codelist:UNCL5305": {
			"title": "Duty or tax or fee category code (UNCL5305)",
			"xml_file": "UNCL5305.xml",
			"default_code": "S",  # Standard rated
			"doctype_mappings": [
				("Item Tax Template", "item_tax_template"),
				("Account", "income_account"),
				("Tax Category", "tax_category"),
				("Sales Taxes and Charges Template", "taxes_and_charges"),
			],
		},
		"urn:peppol:id:codelist:UNECERec20": {
			"title": "Recommendation 20, including Recommendation 21 codes (UN/ECE)",
			"xml_file": "UNECERec20-11e.xml",
			"default_code": "C62",  # Piece
			"doctype_mappings": [("UOM", "uom")],
		},
		"urn:peppol:id:codelist:UNCL4461": {
			"title": "Payment means code (UNCL4461)",
			"xml_file": "UNCL4461.xml",
			"default_code": "30",  # Credit transfer (most common)
			"doctype_mappings": [("Mode of Payment", "mode_of_payment")],
		},
		"urn:peppol:id:codelist:ISO3166-1_Alpha2": {
			"title": "Country codes (ISO 3166-1 alpha-2)",
			"xml_file": "ISO3166-1_Alpha2.xml",
			"default_code": "DE",  # Germany (common in EU)
			"doctype_mappings": [("Country", "country")],
		},
		"urn:peppol:id:codelist:ISO4217": {
			"title": "Currency codes (ISO 4217)",
			"xml_file": "ISO4217_2015.xml",
			"default_code": "EUR",  # Euro (common in EU)
			"doctype_mappings": [("Currency", "currency")],
		},
		"urn:peppol:id:codelist:eas": {
			"title": "Electronic Address Scheme (EAS)",
			"xml_file": "eas.xml",
			"default_code": "EM",  # Email (most common)
			"doctype_mappings": [("Electronic Address Scheme", "electronic_address_scheme")],
		},
	}

	codelist_dir = Path(__file__).parent / "peppol-bis-invoice-3" / "structure" / "codelist"

	for canonical_uri, config in code_list_configs.items():
		xml_file_path = codelist_dir / config["xml_file"]

		if not xml_file_path.exists():
			frappe.logger().warning(f"Code list XML file not found: {xml_file_path}")
			continue

		try:
			frappe.logger().info(f"Processing code list: {canonical_uri}")

			# Create or update Code List
			code_list_name = create_or_update_code_list(canonical_uri, config, xml_file_path)
			frappe.logger().info(f"Created code list: {code_list_name}")

			# Clean up existing common codes for this code list (delete and recreate)
			cleanup_existing_common_codes(code_list_name)
			frappe.logger().info(f"Cleaned up existing common codes for {canonical_uri}")

			# Import codes from XML
			imported_count = import_codes_from_xml(code_list_name, xml_file_path, config["doctype_mappings"])
			frappe.logger().info(f"Imported {imported_count} codes for {canonical_uri}")

			# Set the default common code for this code list
			set_default_common_code(code_list_name, config["default_code"])
			frappe.logger().info(f"Set default code for {canonical_uri}")

			frappe.logger().info(f"Successfully imported code list: {canonical_uri}")

		except Exception as e:
			frappe.logger().error(f"Failed to import code list {canonical_uri}: {e!s}")
			import traceback

			frappe.logger().error(traceback.format_exc())


def create_or_update_code_list(canonical_uri, config, xml_file_path):
	"""Create or update a Code List document."""

	try:
		tree = etree.parse(str(xml_file_path))
		root = tree.getroot()

		# Extract metadata from XML
		title = root.find(".//Title").text if root.find(".//Title") is not None else config["title"]
		version = root.find(".//Version").text if root.find(".//Version") is not None else "1.0"
		agency = root.find(".//Agency").text if root.find(".//Agency") is not None else "PEPPOL"

		code_list_name = canonical_uri

		if frappe.db.exists("Code List", code_list_name):
			code_list = frappe.get_doc("Code List", code_list_name)
		else:
			code_list = frappe.new_doc("Code List")
			code_list.name = code_list_name

		code_list.title = title
		code_list.canonical_uri = canonical_uri
		code_list.version = version
		code_list.publisher = agency
		code_list.description = f"PEPPOL code list: {title}"

		code_list.save()
		frappe.db.commit()

		return code_list_name

	except Exception as e:
		frappe.logger().error(f"Failed to create/update code list {canonical_uri}: {e!s}")
		return None


def import_codes_from_xml(code_list_name, xml_file_path, doctype_mappings):
	"""Import codes from XML file into Common Code documents."""

	try:
		frappe.logger().info(f"Importing codes from {xml_file_path} for {code_list_name}")

		tree = etree.parse(str(xml_file_path))
		root = tree.getroot()

		# Handle namespace - PEPPOL XML uses default namespace
		if root.tag.startswith("{"):
			# XML has default namespace - use full namespace URI
			ns_uri = "urn:fdc:difi.no:2017:vefa:structure:CodeList-1"
			codes = root.findall(f".//{{{ns_uri}}}Code")
		else:
			# XML without namespace
			codes = root.findall(".//Code")

		frappe.logger().info(f"Found {len(codes)} codes in XML file")

		imported_count = 0

		for code_elem in codes:
			# Handle namespace for child elements
			if root.tag.startswith("{"):
				ns_uri = "urn:fdc:difi.no:2017:vefa:structure:CodeList-1"
				code_id = (
					code_elem.find(f"{{{ns_uri}}}Id").text
					if code_elem.find(f"{{{ns_uri}}}Id") is not None
					else None
				)
				code_name = (
					code_elem.find(f"{{{ns_uri}}}Name").text
					if code_elem.find(f"{{{ns_uri}}}Name") is not None
					else ""
				)
				code_desc = (
					code_elem.find(f"{{{ns_uri}}}Description").text
					if code_elem.find(f"{{{ns_uri}}}Description") is not None
					else ""
				)
			else:
				code_id = code_elem.find("Id").text if code_elem.find("Id") is not None else None
				code_name = code_elem.find("Name").text if code_elem.find("Name") is not None else ""
				code_desc = (
					code_elem.find("Description").text if code_elem.find("Description") is not None else ""
				)

			if not code_id:
				continue

			common_code_name = f"{code_list_name}-{code_id}"

			try:
				frappe.logger().info(f"Processing code: {code_id} - {code_name}")

				if frappe.db.exists("Common Code", common_code_name):
					common_code = frappe.get_doc("Common Code", common_code_name)
					frappe.logger().info(f"Updating existing common code: {common_code_name}")
				else:
					common_code = frappe.new_doc("Common Code")
					common_code.name = common_code_name
					frappe.logger().info(f"Creating new common code: {common_code_name}")

				common_code.code_list = code_list_name
				common_code.title = f"{code_id} - {code_name}"
				common_code.common_code = code_id
				common_code.description = code_desc

				# Skip applies_to setup for now to avoid Dynamic Link issues
				# This can be set up manually or through a separate process
				common_code.save()
				frappe.logger().info(f"Successfully saved common code: {common_code_name}")
				imported_count += 1

			except Exception as e:
				frappe.logger().error(f"Failed to save common code {common_code_name}: {e!s}")
				import traceback

				frappe.logger().error(traceback.format_exc())
				continue

		frappe.db.commit()
		frappe.logger().info(f"Successfully imported {imported_count} codes from {xml_file_path.name}")

		return imported_count

	except Exception as e:
		frappe.logger().error(f"Failed to import codes from {xml_file_path}: {e!s}")
		return 0


def cleanup_existing_common_codes(code_list_name):
	"""Delete all existing common codes for a code list to ensure clean state."""

	try:
		# Find all Common Code documents for this code list
		common_codes = frappe.get_all("Common Code", filters={"code_list": code_list_name}, fields=["name"])

		deleted_count = 0
		for common_code in common_codes:
			try:
				frappe.delete_doc("Common Code", common_code.name, force=True)
				deleted_count += 1
			except Exception as e:
				frappe.logger().warning(f"Failed to delete common code {common_code.name}: {e!s}")

		frappe.db.commit()
		frappe.logger().info(
			f"Cleaned up {deleted_count} existing common codes for code list '{code_list_name}'"
		)

	except Exception as e:
		frappe.logger().error(f"Failed to cleanup common codes for {code_list_name}: {e!s}")


def set_default_common_code(code_list_name, default_code_value):
	"""Set the default common code for a code list."""

	try:
		# Find the Common Code document with the default code value
		common_codes = frappe.get_all(
			"Common Code",
			filters={"code_list": code_list_name, "common_code": default_code_value},
			fields=["name"],
		)

		if not common_codes:
			frappe.logger().warning(
				f"Default common code '{default_code_value}' not found in code list '{code_list_name}'"
			)
			return

		default_common_code_name = common_codes[0].name

		# Update the Code List to set the default common code
		code_list = frappe.get_doc("Code List", code_list_name)
		code_list.default_common_code = default_common_code_name
		code_list.save()

		frappe.logger().info(
			f"Set default common code '{default_code_value}' for code list '{code_list_name}'"
		)

	except Exception as e:
		frappe.logger().error(f"Failed to set default common code for {code_list_name}: {e!s}")


def cleanup_existing_mappings():
	"""Clean up existing mappings to avoid conflicts during recreation."""

	try:
		# Get all code lists that we're working with
		code_lists = [
			"urn:peppol:id:codelist:ISO4217",
			"urn:peppol:id:codelist:ISO3166-1_Alpha2",
			"urn:peppol:id:codelist:UNECERec20",
			"urn:peppol:id:codelist:UNCL4461",
			"urn:peppol:id:codelist:eas",
		]

		cleanup_count = 0
		for code_list_uri in code_lists:
			try:
				# Find all Common Code documents for this code list
				common_codes = frappe.get_all(
					"Common Code", filters={"code_list": code_list_uri}, fields=["name"]
				)

				for common_code_doc in common_codes:
					common_code = frappe.get_doc("Common Code", common_code_doc.name)
					# Clear all applies_to mappings
					if hasattr(common_code, "applies_to") and common_code.applies_to:
						common_code.applies_to = []
						common_code.save()
						cleanup_count += 1

			except Exception as e:
				frappe.logger().warning(f"Error cleaning mappings for {code_list_uri}: {e!s}")

		frappe.db.commit()
		frappe.logger().info(f"Cleaned up mappings for {cleanup_count} common codes")

	except Exception as e:
		frappe.logger().error(f"Failed to cleanup existing mappings: {e!s}")


def create_erpnext_mappings():
	"""Create mappings between common ERPNext objects and PEPPOL codes."""

	frappe.logger().info("Creating ERPNext to PEPPOL code mappings...")

	# Clean up existing mappings first to avoid conflicts
	cleanup_existing_mappings()
	frappe.logger().info("Cleaned up existing mappings")

	# Country mappings
	country_mappings = [
		("Germany", "DE"),
		("France", "FR"),
		("United Kingdom", "GB"),
		("Italy", "IT"),
		("Spain", "ES"),
		("Netherlands", "NL"),
		("Belgium", "BE"),
		("Austria", "AT"),
		("Switzerland", "CH"),
	]

	for country_name, country_code in country_mappings:
		create_mapping("urn:peppol:id:codelist:ISO3166-1_Alpha2", country_code, "Country", country_name)

	# Currency mappings
	currency_mappings = [
		("EUR", "EUR"),
		("USD", "USD"),
		("GBP", "GBP"),
		("CHF", "CHF"),
	]

	for currency_name, currency_code in currency_mappings:
		create_mapping("urn:peppol:id:codelist:ISO4217", currency_code, "Currency", currency_name)

	# UOM mappings
	uom_mappings = [
		("Nos", "C62"),
		("Pcs", "C62"),
		("Piece", "C62"),
		("Unit", "C62"),
		("Each", "C62"),
		("Kg", "KGM"),
		("kg", "KGM"),
		("Gm", "GRM"),
		("gm", "GRM"),
		("Ltr", "LTR"),
		("ltr", "LTR"),
		("Mtr", "MTR"),
		("mtr", "MTR"),
		("Cm", "CMT"),
		("cm", "CMT"),
		("Mm", "MMT"),
		("mm", "MMT"),
		("Hr", "HUR"),
		("hr", "HUR"),
		("Day", "DAY"),
		("day", "DAY"),
		("Month", "MON"),
		("month", "MON"),
		("Year", "ANN"),
		("year", "ANN"),
		("Box", "XBX"),
		("box", "XBX"),
		("Pack", "XPK"),
		("pack", "XPK"),
		("Set", "SET"),
		("set", "SET"),
		("Pair", "PR"),
		("pair", "PR"),
		("Dozen", "DZN"),
		("dozen", "DZN"),
		("Gross", "GRO"),
		("gross", "GRO"),
	]

	for uom_name, uom_code in uom_mappings:
		create_mapping("urn:peppol:id:codelist:UNECERec20", uom_code, "UOM", uom_name)

	# Payment means mappings (common ones)
	payment_mappings = [
		("Cash", "10"),
		("Credit Transfer", "30"),
		("SEPA Credit Transfer", "58"),
		("Card Payment", "48"),
	]

	for payment_name, payment_code in payment_mappings:
		create_mapping("urn:peppol:id:codelist:UNCL4461", payment_code, "Mode of Payment", payment_name)

	# EAS (Electronic Address Scheme) mappings to countries
	eas_mappings = [
		# VAT Number schemes (corrected)
		("Austria", "9914"),  # Austrian VAT number
		("Belgium", "9925"),  # Belgium VAT number
		("Bulgaria", "9926"),  # Bulgaria VAT number
		("Croatia", "9934"),  # Croatia VAT number
		("Cyprus", "9928"),  # Cyprus VAT number
		("Czech Republic", "9929"),  # Czech Republic VAT number
		("Estonia", "9931"),  # Estonia VAT number
		("France", "9957"),  # French VAT number
		("Germany", "9930"),  # Germany VAT number
		("Greece", "9933"),  # Greece VAT number
		("Hungary", "9910"),  # Hungary VAT number
		("Ireland", "9935"),  # Ireland VAT number
		("Lithuania", "9937"),  # Lithuania VAT number
		("Luxembourg", "9938"),  # Luxembourg VAT number
		("Malta", "9943"),  # Malta VAT number
		("Netherlands", "9944"),  # Netherlands VAT number
		("Poland", "9945"),  # Poland VAT number
		("Portugal", "9946"),  # Portugal VAT number
		("Romania", "9947"),  # Romania VAT number
		("Slovenia", "9949"),  # Slovenia VAT number
		("Slovakia", "9950"),  # Slovakia VAT number
		("United Kingdom", "9932"),  # United Kingdom VAT number
		# Country-specific identifier schemes
		("Belgium", "0208"),  # Belgian Enterprise Number
		("Netherlands", "0106"),  # Dutch Chamber of Commerce (KVK)
		("Sweden", "0007"),  # Swedish Organization Number
		("Finland", "0037"),  # Finnish Business ID (LY-tunnus)
		("Denmark", "0096"),  # Danish Chamber of Commerce
		("Norway", "0192"),  # Norwegian Organization Number
		("Switzerland", "0183"),  # Swiss UID
		("Global", "0088"),  # GLN (Global Location Number)
		("Email", "EM"),  # Email (most common fallback)
	]

	for country_name, eas_code in eas_mappings:
		create_mapping("urn:peppol:id:codelist:eas", eas_code, "Country", country_name)

	frappe.logger().info("ERPNext mappings created successfully")


def create_mapping(code_list_uri, code_value, doctype, docname):
	"""Create a mapping between an ERPNext object and a PEPPOL code."""

	try:
		# Find the Common Code
		common_codes = frappe.get_all(
			"Common Code", filters={"code_list": code_list_uri, "common_code": code_value}, fields=["name"]
		)

		if not common_codes:
			frappe.logger().warning(f"Common Code not found: {code_list_uri} - {code_value}")
			return

		common_code = frappe.get_doc("Common Code", common_codes[0].name)

		# Check if mapping already exists
		existing_links = [
			link.link_name
			for link in common_code.get("applies_to", [])
			if link.link_doctype == doctype and link.link_name == docname
		]

		if existing_links:
			return  # Already mapped

		# Add the mapping
		common_code.append(
			"applies_to", {"doctype": "Dynamic Link", "link_doctype": doctype, "link_name": docname}
		)

		common_code.save()
		frappe.logger().info(f"Mapped {doctype}:{docname} to {code_list_uri}:{code_value}")

	except Exception as e:
		frappe.logger().error(f"Failed to create mapping {doctype}:{docname} -> {code_value}: {e!s}")


# For bench execute compatibility
def execute():
	"""Entry point for bench execute command."""
	setup_peppol_codes()


if __name__ == "__main__":
	setup_peppol_codes()
