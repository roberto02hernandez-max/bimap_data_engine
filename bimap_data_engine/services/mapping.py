"""Metadata-driven, declarative external-column mappings."""

import json
import re
import unicodedata
from difflib import SequenceMatcher

import frappe
from frappe.model import table_fields
from frappe.utils.data import cast

from bimap_data_engine.services.metadata import SYSTEM_IMMUTABLE_FIELDS, writable_fieldnames
from bimap_data_engine.services.metadata import has_field_permlevel


TRANSFORMS = {"none", "trim", "upper", "lower"}


def _parse_json(value, expected_type, label):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, expected_type):
		frappe.throw(f"{label}: formato JSON inválido.")
	return value


def _normal(value):
	value = unicodedata.normalize("NFKD", str(value or ""))
	return re.sub(r"[^a-z0-9]+", "", value.encode("ascii", "ignore").decode().lower())


def _target_meta(doctype, table_field=None):
	frappe.has_permission(doctype, "write", throw=True)
	parent_meta = frappe.get_meta(doctype)
	if not table_field:
		return parent_meta, writable_fieldnames(parent_meta)
	table_df = parent_meta.get_field(table_field)
	if not table_df or table_df.fieldtype not in table_fields:
		frappe.throw("La tabla hija indicada no existe.")
	if table_df.read_only or not has_field_permlevel(parent_meta, table_df, "write"):
		frappe.throw("La tabla hija indicada no es editable.")
	child_meta = frappe.get_meta(table_df.options)
	return child_meta, writable_fieldnames(child_meta, parenttype=doctype)


def suggest_mapping(doctype, headers, table_field=None):
	headers = _parse_json(headers, list, "Encabezados")
	meta, allowed = _target_meta(doctype, table_field)
	fields = [df for df in meta.fields if df.fieldname in allowed and df.fieldtype not in table_fields]
	suggestions = []
	for header in headers:
		normal_header = _normal(header)
		best = None
		for df in fields:
			candidates = [_normal(df.fieldname), _normal(df.label)]
			score = max(SequenceMatcher(None, normal_header, candidate).ratio() for candidate in candidates)
			if normal_header in candidates:
				score = 1.0
			if best is None or score > best[0]:
				best = (score, df)
		if best and best[0] >= 0.68:
			suggestions.append(
				{"source": header, "target": best[1].fieldname, "label": best[1].label, "score": round(best[0], 3)}
			)
	return suggestions


def validate_mapping(doctype, mapping, defaults=None, table_field=None):
	mapping = _parse_json(mapping, list, "Mapeo")
	defaults = _parse_json(defaults or {}, dict, "Valores predeterminados")
	meta, allowed = _target_meta(doctype, table_field)
	validated = []
	targets = set()
	for index, entry in enumerate(mapping, start=1):
		if not isinstance(entry, dict):
			frappe.throw(f"Mapeo {index}: formato inválido.")
		source = str(entry.get("source") or "").strip()
		target = str(entry.get("target") or "").strip()
		transform = str(entry.get("transform") or "none").strip().lower()
		df = meta.get_field(target)
		if not source or not df or target not in allowed or target in SYSTEM_IMMUTABLE_FIELDS:
			frappe.throw(f"Mapeo {index}: campo destino no editable.")
		if df.fieldtype in table_fields:
			frappe.throw(f"Mapeo {index}: una tabla hija requiere su propio mapeo.")
		if target in targets:
			frappe.throw(f"Mapeo {index}: el campo {target} está repetido.")
		if transform not in TRANSFORMS:
			frappe.throw(f"Mapeo {index}: transformación no permitida.")
		targets.add(target)
		validated.append({"source": source, "target": target, "transform": transform})
	for target in defaults:
		df = meta.get_field(target)
		if not df or target not in allowed or target in SYSTEM_IMMUTABLE_FIELDS or df.fieldtype in table_fields:
			frappe.throw(f"Predeterminado {target}: campo destino no editable.")
	return {"mapping": validated, "defaults": defaults, "target_doctype": meta.name}


def _transform(value, operation):
	if value is None or operation == "none":
		return value
	if operation == "trim":
		return str(value).strip()
	if operation == "upper":
		return str(value).upper()
	if operation == "lower":
		return str(value).lower()
	return value


def map_row(doctype, row, mapping, defaults=None, table_field=None):
	row = _parse_json(row, dict, "Fila")
	validated = validate_mapping(doctype, mapping, defaults, table_field)
	meta = frappe.get_meta(validated["target_doctype"])
	result = {}
	for entry in validated["mapping"]:
		if entry["source"] not in row:
			continue
		value = _transform(row.get(entry["source"]), entry["transform"])
		# Empty import cells mean "let Frappe/ERPNext provide its normal default".
		# They must not overwrite defaults with an explicit empty value.
		if value is None or value == "":
			continue
		result[entry["target"]] = cast(meta.get_field(entry["target"]).fieldtype, value)
	for target, value in validated["defaults"].items():
		if target not in result or result[target] in (None, ""):
			result[target] = cast(meta.get_field(target).fieldtype, value)
	return result


def serialize(value):
	return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
