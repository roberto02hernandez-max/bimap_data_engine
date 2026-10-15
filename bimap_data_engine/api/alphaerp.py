"""System-manager endpoints for the local AlphaERP migration source."""

from collections import Counter
from decimal import Decimal

import frappe
from frappe.utils import flt

from bimap_data_engine.services.alphaerp import normalize_package
from bimap_data_engine.services.alphaerp.equivalences import get_saved_equivalences, save_equivalences as persist_equivalences
from bimap_data_engine.services.alphaerp.migration import preview_catalog as build_catalog_preview
from bimap_data_engine.services.alphaerp.reconcile import reconcile_workbook


def _configured_source():
	frappe.only_for("System Manager")
	path = frappe.conf.get("bimap_alphaerp_source_directory")
	if not path:
		frappe.throw("Configura bimap_alphaerp_source_directory en el sitio antes de leer AlphaERP.")
	return path


@frappe.whitelist(methods=["GET"])
def preview_source():
	"""Read, normalize and reconcile; deliberately performs no ERPNext writes."""
	workbook = normalize_package(_configured_source())
	return {
		"summary": workbook["summary"],
		"issue_summary": workbook["issue_summary"],
		"issues": workbook["issues"],
		"reconciliation": reconcile_workbook(workbook),
	}


@frappe.whitelist(methods=["GET"])
def preview_summary():
	"""Compact status used by the migration entry screen."""
	workbook = normalize_package(_configured_source())
	reconciliation = reconcile_workbook(workbook)
	equivalence_summary = {
		name: dict(Counter(row["status"] for row in rows))
		for name, rows in reconciliation["equivalences"].items()
	}
	return {
		"summary": workbook["summary"],
		"issue_summary": workbook["issue_summary"],
		"fingerprint": reconciliation["source_fingerprint"],
		"company": reconciliation["company"],
		"entities": reconciliation["entities"],
		"equivalences": equivalence_summary,
		"fiscal": reconciliation["fiscal"],
		"writes_performed": False,
	}


def _sheet_rows(workbook, name):
	return next((sheet["rows"] for sheet in workbook["sheets"] if sheet["name"] == name), [])


def _examples(rows, key_field, value, *, limit=3):
	return [
		{"key": row.get("Clave AlphaERP"), "name": row.get("Nombre")}
		for row in rows if row.get(key_field) == value
	][:limit]


def _uom_usage(workbook):
	specs = (
		("Productos", "Unidad AlphaERP", "unidad principal"),
		("Productos", "Unidad de compra", "unidad de compra"),
		("Productos", "Unidad de empaque", "unidad de empaque"),
		("Unidades de producto", "Unidad AlphaERP", "conversión de producto"),
		("Unidades de producto", "Unidad conversión AlphaERP", "destino de conversión"),
		("Relaciones proveedor-producto", "Unidad del proveedor", "relación proveedor-producto"),
	)
	usage = {}
	for sheet, field, label in specs:
		for row in _sheet_rows(workbook, sheet):
			key = str(row.get(field) or "").strip()
			if not key:
				continue
			entry = usage.setdefault(key, {"total": 0, "detail": {}})
			entry["total"] += 1
			entry["detail"][label] = entry["detail"].get(label, 0) + 1
	return usage


def _source_issue_key(issue):
	return "|".join(str(issue.get(field) or "") for field in ("entity", "source_key", "source_field", "code"))


def _issue_target_doctype(issue):
	field = issue.get("source_field") or ""
	if "cliente" in field.lower():
		return "Customer"
	if "proveedor" in field.lower():
		return "Supplier"
	if "producto" in field.lower():
		return "Item"
	if "lista de precios" in field.lower():
		return "Price List"
	return ""


def _rate_key(value):
	"""Return a stable, human-readable rate for grouping fiscal profiles."""
	return format(Decimal(str(value or 0)).normalize(), "f")


