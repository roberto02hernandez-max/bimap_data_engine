"""Curated, permission-aware import choices and capture templates."""

import frappe

from bimap_data_engine.services.metadata import writable_fieldnames


CATALOG = [
	{
		"id": "sales",
		"label": "Ventas",
		"documents": [
			("Quotation", "Cotizaciones", [
				("party_name", "Cliente"), ("transaction_date", "Fecha"),
				("valid_till", "Válida hasta"), ("currency", "Moneda"),
			]),
			("Sales Order", "Pedidos de venta", [
				("customer", "Cliente"), ("transaction_date", "Fecha"),
				("delivery_date", "Fecha de entrega"), ("currency", "Moneda"),
				("customer_po_no", "Orden de compra del cliente"),
			]),
			("Delivery Note", "Remisiones de venta", [
				("customer", "Cliente"), ("posting_date", "Fecha"),
				("set_warehouse", "Almacén"),
			]),
			("Sales Invoice", "Facturas de venta", [
				("customer", "Cliente"), ("posting_date", "Fecha"),
				("due_date", "Fecha de vencimiento"), ("currency", "Moneda"),
				("update_stock", "Afectar inventario"), ("set_warehouse", "Almacén"),
			]),
		],
	},
	{
		"id": "purchases",
		"label": "Compras",
		"documents": [
			("Supplier Quotation", "Cotizaciones de proveedor", [
				("supplier", "Proveedor"), ("transaction_date", "Fecha"),
				("valid_till", "Válida hasta"), ("currency", "Moneda"),
			]),
			("Purchase Order", "Órdenes de compra", [
				("supplier", "Proveedor"), ("transaction_date", "Fecha"),
				("schedule_date", "Fecha requerida"), ("currency", "Moneda"),
			]),
			("Purchase Receipt", "Recepciones de compra", [
				("supplier", "Proveedor"), ("posting_date", "Fecha"),
				("set_warehouse", "Almacén"),
			]),
			("Purchase Invoice", "Facturas de proveedor", [
				("supplier", "Proveedor"), ("posting_date", "Fecha"),
				("due_date", "Fecha de vencimiento"), ("bill_no", "Folio del proveedor"),
				("bill_date", "Fecha de factura"), ("currency", "Moneda"),
				("update_stock", "Afectar inventario"), ("set_warehouse", "Almacén"),
			]),
		],
	},
	{
		"id": "stock",
		"label": "Almacén e inventario",
		"documents": [
			("Stock Entry", "Movimientos de almacén", [
				("stock_entry_type", "Tipo de movimiento"), ("posting_date", "Fecha"),
				("from_warehouse", "Almacén origen"), ("to_warehouse", "Almacén destino"),
			]),
			("Stock Reconciliation", "Conciliaciones de inventario", [
				("posting_date", "Fecha"), ("posting_time", "Hora"),
			]),
		],
	},
	{
		"id": "catalogs",
		"label": "Catálogos",
		"documents": [
			("Customer", "Clientes", [
				("bimap_customer_number", "Clave de cliente"),
				("customer_name", "Nombre del cliente"), ("customer_type", "Tipo de cliente"),
				("customer_group", "Grupo de clientes"), ("territory", "Zona / subzona"),
				("tax_id", "RFC / identificación fiscal"),
			]),
			("Supplier", "Proveedores", [
				("bimap_supplier_number", "Clave de proveedor"),
				("supplier_name", "Nombre del proveedor"), ("supplier_group", "Grupo de proveedores"),
				("supplier_type", "Tipo de proveedor"), ("tax_id", "RFC / identificación fiscal"),
			]),
			("Item", "Artículos", [
				("item_code", "Clave del artículo"), ("item_name", "Nombre del artículo"),
				("item_group", "Grupo de artículos"), ("stock_uom", "Unidad de inventario"),
				("is_stock_item", "Controlar inventario"), ("description", "Descripción"),
			]),
			("Item Price", "Precios de artículos", [
				("item_code", "Artículo"), ("price_list", "Lista de precios"),
				("price_list_rate", "Precio"), ("uom", "Unidad"), ("currency", "Moneda"),
			]),
		],
	},
]


ITEM_FIELDS = [
	("item_code", "Clave de producto"), ("qty", "Cantidad"), ("uom", "Unidad"),
	("rate", "Precio unitario"), ("warehouse", "Almacén"),
	("conversion_factor", "Factor de conversión"),
]

STOCK_ENTRY_FIELDS = [
	("item_code", "Clave de producto"), ("qty", "Cantidad"), ("uom", "Unidad"),
	("s_warehouse", "Almacén origen"), ("t_warehouse", "Almacén destino"),
	("basic_rate", "Costo unitario"),
]

STOCK_RECONCILIATION_FIELDS = [
	("item_code", "Clave de producto"), ("warehouse", "Almacén"),
	("qty", "Existencia"), ("valuation_rate", "Costo de valoración"),
]

BUSINESS_REQUIRED = {
	"Quotation": {"party_name"},
	"Sales Order": {"customer"},
	"Delivery Note": {"customer"},
	"Sales Invoice": {"customer"},
	"Supplier Quotation": {"supplier"},
	"Purchase Order": {"supplier"},
	"Purchase Receipt": {"supplier"},
	"Purchase Invoice": {"supplier"},
	"Customer": {"bimap_customer_number"},
	"Supplier": {"bimap_supplier_number"},
}


