import uuid
import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cstr

from bimap_data_engine.api.records import list_records
from bimap_data_engine.api.records import list_child_rows
from bimap_data_engine.services.change_engine import apply_changes, preview_changes
from bimap_data_engine.services.jobs import create_job, list_jobs, request_cancel, resume_job, run_job


class TestItemDescriptionChanges(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.item_code = f"BDE-TEST-{uuid.uuid4().hex[:10].upper()}"
		item_group = frappe.get_all(
			"Item Group", filters={"is_group": 0}, pluck="name", limit=1
		)[0]
		stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": self.item_code,
				"item_name": "BIMAP Data Engine test item",
				"item_group": item_group,
				"stock_uom": stock_uom,
				"description": "Original description",
				"image": "/files/bde-test-image.png",
				"is_stock_item": 0,
				"barcodes": [{"barcode": f"OLD-{uuid.uuid4().hex[:12]}"}],
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _change(self, value="Updated description"):
		item = frappe.get_doc("Item", self.item_code)
		return {
			"operation": "set",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "description",
			"original": item.description,
			"value": value,
			"snapshot_modified": cstr(item.modified),
		}

	def test_query_always_returns_identity_and_snapshot(self):
		result = list_records(
			"Item",
			["description"],
			filters={"name": self.item_code},
			page_length=1,
		)
		self.assertEqual(result["rows"][0]["name"], self.item_code)
		self.assertIn("modified", result["rows"][0])

	def test_preview_does_not_write(self):
		change = self._change()
		result = preview_changes([change])
		self.assertTrue(result["valid"], result)
		self.assertEqual(
			frappe.db.get_value("Item", self.item_code, "description"),
			"Original description",
		)

	def test_apply_changes_only_requested_field(self):
		before = frappe.db.get_value(
			"Item",
			self.item_code,
			["item_name", "stock_uom", "is_stock_item"],
			as_dict=True,
		)
		result = apply_changes([self._change()])
		after = frappe.db.get_value(
			"Item",
			self.item_code,
			["description", "item_name", "stock_uom", "is_stock_item"],
			as_dict=True,
		)
		self.assertEqual(after.description, "Updated description")
		self.assertEqual(after.item_name, before.item_name)
		self.assertEqual(after.stock_uom, before.stock_uom)
		self.assertEqual(after.is_stock_item, before.is_stock_item)
		self.assertEqual(result["documents"][0]["changed_fields"], ["description"])
		logs = frappe.get_all(
			"BIMAP Data Change Log",
			filters={"operation_id": result["operation_id"]},
			fields=["reference_doctype", "document_name", "fieldname", "operation"],
		)
		self.assertEqual(len(logs), 1)
		self.assertEqual(logs[0].reference_doctype, "Item")
		self.assertEqual(logs[0].document_name, self.item_code)
		self.assertEqual(logs[0].fieldname, "description")
		self.assertEqual(logs[0].operation, "set")

	def test_clear_is_explicit_and_audited(self):
		item = frappe.get_doc("Item", self.item_code)
		change = {
			"operation": "clear",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "image",
			"original": item.image,
			"snapshot_modified": cstr(item.modified),
		}
		preview = preview_changes([change])
		self.assertTrue(preview["valid"], preview)
		result = apply_changes([change])
		self.assertFalse(frappe.db.get_value("Item", self.item_code, "image"))
		log = frappe.get_doc(
			"BIMAP Data Change Log",
			{"operation_id": result["operation_id"], "operation": "clear"},
		)
		self.assertEqual(log.fieldname, "image")
		self.assertIn("bde-test-image.png", log.original_value)

	def test_external_change_is_reported_as_conflict(self):
		change = self._change()
		item = frappe.get_doc("Item", self.item_code)
		item.description = "External update"
		item.save()
		result = preview_changes([change])
		self.assertFalse(result["valid"])
		self.assertTrue(any("conflicto" in error for error in result["documents"][0]["errors"]))

	def test_system_field_is_not_editable(self):
		change = self._change()
		change["fieldname"] = "modified"
		change["original"] = change["snapshot_modified"]
		result = preview_changes([change])
		self.assertFalse(result["valid"])
		self.assertTrue(any("no editable" in error for error in result["documents"][0]["errors"]))

	def test_user_without_item_write_permission_is_rejected(self):
		email = f"bde-no-access-{uuid.uuid4().hex[:10]}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "BDE no access",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		change = self._change()
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			preview_changes([change])

	def test_child_query_returns_persistent_name(self):
		result = list_child_rows("Item", self.item_code, "barcodes", ["barcode"])
		self.assertEqual(len(result["rows"]), 1)
		self.assertTrue(result["rows"][0]["name"])
		self.assertEqual(result["snapshot_modified"], cstr(self.item.modified))

	def test_add_barcode_preserves_existing_rows(self):
		item = frappe.get_doc("Item", self.item_code)
		existing_name = item.barcodes[0].name
		new_barcode = f"NEW-{uuid.uuid4().hex[:12]}"
		change = {
			"operation": "add_child",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "barcodes",
			"value": {"barcode": new_barcode},
			"snapshot_modified": cstr(item.modified),
		}
		result = apply_changes([change])
		item.reload()
		self.assertEqual(len(item.barcodes), 2)
		self.assertIn(existing_name, [row.name for row in item.barcodes])
		self.assertIn(new_barcode, [row.barcode for row in item.barcodes])
		self.assertEqual(result["documents"][0]["operations"], ["add_child"])
		log = frappe.get_doc(
			"BIMAP Data Change Log",
			{"operation_id": result["operation_id"], "operation": "add_child"},
		)
		self.assertIn(log.child_name, [row.name for row in item.barcodes])

	def test_preview_runs_native_mandatory_validation_without_writing(self):
		item = frappe.get_doc("Item", self.item_code)
		change = {
			"operation": "add_child",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "barcodes",
			"value": {"barcode": ""},
			"snapshot_modified": cstr(item.modified),
		}
		result = preview_changes([change])
		self.assertFalse(result["valid"])
		self.assertTrue(any("Validación ERPNext" in error for error in result["documents"][0]["errors"]))
		item.reload()
		self.assertEqual(len(item.barcodes), 1)

	def test_update_barcode_uses_persistent_child_name(self):
		item = frappe.get_doc("Item", self.item_code)
		row = item.barcodes[0]
		new_barcode = f"EDIT-{uuid.uuid4().hex[:12]}"
		change = {
			"operation": "update_child",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "barcodes",
			"child_name": row.name,
			"child_fieldname": "barcode",
			"original": row.barcode,
			"value": new_barcode,
			"snapshot_modified": cstr(item.modified),
		}
		apply_changes([change])
		item.reload()
		self.assertEqual(item.barcodes[0].name, row.name)
		self.assertEqual(item.barcodes[0].barcode, new_barcode)

	def test_delete_barcode_requires_confirmation(self):
		item = frappe.get_doc("Item", self.item_code)
		change = {
			"operation": "delete_child",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "barcodes",
			"child_name": item.barcodes[0].name,
			"snapshot_modified": cstr(item.modified),
		}
		with self.assertRaises(frappe.ValidationError):
			preview_changes([change])
		change["confirmed"] = True
		apply_changes([change])
		item.reload()
		self.assertEqual(item.barcodes, [])

	def test_persistent_job_is_idempotent_after_success(self):
		job_name = create_job([self._change("Changed by job")], batch_size=1)
		self.assertEqual(list_jobs(page_length=1)["jobs"][0].name, job_name)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		job = frappe.get_doc("BIMAP Data Job", job_name)
		record = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, fields=["status", "attempts"]
		)[0]
		self.assertEqual(job.status, "Completed")
		self.assertEqual(record.status, "Success")
		self.assertEqual(record.attempts, 1)
		self.assertEqual(frappe.db.get_value("Item", self.item_code, "description"), "Changed by job")

		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		self.assertEqual(
			frappe.db.get_value("BIMAP Data Job Record", {"job": job_name}, "attempts"), 1
		)

	def test_job_keeps_success_and_can_retry_only_failed_records(self):
		second_code = f"BDE-TEST-{uuid.uuid4().hex[:10].upper()}"
		second = frappe.copy_doc(self.item)
		second.item_code = second_code
		second.item_name = "BIMAP retry test item"
		second.barcodes = []
		second.insert()
		good = self._change("First succeeds")
		bad = {
			"operation": "set",
			"doctype": "Item",
			"name": second.name,
			"fieldname": "description",
			"original": second.description,
			"value": "Second succeeds on retry",
			"snapshot_modified": "1900-01-01 00:00:00",
		}
		job_name = create_job([good, bad], batch_size=2)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		job = frappe.get_doc("BIMAP Data Job", job_name)
		self.assertEqual(job.status, "Completed with errors")
		self.assertEqual(job.succeeded_documents, 1)
		self.assertEqual(job.failed_documents, 1)

		failed = frappe.get_doc(
			"BIMAP Data Job Record", {"job": job_name, "status": "Failed"}
		)
		failed_changes = json.loads(failed.changes_json)
		failed_changes[0]["snapshot_modified"] = cstr(second.modified)
		failed.db_set("changes_json", json.dumps(failed_changes), update_modified=False)
		resume_job(job_name, retry_failed=True, enqueue=False)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)

		job.reload()
		self.assertEqual(job.status, "Completed")
		self.assertEqual(job.succeeded_documents, 2)
		attempts = frappe.get_all(
			"BIMAP Data Job Record", filters={"job": job_name}, pluck="attempts", order_by="sequence asc"
		)
		self.assertEqual(attempts, [1, 2])
		self.assertEqual(frappe.db.get_value("Item", second_code, "description"), "Second succeeds on retry")

	def test_cancelled_job_does_not_apply_pending_changes(self):
		job_name = create_job([self._change("Must not be written")], batch_size=1)
		request_cancel(job_name)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		self.assertEqual(frappe.db.get_value("BIMAP Data Job", job_name, "status"), "Cancelled")
		self.assertEqual(
			frappe.db.get_value("Item", self.item_code, "description"), "Original description"
		)

	def test_interrupted_job_resumes_without_repeating_checkpoint(self):
		changes = [self._change("Resume item 1")]
		item_codes = [self.item_code]
		for index in range(2, 4):
			item_code = f"BDE-TEST-{uuid.uuid4().hex[:10].upper()}"
			item = frappe.copy_doc(self.item)
			item.item_code = item_code
			item.item_name = f"BIMAP resume item {index}"
			item.barcodes = []
			item.insert()
			item_codes.append(item_code)
			changes.append(
				{
					"operation": "set",
					"doctype": "Item",
					"name": item.name,
					"fieldname": "description",
					"original": item.description,
					"value": f"Resume item {index}",
					"snapshot_modified": cstr(item.modified),
				}
			)
		job_name = create_job(changes, batch_size=1)
		commit_count = 0

		def interrupt_after_first_checkpoint():
			nonlocal commit_count
			commit_count += 1
			if commit_count == 2:
				frappe.db.set_value("BIMAP Data Job", job_name, "cancel_requested", 1)

		with patch.object(frappe.db, "commit", side_effect=interrupt_after_first_checkpoint):
			run_job(job_name)
		self.assertEqual(frappe.db.get_value("BIMAP Data Job", job_name, "status"), "Cancelled")
		self.assertEqual(
			frappe.get_all(
				"BIMAP Data Job Record", filters={"job": job_name}, pluck="status", order_by="sequence asc"
			),
			["Success", "Pending", "Pending"],
		)

		resume_job(job_name, enqueue=False)
		with patch.object(frappe.db, "commit"):
			run_job(job_name)
		self.assertEqual(frappe.db.get_value("BIMAP Data Job", job_name, "status"), "Completed")
		self.assertEqual(
			frappe.get_all(
				"BIMAP Data Job Record", filters={"job": job_name}, pluck="attempts", order_by="sequence asc"
			),
			[1, 1, 1],
		)
		for index, item_code in enumerate(item_codes, start=1):
			self.assertEqual(
				frappe.db.get_value("Item", item_code, "description"), f"Resume item {index}"
			)
