# Copyright (c) 2025, Prilk Consulting BV and Contributors
# See license.txt

from types import SimpleNamespace

import frappe
from frappe.utils.data import flt
from lxml import etree as ET

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

from edocument.edocument.profiles.peppol import UBL_NAMESPACES
from edocument.edocument.profiles.peppol.generator import PEPPOLGenerator

CBC = UBL_NAMESPACES["cbc"]
CAC = UBL_NAMESPACES["cac"]


def _build_legal_monetary_total(invoice, document_type="Invoice"):
	"""Run PEPPOLGenerator._set_totals against a stand-in invoice and return the
	LegalMonetaryTotal element. __init__ is bypassed because it loads related
	addresses/contacts from the database, which _set_totals does not need."""
	generator = PEPPOLGenerator.__new__(PEPPOLGenerator)
	generator.invoice = invoice
	generator.document_type = document_type
	generator.root = ET.Element("Root")
	generator._set_totals()
	return generator.root.find(f"{{{CAC}}}LegalMonetaryTotal")


def _amount(legal_total, tag):
	element = legal_total.find(f"{{{CBC}}}{tag}")
	return flt(element.text, 2) if element is not None else None


class TestLegalMonetaryTotals(TestCase):
	"""TaxInclusiveAmount (BT-112) is derived as TaxExclusive + total VAT rather than read from
	grand_total, and a PayableRoundingAmount (BT-114) carries the residual, so the totals satisfy:

	- BR-CO-15: TaxInclusiveAmount = TaxExclusiveAmount + total VAT
	- BR-CO-16: PayableAmount = TaxInclusiveAmount - PrepaidAmount + PayableRoundingAmount
	"""

	def _invoice(self, *, net, tax=0.0, grand, rounded, outstanding, total=None, taxes=None):
		return frappe._dict(
			total=net if total is None else total,
			net_total=net,
			grand_total=grand,
			rounded_total=rounded,
			outstanding_amount=outstanding,
			total_taxes_and_charges=tax,
			currency="EUR",
			taxes=taxes or [],
		)

	def _assert_calculation_rules(self, legal_total, *, tax):
		tax_exclusive = _amount(legal_total, "TaxExclusiveAmount")
		# BR-CO-15
		self.assertEqual(_amount(legal_total, "TaxInclusiveAmount"), flt(tax_exclusive + flt(tax, 2), 2))
		# BR-CO-16
		payable = _amount(legal_total, "PayableAmount")
		tax_inclusive = _amount(legal_total, "TaxInclusiveAmount")
		prepaid = _amount(legal_total, "PrepaidAmount") or 0.0
		rounding = _amount(legal_total, "PayableRoundingAmount") or 0.0
		self.assertEqual(payable, flt(tax_inclusive - prepaid + rounding, 2))

	def test_subcent_tax_inclusive_is_derived(self):
		# The reported regression: net 607.025 + VAT 127.475 (3-decimal). Reading grand_total
		# (734.50) for TaxInclusive while TaxExclusive + VAT rounds to a different cent broke
		# BR-CO-15. Deriving TaxInclusive from the rounded parts keeps it consistent, and
		# PayableAmount still equals the real amount due.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=607.025, tax=127.475, grand=734.50, rounded=734.50, outstanding=734.50)
		)
		self.assertEqual(
			_amount(legal_total, "TaxInclusiveAmount"), flt(flt(607.025, 2) + flt(127.475, 2), 2)
		)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 734.50)
		self._assert_calculation_rules(legal_total, tax=127.475)

	def test_rounded_up_unpaid_invoice(self):
		# Customer owes the rounded total (100.00) while TaxInclusive lands a cent lower; BT-114
		# carries the residual so PayableAmount stays the real amount due.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=99.99, grand=99.99, rounded=100.00, outstanding=100.00)
		)
		self.assertEqual(_amount(legal_total, "TaxInclusiveAmount"), 99.99)
		self.assertEqual(_amount(legal_total, "PayableRoundingAmount"), 0.01)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 100.00)
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PrepaidAmount"))
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_rounded_down_unpaid_invoice(self):
		legal_total = _build_legal_monetary_total(
			self._invoice(net=100.01, grand=100.01, rounded=100.00, outstanding=100.00)
		)
		self.assertEqual(_amount(legal_total, "PayableRoundingAmount"), -0.01)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 100.00)
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_partially_paid_invoice(self):
		# Paid portion is measured against the rounded total due; the remainder still reconciles.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=99.99, grand=99.99, rounded=100.00, outstanding=40.00)
		)
		self.assertEqual(_amount(legal_total, "PrepaidAmount"), 60.00)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 40.00)
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_fully_paid_invoice(self):
		legal_total = _build_legal_monetary_total(
			self._invoice(net=100.00, grand=100.00, rounded=100.00, outstanding=0.0)
		)
		self.assertEqual(_amount(legal_total, "PrepaidAmount"), 100.00)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 0.00)
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PayableRoundingAmount"))
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_no_rounding_omits_rounding_amount(self):
		# grand_total and rounded_total agree and the invoice is unpaid: no prepaid, no rounding.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=100.00, grand=100.00, rounded=100.00, outstanding=100.00)
		)
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PrepaidAmount"))
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PayableRoundingAmount"))
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_disabled_rounded_total_falls_back_to_grand_total(self):
		# Round Off disabled stores rounded_total as 0; the total due falls back to grand_total.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=100.00, grand=100.00, rounded=0.0, outstanding=100.00)
		)
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PrepaidAmount"))
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PayableRoundingAmount"))
		self._assert_calculation_rules(legal_total, tax=0.0)

	def test_credit_note_skips_prepaid_and_rounding(self):
		# Credit notes use grand_total for PayableAmount and emit neither BT-113 nor BT-114.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=-140.0, tax=-29.40, grand=-169.40, rounded=-169.40, outstanding=-169.40),
			document_type="CreditNote",
		)
		self.assertEqual(_amount(legal_total, "TaxInclusiveAmount"), 169.40)
		self.assertEqual(_amount(legal_total, "PayableAmount"), 169.40)
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PrepaidAmount"))
		self.assertIsNone(legal_total.find(f"{{{CBC}}}PayableRoundingAmount"))

	def test_rounding_amount_precedes_payable_amount(self):
		# UBL XSD requires PrepaidAmount, then PayableRoundingAmount, then PayableAmount.
		legal_total = _build_legal_monetary_total(
			self._invoice(net=99.99, grand=99.99, rounded=100.00, outstanding=40.00)
		)
		tags = [ET.QName(child).localname for child in legal_total]
		self.assertLess(tags.index("PrepaidAmount"), tags.index("PayableRoundingAmount"))
		self.assertLess(tags.index("PayableRoundingAmount"), tags.index("PayableAmount"))


