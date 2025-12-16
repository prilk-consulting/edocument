from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from edocument.edocument.profiles.peppol.setup_peppol_codes import setup_peppol_codes


def after_install():
	create_custom_fields(get_custom_fields())
	create_peppol_profile()
	setup_peppol_codes()


def get_custom_fields():
	return {
		"Company": [
			{
				"fieldname": "edocument_tab",
				"label": "EDocument",
				"fieldtype": "Tab Break",
				"insert_after": "dashboard_tab",
			},
			{
				"fieldname": "edocument_profile",
				"label": "EDocument Profile",
				"fieldtype": "Link",
				"options": "EDocument Profile",
				"insert_after": "edocument_tab",
			},
			{
				"fieldname": "edocument_electronic_address_scheme",
				"label": "Electronic Address Scheme",
				"fieldtype": "Link",
				"options": "Common Code",
				"insert_after": "edocument_profile",
			},
			{
				"fieldname": "edocument_electronic_address",
				"label": "Electronic Address",
				"fieldtype": "Data",
				"insert_after": "edocument_electronic_address_scheme",
				"depends_on": "edocument_electronic_address_scheme",
			},
		],
		"Customer": [
			{
				"fieldname": "edocument_tab",
				"label": "EDocument",
				"fieldtype": "Tab Break",
				"insert_after": "portal_users",
			},
			{
				"fieldname": "edocument_profile",
				"label": "EDocument Profile",
				"fieldtype": "Link",
				"options": "EDocument Profile",
				"insert_after": "edocument_tab",
			},
			{
				"fieldname": "edocument_electronic_address_scheme",
				"label": "Electronic Address Scheme",
				"fieldtype": "Link",
				"options": "Common Code",
				"insert_after": "edocument_profile",
			},
			{
				"fieldname": "edocument_electronic_address",
				"label": "Electronic Address",
				"fieldtype": "Data",
				"insert_after": "edocument_electronic_address_scheme",
				"depends_on": "edocument_electronic_address_scheme",
			},
		],
		"Supplier": [
			{
				"fieldname": "edocument_tab",
				"label": "EDocument",
				"fieldtype": "Tab Break",
				"insert_after": "portal_users",
			},
			{
				"fieldname": "edocument_profile",
				"label": "EDocument Profile",
				"fieldtype": "Link",
				"options": "EDocument Profile",
				"insert_after": "edocument_tab",
			},
			{
				"fieldname": "edocument_electronic_address_scheme",
				"label": "Electronic Address Scheme",
				"fieldtype": "Link",
				"options": "Common Code",
				"insert_after": "edocument_profile",
			},
			{
				"fieldname": "edocument_electronic_address",
				"label": "Electronic Address",
				"fieldtype": "Data",
				"insert_after": "edocument_electronic_address_scheme",
				"depends_on": "edocument_electronic_address_scheme",
			},
		],
		"Sales Invoice": [
			{
				"fieldname": "edocument_tab",
				"label": "EDocument",
				"fieldtype": "Tab Break",
				"insert_after": "terms",
			},
			{
				"fieldname": "edocument_profile",
				"label": "EDocument Profile",
				"fieldtype": "Link",
				"options": "EDocument Profile",
				"insert_after": "edocument_tab",
				"fetch_from": "customer.edocument_profile",
				"fetch_if_empty": 1,
			},
		],
	}


def create_peppol_profile():
	"""Create PEPPOL EDocument Profile on installation."""
	import frappe

	profile_name = "PEPPOL"

	# Check if profile already exists
	if frappe.db.exists("EDocument Profile", profile_name):
		return

	try:
		profile = frappe.get_doc(
			{
				"doctype": "EDocument Profile",
				"name": profile_name,
				"identifier_namespace": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
				"identifier_element_name": "CustomizationID",
				"identifier_value": "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0",
				"generator_path": "edocument.edocument.profiles.peppol.generator.generate_peppol_xml",
				"parser_path": "edocument.edocument.profiles.peppol.parser.parse_peppol_xml",
				"validator_path": "edocument.edocument.profiles.peppol.validator.validate_peppol_xml",
				"preview_path": "edocument.edocument.profiles.peppol.preview.preview_peppol_xml",
				"validate_sales_invoice_on_save": 0,
				"validate_sales_invoice_on_submit": 0,
				"action_on_validation_error_during_save": 0,
				"action_on_validation_error_during_submit": 0,
			}
		)
		profile.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Error creating PEPPOL profile: {e!s}", "EDocument Installation")
