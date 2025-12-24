# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Detector module for EDocument field detection.
This module routes to profile-specific detectors based on the EDocument Profile.

Detectors extract field values (like company) from incoming XML to populate EDocument records.
"""

import frappe


def get_edocument_fields(xml_bytes, edocument_profile):
	"""
	Get EDocument field values by routing to profile-specific detector.

	The detector is determined by:
	1. Check if edocument_profile has a detector_path field
	2. If not found, return empty dict (no field detection)

	Args:
		xml_bytes: The XML content as bytes
		edocument_profile: The EDocument Profile document or name

	Returns:
		dict: Field values to populate on EDocument (e.g., {"company": "My Company"})
	"""
	# Get profile doc if name was passed
	if isinstance(edocument_profile, str):
		edocument_profile = frappe.get_doc("EDocument Profile", edocument_profile)

	# Try to get detector from profile's detector_path if specified
	if hasattr(edocument_profile, "detector_path") and edocument_profile.detector_path:
		try:
			detector_func = frappe.get_attr(edocument_profile.detector_path)
			return detector_func(xml_bytes)
		except Exception as e:
			frappe.log_error(
				f"Error loading detector from path {edocument_profile.detector_path}: {e!s}",
				"EDocument Detector Error"
			)
			# Fall through to empty result if loading fails

	# Default: No field detection configured
	return {}
