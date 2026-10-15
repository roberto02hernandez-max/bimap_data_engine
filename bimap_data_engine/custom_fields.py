"""Custom fields owned by the Data Engine for traceable fiscal imports."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
	"Purchase Invoice": [
		{
			"fieldname": "bimap_cfdi_section",
			"label": "CFDI BIMAP",
			"fieldtype": "Section Break",
			"insert_after": "bill_date",
			"collapsible": 1,
		},
		{
			"fieldname": "bimap_cfdi_uuid",
			"label": "UUID CFDI",
			"fieldtype": "Data",
			"insert_after": "bimap_cfdi_section",
			"read_only": 1,
			"no_copy": 1,
			"unique": 1,
			"search_index": 1,
		},
		{
			"fieldname": "bimap_cfdi_file",
			"label": "Archivo CFDI",
			"fieldtype": "Attach",
			"insert_after": "bimap_cfdi_uuid",
			"read_only": 1,
			"no_copy": 1,
		},
	],
	"Payment Entry": [
		{
			"fieldname": "bimap_cfdi_section",
			"label": "CFDI BIMAP",
			"fieldtype": "Section Break",
			"insert_after": "reference_date",
			"collapsible": 1,
		},
		{
			"fieldname": "bimap_cfdi_uuid",
			"label": "UUID CFDI",
			"fieldtype": "Data",
			"insert_after": "bimap_cfdi_section",
			"read_only": 1,
			"no_copy": 1,
			"unique": 0,
			"search_index": 1,
		},
		{
			"fieldname": "bimap_cfdi_payment_index",
			"label": "Número de pago CFDI",
			"fieldtype": "Int",
			"insert_after": "bimap_cfdi_uuid",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "bimap_cfdi_payment_key",
			"label": "Clave de pago CFDI",
			"fieldtype": "Data",
			"insert_after": "bimap_cfdi_payment_index",
			"read_only": 1,
			"no_copy": 1,
			"unique": 1,
			"search_index": 1,
			"hidden": 1,
		},
		{
			"fieldname": "bimap_cfdi_file",
			"label": "Archivo CFDI",
			"fieldtype": "Attach",
			"insert_after": "bimap_cfdi_payment_key",
			"read_only": 1,
			"no_copy": 1,
		},
	],
}


ALPHAERP_COMMERCIAL_FIELDS = {
	"Customer": [
		{
			"fieldname": "bimap_alphaerp_commercial_classification",
			"label": "Clasificación comercial AlphaERP",
			"fieldtype": "Data",
			"insert_after": "customer_group",
			"read_only": 1,
			"search_index": 1,
		},
		{
			"fieldname": "bimap_commercial_tier",
			"label": "Nivel comercial",
			"fieldtype": "Data",
			"insert_after": "bimap_alphaerp_commercial_classification",
			"search_index": 1,
		},
	],
	"Supplier": [
		{
			"fieldname": "bimap_alphaerp_commercial_classification",
			"label": "Clasificación comercial AlphaERP",
			"fieldtype": "Data",
			"insert_after": "supplier_group",
			"read_only": 1,
			"search_index": 1,
		},
		{
			"fieldname": "bimap_commercial_tier",
			"label": "Nivel comercial",
			"fieldtype": "Data",
			"insert_after": "bimap_alphaerp_commercial_classification",
			"search_index": 1,
		},
	],
}


def sync_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)


def sync_alphaerp_commercial_fields():
	"""Explicit opt-in fields; intentionally not part of the normal install sync."""
	create_custom_fields(ALPHAERP_COMMERCIAL_FIELDS, update=True)

