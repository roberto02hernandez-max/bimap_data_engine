"""Explicit safety policies for business rules not expressible by DocType metadata."""

import frappe


ITEM_VARIANT_FIELDS = {"has_variants", "variant_of"}
ITEM_VARIANT_TABLE = "attributes"


def _built_in_change_errors(doc, change):
	errors = []
	if doc.doctype == "Item" and (
		change["fieldname"] in ITEM_VARIANT_FIELDS
		or (
			change["fieldname"] == ITEM_VARIANT_TABLE
			and change["operation"] in {"add_child", "update_child", "delete_child"}
		)
	):
		errors.append(
			"Cambio estructural de variante bloqueado: requiere un adaptador que valide y actualice variantes relacionadas."
		)
	if doc.doctype == "Item Attribute" and change["fieldname"] == "item_attribute_values":
		errors.append(
			"Cambio estructural de valores de atributo bloqueado: puede afectar variantes existentes."
		)
	return errors


def validate_change_policies(doc, change):
	errors = _built_in_change_errors(doc, change)
	for dotted_path in frappe.get_hooks("bimap_data_engine_change_policies") or []:
		result = frappe.get_attr(dotted_path)(doc=doc, change=change)
		if isinstance(result, str):
			errors.append(result)
		elif result:
			errors.extend(result)
	return errors


def validate_import_policies(payload):
	errors = []
	if payload["doctype"] == "Item" and (
		ITEM_VARIANT_FIELDS.intersection(payload.get("values") or {})
		or ITEM_VARIANT_TABLE in (payload.get("children") or {})
	):
		errors.append(
			"Importación estructural de variantes bloqueada hasta configurar un adaptador seguro."
		)
	for dotted_path in frappe.get_hooks("bimap_data_engine_import_policies") or []:
		result = frappe.get_attr(dotted_path)(payload=payload)
		if isinstance(result, str):
			errors.append(result)
		elif result:
			errors.extend(result)
	return errors
