# Copyright (c) 2025, Prilk Consulting BV and contributors
# For license information, please see license.txt

"""
Base classes for EDocument generators and validators.
These provide a common interface that all generators and validators should implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseGenerator(ABC):
	"""Base class for all EDocument generators"""
	
	@abstractmethod
	def generate(self, source_doc, edocument_profile) -> bytes:
		"""
		Generate XML from source document.
		
		Args:
			source_doc: The source document (e.g., Sales Invoice, Purchase Invoice)
			edocument_profile: The EDocument Profile document
			
		Returns:
			bytes: The generated XML as bytes
		"""
		pass


class BaseValidator(ABC):
	"""Base class for all EDocument validators"""
	
	@abstractmethod
	def validate(self, xml_bytes: bytes, edocument_profile) -> Dict[str, Any]:
		"""
		Validate XML against profile requirements.
		
		Args:
			xml_bytes: The XML content as bytes
			edocument_profile: The EDocument Profile document
			
		Returns:
			dict: Validation result with keys:
				- is_valid: bool - Whether validation passed
				- error: str - Error message if validation failed (None if valid)
				- warnings: list - List of warnings (optional)
		"""
		pass

