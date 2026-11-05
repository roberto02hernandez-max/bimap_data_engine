"""Server-side enforcement of AlphaERP product-type matrices."""

from __future__ import annotations

import frappe
from frappe import _


SALES_DOCTYPES = {"Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"}
PURCHASE_DOCTYPES = {"Purchase Order", "Purchase Receipt", "Purchase Invoice"}
STOCK_DOCTYPES = {"Stock Entry", "Stock Reconciliation"}


def _item_type(item_code):
	return frappe.get_cached_value("Item", item_code, "bimap_product_type")


def _type_allowed(product_type, fieldname):
	return not product_type or bool(frappe.get_cached_value("BIMAP Product Type", product_type, fieldname))


def _customer_allowed(customer, product_type):
	if not customer or not product_type:
		return True
	filters = {"customer": customer, "enabled": 1}
	if not frappe.db.exists("BIMAP Customer Product Type Rule", filters):
		# AlphaERP contains 378 customers with no matrix rows.  Absence means the
		# source imposed no restriction; it must not accidentally block all sales.
		return True
	filters["product_type"] = product_type
	return bool(frappe.db.exists("BIMAP Customer Product Type Rule", filters))


def _warehouse_allowed(warehouse, product_type):
	if not warehouse or not product_type:
		return True
	filters = {"warehouse": warehouse, "enabled": 1}
	if not frappe.db.exists("BIMAP Warehouse Product Type Rule", filters):
		return True
	filters["product_type"] = product_type
	return bool(frappe.db.exists("BIMAP Warehouse Product Type Rule", filters))


def validate_product_type_restrictions(doc, method=None):
	if doc.doctype not in SALES_DOCTYPES | PURCHASE_DOCTYPES | STOCK_DOCTYPES:
		return
	operation_field = "allow_sales" if doc.doctype in SALES_DOCTYPES else "allow_purchase" if doc.doctype in PURCHASE_DOCTYPES else "allow_stock"
	customer = doc.get("customer")
	for index, row in enumerate(doc.get("items") or [], start=1):
		item = row.get("item_code")
		if not item:
			continue
		product_type = _item_type(item)
		if not _type_allowed(product_type, operation_field):
			frappe.throw(_("Fila {0}: el tipo {1} no permite esta operación para el producto {2}.").format(index, product_type, item))
		if doc.doctype in SALES_DOCTYPES and not _customer_allowed(customer, product_type):
			frappe.throw(_("Fila {0}: el cliente no puede comprar productos del tipo {1}.").format(index, product_type))
		warehouse = row.get("warehouse") or row.get("s_warehouse") or row.get("t_warehouse")
		if not _warehouse_allowed(warehouse, product_type):
			frappe.throw(_("Fila {0}: el tipo {1} no está permitido en el almacén {2}.").format(index, product_type, warehouse))

