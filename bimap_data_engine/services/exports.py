"""Permission-aware XLSX data exports and job result downloads."""

import csv
import io

import frappe
from frappe.utils import cint
from frappe.utils.xlsxutils import make_xlsx

from bimap_data_engine.api.records import _parse_fields, _parse_filters
from bimap_data_engine.services.context import context_filters, validate_context_fields
from bimap_data_engine.services.jobs import _assert_job_access
from bimap_data_engine.services.metadata import get_doctype_meta, readable_fieldnames
from bimap_data_engine.services.related_filters import apply_related_filters


MAX_EXPORT_ROWS = 25_000


def build_records_xlsx(doctype, fields, filters=None, max_rows=MAX_EXPORT_ROWS, context_id=None):
	meta = get_doctype_meta(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	fields = _parse_fields(fields)
	denied = sorted(set(fields) - readable_fieldnames(meta))
	if denied:
		frappe.throw(f"Campos no exportables: {', '.join(denied)}")
	context = validate_context_fields(context_id, doctype, fields) if context_id else None
	requested_filters = _parse_filters(filters)
	fixed_filters = context_filters(context)
	if fixed_filters:
		if requested_filters and requested_filters != fixed_filters:
			frappe.throw("Este contexto fija los filtros de exportación.", frappe.PermissionError)
		requested_filters = fixed_filters
	requested_filters = apply_related_filters(doctype, requested_filters)
	max_rows = min(max(cint(max_rows) or MAX_EXPORT_ROWS, 1), MAX_EXPORT_ROWS)
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=requested_filters,
		order_by="name asc",
		limit_page_length=max_rows,
	)
	labels = [meta.get_label(field) or field for field in fields]
	data = [labels, *[[row.get(field) for field in fields] for row in rows]]
	return make_xlsx(data, doctype).getvalue(), len(rows)


def build_job_results_csv(job_name):
	job = frappe.get_doc("BIMAP Data Job", job_name)
	_assert_job_access(job)
	buffer = io.StringIO(newline="")
	writer = csv.writer(buffer)
	writer.writerow(
		[
			"sequence", "status", "doctype", "source_document", "result_document",
			"node_id", "external_key", "attempts", "error",
		]
	)
	start = 0
	while True:
		rows = frappe.get_all(
			"BIMAP Data Job Record",
			filters={"job": job_name},
			fields=[
				"sequence", "status", "reference_doctype", "document_name", "result_document",
				"node_id", "external_key", "attempts", "error",
			],
			order_by="sequence asc",
			start=start,
			page_length=5000,
		)
		for row in rows:
			writer.writerow(
				[
					row.sequence, row.status, row.reference_doctype, row.document_name,
					row.result_document, row.node_id, row.external_key, row.attempts, row.error,
				]
			)
		if len(rows) < 5000:
			break
		start += len(rows)
	return buffer.getvalue().encode("utf-8-sig")
