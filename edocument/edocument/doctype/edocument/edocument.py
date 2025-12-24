# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


def _detect_profile_from_xml(xml_bytes: bytes) -> str | None:
	"""
	Detect EDocument Profile from XML bytes using precise matching.

	Requires all 3 fields: namespace + element_name + identifier_value

	Args:
		xml_bytes: The XML content as bytes

	Returns:
		str | None: The name of the EDocument Profile, or None if not detected
	"""
	try:
		from lxml import etree as ET

		root = ET.fromstring(xml_bytes)

		# Get all namespaces declared in the XML document
		all_xml_namespaces = set(root.nsmap.values()) if root.nsmap else set()

		# Get all profiles
		profiles = frappe.get_all(
			"EDocument Profile",
			fields=["name", "identifier_value", "identifier_element_name", "identifier_namespace"],
		)

		for profile in profiles:
			namespace = profile.get("identifier_namespace")
			element_name = profile.get("identifier_element_name")
			identifier_value = profile.get("identifier_value")

			# All 3 fields are required for precise matching
			if not namespace or not element_name or not identifier_value:
				continue

			# Check if the profile's namespace exists in the XML
			if namespace not in all_xml_namespaces:
				continue

			# Find element in the profile's namespace
			elem = root.findall(f".//{{{namespace}}}{element_name}")
			if elem and elem[0].text:
				if elem[0].text.strip() == identifier_value:
					return profile["name"]

	except Exception as e:
		frappe.log_error(f"Error detecting profile from XML: {e!s}", "EDocument Profile Detection Error")

	return None


