# Copyright (c) 2025, Prilk Consulting BV and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe

from edocument.edocument.doctype.edocument.edocument import create_document
from edocument.edocument.profiles.peppol.preview import preview_peppol_xml
from edocument.edocument.profiles.peppol.setup_peppol_codes import setup_peppol_codes
from edocument.edocument.validator import reject_doctype

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

PLAIN_XML = b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>'
ENTITY_XML = b"""<?xml version="1.0"?>
<!DOCTYPE Invoice [<!ENTITY e SYSTEM "file:///etc/hosts">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&e;</Invoice>"""


class TestXmlDoctype(TestCase):
	def test_doctype_is_rejected(self):
		self.assertRaises(frappe.ValidationError, reject_doctype, ENTITY_XML)

	def test_plain_xml_is_accepted(self):
		reject_doctype(PLAIN_XML)

	def test_preview_rejects_external_entities(self):
		self.assertRaises(frappe.ValidationError, preview_peppol_xml, ENTITY_XML, None)


class TestPermissions(TestCase):
	def setUp(self):
		self.edocument = frappe.get_doc({"doctype": "EDocument", "direction": "Outgoing"}).insert(
			ignore_permissions=True
		)

	def test_create_document_needs_read_permission(self):
		with self.set_user("Guest"):
			self.assertRaises(frappe.PermissionError, create_document, self.edocument.name)

	def test_setup_peppol_codes_needs_system_manager(self):
		with self.set_user("Guest"):
			self.assertRaises(frappe.PermissionError, setup_peppol_codes)

	def test_generated_xml_is_private(self):
		self.edocument.edocument_source_type = "Sales Invoice"
		self.edocument.edocument_source_document = "SINV-TEST-PRIVATE"
		self.edocument.edocument_profile = "Test Profile"
		with (
			patch.object(frappe, "get_doc", return_value=MagicMock()) as get_doc,
			patch("edocument.edocument.generator.get_xml_generator", return_value=PLAIN_XML),
		):
			self.edocument._generate_xml_internal()

		file_values = next(call.args[0] for call in get_doc.call_args_list if isinstance(call.args[0], dict))
		self.assertEqual(file_values["doctype"], "File")
		self.assertEqual(file_values["is_private"], 1)
