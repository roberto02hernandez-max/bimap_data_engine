"""Permission-aware, paginated document reads."""

import frappe
from frappe.utils import cint, cstr

from bimap_data_engine.services.metadata import get_doctype_meta, has_field_permlevel, readable_fieldnames


MAX_PAGE_LENGTH = 500


def _parse_fields(fields):
	fields = frappe.parse_json(fields) if isinstance(fields, str) else fields
	if not isinstance(fields, list) or not fields:
		frappe.throw("Selecciona al menos un campo.")
	if not all(isinstance(field, str) and field.strip() for field in fields):
		frappe.throw("La lista de campos es inválida.")
	return list(dict.fromkeys(field.strip() for field in fields))


def _parse_filters(filters):
	if not filters:
		return {}
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if not isinstance(filters, (dict, list)):
		frappe.throw("Los filtros son inválidos.")
	return filters


@frappe.whitelist(methods=["GET"])
def list_records(doctype, fields, filters=None, start=0, page_length=100, context_id=None):
	from bimap_data_engine.services.context import context_filters, validate_context_fields
	from bimap_data_engine.services.related_filters import apply_related_filters

	meta = get_doctype_meta(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	requested = _parse_fields(fields)
	allowed = readable_fieldnames(meta)
	denied = [field for field in requested if field not in allowed]
	if denied:
		frappe.throw(f"Campos no legibles: {', '.join(denied)}")
	context = validate_context_fields(context_id, doctype, requested) if context_id else None
	requested_filters = _parse_filters(filters)
	fixed_filters = context_filters(context)
	if fixed_filters:
		if requested_filters and requested_filters != fixed_filters:
			frappe.throw("Este contexto fija los filtros de consulta.", frappe.PermissionError)
		requested_filters = fixed_filters
	requested_filters = apply_related_filters(doctype, requested_filters)
	for identity_field in ("name", "modified"):
		if identity_field not in requested:
			requested.append(identity_field)
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length), 1), MAX_PAGE_LENGTH)
	rows = frappe.get_list(
		doctype,
		fields=requested,
		filters=requested_filters,
		order_by="name asc",
		limit_start=start,
		limit_page_length=page_length + 1,
	)
	return {
		"doctype": doctype,
		"fields": requested,
		"rows": rows[:page_length],
		"next_start": start + page_length if len(rows) > page_length else None,
	}


@frappe.whitelist(methods=["GET"])
def list_child_rows(doctype, name, table_field, fields, context_id=None):
	from bimap_data_engine.services.context import validate_context_fields

	meta = get_doctype_meta(doctype)
	if context_id:
		validate_context_fields(context_id, doctype, [table_field])
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	table_df = meta.get_field(table_field)
	if not table_df or table_df.fieldtype not in ("Table", "Table MultiSelect"):
		frappe.throw("La tabla hija indicada no existe.")
	if not has_field_permlevel(meta, table_df, "read"):
		frappe.throw("No tienes permiso de lectura para esa tabla hija.")
	child_meta = frappe.get_meta(table_df.options)
	requested = _parse_fields(fields)
	allowed = readable_fieldnames(child_meta, parenttype=doctype)
	denied = [field for field in requested if field not in allowed]
	if denied:
		frappe.throw(f"Campos hijos no legibles: {', '.join(denied)}")
	if "name" not in requested:
		requested.append("name")
	return {
		"doctype": doctype,
		"name": name,
		"table_field": table_field,
		"child_doctype": table_df.options,
		"snapshot_modified": cstr(doc.modified),
		"rows": [
			{field: row.get(field) for field in requested}
			for row in doc.get(table_field) or []
		],
	}
