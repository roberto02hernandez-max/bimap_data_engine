import frappe
from frappe.tests.utils import FrappeTestCase

from bimap_data_engine.services.cfdi import cfdi_to_workbook, parse_cfdi
from bimap_data_engine.services.cfdi_documents import create_cfdi_draft, preview_cfdi_document


INVOICE_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
 Version="4.0" Serie="A" Folio="123" Fecha="2026-10-13T10:00:00"
 Moneda="MXN" SubTotal="100.00" Total="116.00" TipoDeComprobante="I">
 <cfdi:Emisor Rfc="AAA010101AAA" Nombre="PROVEEDOR DEMO" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="BBB010101BBB" Nombre="EMPRESA DEMO" UsoCFDI="G03"
  DomicilioFiscalReceptor="06000" RegimenFiscalReceptor="601"/>
 <cfdi:CfdiRelacionados TipoRelacion="04">
  <cfdi:CfdiRelacionado UUID="11111111-1111-1111-1111-111111111111"/>
 </cfdi:CfdiRelacionados>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="81112100" NoIdentificacion="SERV-1" Cantidad="2"
   ClaveUnidad="E48" Descripcion="Servicio" ValorUnitario="50.00" Importe="100.00" ObjetoImp="02">
   <cfdi:Impuestos><cfdi:Traslados>
    <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00"/>
   </cfdi:Traslados></cfdi:Impuestos>
  </cfdi:Concepto>
 </cfdi:Conceptos>
 <cfdi:Impuestos TotalImpuestosTrasladados="16.00"><cfdi:Traslados>
  <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00"/>
 </cfdi:Traslados></cfdi:Impuestos>
 <cfdi:Complemento>
  <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
   Version="1.1" UUID="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE" FechaTimbrado="2026-10-13T10:01:00"/>
 </cfdi:Complemento>
</cfdi:Comprobante>'''


PAYMENT_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20"
 Version="4.0" Fecha="2026-10-13T12:00:00" Moneda="XXX" SubTotal="0" Total="0" TipoDeComprobante="P">
 <cfdi:Emisor Rfc="AAA010101AAA" Nombre="PROVEEDOR DEMO" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="BBB010101BBB" Nombre="EMPRESA DEMO" UsoCFDI="CP01"/>
 <cfdi:Complemento>
  <pago20:Pagos Version="2.0">
   <pago20:Totales MontoTotalPagos="500.00" TotalTrasladosBaseIVA16="431.03" TotalTrasladosImpuestoIVA16="68.97"/>
   <pago20:Pago FechaPago="2026-10-12T09:00:00" FormaDePagoP="03" MonedaP="MXN" Monto="500.00">
    <pago20:DoctoRelacionado IdDocumento="BBBBBBBB-1111-2222-3333-CCCCCCCCCCCC" MonedaDR="MXN"
     NumParcialidad="1" ImpSaldoAnt="500.00" ImpPagado="500.00" ImpSaldoInsoluto="0.00" ObjetoImpDR="02"/>
    <pago20:ImpuestosP><pago20:TrasladosP>
     <pago20:TrasladoP BaseP="431.03" ImpuestoP="002" TipoFactorP="Tasa" TasaOCuotaP="0.160000" ImporteP="68.97"/>
    </pago20:TrasladosP></pago20:ImpuestosP>
   </pago20:Pago>
  </pago20:Pagos>
  <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
   Version="1.1" UUID="FFFFFFFF-BBBB-CCCC-DDDD-EEEEEEEEEEEE" FechaTimbrado="2026-10-13T12:01:00"/>
 </cfdi:Complemento>
</cfdi:Comprobante>'''


def expense_xml(uuid, supplier_rfc, company_rfc, item_code):
	return f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
 Version="4.0" Serie="BDE" Folio="42" Fecha="2026-10-13T10:00:00"
 Moneda="MXN" SubTotal="100.00" Total="100.00" TipoDeComprobante="I">
 <cfdi:Emisor Rfc="{supplier_rfc}" Nombre="PROVEEDOR BIMAP" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="{company_rfc}" Nombre="EMPRESA BIMAP" UsoCFDI="G03"
  DomicilioFiscalReceptor="06000" RegimenFiscalReceptor="601"/>
 <cfdi:Conceptos>
  <cfdi:Concepto ClaveProdServ="81112100" NoIdentificacion="{item_code}" Cantidad="2"
   ClaveUnidad="E48" Descripcion="Servicio BIMAP" ValorUnitario="50.00" Importe="100.00" ObjetoImp="01"/>
 </cfdi:Conceptos>
 <cfdi:Complemento>
  <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
   Version="1.1" UUID="{uuid}" FechaTimbrado="2026-10-13T10:01:00"/>
 </cfdi:Complemento>