def _tax_signatures(tax_profiles):
	groups = {}
	for row in tax_profiles:
		parts = (
			row["mapping_type"], _rate_key(row["iva"]), _rate_key(row["retention_vat"]),
			_rate_key(row["retention_income"]), bool(row["has_ieps"]), bool(row["exempt"]),
		)
		group = groups.setdefault(parts, {
			"signature_key": "|".join(str(part) for part in parts),
			"mapping_type": row["mapping_type"],
			"party_type": row["party_type"],
			"iva": row["iva"],
			"retention_vat": row["retention_vat"],
			"retention_income": row["retention_income"],
			"has_ieps": row["has_ieps"],
			"exempt": row["exempt"],
			"impact": 0,
			"source_profiles": [],
			"examples": [],
		})
		group["impact"] += row["impact"]
		group["source_profiles"].append({
			"source_key": row["source_key"], "source_label": row["source_label"],
			"impact": row["impact"], "examples": row["examples"],
		})
		group["examples"].extend(row["examples"])
	for group in groups.values():
		group["profile_count"] = len(group["source_profiles"])
		group["source_keys"] = [row["source_key"] for row in group["source_profiles"]]
		group["examples"] = group["examples"][:3]
	return sorted(groups.values(), key=lambda row: (row["party_type"], row["iva"], row["retention_vat"], row["retention_income"], row["signature_key"]))


def _template_tax_signature(doc):
	rates = {"iva": 0.0, "retention_vat": 0.0, "retention_income": 0.0, "has_ieps": False}
	for tax in doc.get("taxes") or []:
		rate = flt(tax.get("rate"))
		text = f"{tax.get('account_head') or ''} {tax.get('description') or ''}".upper()
		if not rate:
			continue
		if "IEPS" in text:
			rates["has_ieps"] = True
		elif "ISR" in text:
			rates["retention_income"] += abs(rate)
		elif "IVA" in text and ("RET" in text or rate < 0):
			rates["retention_vat"] += abs(rate)
		elif "IVA" in text:
			rates["iva"] += abs(rate)
		else:
			return None
	return rates


def _suggest_tax_templates(tax_signatures, company):
	by_type = {}
	for mapping_type, doctype in (("Customer Tax", "Sales Taxes and Charges Template"), ("Supplier Tax", "Purchase Taxes and Charges Template")):
		by_type[mapping_type] = []
		for name in frappe.get_all(doctype, filters={"company": company, "disabled": 0}, pluck="name", limit_page_length=0):
			doc = frappe.get_cached_doc(doctype, name)
			signature = _template_tax_signature(doc)
			if signature is not None:
				by_type[mapping_type].append({"name": name, "tax_category": doc.get("tax_category") or "", **signature})
	for row in tax_signatures:
		match = next((template for template in by_type[row["mapping_type"]] if (
			_rate_key(template["iva"]) == _rate_key(row["iva"])
			and _rate_key(template["retention_vat"]) == _rate_key(row["retention_vat"])
			and _rate_key(template["retention_income"]) == _rate_key(row["retention_income"])
			and bool(template["has_ieps"]) == bool(row["has_ieps"])
			and not row["exempt"]
		)), None)
		parts = [f"IVA {_rate_key(row['iva'])}"]
		if flt(row["retention_vat"]):
			parts.append(f"RET IVA {_rate_key(row['retention_vat'])}")
		if flt(row["retention_income"]):
			parts.append(f"RET ISR {_rate_key(row['retention_income'])}")
		if row["has_ieps"]:
			parts.append("IEPS")
		if row["exempt"]:
			parts.append("Exento")
		row["matched_template"] = match["name"] if match else ""
		row["matched_tax_category"] = match["tax_category"] if match else ""
		row["suggested_name"] = " ".join(parts)
	return tax_signatures


COMMERCIAL_TIERS = ("PLATINO", "ORO", "AZUL")


def _commercial_name(label):
	label = str(label or "").strip()
	upper = label.upper()
	for tier in COMMERCIAL_TIERS:
		if upper == tier or upper.endswith(f" {tier}"):
			return label[:-len(tier)].rstrip(" -/") or label, tier
	return label, ""


