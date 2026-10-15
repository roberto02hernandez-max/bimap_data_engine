"""Registry for ERPNext's own related-document conversion functions."""

import inspect

import frappe
from frappe.utils import cstr


NATIVE_MAPPERS = {
	("Quotation", "Sales Order"): "erpnext.selling.doctype.quotation.quotation.make_sales_order",
	("Sales Order", "Delivery Note"): "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
	("Sales Order", "Sales Invoice"): "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
	("Delivery Note", "Sales Invoice"): "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
	("Supplier Quotation", "Purchase Order"): "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order",
	("Purchase Order", "Purchase Receipt"): "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
	("Purchase Order", "Purchase Invoice"): "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
	("Purchase Receipt", "Purchase Invoice"): "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
}


def get_native_mapper(source_doctype, target_doctype):
	source_doctype = cstr(source_doctype).strip()
	target_doctype = cstr(target_doctype).strip()
	path = NATIVE_MAPPERS.get((source_doctype, target_doctype))
	if not path:
		frappe.throw(
			f"Conversión nativa no soportada: {source_doctype} → {target_doctype}."
		)
	return frappe.get_attr(path)


def make_related_document(source_doctype, source_name, target_doctype, *, args=None):
	"""Map an existing source through ERPNext and re-check permissions for the caller."""
	source_doctype = cstr(source_doctype).strip()
	source_name = cstr(source_name).strip()
	target_doctype = cstr(target_doctype).strip()
	if not source_name:
		frappe.throw("El documento origen es obligatorio.")
	frappe.has_permission(source_doctype, "read", doc=source_name, throw=True)
	frappe.has_permission(target_doctype, "create", throw=True)
	mapper = get_native_mapper(source_doctype, target_doctype)
	parameters = inspect.signature(mapper).parameters
	if "args" in parameters:
		target = mapper(source_name, args=args or {})
	elif "kwargs" in parameters:
		target = mapper(source_name, kwargs=args or {})
	else:
		target = mapper(source_name)
	if not target or target.doctype != target_doctype:
		frappe.throw("El mapeador nativo devolvió un documento inesperado.")
	target.flags.ignore_permissions = False
	target.check_permission("create")
	return target
