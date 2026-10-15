"""Metadata endpoints."""

import frappe

from bimap_data_engine.services.metadata import get_doctype_meta, serialize_schema


@frappe.whitelist(methods=["GET"])
def get_schema(doctype, context_id=None):
	from bimap_data_engine.services.context import validate_context_fields
	from bimap_data_engine.services.related_filters import related_filter_fields

	meta = get_doctype_meta(doctype)
	frappe.has_permission(meta.name, "read", throw=True)
	schema = serialize_schema(meta)
	schema["filter_fields"] = related_filter_fields(meta.name) if not context_id else []
	if context_id:
		context = validate_context_fields(context_id, doctype, [])
		allowed = set(frappe.parse_json(context.allowed_fields_json))
		schema["fields"] = [field for field in schema["fields"] if field["fieldname"] in allowed]
		schema["tables"] = [table for table in schema["tables"] if table["fieldname"] in allowed]
	return schema


@frappe.whitelist(methods=["GET"])
def get_import_catalog():
	from bimap_data_engine.services.import_catalog import get_import_catalog as build_catalog

	return build_catalog()


@frappe.whitelist(methods=["GET"])
def get_edit_catalog():
	from bimap_data_engine.services.import_catalog import get_edit_catalog as build_catalog

	return build_catalog()
