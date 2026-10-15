"""Persistent user-owned editor/import sessions and reusable mappings."""

import json

import frappe
from frappe.utils import cint, now_datetime

from bimap_data_engine.services.mapping import serialize, validate_mapping


MAX_STATE_BYTES = 20 * 1024 * 1024


def _is_manager():
	return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def assert_owned(doc, *, allow_shared=False):
	if _is_manager() or doc.owner == frappe.session.user or (allow_shared and cint(doc.get("is_shared"))):
		return
	frappe.throw("No tienes permiso para este recurso del Data Engine.", frappe.PermissionError)


def _state(value):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, dict):
		frappe.throw("El estado de sesión debe ser un objeto JSON.")
	serialized = serialize(value)
	if len(serialized.encode("utf-8")) > MAX_STATE_BYTES:
		frappe.throw("El estado de sesión excede 20 MB.")
	return serialized


def save_session(session_title, mode, target_doctype, state, session_name=None, **values):
	frappe.has_permission(target_doctype, "read", throw=True)
	serialized = _state(state)
	if session_name:
		doc = frappe.get_doc("BIMAP Data Session", session_name)
		assert_owned(doc)
	else:
		doc = frappe.new_doc("BIMAP Data Session")
	doc.update(
		{
			"session_title": session_title,
			"mode": mode,
			"target_doctype": target_doctype,
			"status": values.get("status") or "Draft",
			"source_file": values.get("source_file"),
			"mapping_profile": values.get("mapping_profile"),
			"row_count": cint(values.get("row_count")),
			"last_opened_on": now_datetime(),
			"state_json": serialized,
		}
	)
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return session_payload(doc)


def session_payload(doc):
	return {
		"name": doc.name,
		"session_title": doc.session_title,
		"mode": doc.mode,
		"target_doctype": doc.target_doctype,
		"status": doc.status,
		"source_file": doc.source_file,
		"mapping_profile": doc.mapping_profile,
		"row_count": doc.row_count,
		"last_opened_on": doc.last_opened_on,
		"state": json.loads(doc.state_json),
	}


def get_session(session_name):
	doc = frappe.get_doc("BIMAP Data Session", session_name)
	assert_owned(doc)
	frappe.has_permission(doc.target_doctype, "read", throw=True)
	doc.db_set("last_opened_on", now_datetime(), update_modified=False)
	return session_payload(doc)


def list_sessions(limit=50):
	limit = min(max(cint(limit) or 50, 1), 200)
	rows = frappe.get_all(
		"BIMAP Data Session",
		filters={"owner": frappe.session.user, "status": ["!=", "Archived"]},
		fields=[
			"name", "session_title", "mode", "target_doctype", "status", "row_count",
			"modified", "last_opened_on",
		],
		order_by="modified desc",
		page_length=limit,
	)
	return rows


def save_mapping_profile(profile_title, target_doctype, mapping, defaults=None, profile_name=None, **values):
	validated = validate_mapping(target_doctype, mapping, defaults, values.get("table_field"))
	if profile_name:
		doc = frappe.get_doc("BIMAP Data Mapping Profile", profile_name)
		assert_owned(doc)
	else:
		doc = frappe.new_doc("BIMAP Data Mapping Profile")
	doc.update(
		{
			"profile_title": profile_title,
			"target_doctype": target_doctype,
			"table_field": values.get("table_field"),
			"source_format": values.get("source_format") or "Any",
			"mapping_json": serialize(validated["mapping"]),
			"defaults_json": serialize(validated["defaults"]),
			"is_shared": cint(values.get("is_shared")) if _is_manager() else 0,
		}
	)
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return mapping_profile_payload(doc)


def mapping_profile_payload(doc):
	return {
		"name": doc.name,
		"profile_title": doc.profile_title,
		"target_doctype": doc.target_doctype,
		"table_field": doc.table_field,
		"source_format": doc.source_format,
		"mapping": json.loads(doc.mapping_json),
		"defaults": json.loads(doc.defaults_json or "{}"),
		"is_shared": cint(doc.is_shared),
		"owner": doc.owner,
	}


def get_mapping_profile(profile_name):
	doc = frappe.get_doc("BIMAP Data Mapping Profile", profile_name)
	assert_owned(doc, allow_shared=True)
	frappe.has_permission(doc.target_doctype, "read", throw=True)
	return mapping_profile_payload(doc)
