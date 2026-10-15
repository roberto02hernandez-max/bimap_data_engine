import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from bimap_data_engine.services.import_engine import (
	build_import_plan,
	create_import_job,
	create_preview_job,
	revalidate_import_rows,
)
from bimap_data_engine.services.jobs import run_job


class TestImportEngine(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.item_group = frappe.get_all(
			"Item Group", filters={"is_group": 0}, pluck="name", limit=1
		)[0]
		self.stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]

	def tearDown(self):
		frappe.set_user("Administrator")

	def _item_workbook(self, item_code, *, orphan=False):
		return {
			"format": "XLSX",
			"sheets": [
				{
					"name": "Items",
					"rows": [
						{
							"External ID": "item-1",
							"Item Code": item_code,
							"Item Name": "Imported BIMAP item",
							"Description": "Imported description",
						}
					],
				},
				{
					"name": "Barcodes",
					"rows": [
						{
							"Parent ID": "missing" if orphan else "item-1",
							"Barcode": f"IMP-{uuid.uuid4().hex[:12]}",
						}
					],
				},
			],
		}

	def _item_spec(self):
		return {
			"nodes": [
				{
					"id": "items",
					"doctype": "Item",
					"sheet": "Items",
					"external_key": "External ID",
					"mapping": [
						{"source": "Item Code", "target": "item_code"},
						{"source": "Item Name", "target": "item_name", "transform": "trim"},
						{"source": "Description", "target": "description"},
					],
					"defaults": {
						"item_group": self.item_group,
						"stock_uom": self.stock_uom,
						"is_stock_item": 0,
					},
					"children": [
						{
							"table_field": "barcodes",
							"sheet": "Barcodes",
							"parent_key": "Parent ID",
							"mapping": [{"source": "Barcode", "target": "barcode", "transform": "trim"}],
						}
					],
				}
			]
		}

	def test_multi_sheet_plan_keeps_children_with_parent(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		plan = build_import_plan(self._item_workbook(item_code), self._item_spec())
		self.assertTrue(plan["valid"], plan)
		self.assertEqual(len(plan["records"]), 1)
		payload = plan["records"][0]
		self.assertEqual(payload["values"]["item_code"], item_code)
		self.assertEqual(len(payload["children"]["barcodes"]), 1)

	def test_submit_mode_is_rejected_for_non_submittable_doctype(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		specification = self._item_spec()
		specification["nodes"][0]["submit"] = True
		with self.assertRaises(frappe.ValidationError):
			build_import_plan(self._item_workbook(item_code), specification)

	def test_orphan_child_is_reported_and_valid_parent_can_be_selected(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		plan = build_import_plan(self._item_workbook(item_code, orphan=True), self._item_spec())
		self.assertFalse(plan["valid"])
		self.assertEqual(len(plan["records"]), 1)
		self.assertTrue(any("sin padre" in error["error"] for error in plan["errors"]))
		issue = plan["errors"][0]
		self.assertEqual(issue["severity"], "error")
		self.assertEqual(issue["source_field"], "Parent ID")
		self.assertEqual(issue["code"], "orphan_child")
		with self.assertRaises(frappe.ValidationError):
			create_import_job(plan)
		job_name = create_import_job(plan, valid_only=True)
		self.assertEqual(frappe.db.get_value("BIMAP Data Job", job_name, "total_documents"), 1)

	def test_native_error_is_projected_to_source_cell_when_field_is_identifiable(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		workbook = {
			"sheets": [{
				"name": "Items",
				"rows": [{
					"External ID": "item-1",
					"Item Code": item_code,
					"Item Name": "Invalid linked group",
					"Item Group": "BDE-GROUP-DOES-NOT-EXIST",
				}],
			}],
		}
		specification = {
			"nodes": [{
				"id": "items",
				"doctype": "Item",
				"sheet": "Items",
				"external_key": "External ID",
				"mapping": [
					{"source": "Item Code", "target": "item_code"},
					{"source": "Item Name", "target": "item_name"},
					{"source": "Item Group", "target": "item_group"},
				],
				"defaults": {"stock_uom": self.stock_uom, "is_stock_item": 0},
			}],
		}
		plan = build_import_plan(workbook, specification)
		self.assertFalse(plan["valid"])
		self.assertEqual(plan["errors"][0]["source_field"], "Item Group")
		self.assertEqual(plan["errors"][0]["target_field"], "item_group")

	def test_incremental_revalidation_returns_only_selected_parent_row(self):
		first_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		second_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		workbook = {
			"sheets": [{
				"name": "Items",
				"rows": [
					{"External ID": "item-1", "Item Code": first_code, "Item Name": "First"},
					{"External ID": "item-2", "Item Code": second_code, "Item Name": "Second"},
				],
			}],
		}
		specification = {
			"nodes": [{
				"id": "items", "doctype": "Item", "sheet": "Items",
				"external_key": "External ID",
				"mapping": [
					{"source": "Item Code", "target": "item_code"},
					{"source": "Item Name", "target": "item_name"},
				],
				"defaults": {
					"item_group": self.item_group, "stock_uom": self.stock_uom, "is_stock_item": 0,
				},
			}],
		}
		plan = revalidate_import_rows(
			workbook, specification, [{"node": "items", "row": 3}]
		)
		self.assertTrue(plan["scope"]["partial"])
		self.assertEqual(plan["scope"]["rows"], [{"node": "items", "row": 3}])
		self.assertEqual(len(plan["records"]), 1)
		self.assertEqual(plan["records"][0]["external_key"], "item-2")
		self.assertEqual(plan["records"][0]["source_row"], 3)

	def test_external_key_errors_are_cell_addressable_instead_of_aborting_preview(self):
		workbook = {
			"sheets": [{
				"name": "Items",
				"rows": [
					{"External ID": "duplicate", "Item Code": "BDE-DUP-1", "Item Name": "One"},
					{"External ID": "duplicate", "Item Code": "BDE-DUP-2", "Item Name": "Two"},
					{"External ID": "", "Item Code": "BDE-BLANK", "Item Name": "Blank"},
				],
			}],
		}
		specification = {
			"nodes": [{
				"id": "items", "doctype": "Item", "sheet": "Items",
				"external_key": "External ID",
				"mapping": [
					{"source": "Item Code", "target": "item_code"},
					{"source": "Item Name", "target": "item_name"},
				],
				"defaults": {
					"item_group": self.item_group, "stock_uom": self.stock_uom, "is_stock_item": 0,
				},
			}],
		}
		plan = build_import_plan(workbook, specification)
		self.assertFalse(plan["valid"])
		self.assertEqual(len(plan["errors"]), 3)
		self.assertTrue(all(issue["source_field"] == "External ID" for issue in plan["errors"]))
		self.assertEqual(
			[issue["code"] for issue in plan["errors"]],
			["duplicate_external_key", "duplicate_external_key", "missing_external_key"],
		)

	def test_incremental_revalidation_falls_back_to_full_plan_for_child_graph(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		plan = revalidate_import_rows(
			self._item_workbook(item_code), self._item_spec(), [{"node": "items", "row": 2}]
		)
		self.assertFalse(plan["scope"]["partial"])
		self.assertEqual(len(plan["records"]), 1)

	def test_persistent_preview_job_validates_without_creating_target_document(self):
		item_code = f"BDE-PREVIEW-{uuid.uuid4().hex[:10].upper()}"
		job_name = create_preview_job(self._item_workbook(item_code), self._item_spec(), batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		job = frappe.get_doc("BIMAP Data Job", job_name)
		self.assertEqual(job.job_type, "Preview")
		self.assertEqual(job.status, "Completed")
		self.assertFalse(frappe.db.exists("Item", item_code))
		results = [
			json.loads(value)
			for value in frappe.get_all(
				"BIMAP Data Job Record", filters={"job": job_name}, pluck="result_json"
			)
		]
		self.assertEqual(sum(len(result["records"]) for result in results), 1)

	def test_persistent_preview_reports_orphan_child_only_once(self):
		item_code = f"BDE-PREVIEW-{uuid.uuid4().hex[:10].upper()}"
		job_name = create_preview_job(
			self._item_workbook(item_code, orphan=True), self._item_spec(), batch_size=2
		)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		results = [
			json.loads(value)
			for value in frappe.get_all(
				"BIMAP Data Job Record", filters={"job": job_name}, pluck="result_json"
			)
		]
		issues = [issue for result in results for issue in result["errors"]]
		self.assertEqual([issue["code"] for issue in issues].count("orphan_child"), 1)

	def test_persistent_preview_processes_500_documents_without_target_writes(self):
		suffix = uuid.uuid4().hex[:8].upper()
		workbook = {
			"sheets": [{
				"name": "UOMs",
				"rows": [
					{"External ID": f"uom-{index}", "UOM": f"BDE-PREVIEW-{suffix}-{index}"}
					for index in range(500)
				],
			}],
		}
		specification = {
			"nodes": [{
				"id": "uoms", "doctype": "UOM", "sheet": "UOMs",
				"external_key": "External ID",
				"mapping": [{"source": "UOM", "target": "uom_name"}],
				"defaults": {"must_be_whole_number": 1},
			}],
		}
		job_name = create_preview_job(workbook, specification, batch_size=100)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		job = frappe.get_doc("BIMAP Data Job", job_name)
		self.assertEqual(job.status, "Completed")
		self.assertEqual(job.processed_documents, 500)
		self.assertEqual(job.succeeded_documents, 500)
		self.assertEqual(
			frappe.db.count("UOM", {"name": ["like", f"BDE-PREVIEW-{suffix}-%"]}), 0
		)

	def test_import_job_inserts_native_parent_and_child_once(self):
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		plan = build_import_plan(self._item_workbook(item_code), self._item_spec())
		job_name = create_import_job(plan, batch_size=1)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		job = frappe.get_doc("BIMAP Data Job", job_name)
		item = frappe.get_doc("Item", item_code)
		self.assertEqual(job.job_type, "Import")
		self.assertEqual(job.status, "Completed")
		self.assertEqual(item.description, "Imported description")
		self.assertEqual(len(item.barcodes), 1)
		self.assertEqual(
			frappe.db.count(
				"BIMAP Data Change Log",
				filters={"operation_id": job.operation_id, "operation": "insert"},
			),
			1,
		)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		self.assertEqual(frappe.db.count("Item", {"name": item_code}), 1)

	def test_dependency_graph_creates_referenced_document_first(self):
		uom_name = f"BDE-{uuid.uuid4().hex[:8].upper()}"
		item_code = f"BDE-IMPORT-{uuid.uuid4().hex[:10].upper()}"
		workbook = {
			"sheets": [
				{"name": "UOMs", "rows": [{"Key": "uom-1", "UOM": uom_name}]},
				{
					"name": "Items",
					"rows": [
						{"Key": "item-1", "Code": item_code, "Name": "Dependent item", "UOM Key": "uom-1"}
					],
				},
			]
		}
		specification = {
			"nodes": [
				{
					"id": "items",
					"doctype": "Item",
					"sheet": "Items",
					"external_key": "Key",
					"mapping": [
						{"source": "Code", "target": "item_code"},
						{"source": "Name", "target": "item_name"},
					],
					"defaults": {"item_group": self.item_group, "is_stock_item": 0},
					"references": [{"source": "UOM Key", "target": "stock_uom", "node": "uoms"}],
				},
				{
					"id": "uoms",
					"doctype": "UOM",
					"sheet": "UOMs",
					"external_key": "Key",
					"mapping": [{"source": "UOM", "target": "uom_name"}],
					"defaults": {"must_be_whole_number": 1},
				},
			]
		}
		plan = build_import_plan(workbook, specification)
		self.assertTrue(plan["valid"], plan)
		self.assertEqual([record["node_id"] for record in plan["records"]], ["uoms", "items"])
		job_name = create_import_job(plan, batch_size=2)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		self.assertEqual(frappe.db.get_value("Item", item_code, "stock_uom"), uom_name)

	def test_cycle_is_rejected(self):
		workbook = {"sheets": [{"name": "A", "rows": []}, {"name": "B", "rows": []}]}
		specification = {
			"nodes": [
				{"id": "a", "references": [{"node": "b"}]},
				{"id": "b", "references": [{"node": "a"}]},
			]
		}
		with self.assertRaises(frappe.ValidationError):
			build_import_plan(workbook, specification)
