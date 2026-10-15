"""Persistent, resumable execution of explicit Data Engine changes."""

import json

import frappe
from frappe.utils import cint, cstr, now_datetime

from bimap_data_engine.services.change_engine import apply_changes, group_changes


MAX_JOB_CHANGES = 100_000
DEFAULT_BATCH_SIZE = 50
MAX_BATCH_SIZE = 500
TERMINAL_STATUSES = {"Completed", "Completed with errors", "Cancelled", "Failed"}


def _json(value):
	return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _assert_job_access(job):
	if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
		return
	if job.requested_by != frappe.session.user:
		frappe.throw("No tienes permiso para consultar este trabajo.", frappe.PermissionError)


def list_jobs(*, start=0, page_length=50, job_type=None):
	"""List only jobs visible to the current user, newest first."""
	page_length = min(max(cint(page_length) or 50, 1), 200)
	filters = {}
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		filters["requested_by"] = frappe.session.user
	if job_type:
		job_type = cstr(job_type).title()
		if job_type not in {"Edit", "Import", "Preview"}:
			frappe.throw("Tipo de trabajo inválido.")
		filters["job_type"] = job_type
	fields = [
		"name", "status", "job_type", "requested_by", "operation_id", "total_documents",
		"processed_documents", "succeeded_documents", "failed_documents", "creation", "modified",
	]
	rows = frappe.get_all(
		"BIMAP Data Job",
		filters=filters,
		fields=fields,
		order_by="creation desc",
		start=max(cint(start), 0),
		page_length=page_length + 1,
	)
	return {"jobs": rows[:page_length], "has_more": len(rows) > page_length}


def _validated_batch_size(batch_size):
	batch_size = cint(batch_size) or DEFAULT_BATCH_SIZE
	if not 1 <= batch_size <= MAX_BATCH_SIZE:
		frappe.throw(f"El tamaño de lote debe estar entre 1 y {MAX_BATCH_SIZE}.")
	return batch_size


def create_job(changes, *, batch_size=DEFAULT_BATCH_SIZE):
	"""Persist one work item per document so a retry never repeats successes."""
	groups = group_changes(changes, max_changes=MAX_JOB_CHANGES)
	batch_size = _validated_batch_size(batch_size)
	for doctype, _name in groups:
		frappe.has_permission(doctype, "write", throw=True)

	job = frappe.get_doc(
		{
			"doctype": "BIMAP Data Job",
			"status": "Draft",
			"job_type": "Edit",
			"requested_by": frappe.session.user,
			"operation_id": frappe.generate_hash(length=20),
			"batch_size": batch_size,
			"total_documents": len(groups),
		}
	).insert(ignore_permissions=True)
	records = (
		{
			"sequence": sequence,
			"reference_doctype": doctype,
			"document_name": name,
			"changes_json": _json(document_changes),
		}
		for sequence, ((doctype, name), document_changes) in enumerate(groups.items(), start=1)
	)
	insert_job_records(job.name, records)
	job.db_set("status", "Queued", update_modified=True)
	return job.name


def insert_job_records(job_name, records):
	"""Bulk-write internal checkpoints; target ERPNext documents never use this path."""
	now = now_datetime()
	user = frappe.session.user
	fields = [
		"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx",
		"job", "sequence", "node_id", "external_key", "reference_doctype",
		"document_name", "status", "attempts", "changes_json", "dependencies_json",
	]
	values = (
		(
			frappe.generate_hash(length=16), now, now, user, user, 0, 0,
			job_name, record["sequence"], record.get("node_id"), record.get("external_key"),
			record["reference_doctype"], record.get("document_name"), "Pending", 0,
			record["changes_json"], record.get("dependencies_json"),
		)
		for record in records
	)
	frappe.db.bulk_insert("BIMAP Data Job Record", fields=fields, values=values, chunk_size=1000)


def enqueue_job(job_name):
	job = frappe.get_doc("BIMAP Data Job", job_name)
	_assert_job_access(job)
	frappe.enqueue(
		"bimap_data_engine.services.jobs.run_job",
		queue="long",
		job_name=f"bimap-data-engine-{job_name}",
		enqueue_after_commit=True,
		job_name_arg=job_name,
	)
	return get_job(job_name)


def _refresh_counts(job_name):
	counts = {
		row.status: row.count
		for row in frappe.get_all(
			"BIMAP Data Job Record",
			filters={"job": job_name},
			fields=["status", "count(name) as count"],
			group_by="status",
		)
	}
	succeeded = cint(counts.get("Success"))
	failed = cint(counts.get("Failed"))
	processed = succeeded + failed
	frappe.db.set_value(
		"BIMAP Data Job",
		job_name,
		{
			"processed_documents": processed,
			"succeeded_documents": succeeded,
			"failed_documents": failed,
		},
		update_modified=True,
	)
	return processed, succeeded, failed


def _mark_terminal(job_name, status, error=None):
	frappe.db.set_value(
		"BIMAP Data Job",
		job_name,
		{"status": status, "finished_at": now_datetime(), "last_error": error},
		update_modified=True,
	)


