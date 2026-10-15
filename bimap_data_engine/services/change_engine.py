"""Explicit partial changes with optimistic concurrency control."""

import json
from collections import OrderedDict

import frappe
from frappe.model import table_fields
from frappe.utils import cstr
from frappe.utils.data import cast

from bimap_data_engine.services.metadata import (
	SYSTEM_IMMUTABLE_FIELDS,
	get_doctype_meta,
	has_field_permlevel,
	writable_fieldnames,
)
from bimap_data_engine.services.policies import validate_change_policies


SUPPORTED_OPERATIONS = {"set", "clear", "add_child", "update_child", "delete_child"}
MAX_SYNCHRONOUS_CHANGES = 500


def _canonical(value):
	return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_changes(changes, *, max_changes=MAX_SYNCHRONOUS_CHANGES):
	changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
	if not isinstance(changes, list) or not changes:
		frappe.throw("Envía al menos un cambio explícito.")
	if max_changes and len(changes) > max_changes:
		frappe.throw(
			f"Esta operación admite hasta {max_changes} cambios; usa un trabajo por lotes."
		)
	return changes


def _normalize_change(raw, index):
	if not isinstance(raw, dict):
		frappe.throw(f"Cambio {index + 1}: formato inválido.")
	base_required = {"doctype", "name", "fieldname", "operation", "snapshot_modified"}
	missing = sorted(base_required - set(raw))
	if missing:
		frappe.throw(f"Cambio {index + 1}: faltan {', '.join(missing)}.")
	change = {
		"doctype": cstr(raw.get("doctype")).strip(),
		"name": cstr(raw.get("name")).strip(),
		"fieldname": cstr(raw.get("fieldname")).strip(),
		"operation": cstr(raw.get("operation")).strip(),
		"snapshot_modified": cstr(raw.get("snapshot_modified")).strip(),
	}
	if change["operation"] not in SUPPORTED_OPERATIONS:
		frappe.throw(f"Cambio {index + 1}: operación no soportada.")
	if not all(change[key] for key in ("doctype", "name", "fieldname", "snapshot_modified")):
		frappe.throw(f"Cambio {index + 1}: identidad o snapshot vacío.")
	if change["operation"] in {"set", "clear"}:
		if "original" not in raw:
			frappe.throw(f"Cambio {index + 1}: falta original.")
		if change["operation"] == "set" and "value" not in raw:
			frappe.throw(f"Cambio {index + 1}: set requiere value.")
		change["original"] = raw.get("original")
		change["value"] = raw.get("value") if change["operation"] == "set" else None
	elif change["operation"] == "add_child":
		if not isinstance(raw.get("value"), dict) or not raw["value"]:
			frappe.throw(f"Cambio {index + 1}: add_child requiere un objeto value.")
		change["value"] = raw["value"]
	else:
		change["child_name"] = cstr(raw.get("child_name")).strip()
		if not change["child_name"]:
			frappe.throw(f"Cambio {index + 1}: falta child_name persistente.")
		if change["operation"] == "update_child":
			if "original" not in raw or "value" not in raw:
				frappe.throw(f"Cambio {index + 1}: update_child requiere original y value.")
			change["child_fieldname"] = cstr(raw.get("child_fieldname")).strip()
			if not change["child_fieldname"]:
				frappe.throw(f"Cambio {index + 1}: falta child_fieldname.")
			change["original"] = raw.get("original")
			change["value"] = raw.get("value")
		elif raw.get("confirmed") is not True:
			frappe.throw(f"Cambio {index + 1}: delete_child requiere confirmed=true.")
	return change


def normalize_changes(changes, *, max_changes=MAX_SYNCHRONOUS_CHANGES):
	normalized = [
		_normalize_change(change, index)
		for index, change in enumerate(_parse_changes(changes, max_changes=max_changes))
	]
	seen = set()
	deleted_rows = set()
	updated_rows = set()
	for change in normalized:
		base = (change["doctype"], change["name"], change["fieldname"])
		if change["operation"] in {"set", "clear"}:
			key = ("parent", *base)
		elif change["operation"] == "add_child":
			continue
		elif change["operation"] == "delete_child":
			key = ("delete", *base, change["child_name"])
			deleted_rows.add((*base, change["child_name"]))
		else:
			key = ("child", *base, change["child_name"], change["child_fieldname"])
			updated_rows.add((*base, change["child_name"]))
		if key in seen:
			frappe.throw("Una celda u operación sólo puede aparecer una vez por conjunto de cambios.")
		seen.add(key)
	if deleted_rows & updated_rows:
		frappe.throw("Una fila hija no puede actualizarse y eliminarse en la misma operación.")
	return normalized


def group_changes(changes, *, max_changes=MAX_SYNCHRONOUS_CHANGES):
	groups = OrderedDict()
	for change in normalize_changes(changes, max_changes=max_changes):
		groups.setdefault((change["doctype"], change["name"]), []).append(change)
	return groups


