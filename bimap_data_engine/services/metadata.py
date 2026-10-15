"""Permission-aware metadata used by query and change services."""

import frappe
from frappe.model import no_value_fields, table_fields


SYSTEM_READ_FIELDS = {"name", "modified"}
SYSTEM_IMMUTABLE_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
}


def get_doctype_meta(doctype):
	if not isinstance(doctype, str) or not doctype.strip():
		frappe.throw("Indica un DocType válido.")
	doctype = doctype.strip()
	if not frappe.db.exists("DocType", doctype):
		frappe.throw(f"DocType inexistente: {doctype}")
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw("Selecciona un DocType principal, no una tabla hija o Single.")
	return meta


def permitted_fieldnames(meta, permission_type, parenttype=None):
	return set(
		meta.get_permitted_fieldnames(
			parenttype=parenttype,
			user=frappe.session.user,
			permission_type=permission_type,
		)
	)


def is_value_field(df):
	return bool(
		df
		and df.fieldname
		and df.fieldtype not in no_value_fields
		and df.fieldtype not in table_fields
		and not getattr(df, "is_virtual", 0)
	)


def readable_fieldnames(meta, parenttype=None):
	fields = {
		df.fieldname
		for df in meta.fields
		if is_value_field(df)
	}
	return (fields & permitted_fieldnames(meta, "read", parenttype)) | SYSTEM_READ_FIELDS


def writable_fieldnames(meta, parenttype=None):
	permitted = permitted_fieldnames(meta, "write", parenttype)
	return {
		df.fieldname
		for df in meta.fields
		if is_value_field(df)
		and df.fieldname in permitted
		and df.fieldname not in SYSTEM_IMMUTABLE_FIELDS
		and not df.read_only
		and not df.set_only_once
	}


def has_field_permlevel(meta, df, permission_type):
	permlevel = df.permlevel or 0
	return permlevel == 0 or permlevel in meta.get_permlevel_access(
		permission_type=permission_type,
		user=frappe.session.user,
	)


def serialize_schema(meta):
	readable = readable_fieldnames(meta)
	writable = writable_fieldnames(meta)
	fields = []
	for df in meta.fields:
		if df.fieldname not in readable or not is_value_field(df):
			continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label,
				"fieldtype": df.fieldtype,
				"options": df.options,
				"required": bool(df.reqd),
				"read_only": df.fieldname not in writable,
				"permlevel": df.permlevel or 0,
			}
		)
	tables = []
	for table_df in meta.get_table_fields():
		if not has_field_permlevel(meta, table_df, "read"):
			continue
		child_meta = frappe.get_meta(table_df.options)
		child_readable = readable_fieldnames(child_meta, parenttype=meta.name)
		child_writable = writable_fieldnames(child_meta, parenttype=meta.name)
		tables.append(
			{
				"fieldname": table_df.fieldname,
				"label": table_df.label,
				"doctype": table_df.options,
				"read_only": bool(table_df.read_only or not has_field_permlevel(meta, table_df, "write")),
				"fields": [
					{
						"fieldname": child_df.fieldname,
						"label": child_df.label,
						"fieldtype": child_df.fieldtype,
						"options": child_df.options,
						"required": bool(child_df.reqd),
						"read_only": child_df.fieldname not in child_writable,
					}
					for child_df in child_meta.fields
					if child_df.fieldname in child_readable and is_value_field(child_df)
				],
			}
		)
	return {
		"doctype": meta.name,
		"title_field": meta.title_field,
		"search_fields": meta.search_fields,
		"is_submittable": bool(meta.is_submittable),
		"fields": fields,
		"tables": tables,
	}
