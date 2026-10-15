"""Server-bound invocation contexts that narrow, never widen, permissions."""

import json
from urllib.parse import urlencode

import frappe
from frappe.utils import add_to_date, cstr, get_datetime, now_datetime

from bimap_data_engine.services.mapping import serialize
from bimap_data_engine.services.metadata import (
	get_doctype_meta,
	has_field_permlevel,
	readable_fieldnames,
	writable_fieldnames,
)


VALID_MODES = {"Edit", "Import", "Export"}


def _list(value, label):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
		frappe.throw(f"{label}: formato inválido.")
	return list(dict.fromkeys(item.strip() for item in value))


def create_context(doctype, mode="Edit", allowed_fields=None, filters=None, source_app=None):
	meta = get_doctype_meta(doctype)
	mode = cstr(mode).title()
	if mode not in VALID_MODES:
		frappe.throw("Modo de integración inválido.")
	permission_type = "create" if mode == "Import" else "read"
	frappe.has_permission(doctype, permission_type, throw=True)
	if mode in {"Edit", "Import"}:
		available = writable_fieldnames(meta)
		available.update(
			df.fieldname
			for df in meta.get_table_fields()
			if not df.read_only and has_field_permlevel(meta, df, "write")
		)
	else:
		available = readable_fieldnames(meta)
		available.update(
			df.fieldname for df in meta.get_table_fields() if has_field_permlevel(meta, df, "read")
		)
	if allowed_fields:
		allowed = _list(allowed_fields, "Campos permitidos")
		denied = sorted(set(allowed) - available)
		if denied:
			frappe.throw(f"El contexto no puede autorizar estos campos: {', '.join(denied)}")
	else:
		allowed = sorted(available)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	if not isinstance(filters, (dict, list)):
		frappe.throw("Filtros de contexto inválidos.")
	doc = frappe.get_doc(
		{
			"doctype": "BIMAP Data Context",
			"target_doctype": doctype,
			"mode": mode,
			"source_app": cstr(source_app)[:140],
			"allowed_fields_json": serialize(allowed),
			"filters_json": serialize(filters),
			"expires_on": add_to_date(now_datetime(), hours=8),
		}
	).insert(ignore_permissions=True)
	return context_payload(doc)


def get_context(context_id, *, doctype=None, mode=None):
	doc = frappe.get_doc("BIMAP Data Context", context_id)
	if doc.owner != frappe.session.user and frappe.session.user != "Administrator":
		frappe.throw("El contexto pertenece a otro usuario.", frappe.PermissionError)
	if doc.disabled or get_datetime(doc.expires_on) <= now_datetime():
		frappe.throw("El contexto expiró o fue deshabilitado.", frappe.PermissionError)
	if doctype and doc.target_doctype != doctype:
		frappe.throw("El DocType no coincide con el contexto.", frappe.PermissionError)
	if mode and doc.mode != mode:
		frappe.throw("El modo no coincide con el contexto.", frappe.PermissionError)
	permission_type = "create" if doc.mode == "Import" else "read"
	frappe.has_permission(doc.target_doctype, permission_type, throw=True)
	return doc


def context_payload(doc):
	route_name = "bimap-data-import" if doc.mode == "Import" else "bimap-data-engine"
	return {
		"context_id": doc.name,
		"doctype": doc.target_doctype,
		"mode": doc.mode,
		"source_app": doc.source_app,
		"allowed_fields": json.loads(doc.allowed_fields_json),
		"filters": json.loads(doc.filters_json),
		"expires_on": doc.expires_on,
		"route": f"/app/{route_name}?{urlencode({'context': doc.name})}",
	}


def validate_context_fields(context_id, doctype, fields, *, mode=None):
	if not context_id:
		return None
	doc = get_context(context_id, doctype=doctype, mode=mode)
	allowed = set(json.loads(doc.allowed_fields_json))
	denied = sorted(set(fields) - allowed)
	if denied:
		frappe.throw(f"Campos fuera del contexto: {', '.join(denied)}", frappe.PermissionError)
	return doc


def validate_context_changes(context_id, changes):
	if not context_id:
		return
	changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
	doctypes = {change.get("doctype") for change in changes if isinstance(change, dict)}
	if len(doctypes) != 1:
		frappe.throw("Un contexto de edición sólo admite un DocType.")
	doctype = next(iter(doctypes))
	fields = {change.get("fieldname") for change in changes}
	validate_context_fields(context_id, doctype, fields, mode="Edit")


def validate_context_import_specification(context_id, specification):
	if not context_id:
		return
	specification = frappe.parse_json(specification) if isinstance(specification, str) else specification
	if not isinstance(specification, dict) or not isinstance(specification.get("nodes"), list):
		frappe.throw("Especificación de importación inválida.")
	context = get_context(context_id, mode="Import")
	fields = set()
	for node in specification["nodes"]:
		if not isinstance(node, dict) or node.get("doctype") != context.target_doctype:
			frappe.throw("El contexto de importación sólo admite su DocType objetivo.", frappe.PermissionError)
		fields.update(entry.get("target") for entry in node.get("mapping") or [] if isinstance(entry, dict))
		fields.update((node.get("defaults") or {}).keys())
		fields.update(entry.get("target") for entry in node.get("references") or [] if isinstance(entry, dict))
		for child in node.get("children") or []:
			if isinstance(child, dict):
				fields.add(child.get("table_field"))
	validate_context_fields(context_id, context.target_doctype, {field for field in fields if field}, mode="Import")


def validate_context_import_plan(context_id, plan):
	if not context_id:
		return
	plan = frappe.parse_json(plan) if isinstance(plan, str) else plan
	if not isinstance(plan, dict) or not isinstance(plan.get("records"), list):
		frappe.throw("Plan de importación inválido.")
	context = get_context(context_id, mode="Import")
	fields = set()
	for record in plan["records"]:
		if not isinstance(record, dict) or record.get("doctype") != context.target_doctype:
			frappe.throw("El plan contiene un DocType fuera del contexto.", frappe.PermissionError)
		fields.update((record.get("values") or {}).keys())
		fields.update((record.get("children") or {}).keys())
		fields.update(entry.get("target") for entry in record.get("references") or [] if isinstance(entry, dict))
	validate_context_fields(context_id, context.target_doctype, {field for field in fields if field}, mode="Import")


def context_filters(doc):
	return json.loads(doc.filters_json) if doc else None