def _child_context(doc, meta, change, errors):
	table_df = meta.get_field(change["fieldname"])
	if not table_df or table_df.fieldtype not in table_fields:
		errors.append(f"{change['fieldname']}: no es una tabla hija.")
		return None, None, None
	if table_df.read_only or not has_field_permlevel(meta, table_df, "write"):
		errors.append(f"{change['fieldname']}: tabla hija no editable.")
		return table_df, None, None
	child_meta = frappe.get_meta(table_df.options)
	row = None
	if change["operation"] != "add_child":
		row = next(
			(candidate for candidate in doc.get(change["fieldname"]) or [] if candidate.name == change["child_name"]),
			None,
		)
		if not row:
			errors.append(f"{change['fieldname']}: fila hija inexistente o ajena al documento.")
	return table_df, child_meta, row


def _validate_child_change(doc, meta, change, errors):
	table_df, child_meta, row = _child_context(doc, meta, change, errors)
	if not child_meta:
		return
	allowed = writable_fieldnames(child_meta, parenttype=meta.name)
	if change["operation"] == "add_child":
		for child_fieldname in change["value"]:
			if child_fieldname not in allowed or child_fieldname in SYSTEM_IMMUTABLE_FIELDS:
				errors.append(f"{change['fieldname']}.{child_fieldname}: campo hijo no editable.")
	elif change["operation"] == "update_child" and row:
		child_fieldname = change["child_fieldname"]
		df = child_meta.get_field(child_fieldname)
		if child_fieldname not in allowed or child_fieldname in SYSTEM_IMMUTABLE_FIELDS:
			errors.append(f"{change['fieldname']}.{child_fieldname}: campo hijo no editable.")
		elif _canonical(row.get(child_fieldname)) != _canonical(
			cast(df.fieldtype, change["original"])
		):
			errors.append(f"{change['fieldname']}.{child_fieldname}: el valor original ya no coincide.")
	if doc.docstatus == 1 and table_df and not table_df.allow_on_submit:
		errors.append(f"{change['fieldname']}: no se permite después de enviar.")


def _validate_document_changes(doctype, name, changes, *, lock=False):
	meta = get_doctype_meta(doctype)
	frappe.has_permission(doctype, "write", throw=True)
	if lock:
		table = frappe.qb.DocType(doctype)
		locked = (
			frappe.qb.from_(table)
			.select(table.name, table.modified, table.docstatus)
			.where(table.name == name)
			.for_update()
		).run(as_dict=True)
		if not locked:
			frappe.throw(f"Documento inexistente: {doctype} {name}")
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	writable = writable_fieldnames(meta)
	errors = []
	if doc.docstatus == 2:
		errors.append("El documento está cancelado.")
	for change in changes:
		if cstr(doc.modified) != change["snapshot_modified"]:
			errors.append(f"{change['fieldname']}: conflicto; el documento cambió desde la consulta.")
		errors.extend(validate_change_policies(doc, change))
		if change["operation"] in {"add_child", "update_child", "delete_child"}:
			_validate_child_change(doc, meta, change, errors)
			continue
		df = meta.get_field(change["fieldname"])
		if change["fieldname"] not in writable or not df:
			errors.append(f"{change['fieldname']}: campo no editable.")
			continue
		if doc.docstatus == 1 and not df.allow_on_submit:
			errors.append(f"{change['fieldname']}: no se permite después de enviar.")
		if _canonical(doc.get(change["fieldname"])) != _canonical(
			cast(df.fieldtype, change["original"])
		):
			errors.append(f"{change['fieldname']}: el valor original ya no coincide.")
	return doc, meta, errors


def _target_value(change, df):
	if change["operation"] == "clear":
		return None
	return cast(df.fieldtype, change["value"])


def _preview_change(doc, meta, change):
	if change["operation"] in {"set", "clear"}:
		df = meta.get_field(change["fieldname"])
		new_value = _target_value(change, df) if df else change.get("value")
		return {
			"fieldname": change["fieldname"],
			"operation": change["operation"],
			"original": doc.get(change["fieldname"]),
			"value": new_value,
			"changed": _canonical(doc.get(change["fieldname"])) != _canonical(new_value),
		}
	result = {
		"fieldname": change["fieldname"],
		"operation": change["operation"],
		"child_name": change.get("child_name"),
	}
	if change["operation"] == "add_child":
		result["value"] = change["value"]
	elif change["operation"] == "update_child":
		result.update(
			{
				"child_fieldname": change["child_fieldname"],
				"original": change["original"],
				"value": change["value"],
			}
		)
	return result