def run_job(job_name_arg):
	"""Worker entry point. Each committed batch is an atomic checkpoint."""
	job_name = cstr(job_name_arg)
	original_user = frappe.session.user
	try:
		job = frappe.get_doc("BIMAP Data Job", job_name)
		if job.status in {"Running", "Completed"}:
			return
		if job.cancel_requested:
			_mark_terminal(job_name, "Cancelled")
			frappe.db.commit()
			return
		frappe.db.set_value(
			"BIMAP Data Job",
			job_name,
			{"status": "Running", "started_at": job.started_at or now_datetime(), "finished_at": None},
			update_modified=True,
		)
		frappe.db.commit()
		frappe.set_user(job.requested_by)

		while True:
			job = frappe.get_doc("BIMAP Data Job", job_name)
			if job.cancel_requested:
				_mark_terminal(job_name, "Cancelled")
				frappe.db.commit()
				return
			record_names = frappe.get_all(
				"BIMAP Data Job Record",
				filters={"job": job_name, "status": "Pending"},
				order_by="sequence asc",
				pluck="name",
				limit_page_length=job.batch_size,
			)
			if not record_names:
				break
			for record_name in record_names:
				record = frappe.get_doc("BIMAP Data Job Record", record_name)
				frappe.db.set_value(
					"BIMAP Data Job Record",
					record_name,
					{"status": "Running", "attempts": cint(record.attempts) + 1, "error": None},
					update_modified=True,
				)
				savepoint = f"bde_job_{frappe.generate_hash(length=10)}"
				frappe.db.savepoint(savepoint)
				try:
					if job.job_type == "Preview":
						from bimap_data_engine.services.import_engine import apply_preview_record

						result = apply_preview_record(job, record)
					elif job.job_type == "Import":
						from bimap_data_engine.services.import_engine import apply_import_record

						result = apply_import_record(job, record)
					else:
						result = apply_changes(
							json.loads(record.changes_json), operation_id=job.operation_id
						)
					result_document = result.get("document_name") if isinstance(result, dict) else None
					frappe.db.set_value(
						"BIMAP Data Job Record",
						record_name,
						{
							"status": "Success",
							"result_document": result_document,
							"result_json": _json(result),
							"error": None,
						},
						update_modified=True,
					)
				except Exception:
					error = frappe.get_traceback(with_context=False)
					frappe.db.rollback(save_point=savepoint)
					frappe.db.set_value(
						"BIMAP Data Job Record",
						record_name,
						{"status": "Failed", "error": error},
						update_modified=True,
					)
					frappe.clear_messages()
			_refresh_counts(job_name)
			frappe.db.commit()

		_processed, _succeeded, failed = _refresh_counts(job_name)
		status = "Completed with errors" if failed else "Completed"
		_mark_terminal(job_name, status)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.set_user("Administrator")
		if frappe.db.exists("BIMAP Data Job", job_name):
			_refresh_counts(job_name)
			_mark_terminal(job_name, "Failed", frappe.get_traceback(with_context=False))
			frappe.db.commit()
		raise
	finally:
		frappe.set_user(original_user)


def request_cancel(job_name):
	job = frappe.get_doc("BIMAP Data Job", job_name)
	_assert_job_access(job)
	if job.status not in TERMINAL_STATUSES:
		job.db_set("cancel_requested", 1, update_modified=True)
	return get_job(job_name)


def resume_job(job_name, *, retry_failed=False, enqueue=True):
	job = frappe.get_doc("BIMAP Data Job", job_name)
	_assert_job_access(job)
	if job.status == "Completed":
		return get_job(job_name)
	frappe.db.set_value(
		"BIMAP Data Job Record",
		{"job": job_name, "status": "Running"},
		"status",
		"Pending",
		update_modified=True,
	)
	if retry_failed:
		frappe.db.set_value(
			"BIMAP Data Job Record",
			{"job": job_name, "status": "Failed"},
			{"status": "Pending", "error": None},
			update_modified=True,
		)
	frappe.db.set_value(
		"BIMAP Data Job",
		job_name,
		{"status": "Queued", "cancel_requested": 0, "finished_at": None, "last_error": None},
		update_modified=True,
	)
	if enqueue:
		return enqueue_job(job_name)
	return get_job(job_name)


def get_job(job_name, *, start=0, page_length=100):
	job = frappe.get_doc("BIMAP Data Job", job_name)
	_assert_job_access(job)
	page_length = min(max(cint(page_length) or 100, 1), 500)
	records = frappe.get_all(
		"BIMAP Data Job Record",
		filters={"job": job_name},
		fields=[
			"name", "sequence", "node_id", "external_key", "reference_doctype",
			"document_name", "status", "attempts", "changes_json", "result_json", "error",
		],
		order_by="sequence asc",
		start=max(cint(start), 0),
		page_length=page_length,
	)
	job_payload = job.as_dict()
	job_payload.pop("request_json", None)
	return {"job": job_payload, "records": records}