class _Item:
	"""Minimal stand-in for a Sales Invoice Item row: _line_extension_amounts only
	reads amount, idx, and precision()."""

	def __init__(self, idx, amount, precision=3):
		self.idx = idx
		self.amount = amount
		self._precision = precision

	def precision(self, fieldname):
		return self._precision


def _line_amounts(items, total, document_type="Invoice"):
	generator = PEPPOLGenerator.__new__(PEPPOLGenerator)
	# SimpleNamespace, not frappe._dict: a _dict's `items` attribute resolves to the built-in
	# dict.items method, shadowing the line list (a real Sales Invoice is a Document, not a dict).
	generator.invoice = SimpleNamespace(total=total, items=items)
	generator.document_type = document_type
	return generator._line_extension_amounts()


class TestLineExtensionReconciliation(TestCase):
	"""The sum of the per-line LineExtensionAmount (BT-131) must equal the document
	LineExtensionAmount (BT-106) with no tolerance (BR-CO-10). On sub-cent (3-decimal)
	lines, rounding each line on its own breaks that; the residual is spread across the
	lines, each moving at most a cent (within PEPPOL-EN16931-R120's +/-0.02 tolerance)."""

	def _assert_reconciles(self, items, total, *, document_type="Invoice"):
		amounts = _line_amounts(items, total, document_type)
		expected_total = abs(flt(total, 2)) if document_type == "CreditNote" else flt(total, 2)
		# BR-CO-10: the rounded sum of the lines equals the document total.
		self.assertEqual(flt(sum(amounts.values()), 2), expected_total)
		# PEPPOL-EN16931-R120: each emitted line stays within 0.02 of its true amount.
		for item in items:
			true_amount = abs(item.amount) if document_type == "CreditNote" else item.amount
			self.assertLessEqual(abs(amounts[item.idx] - true_amount), 0.02)
		return amounts

	def test_two_subcent_lines(self):
		# 10.006 + 10.006: each rounds to 10.01 (sum 20.02) but the document total is 20.01,
		# so one line is nudged down a cent.
		amounts = self._assert_reconciles([_Item(1, 10.006), _Item(2, 10.006)], 20.012)
		self.assertEqual(sorted(amounts.values()), [10.00, 10.01])

	def test_three_subcent_lines(self):
		# 3 x 10.004: each rounds to 10.00 (sum 30.00) but the document total is 30.01,
		# so one line gains a cent.
		amounts = self._assert_reconciles([_Item(1, 10.004), _Item(2, 10.004), _Item(3, 10.004)], 30.012)
		self.assertEqual(sorted(amounts.values()), [10.00, 10.00, 10.01])

	def test_plain_two_decimal_lines_unchanged(self):
		# No sub-cent amounts: nothing to redistribute.
		amounts = self._assert_reconciles([_Item(1, 10.00, precision=2), _Item(2, 20.00, precision=2)], 30.00)
		self.assertEqual(amounts, {1: 10.00, 2: 20.00})

	def test_single_subcent_line_unaffected(self):
		# A lone line already reconciles: round-of-sum is round-of-itself.
		amounts = self._assert_reconciles([_Item(1, 607.025)], 607.025)
		self.assertEqual(amounts, {1: flt(607.025, 2)})

	def test_credit_note_lines_use_absolute_values(self):
		amounts = self._assert_reconciles(
			[_Item(1, -10.006), _Item(2, -10.006)], -20.012, document_type="CreditNote"
		)
		self.assertEqual(sorted(amounts.values()), [10.00, 10.01])

	def test_deduction_line_keeps_sign(self):
		# An invoice deduction line (negative amount) keeps its sign and still reconciles.
		amounts = self._assert_reconciles([_Item(1, 100.005), _Item(2, -10.005)], 90.00)
		self.assertLess(amounts[2], 0)