def _commercial_classifications(tax_profiles, existing_groups):
	groups = {}
	for row in tax_profiles:
		base, tier = _commercial_name(row["source_label"])
		mapping_type = "Customer Commercial" if row["party_type"] == "Cliente" else "Supplier Commercial"
		key = (mapping_type, base.casefold())
		group = groups.setdefault(key, {
			"mapping_type": mapping_type,
			"party_type": row["party_type"],
			"source_key": f"{mapping_type}|{base}",
			"source_label": base,
			"suggested_target": existing_groups.get(mapping_type, {}).get(base.casefold(), ""),
			"target_doctype": "Customer Group" if row["party_type"] == "Cliente" else "Supplier Group",
			"impact": 0,
			"source_profiles": [],
			"examples": [],
			"tiers": [],
		})
		group["impact"] += row["impact"]
		group["source_profiles"].append({
			"source_key": row["source_key"], "source_label": row["source_label"],
			"tier": tier, "impact": row["impact"],
		})
		group["examples"].extend(row["examples"])
		if tier and tier not in group["tiers"]:
			group["tiers"].append(tier)
	for group in groups.values():
		group["examples"] = group["examples"][:3]
		group["profile_count"] = len(group["source_profiles"])
	return sorted(groups.values(), key=lambda row: (row["party_type"], row["source_label"]))


