"""CLI-only fixture helpers for the browser acceptance test."""

import uuid

import frappe
from frappe.utils import add_days, today
from frappe.utils.file_manager import save_file

from bimap_data_engine.services.import_engine import create_import_job
from bimap_data_engine.services.jobs import run_job


def create_item():
	frappe.set_user("Administrator")
	item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
	item_code = f"BDE-E2E-{uuid.uuid4().hex[:10].upper()}"
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": "BIMAP Data Engine E2E",
			"item_group": item_group,
			"stock_uom": stock_uom,
			"description": "E2E original",
			"image": "/files/bde-e2e-image.png",
			"is_stock_item": 0,
			"barcodes": [
				{"barcode": f"E2E-OLD-{uuid.uuid4().hex[:8]}"},
				{"barcode": f"E2E-KEEP-{uuid.uuid4().hex[:8]}"},
			],
		}
	).insert()
	frappe.db.commit()
	return {
		"name": doc.name,
		"description": doc.description,
		"barcodes": [row.barcode for row in doc.barcodes],
	}


def get_description(name):
	return frappe.db.get_value("Item", name, "description")


def get_image(name):
	return frappe.db.get_value("Item", name, "image")


def get_barcodes(name):
	return [row.barcode for row in frappe.get_doc("Item", name).barcodes]


def create_import_file():
	frappe.set_user("Administrator")
	item_code = f"BDE-E2E-IMPORT-{uuid.uuid4().hex[:8].upper()}"
	content = (
		"External ID,Item Code,Item Name,Description\n"
		f"item-1,{item_code},BIMAP imported E2E,Imported through spreadsheet\n"
	).encode()
	file_doc = save_file(f"{item_code}.csv", content, None, None, is_private=1)
	frappe.db.commit()
	return {"item_code": item_code, "file_name": file_doc.name, "file_url": file_doc.file_url}


def create_cfdi_import_file():
	frappe.set_user("Administrator")
	suffix = uuid.uuid4().hex[:10].upper()
	company = frappe.defaults.get_global_default("company")
	supplier_rfc = f"BDE{suffix[:9]}"
	company_rfc = "BDEE2ECOMPANY"
	supplier_group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	supplier = frappe.get_doc({
		"doctype": "Supplier", "supplier_name": f"BDE E2E CFDI {suffix}",
		"supplier_group": supplier_group, "supplier_type": "Company", "tax_id": supplier_rfc,
	}).insert()
	item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
	item_code = f"BDE-E2E-CFDI-{suffix}"
	frappe.get_doc({
		"doctype": "Item", "item_code": item_code, "item_name": item_code,
		"item_group": item_group, "stock_uom": stock_uom, "is_stock_item": 0,
	}).insert()
	cfdi_uuid = f"{suffix[:8]}-1111-2222-3333-{suffix.ljust(12, '0')}"
	content = f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" Serie="E2E" Folio="1"
 Fecha="2026-10-13T10:00:00" Moneda="MXN" SubTotal="100.00" Total="100.00" TipoDeComprobante="I">
 <cfdi:Emisor Rfc="{supplier_rfc}" Nombre="PROVEEDOR E2E" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="{company_rfc}" Nombre="EMPRESA E2E" UsoCFDI="G03"/>
 <cfdi:Conceptos><cfdi:Concepto ClaveProdServ="81112100" NoIdentificacion="{item_code}"
  Cantidad="2" ClaveUnidad="E48" Descripcion="Servicio E2E" ValorUnitario="50.00" Importe="100.00" ObjetoImp="01"/></cfdi:Conceptos>
 <cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="1.1" UUID="{cfdi_uuid}" FechaTimbrado="2026-10-13T10:01:00"/></cfdi:Complemento>
</cfdi:Comprobante>'''.encode()
	file_doc = save_file(f"{cfdi_uuid}.xml", content, None, None, is_private=1)
	frappe.db.commit()
	return {
		"company": company, "supplier": supplier.name, "item_code": item_code,
		"file_name": file_doc.name, "file_url": file_doc.file_url, "uuid": cfdi_uuid,
	}


def get_item_defaults():
	return {
		"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
		"stock_uom": frappe.get_all("UOM", pluck="name", limit=1)[0],
		"is_stock_item": 0,
	}


def create_sales_template_context():
	frappe.set_user("Administrator")
	suffix = uuid.uuid4().hex[:10].upper()
	customer_group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0]
	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": f"BDE Template Customer {suffix}",
		"bimap_customer_number": f"CLI-{suffix}",
		"customer_type": "Individual",
		"customer_group": customer_group,
		"territory": territory,
	}).insert()
	frappe.db.commit()
	return {
		"customer": customer.name,
		"customer_key": customer.bimap_customer_number,
		"company": frappe.defaults.get_global_default("company"),
		"stock_uom": frappe.get_all("UOM", pluck="name", limit=1)[0],
		"date": str(today()),
		"delivery_date": str(add_days(today(), 2)),
	}


def delete_sales_template_context(customer):
	frappe.set_user("Administrator")
	if frappe.db.exists("Customer", customer):
		frappe.delete_doc("Customer", customer, force=True)
	frappe.db.commit()


def execute_import_plan(plan):
	frappe.set_user("Administrator")
	plan = frappe.parse_json(plan) if isinstance(plan, str) else plan
	job_name = create_import_job(plan, batch_size=1)
	frappe.db.commit()
	run_job(job_name)
	record = frappe.get_all(
		"BIMAP Data Job Record",
		filters={"job": job_name},
		fields=["status", "result_document", "error"],
		limit=1,
	)[0]
	return {"job": job_name, **record}


def delete_import_fixture(item_code, file_name):
	frappe.set_user("Administrator")
	if frappe.db.exists("Item", item_code):
		frappe.delete_doc("Item", item_code, force=True)
	if frappe.db.exists("File", file_name):
		frappe.delete_doc("File", file_name, force=True)
	frappe.db.delete("BIMAP Data Change Log", {"reference_doctype": "Item", "document_name": item_code})
	frappe.db.commit()


def delete_cfdi_import_fixture(item_code, supplier, file_name, cfdi_uuid):
	frappe.set_user("Administrator")
	for doctype in ("Purchase Invoice", "Payment Entry"):
		for name in frappe.get_all(doctype, filters={"bimap_cfdi_uuid": cfdi_uuid}, pluck="name"):
			frappe.delete_doc(doctype, name, force=True)
	if frappe.db.exists("File", file_name):
		frappe.delete_doc("File", file_name, force=True)
	if frappe.db.exists("Item", item_code):
		frappe.delete_doc("Item", item_code, force=True)
	if frappe.db.exists("Supplier", supplier):
		frappe.delete_doc("Supplier", supplier, force=True)
	frappe.db.commit()


def delete_item(name):
	frappe.set_user("Administrator")
	if frappe.db.exists("Item", name):
		frappe.delete_doc("Item", name, force=True)
	frappe.db.delete("BIMAP Data Change Log", {"reference_doctype": "Item", "document_name": name})
	frappe.db.commit()
