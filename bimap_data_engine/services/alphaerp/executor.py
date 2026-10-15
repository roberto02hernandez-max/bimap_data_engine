"""Idempotent, server-side AlphaERP catalog migration into ERPNext.

This module intentionally uses Frappe documents and their validations.  It never
writes business records with SQL.  The executor is suitable for a one-off full
catalog migration and can safely be run again after an interruption.
"""

from __future__ import annotations

import json
import re
import traceback
from collections import Counter, defaultdict

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, now_datetime, validate_email_address

from bimap_data_engine.services.alphaerp.normalize import normalize_package


BATCH_SIZE = 100
TIERS = ("PLATINO", "ORO", "AZUL")


TRACE_FIELDS = {
	"Sales Person": [
		{"fieldname": "bimap_alphaerp_agent_code", "label": "Clave vendedor AlphaERP", "fieldtype": "Data", "insert_after": "sales_person_name", "read_only": 1, "unique": 1, "search_index": 1},
	],
	"Customer": [
		{"fieldname": "bimap_alphaerp_tax_profile", "label": "Perfil fiscal AlphaERP", "fieldtype": "Data", "insert_after": "tax_category", "read_only": 1, "search_index": 1},
		{"fieldname": "bimap_alphaerp_zone", "label": "Zona AlphaERP", "fieldtype": "Data", "insert_after": "bimap_alphaerp_tax_profile", "read_only": 1, "search_index": 1},
		{"fieldname": "bimap_alphaerp_subzone", "label": "Subzona AlphaERP", "fieldtype": "Data", "insert_after": "bimap_alphaerp_zone", "read_only": 1, "search_index": 1},
	],
	"Supplier": [
		{"fieldname": "bimap_alphaerp_tax_profile", "label": "Perfil fiscal AlphaERP", "fieldtype": "Data", "insert_after": "tax_category", "read_only": 1, "search_index": 1},
	],
	"Item": [
		{"fieldname": "bimap_alphaerp_base_item", "label": "Producto base AlphaERP", "fieldtype": "Data", "insert_after": "item_code", "read_only": 1, "search_index": 1},
		{"fieldname": "bimap_alphaerp_variant_code", "label": "Variante AlphaERP", "fieldtype": "Data", "insert_after": "bimap_alphaerp_base_item", "read_only": 1, "search_index": 1},
		{"fieldname": "bimap_alphaerp_attributes", "label": "Atributos AlphaERP", "fieldtype": "Long Text", "insert_after": "bimap_alphaerp_variant_code", "read_only": 1},
		{"fieldname": "bimap_alphaerp_tax_config", "label": "Configuración fiscal AlphaERP", "fieldtype": "Long Text", "insert_after": "bimap_alphaerp_attributes", "read_only": 1},
		{"fieldname": "bimap_alphaerp_sat_product_code", "label": "Clave SAT AlphaERP", "fieldtype": "Data", "insert_after": "bimap_alphaerp_tax_config", "read_only": 1, "search_index": 1},
	],
	"Price List": [
		{"fieldname": "bimap_alphaerp_price_list", "label": "Lista AlphaERP", "fieldtype": "Data", "insert_after": "price_list_name", "read_only": 1, "unique": 1, "search_index": 1},
	],
	"Item Price": [
		{"fieldname": "bimap_alphaerp_price_key", "label": "Precio AlphaERP", "fieldtype": "Data", "insert_after": "item_code", "read_only": 1, "unique": 1, "search_index": 1},
	],
	"Address": [
		{"fieldname": "bimap_alphaerp_address_key", "label": "Dirección AlphaERP", "fieldtype": "Data", "insert_after": "address_title", "read_only": 1, "unique": 1, "search_index": 1},
	],
	"Contact": [
		{"fieldname": "bimap_alphaerp_contact_key", "label": "Contacto AlphaERP", "fieldtype": "Data", "insert_after": "first_name", "read_only": 1, "unique": 1, "search_index": 1},
	],
	"Item Supplier": [
		{"fieldname": "bimap_alphaerp_relation_key", "label": "Relación AlphaERP", "fieldtype": "Data", "insert_after": "supplier_part_no", "read_only": 1},
		{"fieldname": "bimap_alphaerp_last_cost", "label": "Último costo AlphaERP", "fieldtype": "Currency", "insert_after": "bimap_alphaerp_relation_key", "read_only": 1},
		{"fieldname": "bimap_alphaerp_currency", "label": "Moneda AlphaERP", "fieldtype": "Data", "insert_after": "bimap_alphaerp_last_cost", "read_only": 1},
		{"fieldname": "bimap_alphaerp_delivery_days", "label": "Días entrega AlphaERP", "fieldtype": "Int", "insert_after": "bimap_alphaerp_currency", "read_only": 1},
	],
}


