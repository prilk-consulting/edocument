# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Generator module for EDocument XML generation.
This module routes to profile-specific generators based on the EDocument Profile.

Note: This module handles XML generation only. XML validation is handled separately.
"""

import frappe
from frappe import _


def get_xml_generator(source_doc, edocument_profile):
	"""
	Get XML generator based on the profile.
	This function generates XML only - validation is handled separately.
	
	The generator is determined by:
	1. Check if edocument_profile has a generator_path field
	2. If not found, fall back to basic generator
	
	Args:
		source_doc: The source document (e.g., Sales Invoice, Purchase Invoice)
		edocument_profile: The EDocument Profile document
		
	Returns:
		bytes: The generated XML as bytes (not validated)
	"""
	# Try to get generator from profile's generator_path if specified
	if hasattr(edocument_profile, 'generator_path') and edocument_profile.generator_path:
		try:
			generator_func = frappe.get_attr(edocument_profile.generator_path)
			return generator_func(source_doc, edocument_profile)
		except Exception as e:
			frappe.log_error(f"Error loading generator from path {edocument_profile.generator_path}: {str(e)}")
	
	# Default: Use basic XML generator
	return generate_basic_xml(source_doc, edocument_profile)


def generate_basic_xml(source_doc, edocument_profile):
	"""
	Basic XML generator (placeholder implementation).
	This should be replaced with actual profile-specific generators.
	
	Args:
		source_doc: The source document
		edocument_profile: The EDocument Profile document
		
	Returns:
		bytes: Basic XML structure as bytes
	"""
	# This is a placeholder implementation
	# You should implement actual XML generation based on your requirements
	# For example, you might want to:
	# 1. Use different generators for different profiles
	# 2. Generate XML based on source document and profile
	# 3. Map source document fields to XML structure
	
	# Basic XML structure (placeholder)
	xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<EDocument>
	<SourceType>{source_doc.doctype}</SourceType>
	<SourceDocument>{source_doc.name}</SourceDocument>
	<Profile>{edocument_profile.name}</Profile>
	<GeneratedAt>{frappe.utils.now()}</GeneratedAt>
</EDocument>"""
	
	return xml_content.encode('utf-8')

