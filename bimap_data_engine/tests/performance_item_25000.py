"""Manual acceptance benchmark for Case A. All database effects are rolled back."""

import hashlib
import json
import resource
import time
import uuid
from unittest.mock import patch

import frappe

from bimap_data_engine.api.records import list_records
from bimap_data_engine.services.jobs import create_job, run_job


TOTAL_ITEMS = 25_000
PREFIX = "BDE-PERF-"


def _digest_rows(doctype, fields, filters, *, page_size=500):
	digest = hashlib.sha256()
	start = 0
	count = 0
	while True:
		rows = frappe.get_all(
			doctype,
			fields=fields,
			filters=filters,
			order_by="name asc",
			start=start,
			page_length=page_size,
		)
		for row in rows:
			digest.update(
				json.dumps(row, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
			)
		count += len(rows)
		if len(rows) < page_size:
			break
		start += len(rows)
	return digest.hexdigest(), count


def _create_items(run_id, total_items):
	item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
	base_code = f"{PREFIX}{run_id}-00000"
	base = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": base_code,
			"item_name": "BDE 25k performance fixture 00000",
			"item_group": item_group,
			"stock_uom": stock_uom,
			"description": "BDE performance original",
			"is_stock_item": 0,
		}
	).insert()
	base_values = base.get_valid_dict(convert_dates_to_str=False, ignore_nulls=False)
	fields = list(base_values)
	fields.remove("name")
	fields.insert(0, "name")

	def values():
		for index in range(1, total_items):
			code = f"{PREFIX}{run_id}-{index:05d}"
			row = dict(base_values)
			row.update({"name": code, "item_code": code, "item_name": f"BDE 25k performance fixture {index:05d}"})
			yield tuple(row.get(field) for field in fields)

	frappe.db.bulk_insert("Item", fields=fields, values=values(), chunk_size=1000)
	return f"{PREFIX}{run_id}-%"


def run(total_items=TOTAL_ITEMS, commit_batches=0):
	frappe.set_user("Administrator")
	total_items = int(total_items)
	commit_batches = int(commit_batches)
	if not 1 <= total_items <= TOTAL_ITEMS:
		raise ValueError(f"total_items debe estar entre 1 y {TOTAL_ITEMS}")
	started = time.perf_counter()
	run_id = uuid.uuid4().hex[:8].upper()
	report = {"case": "A", "target_items": total_items, "run_id": run_id}
	name_filter = None
	job_name = None
	operation_id = None
	try:
		fixture_started = time.perf_counter()
		name_filter = _create_items(run_id, total_items)
		if commit_batches:
			frappe.db.commit()
		report["fixture_seconds"] = round(time.perf_counter() - fixture_started, 3)

		meta = frappe.get_meta("Item")
		guard_fields = [
			"name", "owner", "creation", "docstatus",
			*[
				df.fieldname
				for df in meta.fields
				if df.fieldname
				and df.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Table", "Table MultiSelect"}
				and df.fieldname not in {"description", "modified", "modified_by", "_user_tags", "_comments", "_assign", "_liked_by"}
			],
		]
		guard_fields = list(dict.fromkeys(guard_fields))
		before_digest, before_count = _digest_rows("Item", guard_fields, {"name": ["like", name_filter]})
		child_before, child_count_before = _digest_rows(
			"Item Barcode", ["name", "parent", "idx", "barcode", "barcode_type", "uom"],
			{"parent": ["like", name_filter]},
		)

		query_started = time.perf_counter()
		rows = []
		next_start = 0
		while next_start is not None and len(rows) < total_items:
			page = list_records(
				"Item", ["description"], {"name": ["like", name_filter]},
				start=next_start, page_length=500,
			)
			rows.extend(page["rows"])
			next_start = page["next_start"]
		report["query_seconds"] = round(time.perf_counter() - query_started, 3)
		report["queried_items"] = len(rows)
		if len(rows) != total_items:
			raise AssertionError(f"Se consultaron {len(rows)} Items, se esperaban {total_items}.")

		changes = [
			{
				"operation": "set",
				"doctype": "Item",
				"name": row.name,
				"fieldname": "description",
				"original": row.description,
				"value": "BDE performance updated",
				"snapshot_modified": str(row.modified),
			}
			for row in rows
		]
		job_create_started = time.perf_counter()
		job_name = create_job(changes, batch_size=100)
		if commit_batches:
			frappe.db.commit()
		report["job_create_seconds"] = round(time.perf_counter() - job_create_started, 3)
		run_started = time.perf_counter()
		if commit_batches:
			run_job(job_name)
		else:
			with patch.object(frappe.db, "commit"):
				run_job(job_name)
		report["job_seconds"] = round(time.perf_counter() - run_started, 3)

		job = frappe.get_doc("BIMAP Data Job", job_name)
		operation_id = job.operation_id
		report["job_status"] = job.status
		report["succeeded"] = job.succeeded_documents
		report["failed"] = job.failed_documents
		if job.failed_documents:
			report["failed_records"] = frappe.get_all(
				"BIMAP Data Job Record",
				filters={"job": job_name, "status": "Failed"},
				fields=["sequence", "document_name", "attempts", "error"],
				order_by="sequence asc",
				limit_page_length=20,
			)
		report["updated_descriptions"] = frappe.db.count(
			"Item", {"name": ["like", name_filter], "description": "BDE performance updated"}
		)
		after_digest, after_count = _digest_rows("Item", guard_fields, {"name": ["like", name_filter]})
		child_after, child_count_after = _digest_rows(
			"Item Barcode", ["name", "parent", "idx", "barcode", "barcode_type", "uom"],
			{"parent": ["like", name_filter]},
		)
		report["other_fields_unchanged"] = before_digest == after_digest and before_count == after_count
		report["children_unchanged"] = child_before == child_after and child_count_before == child_count_after
		report["audit_rows"] = frappe.db.count(
			"BIMAP Data Change Log", {"operation_id": job.operation_id, "operation": "set"}
		)
		report["max_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
		report["total_seconds"] = round(time.perf_counter() - started, 3)
		report["passed"] = all(
			[
				job.status == "Completed",
				job.succeeded_documents == total_items,
				job.failed_documents == 0,
				report["updated_descriptions"] == total_items,
				report["other_fields_unchanged"],
				report["children_unchanged"],
				report["audit_rows"] == total_items,
			]
		)
		if not report["passed"]:
			raise AssertionError(json.dumps(report, ensure_ascii=False, default=str))
		return report
	finally:
		if commit_batches:
			frappe.db.rollback()
			if name_filter:
				frappe.db.delete("Item Barcode", {"parent": ["like", name_filter]})
				frappe.db.delete("Version", {"ref_doctype": "Item", "docname": ["like", name_filter]})
				frappe.db.delete("Item", {"name": ["like", name_filter]})
			if operation_id:
				frappe.db.delete("BIMAP Data Change Log", {"operation_id": operation_id})
			if job_name:
				frappe.db.delete("BIMAP Data Job Record", {"job": job_name})
				frappe.db.delete("BIMAP Data Job", {"name": job_name})
			frappe.db.commit()
		else:
			frappe.db.rollback()
