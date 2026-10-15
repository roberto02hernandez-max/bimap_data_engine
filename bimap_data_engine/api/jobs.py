"""Whitelisted endpoints for persistent bulk jobs."""

import frappe
from frappe.utils import cint

from bimap_data_engine.services import jobs


@frappe.whitelist(methods=["POST"])
def create_job(changes, batch_size=50, enqueue_now=1, context_id=None):
	from bimap_data_engine.services.context import validate_context_changes

	validate_context_changes(context_id, changes)
	job_name = jobs.create_job(changes, batch_size=batch_size)
	if cint(enqueue_now):
		return jobs.enqueue_job(job_name)
	return jobs.get_job(job_name)


@frappe.whitelist(methods=["GET"])
def get_job(job_name, start=0, page_length=100):
	return jobs.get_job(job_name, start=start, page_length=page_length)


@frappe.whitelist(methods=["GET"])
def list_jobs(start=0, page_length=50, job_type=None):
	return jobs.list_jobs(start=start, page_length=page_length, job_type=job_type)


@frappe.whitelist(methods=["POST"])
def cancel_job(job_name):
	return jobs.request_cancel(job_name)


@frappe.whitelist(methods=["POST"])
def resume_job(job_name, retry_failed=0):
	return jobs.resume_job(job_name, retry_failed=bool(cint(retry_failed)))
