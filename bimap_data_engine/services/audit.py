"""Transactional audit records for explicit Data Engine changes."""

import frappe
from frappe.utils import now_datetime

from bimap_data_engine.services.change_engine import _canonical


def record_changes(operation_id, doctype, name, entries):
	now = now_datetime()
	user = frappe.session.user
	fields = [
		"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx",
		"operation_id", "changed_by", "changed_on", "reference_doctype", "document_name",
		"table_field", "child_name", "fieldname", "operation", "original_value", "new_value",
	]
	values = (
		(
			frappe.generate_hash(length=16), now, now, user, user, 0, 0,
			operation_id, user, now, doctype, name, entry.get("table_field"),
			entry.get("child_name"), entry.get("fieldname"), entry["operation"],
			_canonical(entry.get("original")), _canonical(entry.get("value")),
		)
		for entry in entries
	)
	frappe.db.bulk_insert("BIMAP Data Change Log", fields=fields, values=values, chunk_size=1000)
