"""End-to-end clean trial setup for the Tirden AlphaERP database."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date

import frappe
from frappe.utils import cint, flt, now_datetime, today

from bimap_data_engine.services.alphaerp.executor import AlphaERPCatalogExecutor, _rows, _tax_name
from bimap_data_engine.services.alphaerp.package import AlphaERPPackage
from bimap_data_engine.services.alphaerp.trial import (
	COMPANIES,
	build_preflight,
	item_code,
	key,
	number,
	text,
	warehouse_company,
)


MEXICO_CHART = "Mexico - Plan de Cuentas"
SOURCE_DIRECTORY_CONFIG = "bimap_alphaerp_source_directory"
STOCK_BATCH_SIZE = 400


def _source_directory(value=None):
	value = value or frappe.conf.get(SOURCE_DIRECTORY_CONFIG)
	if not value:
		frappe.throw(f"No está configurado {SOURCE_DIRECTORY_CONFIG}.")
	return value


def _fiscal_dates():
	year = date.today().year
	return f"{year}-01-01", f"{year}-12-31"


def _complete_setup_wizard():
	if frappe.is_setup_complete() and frappe.db.exists("Company", COMPANIES["TIR"]["name"]):
		return
	if frappe.db.count("Company"):
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	start, end = _fiscal_dates()
	result = setup_complete({
		"language": "Spanish",
		"country": "Mexico",
		"timezone": "America/Mexico_City",
		"time_zone": "America/Mexico_City",
		"currency": "MXN",
		"company_name": COMPANIES["TIR"]["name"],
		"company_abbr": COMPANIES["TIR"]["abbr"],
		"chart_of_accounts": MEXICO_CHART,
		"fy_start_date": start,
		"fy_end_date": end,
		"domain": "Distribution",
		"full_name": "",
		"email": "",
		"password": "",
	})
	if result and result.get("status") not in {"ok", "registered"}:
		frappe.throw(f"El Setup Wizard no terminó correctamente: {result}")


def _company_tax_id(package, company_code):
	for row in package.rows("LUGARES"):
		if warehouse_company(row) == company_code:
			return text(row.get("RFC_COM") or row.get("RFC_LUG"))
	return ""


def _ensure_companies(package):
	_complete_setup_wizard()
	for code, spec in COMPANIES.items():
		name = spec["name"]
		if frappe.db.exists("Company", name):
			doc = frappe.get_doc("Company", name)
		else:
			doc = frappe.get_doc({
				"doctype": "Company",
				"company_name": name,
				"abbr": spec["abbr"],
				"country": "Mexico",
				"default_currency": "MXN",
				"enable_perpetual_inventory": 1,
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": MEXICO_CHART,
			})
		doc.tax_id = _company_tax_id(package, code)
		doc.save(ignore_permissions=True)
	frappe.defaults.set_global_default("company", COMPANIES["TIR"]["name"])
	frappe.defaults.set_global_default("currency", "MXN")
	frappe.defaults.set_global_default("country", "Mexico")
	frappe.defaults.set_global_default("fiscal_year", str(date.today().year))


def _delete_unused_default_warehouses():
	# Setup Wizard links Stores in singleton/company defaults.  Clear only links
	# pointing at generated leaves before deleting those leaves.
	for doctype in ("Stock Settings", "Selling Settings", "Buying Settings"):
		meta = frappe.get_meta(doctype)
		for field in meta.fields:
			if field.fieldtype == "Link" and field.options == "Warehouse":
				frappe.db.set_single_value(doctype, field.fieldname, None)
	for company in frappe.get_all("Company", pluck="name"):
		doc = frappe.get_doc("Company", company)
		changed = False
		for field in doc.meta.fields:
			if field.fieldtype == "Link" and field.options == "Warehouse" and doc.get(field.fieldname):
				doc.set(field.fieldname, None)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
	for row in frappe.get_all("Warehouse", filters={"is_group": 0}, fields=["name", "bimap_alphaerp_warehouse_code"]):
		if not row.bimap_alphaerp_warehouse_code:
			frappe.delete_doc("Warehouse", row.name, ignore_permissions=True, force=True)


def _ensure_source_warehouses(package):
	warehouses = {}
	for row in package.rows("LUGARES"):
		code = text(row.get("LUGAR"))
		if not code:
			continue
		company_code = warehouse_company(row)
		company = COMPANIES[company_code]["name"]
		root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ""}, "name")
		name = frappe.db.get_value("Warehouse", {"bimap_alphaerp_warehouse_code": code}, "name")
		doc = frappe.get_doc("Warehouse", name) if name else frappe.new_doc("Warehouse")
		doc.update({
			"warehouse_name": code,
			"bimap_alphaerp_warehouse_code": code,
			"company": company,
			"parent_warehouse": root,
			"is_group": 0,
			"disabled": 0,
		})
		doc.save(ignore_permissions=True)
		warehouses[code] = doc.name
	return warehouses


def _import_warehouse_rules(package, warehouses, stats):
	for row in package.rows("LUGAALMA"):
		warehouse_code = text(row.get("LUGAR"))
		product_type = key(row.get("CVE_TIAL"))
		warehouse = warehouses.get(warehouse_code)
		if not warehouse or not frappe.db.exists("BIMAP Product Type", product_type):
			stats["warehouse_rule_orphan"] += 1
			continue
		source = f"{warehouse_code}:{product_type}"
		if frappe.db.exists("BIMAP Warehouse Product Type Rule", source):
			stats["warehouse_rules_existing"] += 1
			continue
		doc = frappe.new_doc("BIMAP Warehouse Product Type Rule")
		doc.update({"source_key": source, "warehouse": warehouse, "product_type": product_type, "company": frappe.get_cached_value("Warehouse", warehouse, "company"), "enabled": 1})
		doc.save(ignore_permissions=True)
		stats["warehouse_rules_saved"] += 1


def _import_customer_rules(package, stats):
	customers = dict(frappe.get_all("Customer", fields=["bimap_customer_number", "name"], as_list=True))
	seen = set()
	for row in package.rows("TIPPROCL"):
		customer_code = key(row.get("CVE_CTE"))
		product_type = key(row.get("CVE_TIAL"))
		source = f"{customer_code}:{product_type}"
		if source in seen:
			stats["customer_rule_duplicate"] += 1
			continue
		seen.add(source)
		customer = customers.get(customer_code)
		if not customer or not frappe.db.exists("BIMAP Product Type", product_type):
			stats["customer_rule_orphan"] += 1
			continue
		if frappe.db.exists("BIMAP Customer Product Type Rule", source):
			stats["customer_rules_existing"] += 1
			continue
		doc = frappe.new_doc("BIMAP Customer Product Type Rule")
		doc.update({"source_key": source, "customer": customer, "product_type": product_type, "enabled": cint(number(row.get("TRANS")) != 0)})
		doc.save(ignore_permissions=True)
		stats["customer_rules_saved"] += 1
		if stats["customer_rules_saved"] % 500 == 0:
			frappe.db.commit()


def _import_product_bundles(package, stats):
	components = defaultdict(list)
	for row in package.rows("KIT"):
		parent = text(row.get("CVE_PRODK"))
		component = item_code(text(row.get("CVE_PROD")), text(row.get("NEW_MED")))
		qty = flt(row.get("CANTIDAD"))
		if parent and component and qty > 0:
			components[parent].append((component, qty))
	for parent, rows in components.items():
		if not frappe.db.exists("Item", parent):
			stats["bundle_parent_orphan"] += 1
			continue
		if frappe.get_cached_value("Item", parent, "bimap_alphaerp_item_kind") != "Kit":
			stats["nonkit_composition_omitted"] += 1
			continue
		valid = [(component, qty) for component, qty in rows if frappe.db.exists("Item", component)]
		stats["bundle_component_orphan"] += len(rows) - len(valid)
		if not valid:
			stats["bundle_empty"] += 1
			continue
		name = frappe.db.get_value("Product Bundle", {"new_item_code": parent}, "name")
		doc = frappe.get_doc("Product Bundle", name) if name else frappe.new_doc("Product Bundle")
		doc.new_item_code = parent
		doc.set("items", [])
		for component, qty in valid:
			doc.append("items", {"item_code": component, "qty": qty})
		doc.save(ignore_permissions=True)
		stats["bundles_saved"] += 1


def _batch_for(item, source_batch, stats):
	source_batch = source_batch or "SIN-LOTE"
	source_key = f"{item}:{source_batch}"
	name = frappe.db.get_value("Batch", {"bimap_alphaerp_batch_key": source_key}, "name")
	if name:
		return name
	doc = frappe.get_doc({"doctype": "Batch", "item": item, "batch_id": source_key[:140], "bimap_alphaerp_batch_key": source_key})
	doc.insert(ignore_permissions=True)
	if source_batch == "SIN-LOTE":
		stats["synthetic_blank_batches"] += 1
	return doc.name


def _opening_account(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"Temporary Opening - {abbr}"
	if frappe.db.exists("Account", name):
		return name
	parent = frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "parent_account": ["is", "not set"]}, "name")
	doc = frappe.get_doc({
		"doctype": "Account",
		"account_name": "Temporary Opening",
		"company": company,
		"parent_account": parent,
		"root_type": "Liability",
		"report_type": "Balance Sheet",
		"account_type": "Temporary",
		"is_group": 0,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _import_opening_stock(preflight, warehouses, stats):
	by_company = defaultdict(list)
	for (item, warehouse_code, source_batch), values in preflight["positive_inventory"].items():
		warehouse = warehouses.get(warehouse_code)
		if not warehouse or not frappe.db.exists("Item", item):
			stats["stock_target_orphan"] += 1
			continue
		item_data = frappe.db.get_value("Item", item, ["is_stock_item", "has_batch_no"], as_dict=True)
		if not item_data or not item_data.is_stock_item:
			stats["nonstock_balance_omitted"] += 1
			continue
		product_type = frappe.get_cached_value("Item", item, "bimap_product_type")
		if product_type and not cint(frappe.get_cached_value("BIMAP Product Type", product_type, "allow_stock")):
			stats["stock_type_disallowed_omitted"] += 1
			continue
		warehouse_rules = frappe.db.exists("BIMAP Warehouse Product Type Rule", {"warehouse": warehouse, "enabled": 1})
		if warehouse_rules and not frappe.db.exists("BIMAP Warehouse Product Type Rule", {"warehouse": warehouse, "product_type": product_type, "enabled": 1}):
			stats["stock_warehouse_type_omitted"] += 1
			continue
		row = {
			"item_code": item,
			"warehouse": warehouse,
			"qty": flt(values["qty"]),
			"valuation_rate": max(flt(values["valuation_rate"]), 0),
			"allow_zero_valuation_rate": cint(flt(values["valuation_rate"]) <= 0),
			"use_serial_batch_fields": 1,
		}
		if item_data.has_batch_no:
			row["batch_no"] = _batch_for(item, source_batch, stats)
		company = frappe.get_cached_value("Warehouse", warehouse, "company")
		by_company[company].append(row)

	for company, rows in by_company.items():
		expense_account = _opening_account(company)
		cost_center = frappe.get_cached_value("Company", company, "cost_center")
		for offset in range(0, len(rows), STOCK_BATCH_SIZE):
			doc = frappe.get_doc({
				"doctype": "Stock Reconciliation",
				"company": company,
				"purpose": "Opening Stock",
				"posting_date": today(),
				"posting_time": "00:01:00",
				"set_posting_time": 1,
				"expense_account": expense_account,
				"cost_center": cost_center,
				"items": rows[offset : offset + STOCK_BATCH_SIZE],
			})
			doc.insert(ignore_permissions=True)
			doc.submit()
			stats["stock_reconciliations_submitted"] += 1
			stats["stock_rows_saved"] += len(doc.items)
			frappe.db.commit()


def _finish_setup():
	frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.set_value("Module Onboarding", {}, "is_complete", 1, update_modified=False)
	frappe.db.set_default("desktop:home_page", "workspace")
	for app in frappe.get_all("Installed Application", filters={"has_setup_wizard": 1}, pluck="name"):
		frappe.db.set_value("Installed Application", app, "is_setup_complete", 1, update_modified=False)
	frappe.clear_cache()


def configure_trial_foundation(source_directory=None):
	"""Complete setup, create both companies, and replace default warehouse leaves."""
	source_directory = _source_directory(source_directory)
	package = AlphaERPPackage(source_directory)
	_ensure_companies(package)
	# The custom field exists after migrate.  Source leaves are then the only
	# operational warehouses; ERPNext's mandatory company roots remain.
	_delete_unused_default_warehouses()
	warehouses = _ensure_source_warehouses(package)
	_finish_setup()
	frappe.db.commit()
	return {"companies": list(COMPANIES), "warehouses": warehouses, "setup_complete": frappe.is_setup_complete()}


def execute_trial_migration(source_directory=None, commit=True):
	"""Run the approved clean trial migration after a successful preflight."""
	source_directory = _source_directory(source_directory)
	preflight = build_preflight(source_directory)
	package = AlphaERPPackage(source_directory)
	main = AlphaERPCatalogExecutor(source_directory, company=COMPANIES["TIR"]["name"], commit=commit)
	main._prepare_custom_fields()
	foundation = configure_trial_foundation(source_directory)
	catalog_result = main.run()

	# Fiscal templates are company-specific even though parties and items are shared.
	iso = AlphaERPCatalogExecutor(source_directory, company=COMPANIES["ISO"]["name"], commit=commit)
	iso._prepare_custom_fields()
	iso._prepare_taxes()

	stats = Counter()
	_import_warehouse_rules(package, foundation["warehouses"], stats)
	_import_customer_rules(package, stats)
	_import_product_bundles(package, stats)
	_import_opening_stock(preflight, foundation["warehouses"], stats)
	_finish_setup()
	result = {
		"source_fingerprint": preflight["source_fingerprint"],
		"started": catalog_result["started"],
		"finished": str(now_datetime()),
		"preflight_counts": preflight["counts"],
		"inventory_exceptions": preflight["inventory_exceptions"],
		"catalog_stats": catalog_result["stats"],
		"catalog_errors": catalog_result["errors"],
		"trial_stats": dict(stats),
	}
	with open(frappe.get_site_path("private", "files", "alphaerp-trial-migration.json"), "w", encoding="utf-8") as handle:
		json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
	if commit:
		frappe.db.commit()
	return result


def resume_trial_post_catalog(source_directory=None, commit=True):
	"""Resume matrices, kits, inventory and repaired prices without reimporting masters."""
	source_directory = _source_directory(source_directory)
	preflight = build_preflight(source_directory)
	package = AlphaERPPackage(source_directory)
	warehouses = dict(frappe.get_all("Warehouse", filters={"bimap_alphaerp_warehouse_code": ["!=", ""]}, fields=["bimap_alphaerp_warehouse_code", "name"], as_list=True))
	stats = Counter()
	_import_warehouse_rules(package, warehouses, stats)
	_import_customer_rules(package, stats)
	_import_product_bundles(package, stats)

	prices = AlphaERPCatalogExecutor(source_directory, company=COMPANIES["TIR"]["name"], commit=commit)
	prices.hydrate_maps_from_database()
	prices._import_prices()
	_import_opening_stock(preflight, warehouses, stats)
	_finish_setup()
	result = {
		"source_fingerprint": preflight["source_fingerprint"],
		"finished": str(now_datetime()),
		"inventory_exceptions": preflight["inventory_exceptions"],
		"price_stats": dict(prices.stats),
		"price_errors": prices.errors,
		"trial_stats": dict(stats),
	}
	with open(frappe.get_site_path("private", "files", "alphaerp-trial-migration.json"), "w", encoding="utf-8") as handle:
		json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
	if commit:
		frappe.db.commit()
	return result


def resume_inventory_only(source_directory=None, commit=True):
	"""Create opening stock after catalogs, rules, bundles and prices are complete."""
	source_directory = _source_directory(source_directory)
	preflight = build_preflight(source_directory)
	warehouses = dict(frappe.get_all("Warehouse", filters={"bimap_alphaerp_warehouse_code": ["!=", ""]}, fields=["bimap_alphaerp_warehouse_code", "name"], as_list=True))
	stats = Counter()
	_import_opening_stock(preflight, warehouses, stats)
	_finish_setup()
	result = {
		"source_fingerprint": preflight["source_fingerprint"],
		"finished": str(now_datetime()),
		"inventory_exceptions": preflight["inventory_exceptions"],
		"trial_stats": dict(stats),
	}
	with open(frappe.get_site_path("private", "files", "alphaerp-trial-migration.json"), "w", encoding="utf-8") as handle:
		json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
	if commit:
		frappe.db.commit()
	return result


def repair_draft_stock_reconciliations():
	"""Submit only migration drafts rejected because source valuation was zero."""
	result = Counter()
	for name in frappe.get_all("Stock Reconciliation", filters={"docstatus": 0}, pluck="name", order_by="name"):
		doc = frappe.get_doc("Stock Reconciliation", name)
		doc.expense_account = _opening_account(doc.company)
		doc.cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
		for row in doc.items:
			if flt(row.valuation_rate) <= 0:
				row.allow_zero_valuation_rate = 1
		doc.save(ignore_permissions=True)
		doc._submit()
		frappe.db.commit()
		result["submitted"] += 1
		result["rows"] += len(doc.items)
	_finish_setup()
	frappe.db.commit()
	return dict(result)


def repair_fiscal_profiles(source_directory=None):
	"""Create one Tax Category per AlphaERP profile and reassign every party."""
	source_directory = _source_directory(source_directory)
	by_company = {}
	for code in ("TIR", "ISO"):
		executor = AlphaERPCatalogExecutor(source_directory, company=COMPANIES[code]["name"], commit=True)
		executor._prepare_custom_fields()
		executor._prepare_taxes()
		by_company[code] = dict(executor.stats)
		if code == "TIR":
			for row in frappe.get_all("Customer", fields=["name", "bimap_alphaerp_tax_profile"]):
				category = executor.tax_categories.get(("Cliente", text(row.bimap_alphaerp_tax_profile)))
				if category:
					frappe.db.set_value("Customer", row.name, "tax_category", category, update_modified=False)
			for row in frappe.get_all("Supplier", fields=["name", "bimap_alphaerp_tax_profile"]):
				category = executor.tax_categories.get(("Proveedor", text(row.bimap_alphaerp_tax_profile)))
				if category:
					frappe.db.set_value("Supplier", row.name, "tax_category", category, update_modified=False)
		frappe.db.commit()
	# Remove only the signature-based artifacts produced by the first pass.
	old_names = {_tax_name(row) for row in _rows(executor.workbook, "Perfiles fiscales")}
	for old_name in old_names:
		for doctype, suffix in (("Sales Taxes and Charges Template", "Ventas"), ("Purchase Taxes and Charges Template", "Compras")):
			for template in frappe.get_all(doctype, filters={"title": f"{old_name} - {suffix}"}, pluck="name"):
				frappe.delete_doc(doctype, template, ignore_permissions=True, force=True)
		if frappe.db.exists("Tax Category", old_name):
			party_use = frappe.db.exists("Customer", {"tax_category": old_name}) or frappe.db.exists("Supplier", {"tax_category": old_name})
			template_use = frappe.db.exists("Sales Taxes and Charges Template", {"tax_category": old_name}) or frappe.db.exists("Purchase Taxes and Charges Template", {"tax_category": old_name})
			if not party_use and not template_use:
				frappe.delete_doc("Tax Category", old_name, ignore_permissions=True, force=True)
	frappe.db.commit()
	return by_company


def repair_category_catalog(source_directory=None):
	"""Ensure blank-labeled source category records still have traceable nodes."""
	executor = AlphaERPCatalogExecutor(_source_directory(source_directory), company=COMPANIES["TIR"]["name"], commit=True)
	executor._prepare_item_groups()
	frappe.db.commit()
	return dict(executor.stats)


def finalize_and_audit_trial(source_directory=None):
	"""Set operational defaults and emit a machine-readable final reconciliation."""
	source_directory = _source_directory(source_directory)
	package = AlphaERPPackage(source_directory)
	preflight = build_preflight(source_directory)
	general = frappe.db.get_value("Warehouse", {"bimap_alphaerp_warehouse_code": "GENERAL"}, "name")
	frappe.db.set_single_value("Stock Settings", "default_warehouse", general)
	frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
	frappe.db.set_single_value("Selling Settings", "selling_price_list", "Lista 1")
	if frappe.db.exists("Territory", "Mexico"):
		frappe.db.set_single_value("Selling Settings", "territory", "Mexico")
	frappe.defaults.set_global_default("company", COMPANIES["TIR"]["name"])
	frappe.defaults.set_global_default("currency", "MXN")
	frappe.defaults.set_global_default("country", "Mexico")
	frappe.defaults.set_global_default("fiscal_year", str(date.today().year))
	_finish_setup()

	source_uoms = {text(row.get("UNIDAD")) for row in package.rows("UNIDAD") if text(row.get("UNIDAD"))}
	source_attributes = {text(row.get("LISTA_MED")) for row in package.rows("ATRIBUTO") if text(row.get("LISTA_MED"))}
	source_warehouses = {text(row.get("LUGAR")) for row in package.rows("LUGARES") if text(row.get("LUGAR"))}
	destination_warehouses = set(frappe.get_all("Warehouse", filters={"is_group": 0}, pluck="bimap_alphaerp_warehouse_code"))
	destination_attributes = set(frappe.get_all("Item Attribute", filters={"bimap_alphaerp_attribute_list": ["!=", ""]}, pluck="bimap_alphaerp_attribute_list"))

	counts = {
		"companies": frappe.db.count("Company"),
		"warehouse_roots": frappe.db.count("Warehouse", {"is_group": 1}),
		"warehouse_leaves": frappe.db.count("Warehouse", {"is_group": 0}),
		"base_items": frappe.db.sql("select count(*) from tabItem where ifnull(variant_of, '')='' ")[0][0],
		"templates": frappe.db.count("Item", {"has_variants": 1}),
		"variants": frappe.db.sql("select count(*) from tabItem where ifnull(variant_of, '')!='' ")[0][0],
		"product_types": frappe.db.count("BIMAP Product Type"),
		"warehouse_type_rules": frappe.db.count("BIMAP Warehouse Product Type Rule"),
		"customer_type_rules": frappe.db.count("BIMAP Customer Product Type Rule"),
		"customers": frappe.db.count("Customer"),
		"suppliers": frappe.db.count("Supplier"),
		"attributes": len(destination_attributes),
		"source_category_nodes": sum(len(package.rows(table)) for table in ("CLASES", "SUBCLASE", "SUB2CLAS")),
		"destination_source_category_nodes": frappe.db.count("Item Group") - 6,
		"brands": frappe.db.count("Brand"),
		"item_prices": frappe.db.count("Item Price"),
		"product_bundles": frappe.db.count("Product Bundle"),
		"tax_categories": frappe.db.count("Tax Category", {"title": ["like", "AlphaERP %"]}),
		"submitted_stock_reconciliations": frappe.db.count("Stock Reconciliation", {"docstatus": 1}),
		"draft_stock_reconciliations": frappe.db.count("Stock Reconciliation", {"docstatus": 0}),
		"submitted_stock_rows": frappe.db.sql("select count(*) from `tabStock Reconciliation Item` i join `tabStock Reconciliation` p on p.name=i.parent where p.docstatus=1")[0][0],
		"negative_bins": frappe.db.count("Bin", {"actual_qty": ["<", 0]}),
	}
	failures = []
	checks = {
		"source_fingerprint_matches": preflight["source_fingerprint"] == package.manifest()["fingerprint"],
		"warehouse_codes_exact": source_warehouses == destination_warehouses,
		"uoms_complete": not [name for name in source_uoms if not frappe.db.exists("UOM", name)],
		"attributes_complete": source_attributes == destination_attributes,
		"category_nodes_complete": counts["source_category_nodes"] == counts["destination_source_category_nodes"],
		"companies_complete": counts["companies"] == 2,
		"items_complete": counts["base_items"] == 2617 and counts["templates"] == 432 and counts["variants"] == 4231,
		"type_rules_complete": counts["product_types"] == 26 and counts["warehouse_type_rules"] == 181 and counts["customer_type_rules"] == 30072,
		"no_template_prices": not frappe.db.sql("select p.name from `tabItem Price` p join tabItem i on i.name=p.item_code where i.has_variants=1 limit 1"),
		"no_negative_stock": counts["negative_bins"] == 0,
		"no_draft_openings": counts["draft_stock_reconciliations"] == 0,
		"setup_complete": bool(frappe.is_setup_complete()),
		"onboarding_disabled": not cint(frappe.db.get_single_value("System Settings", "enable_onboarding")),
	}
	for name, passed in checks.items():
		if not passed:
			failures.append(name)
	report = {
		"source_fingerprint": preflight["source_fingerprint"],
		"generated": str(now_datetime()),
		"source_counts": preflight["counts"],
		"destination_counts": counts,
		"inventory_exceptions": preflight["inventory_exceptions"],
		"checks": checks,
		"failures": failures,
	}
	with open(frappe.get_site_path("private", "files", "alphaerp-final-reconciliation.json"), "w", encoding="utf-8") as handle:
		json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
	frappe.db.commit()
	return report


def smoke_operational_trial():
	"""Insert a representative quotation and always roll it back."""
	row = frappe.db.sql(
		"""
		select cr.customer, i.name item_code, i.stock_uom, wr.warehouse, wr.company
		from `tabBIMAP Customer Product Type Rule` cr
		join `tabBIMAP Product Type` pt on pt.name=cr.product_type and pt.allow_sales=1
		join tabItem i on i.bimap_product_type=cr.product_type and i.disabled=0 and i.has_variants=0
		join `tabBIMAP Warehouse Product Type Rule` wr on wr.product_type=cr.product_type and wr.enabled=1
		where cr.enabled=1 and wr.company=%s
		limit 1
		""",
		COMPANIES["TIR"]["name"],
		as_dict=True,
	)
	if not row:
		frappe.throw("No se encontró una combinación válida cliente-producto-almacén para la prueba.")
	row = row[0]
	rate = frappe.db.get_value("Item Price", {"item_code": row.item_code, "price_list": "Lista 1"}, "price_list_rate") or 1
	try:
		doc = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": row.customer,
			"company": row.company,
			"transaction_date": today(),
			"valid_till": today(),
			"currency": "MXN",
			"conversion_rate": 1,
			"selling_price_list": "Lista 1",
			"price_list_currency": "MXN",
			"plc_conversion_rate": 1,
			"items": [{"item_code": row.item_code, "qty": 1, "uom": row.stock_uom, "warehouse": row.warehouse, "rate": rate}],
		})
		doc.insert(ignore_permissions=True)
		return {"ok": True, "customer": row.customer, "item": row.item_code, "warehouse": row.warehouse, "grand_total": doc.grand_total}
	finally:
		frappe.db.rollback()