def _validate_candidate_document(doc):
	"""Run Frappe's pre-save validation pipeline and always discard DB side effects.

	Controllers can inspect ``frappe.flags.in_bimap_data_engine_preview`` to avoid
	non-transactional integrations during preview. Database writes accidentally
	performed by validation hooks are rolled back to the local savepoint.
	"""
	savepoint = f"bde_preview_{frappe.generate_hash(length=10)}"
	previous_flag = getattr(frappe.flags, "in_bimap_data_engine_preview", False)
	frappe.db.savepoint(savepoint)
	try:
		frappe.flags.in_bimap_data_engine_preview = True
		doc._action = "update_after_submit" if doc.docstatus == 1 else "save"
		doc._set_defaults()
		doc.set_parent_in_children()
		doc.set_name_in_children()
		doc.validate_higher_perm_levels()
		doc._validate_links()
		doc.run_before_save_methods()
		doc._validate()
		if doc._action == "update_after_submit":
			doc.validate_update_after_submit()
		doc.set_docstatus()
	finally:
		frappe.db.rollback(save_point=savepoint)
		frappe.flags.in_bimap_data_engine_preview = previous_flag


def preview_changes(changes):
	results = []
	for (doctype, name), document_changes in group_changes(changes).items():
		doc, meta, errors = _validate_document_changes(doctype, name, document_changes)
		preview_rows = [_preview_change(doc, meta, change) for change in document_changes]
		if not errors:
			try:
				doc._doc_before_save = frappe.get_doc(doctype, name)
				for change in document_changes:
					_apply_change(doc, meta, change)
				_validate_candidate_document(doc)
			except Exception as exc:
				errors.append(f"Validación ERPNext: {cstr(exc)}")
				frappe.clear_messages()
		results.append(
			{
				"doctype": doctype,
				"name": name,
				"valid": not errors,
				"errors": errors,
				"changes": preview_rows,
			}
		)
	return {"valid": all(result["valid"] for result in results), "documents": results}


def _cast_child_values(child_meta, values):
	return {
		fieldname: cast(child_meta.get_field(fieldname).fieldtype, value)
		for fieldname, value in values.items()
	}


def _apply_change(doc, meta, change):
	if change["operation"] in {"set", "clear"}:
		df = meta.get_field(change["fieldname"])
		new_value = _target_value(change, df)
		if _canonical(doc.get(change["fieldname"])) == _canonical(new_value):
			return False
		doc.set(change["fieldname"], new_value)
		return True
	table_df = meta.get_field(change["fieldname"])
	child_meta = frappe.get_meta(table_df.options)
	if change["operation"] == "add_child":
		doc.append(change["fieldname"], _cast_child_values(child_meta, change["value"]))
		return True
	row = next(row for row in doc.get(change["fieldname"]) if row.name == change["child_name"])
	if change["operation"] == "delete_child":
		doc.remove(row)
		return True
	df = child_meta.get_field(change["child_fieldname"])
	new_value = cast(df.fieldtype, change["value"])
	if _canonical(row.get(change["child_fieldname"])) == _canonical(new_value):
		return False
	row.set(change["child_fieldname"], new_value)
	return True


def _audit_entry(doc, change):
	if change["operation"] in {"set", "clear"}:
		return {
			"operation": change["operation"],
			"fieldname": change["fieldname"],
			"original": doc.get(change["fieldname"]),
			"value": change.get("value"),
		}
	if change["operation"] == "add_child":
		return {
			"operation": "add_child",
			"table_field": change["fieldname"],
			"value": change["value"],
		}
	row = next(row for row in doc.get(change["fieldname"]) if row.name == change["child_name"])
	if change["operation"] == "delete_child":
		return {
			"operation": "delete_child",
			"table_field": change["fieldname"],
			"child_name": row.name,
			"original": row.as_dict(no_nulls=False),
		}
	return {
		"operation": "update_child",
		"table_field": change["fieldname"],
		"child_name": row.name,
		"fieldname": change["child_fieldname"],
		"original": row.get(change["child_fieldname"]),
		"value": change["value"],
	}


def apply_changes(changes, *, operation_id=None):
	from bimap_data_engine.services.audit import record_changes

	operation_id = operation_id or frappe.generate_hash(length=20)
	results = []
	for (doctype, name), document_changes in group_changes(changes).items():
		doc, meta, errors = _validate_document_changes(doctype, name, document_changes, lock=True)
		if errors:
			frappe.throw("; ".join(dict.fromkeys(errors)), title="Cambios no aplicados")
		changed_operations = []
		audit_entries = []
		for change in document_changes:
			audit_entry = _audit_entry(doc, change)
			if _apply_change(doc, meta, change):
				if change["operation"] == "add_child":
					audit_entry["_child_row"] = doc.get(change["fieldname"])[-1]
				changed_operations.append(change["operation"])
				audit_entries.append(audit_entry)
		if changed_operations:
			doc.save()
			for audit_entry in audit_entries:
				child_row = audit_entry.pop("_child_row", None)
				if child_row:
					audit_entry["child_name"] = child_row.name
			record_changes(operation_id, doctype, name, audit_entries)
		results.append(
			{
				"doctype": doctype,
				"name": name,
				"modified": cstr(doc.modified),
				"changed_fields": sorted({change["fieldname"] for change in document_changes}),
				"operations": changed_operations,
			}
		)
	return {"operation_id": operation_id, "documents": results}
