"""Prepare spreadsheet rows inside an unsaved ERPNext document without persisting it."""

from collections import defaultdict

import frappe
from frappe.model import table_fields
from frappe.utils import cstr

from bimap_data_engine.services.adapters import prepare_import_document
from bimap_data_engine.services.metadata import has_field_permlevel, writable_fieldnames
from bimap_data_engine.services.mapping import map_row, validate_mapping


VALID_MERGE_POLICIES = {"append", "consolidate", "update", "reject_duplicates"}
DEFAULT_MATCH_FIELDS = ("item_code", "uom", "warehouse")


def _object(value, label):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, dict):
		frappe.throw(f"{label}: formato inválido.")
	return value


def _rows(value, label):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
		frappe.throw(f"{label}: formato inválido.")
	return value


def _clean_values(values, allowed):
	return {key: value for key, value in values.items() if key in allowed}


def _match_key(row, match_fields):
	return tuple(cstr(row.get(field)).strip() for field in match_fields)


def _merge_rows(existing_rows, imported_rows, policy, match_fields):
	if policy == "append":
		return [*existing_rows, *imported_rows], {"added": len(imported_rows), "updated": 0}
	positions = defaultdict(list)
	for index, row in enumerate(existing_rows):
		positions[_match_key(row, match_fields)].append(index)
	merged = [dict(row) for row in existing_rows]
	added = 0
	updated = 0
	for row in imported_rows:
		key = _match_key(row, match_fields)
		matches = positions.get(key) or []
		if not matches:
			positions[key].append(len(merged))
			merged.append(dict(row))
			added += 1
			continue
		if policy == "reject_duplicates":
			frappe.throw(f"Partida duplicada: {' / '.join(key)}.")
		index = matches[0]
		if policy == "consolidate":
			merged[index]["qty"] = float(merged[index].get("qty") or 0) + float(row.get("qty") or 0)
		else:
			merged[index].update(row)
		updated += 1
	return merged, {"added": added, "updated": updated}


def map_imported_rows(parent_doctype, table_field, rows, mapping, defaults=None):
	"""Map external rows to a child table and keep failures addressable in the source grid."""
	rows = _rows(rows, "Filas externas")
	validated = validate_mapping(parent_doctype, mapping, defaults, table_field)
	records = []
	errors = []
	for index, row in enumerate(rows, start=2):
		try:
			records.append({
				"source_row": index,
				"values": map_row(parent_doctype, row, mapping, defaults, table_field),
			})
		except Exception as exc:
			message = cstr(exc)
			source_field = None
			target_field = getattr(exc, "fieldname", None)
			for entry in validated["mapping"]:
				if entry["target"].lower() in message.lower():
					source_field = entry["source"]
					target_field = entry["target"]
					break
			errors.append({
				"sheet": None,
				"row": index,
				"source_field": source_field,
				"target_field": target_field,
				"severity": "error",
				"code": "line_mapping",
				"message": message,
				"error": message,
			})
			frappe.clear_messages()
	return {"valid": not errors, "records": records, "errors": errors}


def prepare_line_import(
	parent_doctype,
	table_field,
	parent_values,
	existing_rows,
	imported_rows,
	*,
	merge_policy="append",
	match_fields=None,
):
	"""Run native preparation for existing + imported rows and always roll back side effects."""
	parent_values = _object(parent_values, "Encabezado")
	existing_rows = _rows(existing_rows, "Partidas existentes")
	imported_rows = _rows(imported_rows, "Partidas importadas")
	merge_policy = cstr(merge_policy).strip().lower()
	if merge_policy not in VALID_MERGE_POLICIES:
		frappe.throw("Política de combinación inválida.")
	match_fields = frappe.parse_json(match_fields) if isinstance(match_fields, str) else match_fields
	match_fields = tuple(match_fields or DEFAULT_MATCH_FIELDS)
	if not match_fields or not all(isinstance(field, str) and field.strip() for field in match_fields):
		frappe.throw("Campos de coincidencia inválidos.")

	frappe.has_permission(parent_doctype, "create", throw=True)
	meta = frappe.get_meta(parent_doctype)
	table_df = meta.get_field(table_field)
	if (
		not table_df
		or table_df.fieldtype not in table_fields
		or table_df.read_only
		or not has_field_permlevel(meta, table_df, "write")
	):
		frappe.throw("La tabla hija no es editable.")
	parent_allowed = writable_fieldnames(meta)
	child_meta = frappe.get_meta(table_df.options)
	child_allowed = writable_fieldnames(child_meta, parenttype=parent_doctype)
	if any(field not in child_allowed for field in match_fields):
		frappe.throw("Un campo de coincidencia no es editable en la tabla hija.")
	clean_existing = [_clean_values(row, child_allowed) for row in existing_rows]
	clean_imported = [_clean_values(row, child_allowed) for row in imported_rows]
	merged_rows, merge_result = _merge_rows(
		clean_existing, clean_imported, merge_policy, match_fields
	)

	doc = frappe.get_doc({
		"doctype": parent_doctype,
		**_clean_values(parent_values, parent_allowed),
	})
	for row in merged_rows:
		doc.append(table_field, row)
	doc.check_permission("create")
	savepoint = f"bde_line_preview_{frappe.generate_hash(length=10)}"
	previous_flag = getattr(frappe.flags, "in_bimap_data_engine_preview", False)
	frappe.db.savepoint(savepoint)
	try:
		frappe.flags.in_bimap_data_engine_preview = True
		doc.set("__islocal", True)
		doc._action = "save"
		doc._set_defaults()
		doc.set_user_and_timestamp()
		doc.set_docstatus()
		doc._validate_links()
		doc.run_method("before_insert")
		doc.set_new_name(set_child_names=True)
		doc.set_parent_in_children()
		doc.set_name_in_children()
		doc.validate_higher_perm_levels()
		doc.flags.in_insert = True
		prepare_import_document(doc)
		doc.run_before_save_methods()
		doc._validate()
	finally:
		doc.flags.in_insert = False
		frappe.db.rollback(save_point=savepoint)
		frappe.flags.in_bimap_data_engine_preview = previous_flag

	prepared_rows = []
	for row in doc.get(table_field) or []:
		prepared_rows.append({
			field: row.get(field)
			for field in child_allowed
			if row.get(field) not in (None, "")
		})
	return {
		"doctype": parent_doctype,
		"table_field": table_field,
		"rows": prepared_rows,
		"merge": {"policy": merge_policy, **merge_result, "total": len(prepared_rows)},
		"totals": {
			field: doc.get(field)
			for field in ("total_qty", "total", "net_total", "total_taxes_and_charges", "grand_total", "rounded_total")
			if meta.has_field(field)
		},
	}
