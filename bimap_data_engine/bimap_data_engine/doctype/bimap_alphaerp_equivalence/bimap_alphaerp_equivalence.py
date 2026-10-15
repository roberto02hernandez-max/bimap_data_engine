import hashlib

from frappe.model.document import Document


class BIMAPAlphaERPEquivalence(Document):
	def autoname(self):
		key = f"{self.source_system}|{self.mapping_type}|{self.source_key}"
		self.mapping_key = key
		self.name = f"AERP-{hashlib.sha256(key.encode()).hexdigest()[:20]}"
