# Copyright (c) 2025, Prilk Consulting BV and Contributors
# See license.txt

# import frappe
try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase


class TestEDocument(TestCase):
	"""
	Integration tests for EDocument.
	Use this class for testing interactions between multiple components.
	"""

	pass