</cfdi:Comprobante>'''.encode()


def supplier_payment_xml(uuid, invoice_uuid, supplier_rfc, company_rfc):
	return f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:pago20="http://www.sat.gob.mx/Pagos20"
 Version="4.0" Fecha="2026-10-13T12:00:00" Moneda="XXX" SubTotal="0" Total="0" TipoDeComprobante="P">
 <cfdi:Emisor Rfc="{supplier_rfc}" Nombre="PROVEEDOR BIMAP" RegimenFiscal="601"/>
 <cfdi:Receptor Rfc="{company_rfc}" Nombre="EMPRESA BIMAP" UsoCFDI="CP01"/>
 <cfdi:Complemento>
  <pago20:Pagos Version="2.0">
   <pago20:Totales MontoTotalPagos="100.00"/>
   <pago20:Pago FechaPago="2026-10-13T09:00:00" FormaDePagoP="03" MonedaP="MXN" Monto="100.00">
    <pago20:DoctoRelacionado IdDocumento="{invoice_uuid}" MonedaDR="MXN"
     NumParcialidad="1" ImpSaldoAnt="100.00" ImpPagado="100.00" ImpSaldoInsoluto="0.00" ObjetoImpDR="01"/>
   </pago20:Pago>
  </pago20:Pagos>
  <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
   Version="1.1" UUID="{uuid}" FechaTimbrado="2026-10-13T12:01:00"/>
 </cfdi:Complemento>
</cfdi:Comprobante>'''.encode()