class EDocument(Document):
	@frappe.whitelist()
	def _has_xml_file(self) -> bool:
		"""Check if XML file is attached to this EDocument."""
		xml_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "EDocument",
				"attached_to_name": self.name,
				"file_name": ["like", "%.xml"],
			},
			limit=1,
		)
		return len(xml_files) > 0

	def _generate_xml_internal(self):
		"""
		Internal method to generate XML (used by before_save).
		Sets fields on self instead of using db_set.
		"""
		if not self.edocument_source_type or not self.edocument_source_document:
			raise ValueError(_("Source Type and Source Document are required to generate XML."))

		if not self.edocument_profile:
			raise ValueError(_("EDocument Profile is required to generate XML."))

		# Get the source document
		source_doc = frappe.get_doc(self.edocument_source_type, self.edocument_source_document)

		# Get the profile to determine which generator to use
		edocument_profile = frappe.get_doc("EDocument Profile", self.edocument_profile)

		# Import and call the profile-specific generator
		from edocument.edocument.generator import get_xml_generator

		# Generate XML using profile-specific generator
		xml_bytes = get_xml_generator(source_doc, edocument_profile)

		# Create filename
		filename = f"{self.name}_{self.edocument_source_document}.xml"

		# Attach file to EDocument
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"attached_to_doctype": "EDocument",
				"attached_to_name": self.name,
				"folder": "Home/Attachments",
				"content": xml_bytes,
				"is_private": 0,
			}
		)
		file_doc.insert(ignore_permissions=True)

		# Reset status and error when new XML is generated
		# (since this is a new XML that hasn't been validated yet)
		self.status = None  # Clear status - will be set after validation
		self.error = None  # Clear previous errors

		return filename

	@frappe.whitelist()
	def generate_xml(self):
		"""
		Generate XML file for the EDocument and attach it to the record.
		Note: This method only generates XML - validation is handled separately.
		This is the public method called from the button.
		"""
		try:
			file_name = self._generate_xml_internal()
			# Save the document to persist status and error field changes
			# _generate_xml_internal() already sets self.status and self.error
			self.save()

			frappe.msgprint(
				_("XML file {0} generated and attached successfully.").format(frappe.bold(file_name)),
				indicator="green",
				alert=True,
			)

			return file_name

		except Exception as e:
			# Update error field on generation failure (no status change - validation hasn't happened yet)
			error_msg = str(e)
			self.error = error_msg
			self.save()
			frappe.log_error(f"Error generating XML for EDocument {self.name}: {error_msg}")
			frappe.throw(_("Error generating XML: {0}").format(error_msg))

	def _validate_xml_internal(self):
		"""
		Internal method to validate XML (used by before_save).
		Sets fields on self instead of using db_set.
		"""
		# Initialize status and error fields
		self.status = None
		self.error = None

		if not self.edocument_profile:
			return

		# Get XML from attached files (both uploaded and generated XML are attached)
		try:
			xml_bytes = self._get_xml_from_attached_files()
		except Exception as e:
			error_msg = _("Cannot retrieve XML file for validation.")
			error_details = f"{error_msg}\nError: {e!s}"
			self.status = "Validation Failed"
			self.error = error_details
			frappe.log_error(error_details, reference_doctype=self.doctype, reference_name=self.name)
			return

		# Get the profile to determine which validator to use
		try:
			edocument_profile = frappe.get_doc("EDocument Profile", self.edocument_profile)
		except Exception as e:
			error_msg = _("Cannot load EDocument Profile.")
			error_details = f"{error_msg}\nError: {e!s}\nProfile: {self.edocument_profile}"
			self.status = "Validation Failed"
			self.error = error_details
			frappe.log_error(error_details, reference_doctype=self.doctype, reference_name=self.name)
			return

		# Import and call the profile-specific validator
		from edocument.edocument.validator import get_xml_validator

		try:
			# Validate XML using profile-specific validator
			validation_result = get_xml_validator(xml_bytes, edocument_profile)
		except Exception as e:
			error_msg = _("Cannot validate XML.")
			error_details = f"{error_msg}\nError: {e!s}\nProfile: {self.edocument_profile}"
			self.status = "Validation Failed"
			self.error = error_details
			frappe.log_error(error_details, reference_doctype=self.doctype, reference_name=self.name)
			return

		# Build error message from errors and warnings
		error_msg = validation_result.get("error")
		warnings = validation_result.get("warnings", [])

		# Combine errors and warnings in the error field
		error_text_parts = []
		if error_msg:
			error_text_parts.append(error_msg)
		if warnings:
			warnings_text = "\n".join(warnings)
			error_text_parts.append(f"Warnings:\n{warnings_text}")

		error_text = "\n\n".join(error_text_parts) if error_text_parts else None

		# Update status and error fields on self (will be saved automatically in before_save)
		if validation_result.get("is_valid"):
			self.status = "Validation Successful"
			self.error = error_text  # Include warnings even if validation passes
		else:
			self.status = "Validation Failed"
			self.error = error_text or _("Validation failed")

	@frappe.whitelist()
	def validate_xml(self):
		"""
		Validate the XML file (either generated or uploaded) using profile-specific validator.
		Updates the status and error fields based on validation results.
		This is the public method called from the button.
		"""
		try:
			self._validate_xml_internal()
			# Save the document to persist status and error field changes
			# _validate_xml_internal() already sets self.status and self.error
			self.save()
		except Exception as e:
			# If validation throws, just set the error (don't re-throw)
			error_msg = str(e)
			self.status = "Validation Failed"
			self.error = error_msg
			self.save()
			frappe.log_error(f"Error validating XML for EDocument {self.name}: {error_msg}")

	def before_save(self):
		"""
		Automatically detect profile, generate XML, and validate XML on save.
		"""
		# Set direction automatically:
		# - Outgoing: if source document exists (generated from Sales Invoice, etc.)
		# - Incoming: if XML file exists but no source document (uploaded/received XML)
		if self.edocument_source_document:
			self.direction = "Outgoing"
		elif self.xml_file or self._has_xml_file():
			self.direction = "Incoming"
		# If neither condition is met, keep existing value or default to "Outgoing"
		elif not self.direction:
			self.direction = "Outgoing"

		# Check if XML is available (either via xml_file field or attached files)
		has_xml = self.xml_file or self._has_xml_file()

		# Auto-detect profile from XML if:
		xml_file_changed = self.has_value_changed("xml_file")
		should_detect_profile = (xml_file_changed or not self.edocument_profile) and has_xml

		if should_detect_profile:
			# Try to detect profile from XML
			try:
				xml_bytes = self._get_xml_from_attached_files()
				if xml_bytes:
					detected_profile = _detect_profile_from_xml(xml_bytes)
					if detected_profile:
						self.edocument_profile = detected_profile
			except (ValueError, AttributeError, Exception) as e:
				# If detection fails (file not found, parsing error, etc.), log but don't block save
				error_msg = str(e)
				frappe.log_error(
					f"Error detecting profile from XML for EDocument {self.name if self.name else 'NEW'}: {error_msg}\nTraceback: {frappe.get_traceback()}",
					"EDocument Profile Detection Error",
				)

		# Auto-detect EDocument fields (company, etc.) from XML using profile-specific detector
		if self.edocument_profile and has_xml and not self.company:
			try:
				xml_bytes = self._get_xml_from_attached_files()
				if xml_bytes:
					from edocument.edocument.detector import get_edocument_fields

					detected_fields = get_edocument_fields(xml_bytes, self.edocument_profile)
					# Set detected fields on the document
					for field, value in detected_fields.items():
						if hasattr(self, field) and not getattr(self, field):
							setattr(self, field, value)
			except Exception as e:
				frappe.log_error(
					f"Error detecting fields from XML for EDocument {self.name if self.name else 'NEW'}: {e!s}",
					"EDocument Field Detection Error",
				)

		if self.edocument_source_document and self.edocument_profile and not self.xml_file:
			# Check if XML already exists (for generated XML)
			if not self._has_xml_file():
				# Generate XML automatically
				try:
					self._generate_xml_internal()
				except Exception as e:
					error_msg = str(e)
					self.error = f"Error generating XML: {error_msg}"
					frappe.log_error(
						f"Error during automatic XML generation for EDocument {self.name}: {error_msg}"
					)

		if self.edocument_profile:
			# Validate XML automatically
			try:
				self._validate_xml_internal()
			except Exception as e:
				# If validation throws, just set the error (don't re-throw)
				error_msg = str(e)
				self.status = "Validation Failed"
				self.error = error_msg
				frappe.log_error(
					f"Error during automatic XML validation for EDocument {self.name}: {error_msg}"
				)

			# If caller requested to block on validation error, throw before document is saved
			if (
				getattr(frappe.flags, "block_on_validation_error", False)
				and self.status == "Validation Failed"
			):
				frappe.throw(_("EDocument validation failed: {0}").format(self.error or _("Unknown error")))

	def on_update(self):
		"""
		Called after document is saved.
		Detect profile and fields from XML if not detected in before_save (e.g., file attached separately).
		"""
		# Check if XML is available (either via xml_file field or attached files)
		has_xml = self.xml_file or self._has_xml_file()

		# Auto-detect profile from XML if:
		xml_file_changed = self.has_value_changed("xml_file")
		should_detect_profile = (xml_file_changed or not self.edocument_profile) and has_xml

		if should_detect_profile:
			# Try to detect profile from XML
			try:
				xml_bytes = self._get_xml_from_attached_files()
				if xml_bytes:
					detected_profile = _detect_profile_from_xml(xml_bytes)
					if detected_profile and detected_profile != self.edocument_profile:
						self.db_set("edocument_profile", detected_profile, update_modified=False)
			except Exception as e:
				frappe.log_error(
					f"Error detecting profile from XML in on_update for EDocument {self.name}: {e!s}"
				)

		# Auto-detect EDocument fields (company, etc.) from XML using profile-specific detector
		if self.edocument_profile and has_xml and not self.company:
			try:
				xml_bytes = self._get_xml_from_attached_files()
				if xml_bytes:
					from edocument.edocument.detector import get_edocument_fields

					detected_fields = get_edocument_fields(xml_bytes, self.edocument_profile)
					# Update detected fields directly in database
					for field, value in detected_fields.items():
						if hasattr(self, field) and not getattr(self, field):
							self.db_set(field, value, update_modified=False)
			except Exception as e:
				frappe.log_error(
					f"Error detecting fields from XML in on_update for EDocument {self.name}: {e!s}"
				)

		# Update source document with EDocument reference and status (for outgoing documents)
		if self.direction == "Outgoing" and self.edocument_source_type and self.edocument_source_document:
			frappe.db.set_value(
				self.edocument_source_type,
				self.edocument_source_document,
				"edocument",
				self.name,
				update_modified=False,
			)
			frappe.db.set_value(
				self.edocument_source_type,
				self.edocument_source_document,
				"edocument_status",
				self.status,
				update_modified=False,
			)

	@frappe.whitelist()
	def generate_preview(self) -> str:
		"""
		Generate HTML preview from attached XML file using profile-specific transformation.
		Returns HTML string ready for display in HTML field.
		"""
		if not self.name:
			frappe.throw(_("Document name is required"))

		# Get XML bytes
		xml_bytes = self._get_xml_from_attached_files()

		if not xml_bytes:
			frappe.throw(_("No XML content found"))

		# Generate HTML preview using the preview module
		from edocument.preview import get_xml_preview

		return get_xml_preview(xml_bytes, self.edocument_profile)

	def _get_xml_from_attached_files(self) -> bytes:
		"""
		Get XML bytes from the most recently attached XML file.
		Follows standard Frappe pattern for file handling.

		Returns:
			bytes: XML content as bytes

		Raises:
			ValueError: If no XML file found or file cannot be read
		"""
		# Get attached XML files (standard Frappe pattern)
		file_docs = frappe.get_all(
			"File",
			fields=["name"],
			filters={
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"file_name": ["like", "%.xml"],
			},
			order_by="creation desc",
			limit=1,
		)

		if not file_docs:
			frappe.throw(_("No XML file found. Please upload an XML file or generate XML first."))

		try:
			file_doc = frappe.get_doc("File", file_docs[0].name)
			content = file_doc.get_content()
			if not content:
				frappe.throw(_("XML file has no content"))
			# Ensure we return bytes for XML parsing
			if isinstance(content, str):
				return content.encode("utf-8")
			return content
		except Exception as e:
			frappe.log_error(f"Error reading XML file {file_docs[0].name}: {e!s}")
			frappe.throw(_("Cannot read XML file: {0}").format(str(e)))

	@frappe.whitelist()
	def create_and_save_document(self):
		"""
		Parse the uploaded XML file, create and save a document (e.g., Purchase Invoice).
		Uses profile-specific parser based on edocument_profile.
		After creation, updates edocument_target_type and edocument_target_document fields.
		"""
		try:
			# Use the standalone create_document function to get the document
			# (edocument and edocument_status are set in create_document)
			doc = create_document(self.name, target_doc=None)

			# Save the document
			doc.insert(ignore_permissions=True)

			# Update EDocument with target document information
			self.edocument_target_type = doc.doctype
			self.edocument_target_document = doc.name
			self.save()

			frappe.msgprint(
				_("{0} {1} created successfully from XML.").format(
					frappe.bold(doc.doctype), frappe.bold(doc.name)
				),
				indicator="green",
				alert=True,
			)

			return doc.name

		except Exception as e:
			error_msg = str(e)
			self.error = error_msg
			self.save()
			frappe.log_error(f"Error creating document from XML for EDocument {self.name}: {error_msg}")
			frappe.throw(_("Error creating document: {0}").format(error_msg))


