"""Persistent, validated AlphaERP to ERPNext equivalences."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cstr, flt


DOCTYPE = "BIMAP AlphaERP Equivalence"
ALLOWED_TYPES = {
	"UOM", "Customer Tax", "Supplier Tax", "Customer Commercial", "Supplier Commercial",
	"Item Group", "Source Issue",
}
ALLOWED_RESOLUTIONS = {"Reuse", "Create", "Ignore", "Packaging", "Variant"}


def mapping_key(mapping_type, source_key):
	return f"AlphaERP|{mapping_type}|{cstr(source_key).strip()}"


def get_saved_equivalences():
	rows = frappe.get_all(
		DOCTYPE,
		fields=["name", "mapping_type", "source_key", "source_label", "resolution", "target_doctype", "target_name", "settings_json"],
		limit_page_length=0,
	)
	result = {}
	for row in rows:
		row["settings"] = frappe.parse_json(row.pop("settings_json") or "{}")
		result[mapping_key(row["mapping_type"], row["source_key"])] = row
	return result


def _validate_target(mapping_type, resolution, target_name, settings, company):
	if resolution == "Ignore":
		return None
	if mapping_type == "Source Issue":
		target_doctype = cstr(settings.get("target_doctype")).strip()
		if resolution != "Reuse" or target_doctype not in {"Customer", "Supplier", "Item", "Price List"}:
			frappe.throw("La incidencia sólo puede excluirse o relacionarse con un registro permitido.")
		if not target_name or not frappe.db.exists(target_doctype, target_name):
			frappe.throw(f"El registro destino no existe: {target_doctype}/{target_name or '(vacío)'}.")
		return target_doctype
	if mapping_type == "UOM":
		if not target_name:
			frappe.throw("Cada unidad requiere una unidad destino.")
		if resolution in {"Reuse", "Packaging", "Variant"} and not frappe.db.exists("UOM", target_name):
			frappe.throw(f"La unidad destino no existe: {target_name}.")
		if resolution == "Packaging" and flt(settings.get("conversion_factor")) <= 0:
			frappe.throw("Cada empaque requiere un factor de conversión mayor que cero.")
		return "UOM"
	if mapping_type == "Item Group":
		if not target_name:
			frappe.throw("Cada grupo requiere un grupo destino.")
		if resolution == "Reuse" and not frappe.db.exists("Item Group", target_name):
			frappe.throw(f"El grupo de artículos destino no existe: {target_name}.")
		return "Item Group"
	if mapping_type in {"Customer Commercial", "Supplier Commercial"}:
		doctype = "Customer Group" if mapping_type == "Customer Commercial" else "Supplier Group"
		if not target_name:
			frappe.throw("Cada clasificación comercial requiere un grupo destino.")
		if resolution == "Reuse" and not frappe.db.exists(doctype, target_name):
			frappe.throw(f"El grupo comercial destino no existe: {target_name}.")
		return doctype

	if resolution == "Reuse":
		if not target_name or not frappe.db.exists("Tax Category", target_name):
			frappe.throw(f"La categoría fiscal destino no existe: {target_name or '(vacía)'}.")
	if resolution == "Create" and not target_name:
		frappe.throw("La configuración fiscal nueva requiere un nombre.")
	existing_template = cstr(settings.get("existing_template")).strip()
	if existing_template:
		doctype = "Sales Taxes and Charges Template" if mapping_type == "Customer Tax" else "Purchase Taxes and Charges Template"
		if not frappe.db.exists(doctype, {"name": existing_template, "company": company, "disabled": 0}):
			frappe.throw(f"La plantilla fiscal existente no es válida: {existing_template}.")
	if resolution == "Create" and not existing_template and not cstr(settings.get("template_name")).strip():
		frappe.throw("La plantilla fiscal nueva requiere un nombre.")
	for fieldname, doctype in (
		("sales_template", "Sales Taxes and Charges Template"),
		("purchase_template", "Purchase Taxes and Charges Template"),
	):
		value = cstr(settings.get(fieldname)).strip()
		if not value:
			continue
		if not frappe.db.exists(doctype, {"name": value, "company": company, "disabled": 0}):
			frappe.throw(f"Plantilla fiscal inválida: {value}.")
	return "Tax Category"


def save_equivalences(rows, *, allowed_sources, fingerprint, company):
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list) or len(rows) > 1000:
		frappe.throw("El conjunto de equivalencias es inválido.")
	saved = []
	for values in rows:
		mapping_type = cstr(values.get("mapping_type")).strip()
		source_key = cstr(values.get("source_key")).strip()
		resolution = cstr(values.get("resolution")).strip()
		target_name = cstr(values.get("target_name")).strip()
		settings = values.get("settings") or {}
		if mapping_type not in ALLOWED_TYPES or resolution not in ALLOWED_RESOLUTIONS:
			frappe.throw("Tipo o resolución de equivalencia inválidos.")
		if source_key not in allowed_sources.get(mapping_type, set()):
			frappe.throw(f"Clave AlphaERP no reconocida: {mapping_type}/{source_key}.")
		if not isinstance(settings, dict):
			frappe.throw("La configuración de equivalencia debe ser un objeto.")
		settings = {
			key: cstr(settings.get(key)).strip()
			for key in (
				"sales_template", "purchase_template", "conversion_factor", "note", "target_doctype",
				"classification_mode", "brand_name",
				"commercial_tier", "source_profile",
				"template_name", "existing_template",
			)
			if settings.get(key) not in (None, "")
		}
		target_doctype = _validate_target(mapping_type, resolution, target_name, settings, company)
		key = mapping_key(mapping_type, source_key)
		name = frappe.db.get_value(DOCTYPE, {"mapping_key": key}, "name")
		doc = frappe.get_doc(DOCTYPE, name) if name else frappe.new_doc(DOCTYPE)
		doc.update({
			"source_system": "AlphaERP",
			"source_fingerprint": fingerprint,
			"mapping_type": mapping_type,
			"source_key": source_key,
			"source_label": cstr(values.get("source_label")).strip(),
			"resolution": resolution,
			"target_doctype": target_doctype,
			"target_name": target_name if resolution != "Ignore" else None,
			"settings_json": json.dumps(settings, ensure_ascii=False, sort_keys=True),
			"mapping_key": key,
		})
		doc.save()
		saved.append(doc.name)
	return saved
