"""Compare a normalized AlphaERP package with the active ERPNext site."""

from __future__ import annotations

from collections import Counter

import frappe


def _sheet_rows(workbook, name):
	return next((sheet["rows"] for sheet in workbook.get("sheets", []) if sheet["name"] == name), [])


def _existing_values(doctype, fieldname):
	if fieldname != "name" and not frappe.get_meta(doctype).has_field(fieldname):
		return set()
	return {str(value).strip() for value in frappe.get_all(doctype, pluck=fieldname) if value not in (None, "")}


def _actions(rows, source_field, existing):
	counts = Counter()
	for row in rows:
		key = str(row.get(source_field) or "").strip()
		counts["invalid" if not key else "update" if key in existing else "create"] += 1
	return dict(counts)


def reconcile_workbook(workbook):
	"""Return deterministic create/update counts and required equivalences; never write."""
	customers = _sheet_rows(workbook, "Clientes")
	suppliers = _sheet_rows(workbook, "Proveedores")
	items = _sheet_rows(workbook, "Productos")
	uoms = _sheet_rows(workbook, "Unidades")
	currencies = _sheet_rows(workbook, "Monedas")
	groups = {row.get("Ruta grupo de artículos") for row in items if row.get("Ruta grupo de artículos")}

	existing_customers = _existing_values("Customer", "bimap_customer_number")
	existing_suppliers = _existing_values("Supplier", "bimap_supplier_number")
	existing_items = _existing_values("Item", "name")
	existing_uoms = _existing_values("UOM", "name")
	uoms_by_folded_name = {name.casefold(): name for name in existing_uoms}
	existing_currencies = _existing_values("Currency", "name")
	existing_groups = _existing_values("Item Group", "name")

	uom_equivalences = []
	for row in uoms:
		key = str(row.get("Unidad AlphaERP") or "").strip()
		description = str(row.get("Descripción") or "").strip()
		match = next((
			uoms_by_folded_name[candidate.casefold()]
			for candidate in (key, description)
			if candidate and candidate.casefold() in uoms_by_folded_name
		), "")
		uom_equivalences.append({
			"source": key, "description": description, "sat": row.get("Unidad SAT"),
			"target": match, "status": "reuse" if match else "review",
		})

	currency_equivalences = []
	for row in currencies:
		iso = str(row.get("Moneda ISO") or "").strip()
		currency_equivalences.append({
			"source": str(row.get("Moneda AlphaERP") or ""), "target": iso,
			"status": "reuse" if iso in existing_currencies else "missing",
		})

	company = frappe.defaults.get_global_default("company")
	return {
		"mode": "preview",
		"writes_performed": False,
		"company": company,
		"source_fingerprint": workbook.get("source", {}).get("manifest", {}).get("fingerprint"),
		"entities": {
			"Customer": _actions(customers, "Clave AlphaERP", existing_customers),
			"Supplier": _actions(suppliers, "Clave AlphaERP", existing_suppliers),
			"Item": _actions(items, "Clave AlphaERP", existing_items),
		},
		"equivalences": {
			"currencies": currency_equivalences,
			"uoms": uom_equivalences,
			"item_groups": [{
				# Item Group names are globally unique in ERPNext, while AlphaERP
				# repeats terminal labels below multiple parents. Preserve the full
				# path as the deterministic target key.
				"source": group, "target": group,
				"status": "reuse" if group in existing_groups else "create",
			} for group in sorted(groups)],
		},
		"fiscal": {
			"profiles": len(_sheet_rows(workbook, "Perfiles fiscales")),
			"status": "requires_template_plan",
			"note": "Los perfiles se resolverán con Tax Category, Tax Rule, plantillas e Item Tax Template; no se crean por inferencia.",
		},
		"source_issues": workbook.get("issue_summary", {}),
	}
