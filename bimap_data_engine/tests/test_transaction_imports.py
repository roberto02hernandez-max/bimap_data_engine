import uuid
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from bimap_data_engine.services.import_engine import build_import_plan, create_import_job
from bimap_data_engine.services.jobs import run_job
from bimap_data_engine.services.line_import import map_imported_rows, prepare_line_import


class TestTransactionImports(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		suffix = uuid.uuid4().hex[:10].upper()
		self.company = frappe.defaults.get_global_default("company")
		self.stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
		item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		self.item_code = f"BDE-TXN-{suffix}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": self.item_code,
				"item_name": "BIMAP transaction import item",
				"item_group": item_group,
				"stock_uom": self.stock_uom,
				"is_stock_item": 0,
			}
		).insert()
		customer_group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0]
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"BDE Customer {suffix}",
				"customer_type": "Individual",
				"customer_group": customer_group,
				"territory": territory,
			}
		).insert().name
		supplier_group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		self.supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"BDE Supplier {suffix}",
				"supplier_group": supplier_group,
				"supplier_type": "Individual",
			}
		).insert().name

	def tearDown(self):
		frappe.set_user("Administrator")

	def _import_transaction(self, doctype, party_field, party, child_date_field):
		date = str(today())
		delivery = str(add_days(today(), 2))
		workbook = {
			"sheets": [
				{
					"name": "Documents",
					"rows": [{"External ID": "doc-1", "Party": party, "Date": date, "Due": delivery}],
				},
				{
					"name": "Lines",
					"rows": [
						{"Document ID": "doc-1", "Item": self.item_code, "Qty": 2, "Rate": 17.5, "Due": delivery},
						{"Document ID": "doc-1", "Item": self.item_code, "Qty": 3, "Rate": 18.5, "Due": delivery},
					],
				},
			]
		}
		parent_mapping = [
			{"source": "Party", "target": party_field},
			{"source": "Date", "target": "transaction_date"},
		]
		parent_due_field = "delivery_date" if doctype == "Sales Order" else "schedule_date"
		parent_mapping.append({"source": "Due", "target": parent_due_field})
		specification = {
			"nodes": [
				{
					"id": "documents",
					"doctype": doctype,
					"sheet": "Documents",
					"external_key": "External ID",
					"mapping": parent_mapping,
					"defaults": {"company": self.company},
					"children": [
						{
							"table_field": "items",
							"sheet": "Lines",
							"parent_key": "Document ID",
							"mapping": [
								{"source": "Item", "target": "item_code"},
								{"source": "Qty", "target": "qty"},
								{"source": "Rate", "target": "rate"},
								{"source": "Due", "target": child_date_field},
							],
							"defaults": {"uom": self.stock_uom},
						}
					],
				}
			]
		}
		plan = build_import_plan(workbook, specification)
		self.assertTrue(plan["valid"], plan)
		job_name = create_import_job(plan, batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		record = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, fields=["status", "result_document"]
		)[0]
		self.assertEqual(record.status, "Success")
		return frappe.get_doc(doctype, record.result_document)

	def test_sales_order_with_multiple_items(self):
		doc = self._import_transaction("Sales Order", "customer", self.customer, "delivery_date")
		self.assertEqual(doc.customer, self.customer)
		self.assertEqual(len(doc.items), 2)
		self.assertEqual([row.qty for row in doc.items], [2, 3])
		self.assertEqual(doc.docstatus, 0)

	def test_purchase_order_with_multiple_items(self):
		doc = self._import_transaction("Purchase Order", "supplier", self.supplier, "schedule_date")
		self.assertEqual(doc.supplier, self.supplier)
		self.assertEqual(len(doc.items), 2)
		self.assertEqual([row.qty for row in doc.items], [2, 3])
		self.assertEqual(doc.docstatus, 0)

	def _import_invoice(self, doctype, party_field, party):
		date = str(today())
		workbook = {
			"sheets": [
				{"name": "Documents", "rows": [{
					"External ID": "invoice-1", "Party": party, "Date": date,
				}]},
				{"name": "Lines", "rows": [{
					"Document ID": "invoice-1", "Item": self.item_code, "Qty": 2, "Rate": 17.5,
				}]},
			],
		}
		specification = {
			"nodes": [{
				"id": "documents", "doctype": doctype, "sheet": "Documents",
				"external_key": "External ID",
				"mapping": [
					{"source": "Party", "target": party_field},
					{"source": "Date", "target": "posting_date"},
				],
				"defaults": {"company": self.company, "due_date": date},
				"children": [{
					"table_field": "items", "sheet": "Lines", "parent_key": "Document ID",
					"mapping": [
						{"source": "Item", "target": "item_code"},
						{"source": "Qty", "target": "qty"},
						{"source": "Rate", "target": "rate"},
					],
					"defaults": {"uom": self.stock_uom},
				}],
			}],
		}
		plan = build_import_plan(workbook, specification)
		self.assertTrue(plan["valid"], plan)
		job_name = create_import_job(plan, batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		record = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, fields=["status", "result_document"]
		)[0]
		self.assertEqual(record.status, "Success")
		return frappe.get_doc(doctype, record.result_document)

	def test_sales_invoice_uses_native_preparation_and_stays_draft(self):
		doc = self._import_invoice("Sales Invoice", "customer", self.customer)
		self.assertEqual(doc.customer, self.customer)
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(len(doc.items), 1)
		self.assertGreater(doc.grand_total, 0)

	def test_purchase_invoice_uses_native_preparation_and_stays_draft(self):
		doc = self._import_invoice("Purchase Invoice", "supplier", self.supplier)
		self.assertEqual(doc.supplier, self.supplier)
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(len(doc.items), 1)
		self.assertGreater(doc.grand_total, 0)

	def test_native_quotation_to_sales_order_keeps_erpnext_source_links(self):
		quotation = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": self.customer,
			"company": self.company,
			"transaction_date": today(),
			"valid_till": add_days(today(), 10),
			"items": [{
				"item_code": self.item_code,
				"qty": 4,
				"uom": self.stock_uom,
				"rate": 25,
			}],
		}).insert()
		quotation.submit()
		workbook = {
			"sheets": [{
				"name": "Orders",
				"rows": [{"External ID": "order-1", "Quotation": quotation.name}],
			}],
		}
		specification = {
			"nodes": [{
				"id": "orders",
				"doctype": "Sales Order",
				"sheet": "Orders",
				"external_key": "External ID",
				"mapping": [],
				"defaults": {"delivery_date": str(add_days(today(), 2))},
				"native_source": {
					"doctype": "Quotation",
					"source": "Quotation",
				},
			}],
		}
		plan = build_import_plan(workbook, specification)
		self.assertTrue(plan["valid"], plan)
		self.assertEqual(plan["records"][0]["native_source"]["name"], quotation.name)
		job_name = create_import_job(plan, batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		record = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, fields=["status", "result_document"]
		)[0]
		self.assertEqual(record.status, "Success")
		order = frappe.get_doc("Sales Order", record.result_document)
		self.assertEqual(order.items[0].prevdoc_docname, quotation.name)
		self.assertEqual(order.items[0].qty, 4)

	def test_delivery_note_to_sales_invoice_creates_receivable_without_second_stock_movement(self):
		suffix = uuid.uuid4().hex[:10].upper()
		item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		stock_item = f"BDE-STOCK-{suffix}"
		frappe.get_doc({
			"doctype": "Item", "item_code": stock_item, "item_name": stock_item,
			"item_group": item_group, "stock_uom": self.stock_uom, "is_stock_item": 1,
		}).insert()
		warehouse = frappe.get_all(
			"Warehouse", filters={"company": self.company, "is_group": 0, "disabled": 0},
			pluck="name", limit=1,
		)[0]
		frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": self.company,
			"items": [{
				"item_code": stock_item, "qty": 5, "t_warehouse": warehouse,
				"basic_rate": 10, "uom": self.stock_uom,
			}],
		}).insert().submit()
		delivery = frappe.get_doc({
			"doctype": "Delivery Note", "customer": self.customer, "company": self.company,
			"posting_date": today(), "set_warehouse": warehouse,
			"items": [{
				"item_code": stock_item, "qty": 2, "rate": 25,
				"uom": self.stock_uom, "warehouse": warehouse,
			}],
		}).insert()
		delivery.submit()
		delivery_sle = frappe.db.count("Stock Ledger Entry", {
			"voucher_type": "Delivery Note", "voucher_no": delivery.name, "is_cancelled": 0,
		})
		self.assertGreater(delivery_sle, 0)
		workbook = {"sheets": [{
			"name": "Invoices", "rows": [{"External ID": "invoice-1", "Delivery Note": delivery.name}],
		}]}
		specification = {"nodes": [{
			"id": "invoices", "doctype": "Sales Invoice", "sheet": "Invoices",
			"external_key": "External ID", "mapping": [],
			"submit": True,
			"native_source": {"doctype": "Delivery Note", "source": "Delivery Note"},
		}]}
		plan = build_import_plan(workbook, specification)
		self.assertTrue(plan["valid"], plan)
		job_name = create_import_job(plan, batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		record = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, fields=["status", "result_document"]
		)[0]
		self.assertEqual(record.status, "Success")
		invoice = frappe.get_doc("Sales Invoice", record.result_document)
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.update_stock, 0)
		self.assertEqual(invoice.items[0].dn_detail, delivery.items[0].name)
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {
			"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0,
		}), 0)
		self.assertGreater(frappe.db.count("GL Entry", {
			"voucher_type": "Sales Invoice", "voucher_no": invoice.name, "is_cancelled": 0,
		}), 0)
		self.assertGreater(invoice.outstanding_amount, 0)

	def test_lines_can_be_consolidated_into_unsaved_document_without_persisting(self):
		before = frappe.db.count("Sales Order")
		result = prepare_line_import(
			"Sales Order",
			"items",
			{
				"customer": self.customer,
				"company": self.company,
				"transaction_date": str(today()),
				"delivery_date": str(add_days(today(), 2)),
			},
			[{
				"item_code": self.item_code, "qty": 1, "uom": self.stock_uom,
				"delivery_date": str(add_days(today(), 2)), "rate": 10,
			}],
			[{
				"item_code": self.item_code, "qty": 2, "uom": self.stock_uom,
				"delivery_date": str(add_days(today(), 2)), "rate": 10,
			}],
			merge_policy="consolidate",
		)
		self.assertEqual(result["merge"]["updated"], 1)
		self.assertEqual(result["merge"]["total"], 1)
		self.assertEqual(result["rows"][0]["qty"], 3)
		self.assertGreater(result["totals"]["grand_total"], 0)
		self.assertEqual(frappe.db.count("Sales Order"), before)

	def test_external_line_columns_map_to_native_child_fields(self):
		result = map_imported_rows(
			"Sales Order",
			"items",
			[{"Producto": self.item_code, "Cantidad": "5", "Unidad": self.stock_uom}],
			[
				{"source": "Producto", "target": "item_code", "transform": "trim"},
				{"source": "Cantidad", "target": "qty", "transform": "trim"},
				{"source": "Unidad", "target": "uom", "transform": "trim"},
			],
		)
		self.assertTrue(result["valid"], result)
		self.assertEqual(result["records"][0]["values"]["item_code"], self.item_code)
		self.assertEqual(result["records"][0]["values"]["qty"], 5.0)
