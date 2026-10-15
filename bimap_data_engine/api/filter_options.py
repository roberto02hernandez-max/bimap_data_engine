"""Permission-aware option lists for the visual filter builder."""

import frappe

from bimap_data_engine.services.metadata import readable_fieldnames


# These are small reference catalogs that are more useful as a closed selector than
# as a free-form Link search. Large masters (Item, Customer, Supplier, etc.) keep the
# regular Link autocomplete so the browser never has to load thousands of options.
SELECTOR_DOCTYPES = {
	"Brand",
	"Company",
	"Currency",
	"Customer Group",
	"Item Group",
	"Price List",
	"Supplier Group",
	"Territory",
	"UOM",
	"Warehouse",
}


def _depths(rows, parent_field):
	parents = {row.name: row.get(parent_field) for row in rows}
	cache = {}

	def depth(name, trail=None):
		if name in cache:
			return cache[name]
		trail = trail or set()
		parent = parents.get(name)
		if not parent or parent not in parents or name in trail:
			cache[name] = 0
			return 0
		cache[name] = min(depth(parent, trail | {name}) + 1, 20)
		return cache[name]

	return {name: depth(name) for name in parents}


@frappe.whitelist(methods=["GET"])
def get_filter_options(link_doctype):
	"""Return existing, permitted values for a supported Link filter."""
	if not isinstance(link_doctype, str) or link_doctype not in SELECTOR_DOCTYPES:
		frappe.throw("Este catálogo no admite una lista cerrada de opciones.")
	if not frappe.db.exists("DocType", link_doctype):
		frappe.throw(f"DocType inexistente: {link_doctype}")

	frappe.has_permission(link_doctype, "read", throw=True)
	meta = frappe.get_meta(link_doctype)
	readable = readable_fieldnames(meta)
	parent_field = getattr(meta, "nsm_parent_field", None)
	if parent_field not in readable:
		parent_field = None

	fields = ["name"]
	title_field = meta.title_field if meta.title_field in readable else None
	if title_field and title_field != "name":
		fields.append(title_field)
	if parent_field:
		fields.append(parent_field)
	if "is_group" in readable:
		fields.append("is_group")

	rows = frappe.get_list(
		link_doctype,
		fields=fields,
		order_by="lft asc" if parent_field else "name asc",
		limit_page_length=5000,
	)
	depths = _depths(rows, parent_field) if parent_field else {}
	return {
		"doctype": link_doctype,
		"tree": bool(parent_field),
		"options": [
			{
				"value": row.name,
				"label": row.get(title_field) or row.name,
				"depth": depths.get(row.name, 0),
				"is_group": bool(row.get("is_group")),
			}
			for row in rows
		],
	}
