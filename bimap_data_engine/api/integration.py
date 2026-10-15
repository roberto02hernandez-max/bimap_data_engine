"""Stable entry point for BIMAP modules embedding the Data Engine."""

import frappe

from bimap_data_engine.services.context import context_payload, create_context, get_context
from bimap_data_engine.services.line_import import map_imported_rows, prepare_line_import


@frappe.whitelist(methods=["POST"])
def create_editor_context(doctype, mode="Edit", allowed_fields=None, filters=None, source_app=None):
	return create_context(doctype, mode, allowed_fields, filters, source_app)


@frappe.whitelist(methods=["GET"])
def get_editor_context(context_id):
	return context_payload(get_context(context_id))


@frappe.whitelist(methods=["POST"])
def prepare_document_lines(
	parent_doctype,
	table_field,
	parent_values,
	existing_rows,
	imported_rows,
	merge_policy="append",
	match_fields=None,
):
	return prepare_line_import(
		parent_doctype,
		table_field,
		parent_values,
		existing_rows,
		imported_rows,
		merge_policy=merge_policy,
		match_fields=match_fields,
	)


@frappe.whitelist(methods=["POST"])
def map_document_lines(parent_doctype, table_field, rows, mapping, defaults=None):
	return map_imported_rows(parent_doctype, table_field, rows, mapping, defaults)
