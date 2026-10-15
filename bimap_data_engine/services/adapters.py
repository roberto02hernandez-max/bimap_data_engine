"""Small, explicit adapters for DocTypes whose native setup precedes validation."""

import frappe


def prepare_trading_document(doc):
	"""Use ERPNext's own setup and totals logic for sales/purchase transactions."""
	doc.set_missing_values(for_validate=True)
	doc.calculate_taxes_and_totals()


BUILT_IN_IMPORT_ADAPTERS = {
	"Quotation": prepare_trading_document,
	"Sales Order": prepare_trading_document,
	"Delivery Note": prepare_trading_document,
	"Sales Invoice": prepare_trading_document,
	"Purchase Order": prepare_trading_document,
	"Purchase Receipt": prepare_trading_document,
	"Purchase Invoice": prepare_trading_document,
}


def prepare_import_document(doc):
	adapter = BUILT_IN_IMPORT_ADAPTERS.get(doc.doctype)
	hook_adapters = frappe.get_hooks("bimap_data_engine_import_adapters") or {}
	if isinstance(hook_adapters, dict) and doc.doctype in hook_adapters:
		adapter = frappe.get_attr(hook_adapters[doc.doctype])
	if adapter:
		adapter(doc)
