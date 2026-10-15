"""Download endpoints for source data and per-record execution results."""

import frappe

from bimap_data_engine.services.exports import build_job_results_csv, build_records_xlsx


def _download(filename, content):
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["GET"])
def download_records(doctype, fields, filters=None, max_rows=25000, context_id=None):
	content, _row_count = build_records_xlsx(doctype, fields, filters, max_rows, context_id)
	_download(f"{doctype}.xlsx", content)


@frappe.whitelist(methods=["GET"])
def download_job_results(job_name):
	_download(f"bimap-data-job-{job_name}.csv", build_job_results_csv(job_name))