def _field_spec(meta, configured_fields, parenttype=None):
	writable = writable_fieldnames(meta, parenttype=parenttype)
	result = []
	preferred = list(configured_fields)
	configured_names = {fieldname for fieldname, _label in preferred}
	available = [
		(df.fieldname, frappe._(df.label or df.fieldname))
		for df in meta.fields
		if df.fieldname in writable and df.fieldname not in configured_names
	]
	for fieldname, label in [*preferred, *available]:
		df = meta.get_field(fieldname)
		if not df or fieldname not in writable:
			continue
		field = {
			"fieldname": fieldname,
			"label": label,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"preferred": fieldname in configured_names,
			"required": bool(
				(fieldname in configured_names and df.reqd)
				or fieldname in BUSINESS_REQUIRED.get(meta.name, set())
				or fieldname == "item_code"
			),
		}
		lookup = _lookup_spec(meta.name, fieldname)
		if lookup:
			field["label"] = lookup["key_label"]
			field["lookup"] = lookup
		result.append(field)
	return result


def _catalog_for_permission(permission_type):
	"""Build the curated Spanish catalog for a concrete document operation."""
	areas = []
	for configured_area in CATALOG:
		documents = []
		for doctype, label, configured_fields in configured_area["documents"]:
			if (
				not frappe.db.exists("DocType", doctype)
				or not frappe.has_permission(doctype, permission_type)
				or (permission_type == "write" and not frappe.has_permission(doctype, "read"))
			):
				continue
			meta = frappe.get_meta(doctype)
			fields = _field_spec(meta, configured_fields)
			if not fields:
				continue
			documents.append({
				"id": doctype,
				"doctype": doctype,
				"label": label,
				"is_submittable": bool(meta.is_submittable),
				"fields": fields,
				"child": _child_template(meta),
			})
		if documents:
			areas.append({"id": configured_area["id"], "label": configured_area["label"], "documents": documents})
	return {"areas": areas}


def _lookup_spec(doctype, fieldname):
	"""Describe business-key lookups without changing ERPNext target fields."""
	if fieldname in {"customer", "party_name"} and doctype != "Customer":
		return {
			"kind": "customer", "doctype": "Customer",
			"key_field": "bimap_customer_number", "label_field": "customer_name",
			"key_label": "Clave de cliente", "display_label": "Nombre del cliente",
		}
	if fieldname == "supplier" and doctype != "Supplier":
		return {
			"kind": "supplier", "doctype": "Supplier",
			"key_field": "bimap_supplier_number", "label_field": "supplier_name",
			"key_label": "Clave de proveedor", "display_label": "Nombre del proveedor",
		}
	if fieldname == "item_code" and doctype != "Item":
		return {
			"kind": "item", "doctype": "Item",
			"key_field": "item_code", "label_field": "item_name",
			"key_label": "Clave de producto", "display_label": "Nombre del producto",
		}
	return None


def _child_template(meta):
	preferred = meta.get_field("items")
	if not preferred or preferred.fieldtype not in {"Table", "Table MultiSelect"}:
		return None
	child_meta = frappe.get_meta(preferred.options)
	if meta.name == "Stock Entry":
		configured = STOCK_ENTRY_FIELDS
	elif meta.name == "Stock Reconciliation":
		configured = STOCK_RECONCILIATION_FIELDS
	else:
		configured = ITEM_FIELDS
	fields = _field_spec(child_meta, configured, parenttype=meta.name)
	if not fields:
		return None
	return {
		"table_field": preferred.fieldname,
		"label": "Partidas",
		"doctype": preferred.options,
		"fields": fields,
	}


def get_import_catalog():
	"""Return only curated DocTypes the current user may create."""
	return _catalog_for_permission("create")


def get_edit_catalog():
	"""Return curated DocTypes the current user may read and update."""
	catalog = _catalog_for_permission("write")
	if not frappe.has_permission("Price List", "read"):
		return catalog
	catalog_area = next((area for area in catalog["areas"] if area["id"] == "catalogs"), None)
	if not catalog_area:
		return catalog
	base = next((document for document in catalog_area["documents"] if document["doctype"] == "Item Price"), None)
	if not base:
		return catalog
	price_lists = frappe.get_list(
		"Price List",
		fields=["name", "price_list_name", "currency", "selling", "buying", "enabled"],
		order_by="price_list_name asc",
		limit_page_length=0,
	)
	dynamic_documents = []
	for price_list in price_lists:
		kind = "Venta" if price_list.selling else "Compra" if price_list.buying else "General"
		state = "" if price_list.enabled else " · Deshabilitada"
		dynamic_documents.append({
			**base,
			"id": f"Item Price::{price_list.name}",
			"label": f"Precios — {price_list.price_list_name} ({kind} · {price_list.currency or 'sin moneda'}{state})",
			"filters": {"price_list": price_list.name},
			"price_list": {
				"name": price_list.name,
				"label": price_list.price_list_name,
				"currency": price_list.currency,
				"selling": bool(price_list.selling),
				"buying": bool(price_list.buying),
				"enabled": bool(price_list.enabled),
			},
		})
	base["label"] = "Precios de artículos — todas las listas"
	catalog_area["documents"].extend(dynamic_documents)
	return catalog