def _rows(workbook, sheet):
	return next((row["rows"] for row in workbook["sheets"] if row["name"] == sheet), [])


def _text(value):
	return str(value or "").strip()


def _safe_email(value):
	value = _text(value)
	return validate_email_address(value, throw=False) or ""


def _commercial(label):
	label = _text(label)
	upper = label.upper()
	for tier in TIERS:
		if upper == tier or upper.endswith(" " + tier):
			return label[:-len(tier)].rstrip(" -/") or label, tier
	return label or "General", ""


def _tax_name(profile):
	parts = [f"IVA {_rate(profile.get('IVA'))}"]
	if flt(profile.get("Retención IVA")):
		parts.append(f"RET IVA {_rate(profile.get('Retención IVA'))}")
	if flt(profile.get("Retención ISR")):
		parts.append(f"RET ISR {_rate(profile.get('Retención ISR'))}")
	if profile.get("Maneja IEPS"):
		parts.append("IEPS")
	if profile.get("Exento"):
		parts.append("EXENTO")
	return " ".join(parts)


def _rate(value):
	value = flt(value)
	return ("%.6f" % value).rstrip("0").rstrip(".") or "0"


class AlphaERPCatalogExecutor:
	def __init__(self, source_directory, *, company=None, commit=True):
		self.source_directory = source_directory
		self.company = company or frappe.defaults.get_global_default("company")
		self.commit = commit
		self.workbook = normalize_package(source_directory)
		self.stats = Counter()
		self.errors = []
		self.maps = {"sales_persons": {}, "customers": {}, "suppliers": {}, "items": {}, "variants": {}, "price_lists": {}, "currencies": {}}
		self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency") or "MXN"
		self.abbr = frappe.get_cached_value("Company", self.company, "abbr")

	def run(self):
		started = now_datetime()
		self._step("custom_fields", self._prepare_custom_fields)
		self._step("currencies", self._import_currencies)
		self._step("uoms", self._import_uoms)
		self._step("price_lists", self._import_price_lists)
		self._step("taxes", self._prepare_taxes)
		self._step("party_groups", self._prepare_party_groups)
		self._step("item_groups", self._prepare_item_groups)
		self._step("sales_persons", self._import_sales_persons)
		self._step("customers", self._import_customers)
		self._step("suppliers", self._import_suppliers)
		self._step("items", self._import_items)
		self._step("variants", self._import_variants)
		self._step("item_uoms", self._import_item_uoms)
		self._step("supplier_relations", self._import_supplier_relations)
		self._step("addresses", self._import_addresses)
		self._step("contacts", self._import_contacts)
		self._step("prices", self._import_prices)
		result = {
			"company": self.company,
			"source_fingerprint": self.workbook["source"]["manifest"].get("fingerprint"),
			"started": str(started), "finished": str(now_datetime()),
			"stats": dict(self.stats), "errors": self.errors,
		}
		path = frappe.get_site_path("private", "files", "alphaerp-catalog-migration.json")
		with open(path, "w", encoding="utf-8") as handle:
			json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
		if self.commit:
			frappe.db.commit()
		return result

	def _step(self, name, method):
		print(f"ALPHAERP START {name}")
		try:
			method()
		except Exception as exc:
			self._error(name, "", exc, fatal=True)
			raise
		if self.commit:
			frappe.db.commit()
		print(f"ALPHAERP DONE {name} {dict(self.stats)}")

	def _error(self, entity, key, exc, *, fatal=False):
		message = str(exc)
		self.errors.append({"entity": entity, "key": key, "error": message, "fatal": fatal, "traceback": traceback.format_exc() if fatal else ""})
		self.stats[f"{entity}_errors"] += 1
		if fatal or len(self.errors) <= 20 or len(self.errors) % 250 == 0:
			print(f"ALPHAERP ERROR {entity} {key}: {message}")

	def _save(self, doc, entity, key):
		savepoint = f"alphaerp_{re.sub(r'[^a-z0-9_]', '_', entity.lower())}_{self.stats[f'{entity}_saved'] % 1000}"
		frappe.db.savepoint(savepoint)
		try:
			doc.flags.ignore_mandatory = False
			doc.save(ignore_permissions=True)
			self.stats[f"{entity}_saved"] += 1
			if self.commit and self.stats[f"{entity}_saved"] % BATCH_SIZE == 0:
				frappe.db.commit()
			return doc
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			self._error(entity, key, exc)
			return None

	def _prepare_custom_fields(self):
		from bimap_data_engine.custom_fields import sync_alphaerp_commercial_fields
		sync_alphaerp_commercial_fields()
		create_custom_fields(TRACE_FIELDS, update=True)
		frappe.clear_cache()

	def _import_currencies(self):
		for row in _rows(self.workbook, "Monedas"):
			iso = _text(row.get("Moneda ISO"))
			if not iso:
				continue
			if not frappe.db.exists("Currency", iso):
				doc = frappe.get_doc({"doctype": "Currency", "currency_name": iso, "enabled": 1, "fraction": "Centavo", "fraction_units": 100})
				self._save(doc, "currency", iso)
			self.maps["currencies"][_text(row.get("Moneda AlphaERP"))] = iso

	def _import_uoms(self):
		for row in _rows(self.workbook, "Unidades"):
			name = _text(row.get("Unidad AlphaERP"))
			if name and not frappe.db.exists("UOM", name):
				self._save(frappe.get_doc({"doctype": "UOM", "uom_name": name, "must_be_whole_number": 0}), "uom", name)

	def _import_price_lists(self):
		for row in _rows(self.workbook, "Listas de precios"):
			key = _text(row.get("Lista de precios AlphaERP"))
			label = _text(row.get("Nombre")) or f"Lista {key}"
			name = frappe.db.get_value("Price List", {"bimap_alphaerp_price_list": key}, "name") or frappe.db.get_value("Price List", {"price_list_name": label}, "name")
			doc = frappe.get_doc("Price List", name) if name else frappe.new_doc("Price List")
			doc.update({"price_list_name": label, "bimap_alphaerp_price_list": key, "currency": self.company_currency, "selling": 1, "buying": 0, "enabled": 1})
			doc = self._save(doc, "price_list", key)
			if doc:
				self.maps["price_lists"][key] = doc.name

	def _tax_account(self, title):
		full = f"{title} - {self.abbr}"
		if frappe.db.exists("Account", full):
			return full
		doc = frappe.get_doc({"doctype": "Account", "account_name": title, "company": self.company, "parent_account": f"Duties and Taxes - {self.abbr}", "account_type": "Tax", "root_type": "Liability", "is_group": 0})
		doc.insert(ignore_permissions=True)
		return doc.name

	def _prepare_taxes(self):
		self.tax_categories = {}
		accounts = {
			"iva": self._tax_account("IVA"), "ret_iva": self._tax_account("Retención IVA"),
			"ret_isr": self._tax_account("Retención ISR"), "ieps": self._tax_account("IEPS"),
		}
		for row in _rows(self.workbook, "Perfiles fiscales"):
			party = row["Tipo de tercero"]
			key = _text(row["Clave fiscal AlphaERP"])
			name = _tax_name(row)
			category = frappe.db.get_value("Tax Category", {"title": name}, "name")
			if not category:
				doc = frappe.get_doc({"doctype": "Tax Category", "title": name, "disabled": 0})
				doc.insert(ignore_permissions=True)
				category = doc.name
			self.tax_categories[(party, key)] = category
			doctype = "Sales Taxes and Charges Template" if party == "Cliente" else "Purchase Taxes and Charges Template"
			template_name = f"{name} - {'Ventas' if party == 'Cliente' else 'Compras'}"
			if frappe.db.exists(doctype, {"title": template_name, "company": self.company}):
				continue
			taxes = []
			if flt(row.get("IVA")) and not row.get("Exento"):
				taxes.append({"charge_type": "On Net Total", "account_head": accounts["iva"], "description": f"IVA {_rate(row['IVA'])}", "rate": flt(row["IVA"])})
			if flt(row.get("Retención IVA")):
				taxes.append({"charge_type": "On Net Total", "account_head": accounts["ret_iva"], "description": f"Retención IVA {_rate(row['Retención IVA'])}", "rate": -abs(flt(row["Retención IVA"]))})
			if flt(row.get("Retención ISR")):
				taxes.append({"charge_type": "On Net Total", "account_head": accounts["ret_isr"], "description": f"Retención ISR {_rate(row['Retención ISR'])}", "rate": -abs(flt(row["Retención ISR"]))})
			if taxes:
				doc = frappe.get_doc({"doctype": doctype, "title": template_name, "company": self.company, "tax_category": category, "is_default": 0, "disabled": 0, "taxes": taxes})
				self._save(doc, "tax_template", f"{party}:{key}")

	def _prepare_party_groups(self):
		self.party_groups = {}
		for row in _rows(self.workbook, "Perfiles fiscales"):
			party = row["Tipo de tercero"]
			key = _text(row["Clave fiscal AlphaERP"])
			group, tier = _commercial(row.get("Descripción"))
			doctype = "Customer Group" if party == "Cliente" else "Supplier Group"
			parent = "All Customer Groups" if party == "Cliente" else "All Supplier Groups"
			if not frappe.db.exists(doctype, group):
				doc = frappe.get_doc({"doctype": doctype, ("customer_group_name" if party == "Cliente" else "supplier_group_name"): group, ("parent_customer_group" if party == "Cliente" else "parent_supplier_group"): parent, "is_group": 0})
				self._save(doc, "party_group", f"{party}:{key}")
			self.party_groups[(party, key)] = (group, tier, _text(row.get("Descripción")))

	def _prepare_item_groups(self):
		self.item_groups = {}
		for row in _rows(self.workbook, "Productos"):
			path = _text(row.get("Ruta grupo de artículos"))
			if path in self.item_groups:
				continue
			parent = "All Item Groups"
			parts = [part.strip() for part in path.split("/") if part.strip()] or ["Products"]
			for index, part in enumerate(parts):
				is_last = index == len(parts) - 1
				name = part
				if frappe.db.exists("Item Group", name):
					existing_parent = frappe.db.get_value("Item Group", name, "parent_item_group")
					if existing_parent != parent and name != "Products":
						name = f"{part} / {parent}"[:140]
				if not frappe.db.exists("Item Group", name):
					doc = frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent, "is_group": 0 if is_last else 1})
					self._save(doc, "item_group", path)
				elif not is_last and not cint(frappe.db.get_value("Item Group", name, "is_group")):
					# Existing leaves cannot receive children. Keep the remaining path flattened.
					name = (" / ".join(parts[: index + 1]))[:140]
					if not frappe.db.exists("Item Group", name):
						self._save(frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups", "is_group": 1}), "item_group", path)
				parent = name
			self.item_groups[path] = parent

	def _import_customers(self):
		for row in _rows(self.workbook, "Clientes"):
			key = _text(row["Clave AlphaERP"])
			name = frappe.db.get_value("Customer", {"bimap_customer_number": key}, "name")
			doc = frappe.get_doc("Customer", name) if name else frappe.new_doc("Customer")
			group, tier, source = self.party_groups.get(("Cliente", _text(row.get("Tipo fiscal AlphaERP"))), ("Commercial", "", ""))
			price_list = self.maps["price_lists"].get(_text(row.get("Lista de precios AlphaERP")))
			doc.update({"customer_name": _text(row.get("Nombre")) or f"Cliente {key}", "customer_type": "Company", "customer_group": group, "territory": "Mexico", "tax_id": _text(row.get("RFC")), "bimap_customer_number": key, "default_currency": _text(row.get("Moneda ISO")) or self.company_currency, "default_price_list": price_list, "tax_category": self.tax_categories.get(("Cliente", _text(row.get("Tipo fiscal AlphaERP")))), "bimap_alphaerp_tax_profile": _text(row.get("Tipo fiscal AlphaERP")), "bimap_alphaerp_commercial_classification": source, "bimap_commercial_tier": tier, "bimap_alphaerp_zone": _text(row.get("Zona AlphaERP")), "bimap_alphaerp_subzone": _text(row.get("Subzona AlphaERP")), "disabled": 0})
			self._set_primary_sales_person(doc, row)
			doc = self._save(doc, "customer", key)
			if doc:
				self.maps["customers"][key] = doc.name

	def _import_sales_persons(self):
		for row in _rows(self.workbook, "Vendedores"):
			key = _text(row.get("Clave vendedor AlphaERP"))
			if not key:
				continue
			name = frappe.db.get_value("Sales Person", {"bimap_alphaerp_agent_code": key}, "name")
			if not name:
				name = frappe.db.get_value("Sales Person", {"sales_person_name": _text(row.get("Nombre"))}, "name")
			doc = frappe.get_doc("Sales Person", name) if name else frappe.new_doc("Sales Person")
			doc.update({
				"sales_person_name": _text(row.get("Nombre")) or f"Vendedor {key}",
				"parent_sales_person": "Sales Team",
				"is_group": 0,
				"enabled": 1,
				"bimap_alphaerp_agent_code": key,
			})
			doc = self._save(doc, "sales_person", key)
			if doc:
				self.maps["sales_persons"][key] = doc.name

	def _set_primary_sales_person(self, doc, row):
		key = _text(row.get("Clave vendedor AlphaERP"))
		sales_person = self.maps["sales_persons"].get(key)
		if not key or not sales_person:
			return
		doc.set("sales_team", [])
		doc.append("sales_team", {"sales_person": sales_person, "allocated_percentage": 100})

	def _assign_customer_sales_persons(self):
		for row in _rows(self.workbook, "Clientes"):
			key = _text(row.get("Clave AlphaERP"))
			name = frappe.db.get_value("Customer", {"bimap_customer_number": key}, "name")
			if not name:
				self.stats["customer_sales_person_orphan"] += 1
				continue
			agent_key = _text(row.get("Clave vendedor AlphaERP"))
			if not agent_key or agent_key not in self.maps["sales_persons"]:
				continue
			doc = frappe.get_doc("Customer", name)
			self._set_primary_sales_person(doc, row)
			self._save(doc, "customer_sales_person", key)

	def _import_suppliers(self):
		for row in _rows(self.workbook, "Proveedores"):
			key = _text(row["Clave AlphaERP"])
			name = frappe.db.get_value("Supplier", {"bimap_supplier_number": key}, "name")
			doc = frappe.get_doc("Supplier", name) if name else frappe.new_doc("Supplier")
			group, tier, source = self.party_groups.get(("Proveedor", _text(row.get("Tipo fiscal AlphaERP"))), ("Local", "", ""))
			doc.update({"supplier_name": _text(row.get("Nombre")) or f"Proveedor {key}", "supplier_type": "Company", "supplier_group": group, "country": "Mexico", "tax_id": _text(row.get("RFC")), "bimap_supplier_number": key, "default_currency": _text(row.get("Moneda ISO")) or self.company_currency, "tax_category": self.tax_categories.get(("Proveedor", _text(row.get("Tipo fiscal AlphaERP")))), "bimap_alphaerp_tax_profile": _text(row.get("Tipo fiscal AlphaERP")), "bimap_alphaerp_commercial_classification": source, "bimap_commercial_tier": tier, "disabled": 0})
			doc = self._save(doc, "supplier", key)
			if doc:
				self.maps["suppliers"][key] = doc.name

	def _tax_json(self, row):
		return json.dumps({key: row.get(key) for key in ("Modo IVA", "Tasa IVA producto", "No objeto de impuesto", "Maneja IEPS", "Tipo IEPS", "Porcentaje IEPS", "Unidad IEPS", "Monto IEPS", "Excluir IEPS de base IVA", "IVA IMMEX", "Modo retención IVA", "Tasa retención IVA producto", "Modo retención ISR", "Tasa retención ISR producto")}, ensure_ascii=False, default=str)

	def _import_items(self):
		for row in _rows(self.workbook, "Productos"):
			key = _text(row["Clave AlphaERP"])
			doc = frappe.get_doc("Item", key) if frappe.db.exists("Item", key) else frappe.new_doc("Item")
			doc.update({"item_code": key, "item_name": _text(row.get("Nombre")) or key, "description": _text(row.get("Descripción")) or _text(row.get("Nombre")) or key, "item_group": self.item_groups.get(_text(row.get("Ruta grupo de artículos")), "Products"), "stock_uom": _text(row.get("Unidad AlphaERP")) or "Nos.", "is_stock_item": 1, "has_batch_no": cint(row.get("Maneja lotes")), "shelf_life_in_days": cint(row.get("Vida útil días")), "disabled": 0, "bimap_alphaerp_base_item": key, "bimap_alphaerp_variant_code": "", "bimap_alphaerp_attributes": "", "bimap_alphaerp_tax_config": self._tax_json(row), "bimap_alphaerp_sat_product_code": _text(row.get("Clave producto SAT"))})
			barcode = _text(row.get("Código de barras"))
			if barcode and not frappe.db.exists("Item Barcode", {"barcode": barcode}) and not any(child.barcode == barcode for child in doc.barcodes):
				doc.append("barcodes", {"barcode": barcode, "uom": doc.stock_uom})
			doc = self._save(doc, "item", key)
			if doc:
				self.maps["items"][key] = doc.name

	def _variant_item_code(self, base, variant):
		return f"{base}::{variant}"[:140]

	def _import_variants(self):
		base_rows = {_text(row["Clave AlphaERP"]): row for row in _rows(self.workbook, "Productos")}
		for row in _rows(self.workbook, "Variantes"):
			base = _text(row.get("Clave producto AlphaERP"))
			variant = _text(row.get("Código variante AlphaERP"))
			if not base or not variant or base not in self.maps["items"]:
				self.stats["variant_skipped"] += 1
				continue
			code = self._variant_item_code(base, variant)
			base_row = base_rows[base]
			doc = frappe.get_doc("Item", code) if frappe.db.exists("Item", code) else frappe.new_doc("Item")
			attrs = {f"Atributo {i}": row.get(f"Atributo {i}") for i in range(1, 13) if _text(row.get(f"Atributo {i}"))}
			doc.update({"item_code": code, "item_name": f"{_text(base_row.get('Nombre')) or base} - {variant}", "description": _text(base_row.get("Descripción")) or _text(base_row.get("Nombre")) or base, "item_group": self.item_groups.get(_text(base_row.get("Ruta grupo de artículos")), "Products"), "stock_uom": _text(base_row.get("Unidad AlphaERP")) or "Nos.", "is_stock_item": 1, "has_batch_no": cint(base_row.get("Maneja lotes")), "shelf_life_in_days": cint(base_row.get("Vida útil días")), "disabled": 0, "bimap_alphaerp_base_item": base, "bimap_alphaerp_variant_code": variant, "bimap_alphaerp_attributes": json.dumps(attrs, ensure_ascii=False), "bimap_alphaerp_tax_config": self._tax_json(base_row), "bimap_alphaerp_sat_product_code": _text(base_row.get("Clave producto SAT"))})
			barcode = _text(row.get("Código de barras"))
			if barcode and not frappe.db.exists("Item Barcode", {"barcode": barcode}) and not any(child.barcode == barcode for child in doc.barcodes):
				doc.append("barcodes", {"barcode": barcode, "uom": doc.stock_uom})
			doc = self._save(doc, "variant", f"{base}:{variant}")
			if doc:
				self.maps["variants"][(base, variant)] = doc.name

	def _target_item(self, base, variant=""):
		return self.maps["variants"].get((base, variant)) if variant else self.maps["items"].get(base)

	def _import_item_uoms(self):
		by_item = defaultdict(list)
		for row in _rows(self.workbook, "Unidades de producto"):
			by_item[_text(row.get("Clave producto AlphaERP"))].append(row)
		for base, rows in by_item.items():
			name = self.maps["items"].get(base)
			if not name:
				continue
			doc = frappe.get_doc("Item", name)
			for row in rows:
				uom = _text(row.get("Unidad AlphaERP")) or _text(row.get("Unidad conversión AlphaERP"))
				factor = flt(row.get("Factor")) or 1
				if uom and not any(child.uom == uom for child in doc.uoms):
					doc.append("uoms", {"uom": uom, "conversion_factor": factor})
			self._save(doc, "item_uom", base)

	def _import_supplier_relations(self):
		grouped = defaultdict(list)
		for row in _rows(self.workbook, "Relaciones proveedor-producto"):
			item = self._target_item(_text(row.get("Clave producto AlphaERP")), _text(row.get("Código variante AlphaERP")))
			supplier = self.maps["suppliers"].get(_text(row.get("Clave proveedor AlphaERP")))
			if not item or not supplier:
				self.stats["supplier_relation_orphan"] += 1
				continue
			grouped[item].append((supplier, row))
		for item, relations in grouped.items():
			doc = frappe.get_doc("Item", item)
			for supplier, row in relations:
				key = _text(row.get("Identificador relación"))
				child = next((entry for entry in doc.supplier_items if entry.get("bimap_alphaerp_relation_key") == key), None)
				if not child:
					child = doc.append("supplier_items", {})
				child.update({"supplier": supplier, "supplier_part_no": _text(row.get("Clave SAT proveedor")) or _text(row.get("Código variante AlphaERP")), "bimap_alphaerp_relation_key": key, "bimap_alphaerp_last_cost": flt(row.get("Último costo")), "bimap_alphaerp_currency": self.maps["currencies"].get(_text(row.get("Moneda AlphaERP")), self.company_currency), "bimap_alphaerp_delivery_days": cint(row.get("Días de entrega"))})
			self._save(doc, "supplier_relation", item)

	def _country(self, value):
		value = _text(value)
		if value and frappe.db.exists("Country", value):
			return value
		if value.upper() in {"MX", "MEX", "MEXICO", "MÉXICO"}:
			return "Mexico"
		return "Mexico"

	def _import_addresses(self):
		for row in _rows(self.workbook, "Direcciones"):
			key = _text(row.get("Identificador dirección"))
			party_type = row.get("Tipo de tercero")
			party = (self.maps["customers"] if party_type == "Cliente" else self.maps["suppliers"]).get(_text(row.get("Clave AlphaERP")))
			if not party:
				self.stats["address_orphan"] += 1
				continue
			meaningful = any(_text(row.get(field)) for field in ("Calle", "Colonia", "Ciudad", "Municipio", "Estado", "Código postal"))
			if not meaningful:
				self.stats["address_empty"] += 1
				continue
			name = frappe.db.get_value("Address", {"bimap_alphaerp_address_key": key}, "name")
			doc = frappe.get_doc("Address", name) if name else frappe.new_doc("Address")
			address_type = "Shipping" if row.get("Tipo de dirección") == "Envío" else "Billing"
			line1 = " ".join(filter(None, (_text(row.get("Calle")), _text(row.get("Número exterior"))))) or _text(row.get("Colonia")) or "Sin calle"
			line2 = " ".join(filter(None, (_text(row.get("Número interior")), _text(row.get("Colonia")))))
			doc.update({"address_title": _text(row.get("Título")) or party, "bimap_alphaerp_address_key": key, "address_type": address_type, "address_line1": line1[:140], "address_line2": line2[:140], "city": (_text(row.get("Ciudad")) or _text(row.get("Municipio")) or "Sin ciudad")[:140], "state": _text(row.get("Estado")), "pincode": _text(row.get("Código postal")), "country": self._country(row.get("País")), "is_primary_address": 1 if row.get("Tipo de dirección") == "Principal" else 0, "is_shipping_address": 1 if address_type == "Shipping" else 0})
			doc.set("links", [])
			doc.append("links", {"link_doctype": "Customer" if party_type == "Cliente" else "Supplier", "link_name": party})
			self._save(doc, "address", key)

	def _import_contacts(self, keys=None):
		for row in _rows(self.workbook, "Contactos"):
			key = _text(row.get("Identificador contacto"))
			if keys is not None and key not in keys:
				continue
			is_customer = bool(row.get("Clave cliente AlphaERP"))
			party = (self.maps["customers"] if is_customer else self.maps["suppliers"]).get(_text(row.get("Clave cliente AlphaERP") or row.get("Clave proveedor AlphaERP")))
			if not party:
				self.stats["contact_orphan"] += 1
				continue
			if not any(_text(row.get(field)) for field in ("Nombre", "Teléfono", "Móvil", "Correo")):
				self.stats["contact_empty"] += 1
				continue
			name = frappe.db.get_value("Contact", {"bimap_alphaerp_contact_key": key}, "name")
			doc = frappe.get_doc("Contact", name) if name else frappe.new_doc("Contact")
			doc.update({"first_name": _text(row.get("Nombre")) or party, "designation": _text(row.get("Puesto")), "bimap_alphaerp_contact_key": key})
			doc.set("links", [])
			doc.append("links", {"link_doctype": "Customer" if is_customer else "Supplier", "link_name": party})
			doc.set("email_ids", [])
			if _safe_email(row.get("Correo")):
				doc.append("email_ids", {"email_id": _safe_email(row.get("Correo")), "is_primary": 1})
			doc.set("phone_nos", [])
			for index, phone in enumerate(filter(None, (_text(row.get("Teléfono")), _text(row.get("Teléfono alterno")), _text(row.get("Móvil"))))):
				doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1 if index == 0 else 0, "is_primary_mobile_no": 1 if phone == _text(row.get("Móvil")) else 0})
			self._save(doc, "contact", key)

	def _import_prices(self, only_duplicate_keys=False):
		rows = _rows(self.workbook, "Precios")
		key_counts = Counter(_text(row.get("Identificador precio")) for row in rows)
		key_seen = Counter()
		for row in rows:
			key = _text(row.get("Identificador precio"))
			if only_duplicate_keys and key_counts[key] < 2:
				continue
			key_seen[key] += 1
			if key_seen[key] > 1:
				key = f"{key}:QTY:{_text(row.get('Cantidad desde'))}:{_text(row.get('Cantidad hasta'))}"
			item = self._target_item(_text(row.get("Clave producto AlphaERP")), _text(row.get("Código variante AlphaERP")))
			if not item:
				self.stats["price_orphan"] += 1
				continue
			customer = self.maps["customers"].get(_text(row.get("Clave cliente AlphaERP")))
			if row.get("Origen") == "Especial cliente":
				price_list = next(iter(self.maps["price_lists"].values()), "Standard Selling")
				currency = self.maps["currencies"].get(_text(row.get("Moneda AlphaERP")), self.company_currency)
			else:
				price_list = self.maps["price_lists"].get(_text(row.get("Lista de precios AlphaERP")))
				currency = frappe.get_cached_value("Price List", price_list, "currency") if price_list else self.company_currency
			if not price_list or (row.get("Origen") == "Especial cliente" and not customer):
				self.stats["price_orphan"] += 1
				continue
			name = frappe.db.get_value("Item Price", {"bimap_alphaerp_price_key": key}, "name")
			doc = frappe.get_doc("Item Price", name) if name else frappe.new_doc("Item Price")
			uom = frappe.get_cached_value("Item", item, "stock_uom")
			doc.update({"item_code": item, "bimap_alphaerp_price_key": key, "price_list": price_list, "price_list_rate": flt(row.get("Precio")), "currency": currency, "uom": uom, "customer": customer, "min_qty": flt(row.get("Cantidad desde")), "valid_from": row.get("Fecha precio") or None})
			self._save(doc, "price", key)


def execute_catalog_migration(source_directory=None, company=None, commit=True):
	"""Run the complete catalog migration and return counters plus error details."""
	source_directory = source_directory or frappe.conf.get("bimap_alphaerp_source_directory")
	if not source_directory:
		frappe.throw("No está configurado bimap_alphaerp_source_directory.")
	return AlphaERPCatalogExecutor(source_directory, company=company, commit=commit).run()