@frappe.whitelist()
def create_document(source_name, target_doc=None):
	"""
	Parse XML from EDocument and create a document (e.g., Purchase Invoice).
	Used by both:
	- frappe.model.open_mapped_doc to open document with prefilled data (returns unsaved doc)
	- create_and_save_document instance method (which then saves it)

	Args:
		source_name: Name of the EDocument
		target_doc: Optional target document (if None, creates new document)

	Returns:
		Document (not saved) - caller can save it or open it in UI
	"""
	# Get the EDocument instance
	edocument = frappe.get_doc("EDocument", source_name)

	if not edocument.edocument_profile:
		frappe.throw(_("EDocument Profile is required to parse XML and create document."))

	# Get XML bytes from attached files
	xml_bytes = edocument._get_xml_from_attached_files()

	# Get the profile to determine which parser to use
	edocument_profile = frappe.get_doc("EDocument Profile", edocument.edocument_profile)

	# Import and call the profile-specific parser
	from edocument.edocument.parser import get_xml_parser

	# Parse XML using profile-specific parser
	document_data = get_xml_parser(xml_bytes, edocument_profile)

	# Validate that parser returned a dict with doctype
	if not isinstance(document_data, dict):
		frappe.throw(_("Parser must return a dictionary with document data."))

	if "doctype" not in document_data:
		frappe.throw(_("Parser must return a dictionary with 'doctype' field."))

	doctype = document_data["doctype"]
	doc = frappe.new_doc(doctype)
	doc.update(document_data)

	# Set EDocument reference on target document
	doc.edocument = source_name
	doc.edocument_status = edocument.status

	# Set missing values before returning
	doc.set_missing_values()

	# Return document (not saved) - caller decides whether to save or open in UI
	return doc
