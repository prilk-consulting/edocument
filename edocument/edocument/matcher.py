# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Matcher module for EDocument XML matching.
This module routes to profile-specific matchers based on the EDocument Profile.

Profile matchers should implement a function with signature:
    match_xxx_xml(xml_bytes, edocument_profile, edocument=None) -> dict

The function should return:
{
    "is_matched": True/False,
    "matching_data": {...},
    "dialog_config": {...},
    "matching_summary": "..."
}

Example matcher_path: edocument.edocument.profiles.peppol.matcher.match_peppol_xml
"""

import frappe
from frappe import _


def get_xml_matcher(xml_bytes, edocument_profile, edocument=None):
	"""
	Get XML matcher result based on the profile.

	Similar to get_xml_validator in validator.py.

	Args:
		xml_bytes: Raw XML content as bytes
		edocument_profile: EDocument Profile document
		edocument: EDocument document (optional, for existing matching_data)

	Returns:
		dict: Matching result with is_matched, matching_data, dialog_config, matching_summary
	"""
	# Try to get matcher from profile's matcher_path if specified
	if edocument_profile.matcher_path:
		try:
			matcher_func = frappe.get_attr(edocument_profile.matcher_path)
			return matcher_func(xml_bytes, edocument_profile, edocument)
		except Exception as e:
			frappe.log_error(
				f"Error loading matcher from path {edocument_profile.matcher_path}: {e!s}",
				"EDocument Matcher Error",
			)

	# Default: Use basic matcher (no matching needed)
	return match_basic_xml(xml_bytes, edocument_profile)


def match_basic_xml(xml_bytes, edocument_profile):
	"""
	Basic XML matcher (placeholder implementation).

	Returns a result indicating no matching is needed - all entities are
	considered matched by default. Profiles that need matching should
	implement their own matcher.

	Args:
		xml_bytes: Raw XML content as bytes
		edocument_profile: EDocument Profile document

	Returns:
		dict: Matching result with is_matched=True
	"""
	return {
		"is_matched": True,
		"matching_data": {},
		"dialog_config": {
			"title": _("Match Document"),
			"fields": [
				{
					"fieldtype": "HTML",
					"fieldname": "info",
					"options": _("No matching configuration for this profile. All entities are considered matched."),
				}
			],
			"primary_action_label": _("OK"),
		},
		"matching_summary": _("No matching required for this profile."),
	}
