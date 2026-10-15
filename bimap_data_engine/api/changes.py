"""Preview and application endpoints for explicit partial changes."""

import frappe

from bimap_data_engine.services.change_engine import apply_changes as _apply_changes
from bimap_data_engine.services.change_engine import preview_changes as _preview_changes


@frappe.whitelist(methods=["POST"])
def preview_changes(changes, context_id=None):
	from bimap_data_engine.services.context import validate_context_changes

	validate_context_changes(context_id, changes)
	return _preview_changes(changes)


@frappe.whitelist(methods=["POST"])
def apply_changes(changes, context_id=None):
	from bimap_data_engine.services.context import validate_context_changes

	validate_context_changes(context_id, changes)
	return _apply_changes(changes)
