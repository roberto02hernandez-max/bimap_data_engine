"""Filter-only fields whose values live on a linked master document."""

from __future__ import annotations

from collections import defaultdict

import frappe

from bimap_data_engine.services.metadata import readable_fieldnames


RELATED_FILTER_CONFIG = {
	"Item Price": {
		"source_doctype": "Item",
		"target_link_field": "item_code",
		"fields": (
			("item_name", "Producto · Nombre"),
			("item_group", "Producto · Categoría o subcategoría"),
			("brand", "Producto · Marca"),
			("stock_uom", "Producto · Unidad de inventario"),
			("is_stock_item", "Producto · Controla inventario"),
			("disabled", "Producto · Deshabilitado"),
			("variant_of", "Producto · Plantilla de variante"),
		),
	},
}


def related_filter_fields(doctype):
	config = RELATED_FILTER_CONFIG.get(doctype)
	if not config or not frappe.has_permission(config["source_doctype"], "read"):
		return []

	meta = frappe.get_meta(config["source_doctype"])
	readable = readable_fieldnames(meta)
	result = []
	for source_fieldname, label in config["fields"]:
		if source_fieldname not in readable:
			continue
		df = meta.get_field(source_fieldname)
		if not df:
			continue
		result.append({
			"fieldname": f"related__{config['source_doctype']}__{source_fieldname}",
			"label": label,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"required": False,
			"read_only": True,
			"filter_only": True,
			"related_doctype": config["source_doctype"],
			"related_fieldname": source_fieldname,
		})
	return result


def apply_related_filters(doctype, filters):
	"""Resolve filter-only conditions into an allowed-name condition on the target."""
	config = RELATED_FILTER_CONFIG.get(doctype)
	if not filters:
		return filters

	conditions = _as_conditions(doctype, filters)
	if not config:
		return conditions
	virtual_fields = {field["fieldname"]: field for field in related_filter_fields(doctype)}
	base_conditions = []
	related_conditions = defaultdict(list)
	for condition in conditions:
		offset = 1 if len(condition) == 4 else 0
		fieldname = condition[offset]
		field = virtual_fields.get(fieldname)
		if not field:
			base_conditions.append(condition)
			continue
		related_conditions[field["related_doctype"]].append([
			field["related_doctype"],
			field["related_fieldname"],
			condition[offset + 1],
			condition[offset + 2],
		])

	for source_doctype, source_filters in related_conditions.items():
		frappe.has_permission(source_doctype, "read", throw=True)
		allowed_names = frappe.get_list(
			source_doctype,
			filters=source_filters,
			pluck="name",
			limit_page_length=0,
		)
		base_conditions.append([
			doctype,
			config["target_link_field"],
			"in",
			allowed_names or ["__bimap_no_related_filter_matches__"],
		])
	return base_conditions


def _as_conditions(doctype, filters):
	if isinstance(filters, dict):
		conditions = []
		for fieldname, value in filters.items():
			if isinstance(value, (list, tuple)) and len(value) == 2:
				conditions.append([doctype, fieldname, value[0], value[1]])
			else:
				conditions.append([doctype, fieldname, "=", value])
	else:
		conditions = [list(condition) for condition in filters]

	normalized = []
	for condition in conditions:
		offset = 1 if len(condition) == 4 else 0
		operator = str(condition[offset + 1]).lower()
		value = condition[offset + 2]
		if operator == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
			prefix = condition[: offset + 1]
			normalized.append([*prefix, ">=", value[0]])
			normalized.append([*prefix, "<=", value[1]])
		else:
			normalized.append(condition)
	return normalized
