"""Paged, non-writing AlphaERP migration previews."""

from __future__ import annotations

import frappe
from frappe.utils import cint

from bimap_data_engine.services.alphaerp.equivalences import get_saved_equivalences, mapping_key


CATALOGS = {"Customer": "Clientes", "Supplier": "Proveedores", "Item": "Productos"}
MAX_PAGE_LENGTH = 200


def _sheet_rows(workbook, name):
	return next((sheet["rows"] for sheet in workbook["sheets"] if sheet["name"] == name), [])


def _mapping(saved, mapping_type, source_key):
	return saved.get(mapping_key(mapping_type, source_key))


def _destination_action(doctype, source_key):
	fieldname = {"Customer": "bimap_customer_number", "Supplier": "bimap_supplier_number", "Item": "name"}[doctype]
	filters = {fieldname: source_key} if fieldname != "name" else source_key
	name = frappe.db.get_value(doctype, filters, "name")
	return ("update", name) if name else ("create", None)


def _party_preview(doctype, row, saved):
	is_customer = doctype == "Customer"
	key = row["Clave AlphaERP"]
	mapping_type = "Customer Tax" if is_customer else "Supplier Tax"
	tax_mapping = _mapping(saved, mapping_type, row.get("Tipo fiscal AlphaERP"))
	commercial_type = "Customer Commercial" if is_customer else "Supplier Commercial"
	commercial_mapping = _mapping(saved, commercial_type, row.get("Tipo fiscal AlphaERP"))
	action, existing_name = _destination_action(doctype, key)
	issues = []
	if row.get("Tipo fiscal AlphaERP") and not tax_mapping:
		issues.append({"field": "Tipo fiscal AlphaERP", "code": "missing_equivalence", "message": "Falta elegir la categoría fiscal."})
	elif tax_mapping and tax_mapping["resolution"] == "Ignore":
		issues.append({"field": "Tipo fiscal AlphaERP", "code": "ignored", "severity": "warning", "message": "El perfil fiscal será omitido por decisión del usuario."})
	if row.get("Tipo fiscal AlphaERP") and not commercial_mapping:
		issues.append({"field": "Clasificación comercial", "code": "missing_commercial_equivalence", "message": "Falta decidir el grupo comercial."})
	return {
		"source_key": key,
		"action": action,
		"existing_name": existing_name,
		"values": {
			"name": row["Nombre"],
			"tax_id": row.get("RFC"),
			"currency": row.get("Moneda ISO"),
			"tax_category": tax_mapping.get("target_name") if tax_mapping and tax_mapping["resolution"] != "Ignore" else None,
			"source_tax_profile": row.get("Tipo fiscal AlphaERP"),
			"customer_group" if is_customer else "supplier_group": commercial_mapping.get("target_name") if commercial_mapping and commercial_mapping["resolution"] != "Ignore" else None,
			"bimap_alphaerp_commercial_classification": commercial_mapping.get("settings", {}).get("source_profile") if commercial_mapping else row.get("Tipo fiscal AlphaERP"),
			"bimap_commercial_tier": commercial_mapping.get("settings", {}).get("commercial_tier") if commercial_mapping else None,
			"price_list": row.get("Lista de precios AlphaERP") if is_customer else None,
			"zone": row.get("Zona AlphaERP") if is_customer else None,
			"subzone": row.get("Subzona AlphaERP") if is_customer else None,
		},
		"issues": issues,
	}


def _item_preview(row, saved):
	key = row["Clave AlphaERP"]
	uom_mapping = _mapping(saved, "UOM", row.get("Unidad AlphaERP"))
	group_mapping = _mapping(saved, "Item Group", row.get("Ruta grupo de artículos"))
	action, existing_name = _destination_action("Item", key)
	issues = []
	if not uom_mapping:
		issues.append({"field": "Unidad AlphaERP", "code": "missing_equivalence", "message": "Falta elegir la unidad de inventario."})
	elif uom_mapping["resolution"] == "Ignore":
		issues.append({"field": "Unidad AlphaERP", "code": "ignored_required", "message": "La unidad obligatoria no puede omitirse para este producto."})
	if row.get("Ruta grupo de artículos") and not group_mapping:
		issues.append({"field": "Ruta grupo de artículos", "code": "missing_equivalence", "message": "Falta decidir el grupo de artículos."})
	elif group_mapping and group_mapping["resolution"] == "Ignore":
		issues.append({"field": "Ruta grupo de artículos", "code": "ignored_required", "message": "El grupo obligatorio no puede omitirse para este producto."})
	if row.get("Maneja IEPS") or row.get("Modo IVA") == "Por producto" or row.get("Modo retención IVA") == "Por producto" or row.get("Modo retención ISR") == "Por producto":
		issues.append({"field": "Impuestos", "code": "item_tax_template_required", "severity": "warning", "message": "Se creará o asignará una plantilla fiscal por producto."})
	return {
		"source_key": key,
		"action": action,
		"existing_name": existing_name,
		"values": {
			"item_name": row["Nombre"],
			"description": row.get("Descripción"),
			"item_group": group_mapping.get("target_name") if group_mapping and group_mapping["resolution"] != "Ignore" else None,
			"stock_uom": uom_mapping.get("target_name") if uom_mapping and uom_mapping["resolution"] != "Ignore" else None,
			"source_uom": row.get("Unidad AlphaERP"),
			"has_batch_no": row.get("Maneja lotes"),
			"shelf_life_in_days": row.get("Vida útil días"),
			"sat_product_code": row.get("Clave producto SAT"),
			"source_tax_modes": {
				"vat": row.get("Modo IVA"), "ieps": row.get("Maneja IEPS"),
				"withholding_vat": row.get("Modo retención IVA"),
				"withholding_income": row.get("Modo retención ISR"),
			},
		},
		"issues": issues,
	}


def preview_catalog(workbook, catalog, start=0, page_length=50):
	if catalog not in CATALOGS:
		frappe.throw("Catálogo AlphaERP no reconocido.")
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length), 1), MAX_PAGE_LENGTH)
	rows = _sheet_rows(workbook, CATALOGS[catalog])
	saved = get_saved_equivalences()
	page = rows[start : start + page_length]
	projected = [
		_item_preview(row, saved) if catalog == "Item" else _party_preview(catalog, row, saved)
		for row in page
	]
	blocking = sum(any(issue.get("severity", "error") == "error" for issue in row["issues"]) for row in projected)
	return {
		"catalog": catalog,
		"start": start,
		"page_length": page_length,
		"total": len(rows),
		"next_start": start + len(page) if start + len(page) < len(rows) else None,
		"rows": projected,
		"blocking_rows": blocking,
		"writes_performed": False,
	}
