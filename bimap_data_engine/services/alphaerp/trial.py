"""Deterministic rules and preflight for the clean AlphaERP trial migration.

The preflight is deliberately independent from Frappe.  It is the contract used
before the old site is reinstalled and again after the import for reconciliation.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from bimap_data_engine.services.alphaerp.package import AlphaERPPackage


COMPANIES = {
	"TIR": {"name": "Tirden", "abbr": "TIR"},
	"ISO": {"name": "ISTITUTO STUDI ODONTODIATRICI MEXICO", "abbr": "ISO"},
}
ISO_SOURCE_NAMES = {"ISTITUTO STUDI ODONTODIATRICI MEXICO"}


def text(value) -> str:
	return str(value or "").strip()


def key(value) -> str:
	if value is None:
		return ""
	if isinstance(value, Decimal):
		return str(int(value)) if value == value.to_integral_value() else format(value, "f")
	return text(value)


def number(value) -> Decimal:
	if value in (None, ""):
		return Decimal(0)
	return value if isinstance(value, Decimal) else Decimal(str(value))


def warehouse_company(row: dict) -> str:
	"""Map a source warehouse by its company fields, never by its description."""
	legal_name = text(row.get("NOM_COM") or row.get("NOM_LUG")).upper()
	return "ISO" if legal_name in ISO_SOURCE_NAMES else "TIR"


def item_kind(row: dict) -> str:
	if int(number(row.get("KIT"))):
		return "Kit"
	if int(number(row.get("STACLAS1"))):
		return "Servicio"
	return "Producto"


def item_code(base: str, variant: str = "") -> str:
	return f"{base}::{variant}" if variant else base


def build_preflight(source_directory) -> dict:
	tables = AlphaERPPackage(source_directory).load()
	products = {text(row.get("CVE_PROD")): row for row in tables["PRODUCTO"] if text(row.get("CVE_PROD"))}
	customers = {key(row.get("CVE_CTE")) for row in tables["CLIENTES"] if key(row.get("CVE_CTE"))}
	product_types = {key(row.get("CVE_TIAL")) for row in tables["TIPOALMA"] if key(row.get("CVE_TIAL"))}
	warehouses = {text(row.get("LUGAR")): row for row in tables["LUGARES"] if text(row.get("LUGAR"))}
	variants = {
		(text(row.get("CVE_PROD")), text(row.get("NEW_MED")))
		for row in tables["PRODMED"]
		if text(row.get("CVE_PROD")) and text(row.get("NEW_MED"))
	}

	price_usage = Counter()
	for table, field in (("PRECIPROD", "NLISPRE"), ("PRECIMED", "NLISPRE")):
		for row in tables[table]:
			if number(row.get("LPRECPROD")) != 0:
				price_usage[key(row.get(field))] += 1
	price_lists = {
		key(row.get("NLISPRE")): text(row.get("DESLISPRE"))
		for row in tables["CATLISPRE"]
		if price_usage[key(row.get("NLISPRE"))]
	}

	inventory = Counter()
	inventory_value = Counter()
	inventory_exceptions = Counter()
	for row in tables["EXISTE"]:
		base = text(row.get("CVE_PROD"))
		variant = text(row.get("NEW_MED"))
		warehouse = text(row.get("LUGAR"))
		qty = number(row.get("EXISTENCIA"))
		batch = text(row.get("LOTE"))
		if not warehouse:
			inventory_exceptions["blank_warehouse_rows"] += 1
			if qty:
				inventory_exceptions["blank_warehouse_nonzero_rows"] += 1
			continue
		if warehouse not in warehouses:
			inventory_exceptions["unknown_warehouse_rows"] += 1
			continue
		if base not in products:
			inventory_exceptions["unknown_product_rows"] += 1
			continue
		if variant and (base, variant) not in variants:
			inventory_exceptions["unknown_variant_rows"] += 1
			continue
		group = (item_code(base, variant), warehouse, batch)
		inventory[group] += qty
		inventory_value[group] += qty * number(row.get("COSTO_PROM"))

	positive_inventory = {}
	for group, qty in inventory.items():
		if qty <= 0:
			inventory_exceptions["nonpositive_balance_groups"] += 1
			if qty < 0:
				inventory_exceptions["negative_balance_groups"] += 1
			continue
		positive_inventory[group] = {
			"qty": qty,
			"valuation_rate": inventory_value[group] / qty if qty else Decimal(0),
		}

	warehouse_type_pairs = {
		(text(row.get("LUGAR")), key(row.get("CVE_TIAL")))
		for row in tables["LUGAALMA"]
		if text(row.get("LUGAR")) and key(row.get("CVE_TIAL"))
	}
	customer_type_pairs = {
		(key(row.get("CVE_CTE")), key(row.get("CVE_TIAL")))
		for row in tables["TIPPROCL"]
		if key(row.get("CVE_CTE")) and key(row.get("CVE_TIAL")) and int(number(row.get("TRANS"))) != 0
	}

	return {
		"source_fingerprint": AlphaERPPackage(source_directory).manifest()["fingerprint"],
		"companies": {
			code: {**spec, "warehouses": sorted(name for name, row in warehouses.items() if warehouse_company(row) == code)}
			for code, spec in COMPANIES.items()
		},
		"counts": {
			"products": len(products),
			"templates": len({base for base, _variant in variants}),
			"variants": len(variants),
			"item_kinds": dict(Counter(item_kind(row) for row in products.values())),
			"product_types": len(product_types),
			"warehouses": len(warehouses),
			"warehouse_type_rules": len(warehouse_type_pairs),
			"customer_type_rules": len(customer_type_pairs),
			"customers_without_type_rules": len(customers - {customer for customer, _type in customer_type_pairs}),
			"price_lists": len(price_lists),
			"positive_inventory_groups": len(positive_inventory),
		},
		"price_lists": price_lists,
		"inventory_exceptions": dict(inventory_exceptions),
		"positive_inventory": positive_inventory,
		"rules": {
			"negative_inventory": "omit",
			"blank_warehouse_inventory": "omit",
			"empty_price_lists": "omit",
			"unknown_source_references": "omit_and_report",
		},
	}


def preflight_summary(source_directory) -> dict:
	"""JSON-safe preflight payload for CLI/UI checks before destructive work."""
	result = build_preflight(source_directory)
	return {key: value for key, value in result.items() if key != "positive_inventory"}