class TestCFDISourceAdapter(FrappeTestCase):
	def test_invoice_cfdi_is_normalized_into_generic_workbook(self):
		parsed = parse_cfdi(INVOICE_XML, filename="invoice.xml")
		self.assertEqual(parsed["document_type"], "invoice")
		self.assertEqual(parsed["uuid"], "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
		self.assertEqual(parsed["emitter"]["Rfc"], "AAA010101AAA")
		self.assertEqual(parsed["concepts"][0]["Cantidad"], 2.0)
		self.assertEqual(parsed["taxes"][0]["Impuesto"], "002")
		self.assertEqual(parsed["related"][0]["TipoRelacion"], "04")
		workbook = cfdi_to_workbook(parsed)
		self.assertEqual(workbook["format"], "CFDI XML")
		self.assertEqual(workbook["sheets"][0]["name"], "CFDI")
		self.assertEqual(workbook["sheets"][1]["row_count"], 1)

	def test_payment_complement_exposes_payments_and_related_documents(self):
		parsed = parse_cfdi(PAYMENT_XML)
		self.assertEqual(parsed["document_type"], "payment")
		self.assertEqual(parsed["payments"][0]["Monto"], 500.0)
		self.assertEqual(parsed["payment_documents"][0]["NumParcialidad"], "1")
		self.assertEqual(parsed["payment_documents"][0]["ImpSaldoInsoluto"], 0.0)
		self.assertEqual(parsed["payment_totals"]["MontoTotalPagos"], "500.00")

	def test_xml_with_doctype_or_entity_is_rejected(self):
		malicious = b'''<?xml version="1.0"?><!DOCTYPE x [<!ENTITY probe "unsafe">]>
<Comprobante Version="4.0">&probe;</Comprobante>'''
		with self.assertRaises(frappe.ValidationError):
			parse_cfdi(malicious)


class TestCFDINativeDocuments(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=10).upper()
		self.company = frappe.defaults.get_global_default("company")
		self.supplier_rfc = f"BDE{suffix[:9]}"
		self.company_rfc = "BDECOMPANYRFC"
		supplier_group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		self.supplier = frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": f"BDE CFDI Supplier {suffix}",
			"supplier_group": supplier_group,
			"supplier_type": "Company",
			"tax_id": self.supplier_rfc,
		}).insert().name
		item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
		self.item_code = f"BDE-CFDI-{suffix}"
		frappe.get_doc({
			"doctype": "Item", "item_code": self.item_code,
			"item_name": "BDE CFDI expense", "item_group": item_group,
			"stock_uom": stock_uom, "is_stock_item": 0,
		}).insert()
		self.cfdi_uuid = f"{suffix[:8]}-1111-2222-3333-{suffix[:10].ljust(12, '0')}"
		xml = expense_xml(self.cfdi_uuid, self.supplier_rfc, self.company_rfc, self.item_code)
		self.file = frappe.get_doc({
			"doctype": "File", "file_name": f"bde-cfdi-{suffix}.xml",
			"is_private": 1, "content": xml,
		}).insert()

	def test_invoice_preview_uses_native_purchase_invoice_defaults_without_writing(self):
		before = frappe.db.count("Purchase Invoice", {"bimap_cfdi_uuid": self.cfdi_uuid})
		preview = preview_cfdi_document(self.file.file_url, {
			"company": self.company, "supplier": self.supplier,
		})
		self.assertTrue(preview["valid"], preview)
		self.assertEqual(preview["document"]["supplier"], self.supplier)
		self.assertEqual(preview["document"]["items"][0]["item_code"], self.item_code)
		self.assertEqual(preview["document"]["grand_total"], 100)
		self.assertEqual(frappe.db.count("Purchase Invoice", {"bimap_cfdi_uuid": self.cfdi_uuid}), before)

	def test_invoice_draft_is_audited_and_duplicate_uuid_is_blocked(self):
		result = create_cfdi_draft(self.file.file_url, {
			"company": self.company, "supplier": self.supplier,
		}, operation_id=f"cfdi-{self.cfdi_uuid}")
		doc = frappe.get_doc("Purchase Invoice", result["name"])
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.bimap_cfdi_uuid, self.cfdi_uuid)
		self.assertEqual(doc.bill_no, "BDE-42")
		self.assertTrue(frappe.db.exists("BIMAP Data Change Log", {
			"operation_id": f"cfdi-{self.cfdi_uuid}", "document_name": doc.name,
		}))
		duplicate = preview_cfdi_document(self.file.file_url, {
			"company": self.company, "supplier": self.supplier,
		})
		self.assertFalse(duplicate["valid"])
		self.assertIn("duplicate_cfdi", {issue["code"] for issue in duplicate["issues"]})

	def test_payment_complement_prepares_reconciled_payment_draft_and_blocks_duplicate(self):
		invoice_result = create_cfdi_draft(self.file.file_url, {
			"company": self.company, "supplier": self.supplier,
		})
		invoice = frappe.get_doc("Purchase Invoice", invoice_result["name"])
		invoice.submit()
		bank_account = frappe.get_all(
			"Account",
			filters={"company": self.company, "is_group": 0, "account_type": ["in", ["Bank", "Cash"]]},
			pluck="name", limit=1,
		)[0]
		payment_uuid = f"{frappe.generate_hash(length=8).upper()}-AAAA-BBBB-CCCC-123456789012"
		payment_file = frappe.get_doc({
			"doctype": "File", "file_name": f"payment-{payment_uuid}.xml", "is_private": 1,
			"content": supplier_payment_xml(payment_uuid, self.cfdi_uuid, self.supplier_rfc, self.company_rfc),
		}).insert()
		preview = preview_cfdi_document(payment_file.file_url, {"bank_account": bank_account})
		self.assertTrue(preview["valid"], preview)
		self.assertEqual(preview["document_type"], "payment")
		self.assertEqual(preview["document"]["party"], self.supplier)
		self.assertEqual(preview["document"]["references"][0]["reference_name"], invoice.name)
		self.assertEqual(preview["document"]["references"][0]["allocated_amount"], 100)
		result = create_cfdi_draft(payment_file.file_url, {"bank_account": bank_account})
		payment = frappe.get_doc("Payment Entry", result["name"])
		self.assertEqual(payment.docstatus, 0)
		self.assertEqual(payment.references[0].reference_name, invoice.name)
		self.assertEqual(payment.bimap_cfdi_payment_key, f"{payment_uuid}#1")
		duplicate = preview_cfdi_document(payment_file.file_url, {"bank_account": bank_account})
		self.assertFalse(duplicate["valid"])
		self.assertIn("duplicate_cfdi_payment", {issue["code"] for issue in duplicate["issues"]})