@frappe.whitelist(methods=["GET"])
def get_equivalence_setup():
	workbook = normalize_package(_configured_source())
	reconciliation = reconcile_workbook(workbook)
	company = reconciliation["company"]
	items = _sheet_rows(workbook, "Productos")
	customers = _sheet_rows(workbook, "Clientes")
	suppliers = _sheet_rows(workbook, "Proveedores")
	uom_usage = _uom_usage(workbook)
	uom_status = {row["source"]: row for row in reconciliation["equivalences"]["uoms"]}
	uoms = [{
		"mapping_type": "UOM",
		"source_key": row["Unidad AlphaERP"],
		"source_label": row["Descripción"],
		"sat": row["Unidad SAT"],
		"suggested_target": uom_status.get(row["Unidad AlphaERP"], {}).get("target", ""),
		"impact": uom_usage.get(row["Unidad AlphaERP"], {}).get("total", 0),
		"impact_detail": uom_usage.get(row["Unidad AlphaERP"], {}).get("detail", {}),
		"used": bool(uom_usage.get(row["Unidad AlphaERP"], {}).get("total", 0)),
		"examples": _examples(items, "Unidad AlphaERP", row["Unidad AlphaERP"]),
	} for row in _sheet_rows(workbook, "Unidades")]
	tax_profiles = [{
		"mapping_type": "Customer Tax" if row["Tipo de tercero"] == "Cliente" else "Supplier Tax",
		"source_key": row["Clave fiscal AlphaERP"],
		"source_label": row["Descripción"],
		"party_type": row["Tipo de tercero"],
		"iva": row["IVA"],
		"retention_vat": row["Retención IVA"],
		"retention_income": row["Retención ISR"],
		"has_ieps": row["Maneja IEPS"],
		"exempt": row.get("Exento", False),
		"impact": sum(party.get("Tipo fiscal AlphaERP") == row["Clave fiscal AlphaERP"] for party in (customers if row["Tipo de tercero"] == "Cliente" else suppliers)),
		"examples": _examples(customers if row["Tipo de tercero"] == "Cliente" else suppliers, "Tipo fiscal AlphaERP", row["Clave fiscal AlphaERP"]),
	} for row in _sheet_rows(workbook, "Perfiles fiscales")]
	tax_signatures = _suggest_tax_templates(_tax_signatures(tax_profiles), company)
	existing_groups = {
		"Customer Commercial": {name.casefold(): name for name in frappe.get_all("Customer Group", pluck="name", limit_page_length=0)},
		"Supplier Commercial": {name.casefold(): name for name in frappe.get_all("Supplier Group", pluck="name", limit_page_length=0)},
	}
	commercial_classifications = _commercial_classifications(tax_profiles, existing_groups)
	item_groups = [{
		"mapping_type": "Item Group",
		"source_key": row["source"],
		"source_label": row["source"],
		"suggested_target": row["target"] if row["status"] == "reuse" else "",
		"impact": sum(item.get("Ruta grupo de artículos") == row["source"] for item in items),
		"examples": _examples(items, "Ruta grupo de artículos", row["source"]),
		"levels": [part.strip() for part in row["source"].split("/") if part.strip()],
	} for row in reconciliation["equivalences"]["item_groups"]]
	terminal_frequency = Counter(
		row["levels"][-1] for row in item_groups if len(row["levels"]) >= 3
	)
	existing_brands = set(frappe.get_all("Brand", pluck="name", limit_page_length=0))
	for row in item_groups:
		terminal = row["levels"][-1] if len(row["levels"]) >= 3 else ""
		row["suggest_brand"] = bool(terminal and (terminal in existing_brands or terminal_frequency[terminal] > 1))
		row["brand_name"] = terminal if row["suggest_brand"] else ""
	source_issues = [{
		**issue,
		"mapping_type": "Source Issue",
		"source_key": _source_issue_key(issue),
		"target_doctype": _issue_target_doctype(issue),
	} for issue in workbook.get("issues", [])]
	return {
		"fingerprint": reconciliation["source_fingerprint"],
		"company": company,
		"uoms": uoms,
		"tax_profiles": tax_profiles,
		"tax_signatures": tax_signatures,
		"commercial_classifications": commercial_classifications,
		"item_groups": item_groups,
		"source_issues": source_issues,
		"options": {
			"uoms": frappe.get_all("UOM", pluck="name", order_by="name", limit_page_length=0),
			"item_groups": frappe.get_all("Item Group", pluck="name", order_by="name", limit_page_length=0),
			"tax_categories": frappe.get_all("Tax Category", filters={"disabled": 0}, pluck="name", order_by="name", limit_page_length=0),
			"sales_templates": frappe.get_all("Sales Taxes and Charges Template", filters={"company": company, "disabled": 0}, pluck="name", order_by="name", limit_page_length=0),
			"purchase_templates": frappe.get_all("Purchase Taxes and Charges Template", filters={"company": company, "disabled": 0}, pluck="name", order_by="name", limit_page_length=0),
			"customer_groups": frappe.get_all("Customer Group", pluck="name", order_by="name", limit_page_length=0),
			"supplier_groups": frappe.get_all("Supplier Group", pluck="name", order_by="name", limit_page_length=0),
		},
		"commercial_fields": {
			"customer_tier": frappe.get_meta("Customer").has_field("bimap_commercial_tier"),
			"customer_source": frappe.get_meta("Customer").has_field("bimap_alphaerp_commercial_classification"),
			"supplier_tier": frappe.get_meta("Supplier").has_field("bimap_commercial_tier"),
			"supplier_source": frappe.get_meta("Supplier").has_field("bimap_alphaerp_commercial_classification"),
		},
		"saved": get_saved_equivalences(),
	}


@frappe.whitelist(methods=["POST"])
def save_equivalence_setup(rows):
	path = _configured_source()
	workbook = normalize_package(path)
	fingerprint = workbook["source"]["manifest"]["fingerprint"]
	profiles = _sheet_rows(workbook, "Perfiles fiscales")
	issues = workbook.get("issues", [])
	allowed_sources = {
		"UOM": {row["Unidad AlphaERP"] for row in _sheet_rows(workbook, "Unidades")},
		"Customer Tax": {row["Clave fiscal AlphaERP"] for row in profiles if row["Tipo de tercero"] == "Cliente"},
		"Supplier Tax": {row["Clave fiscal AlphaERP"] for row in profiles if row["Tipo de tercero"] == "Proveedor"},
		"Customer Commercial": {row["Clave fiscal AlphaERP"] for row in profiles if row["Tipo de tercero"] == "Cliente"},
		"Supplier Commercial": {row["Clave fiscal AlphaERP"] for row in profiles if row["Tipo de tercero"] == "Proveedor"},
		"Item Group": {row["Ruta grupo de artículos"] for row in _sheet_rows(workbook, "Productos") if row.get("Ruta grupo de artículos")},
		"Source Issue": {_source_issue_key(issue) for issue in issues},
	}
	company = frappe.defaults.get_global_default("company")
	names = persist_equivalences(
		rows,
		allowed_sources=allowed_sources,
		fingerprint=fingerprint,
		company=company,
	)
	frappe.db.commit()
	return {"saved": len(names), "fingerprint": fingerprint}


