"""Resolve spreadsheet business keys to permission-safe ERPNext links."""

import frappe
from frappe import _

from bimap_core.api.permisos import validar_cliente, validar_documento_permitido


LOOKUPS = {
	"customer": {
		"doctype": "Customer",
		"key_field": "bimap_customer_number",
		"label_field": "customer_name",
	},
	"supplier": {
		"doctype": "Supplier",
		"key_field": "bimap_supplier_number",
		"label_field": "supplier_name",
	},
	"item": {
		"doctype": "Item",
		"key_field": "item_code",
		"label_field": "item_name",
	},
}


def _normalized_key(value):
	return str(value or "").strip().casefold()


def _allowed_lookup(lookup, target_doctype, doctype):
	name = lookup["name"]
	try:
		if doctype == "Customer":
			validar_cliente(name, target_doctype=target_doctype)
		else:
			validar_documento_permitido(doctype, name, target_doctype=target_doctype)
		return True
	except (frappe.PermissionError, frappe.ValidationError):
		return False


def _resolve_values(kind, values, target_doctype):
	config = LOOKUPS[kind]
	if not frappe.db.has_column(config["doctype"], config["key_field"]):
		frappe.throw(
			_("Falta instalar el campo de clave BIMAP para {0}.").format(config["doctype"])
		)
	frappe.has_permission(config["doctype"], "read", throw=True)
	clean_values = sorted({str(value).strip() for value in values if str(value or "").strip()})
	if not clean_values:
		return {}
	rows = frappe.get_list(
		config["doctype"],
		filters={config["key_field"]: ["in", clean_values]},
		fields=["name", config["key_field"], config["label_field"]],
		limit_page_length=len(clean_values),
	)
	resolved = {}
	for row in rows:
		if not _allowed_lookup(row, target_doctype, config["doctype"]):
			continue
		resolved[_normalized_key(row.get(config["key_field"]))] = {
			"name": row.name,
			"label": row.get(config["label_field"]) or row.name,
		}
	return resolved


@frappe.whitelist()
def resolve_import_keys(target_doctype, rows, lookups):
	"""Resolve configured capture columns, returning cloned rows and cell issues."""
	frappe.has_permission(target_doctype, "create", throw=True)
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	lookups = frappe.parse_json(lookups) if isinstance(lookups, str) else lookups
	if not isinstance(rows, list) or not isinstance(lookups, list):
		frappe.throw(_("La solicitud de claves no es válida."))
	if len(rows) > 5000:
		frappe.throw(_("Sólo se pueden resolver 5,000 filas por solicitud."))

	valid_specs = []
	for spec in lookups:
		kind = spec.get("kind")
		if kind not in LOOKUPS or not spec.get("source") or not spec.get("display_source"):
			frappe.throw(_("La configuración de una clave no es válida."))
		valid_specs.append(spec)

	resolved_by_kind = {}
	for kind in {spec["kind"] for spec in valid_specs}:
		kind_specs = [spec for spec in valid_specs if spec["kind"] == kind]
		values = [row.get(spec["source"]) for row in rows for spec in kind_specs]
		resolved_by_kind[kind] = _resolve_values(kind, values, target_doctype)
	resolved_rows = [dict(row) for row in rows]
	display_rows = []
	issues = []
	for index, row in enumerate(rows):
		display = {}
		for spec in valid_specs:
			source = spec["source"]
			value = str(row.get(source) or "").strip()
			match = resolved_by_kind[spec["kind"]].get(_normalized_key(value)) if value else None
			display[spec["display_source"]] = match["label"] if match else ""
			if match:
				resolved_rows[index][source] = match["name"]
			elif value:
				issues.append({
					"node": "documents", "sheet": "Captura", "row": index + 2,
					"source_field": source, "severity": "error", "code": "unknown_business_key",
					"message": _("No existe o no tienes permiso para usar la clave {0}.").format(value),
					"error": _("No existe o no tienes permiso para usar la clave {0}.").format(value),
				})
		display_rows.append(display)
	return {"rows": resolved_rows, "display_rows": display_rows, "issues": issues}