@frappe.whitelist(methods=["POST"])
def create_commercial_custom_fields():
	"""Create only the AlphaERP trace/tier fields after an explicit user action."""
	_configured_source()
	from bimap_data_engine.custom_fields import sync_alphaerp_commercial_fields

	sync_alphaerp_commercial_fields()
	frappe.db.commit()
	return {"created": True}


@frappe.whitelist(methods=["POST"])
def prepare_all_commercial_classifications():
	"""Apply the safe default to every commercial class in one explicit action."""
	path = _configured_source()
	workbook = normalize_package(path)
	reconciliation = reconcile_workbook(workbook)
	customers = _sheet_rows(workbook, "Clientes")
	suppliers = _sheet_rows(workbook, "Proveedores")
	profiles = [{
		"mapping_type": "Customer Tax" if row["Tipo de tercero"] == "Cliente" else "Supplier Tax",
		"source_key": row["Clave fiscal AlphaERP"],
		"source_label": row["Descripción"],
		"party_type": row["Tipo de tercero"],
		"impact": sum(party.get("Tipo fiscal AlphaERP") == row["Clave fiscal AlphaERP"] for party in (customers if row["Tipo de tercero"] == "Cliente" else suppliers)),
		"examples": [],
	} for row in _sheet_rows(workbook, "Perfiles fiscales")]
	existing_groups = {
		"Customer Commercial": {name.casefold(): name for name in frappe.get_all("Customer Group", pluck="name", limit_page_length=0)},
		"Supplier Commercial": {name.casefold(): name for name in frappe.get_all("Supplier Group", pluck="name", limit_page_length=0)},
	}
	classifications = _commercial_classifications(profiles, existing_groups)
	rows = []
	reused = 0
	to_create = 0
	for classification in classifications:
		target = classification["suggested_target"] or classification["source_label"]
		resolution = "Reuse" if classification["suggested_target"] else "Create"
		if resolution == "Reuse":
			reused += 1
		else:
			to_create += 1
		for profile in classification["source_profiles"]:
			rows.append({
				"mapping_type": classification["mapping_type"],
				"source_key": profile["source_key"],
				"source_label": profile["source_label"],
				"resolution": resolution,
				"target_name": target,
				"settings": {
					"commercial_tier": profile.get("tier") or "",
					"source_profile": profile["source_label"] or profile["source_key"],
				},
			})
	from bimap_data_engine.custom_fields import sync_alphaerp_commercial_fields

	sync_alphaerp_commercial_fields()
	persist_equivalences(
		rows,
		allowed_sources={
			"Customer Commercial": {row["Clave fiscal AlphaERP"] for row in _sheet_rows(workbook, "Perfiles fiscales") if row["Tipo de tercero"] == "Cliente"},
			"Supplier Commercial": {row["Clave fiscal AlphaERP"] for row in _sheet_rows(workbook, "Perfiles fiscales") if row["Tipo de tercero"] == "Proveedor"},
		},
		fingerprint=workbook["source"]["manifest"]["fingerprint"],
		company=reconciliation["company"],
	)
	frappe.db.commit()
	return {"classifications": len(classifications), "mappings": len(rows), "reused": reused, "to_create": to_create}


@frappe.whitelist(methods=["GET"])
def preview_catalog(catalog, start=0, page_length=50):
	workbook = normalize_package(_configured_source())
	return build_catalog_preview(workbook, catalog, start=start, page_length=page_length)
