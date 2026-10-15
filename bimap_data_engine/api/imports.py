"""File inspection, mappings and persistent session endpoints."""

import frappe
from frappe.utils import cint

from bimap_data_engine.services.files import parse_attached_file
from bimap_data_engine.services.import_engine import (
	build_import_plan,
	create_preview_job,
	create_import_job,
	revalidate_import_rows as revalidate_rows,
)
from bimap_data_engine.services.jobs import enqueue_job, get_job
from bimap_data_engine.services.mapping import map_row, suggest_mapping
from bimap_data_engine.services.sessions import (
	get_mapping_profile,
	get_session,
	list_sessions,
	save_mapping_profile,
	save_session,
)


@frappe.whitelist(methods=["POST"])
def inspect_file(file_url):
	return parse_attached_file(file_url)


@frappe.whitelist(methods=["POST"])
def suggest(doctype, headers, table_field=None):
	return suggest_mapping(doctype, headers, table_field)


@frappe.whitelist(methods=["POST"])
def preview_mapped_row(doctype, row, mapping, defaults=None, table_field=None):
	return map_row(doctype, row, mapping, defaults, table_field)


@frappe.whitelist(methods=["POST"])
def preview_import(workbook, specification, context_id=None):
	from bimap_data_engine.services.context import validate_context_import_specification

	validate_context_import_specification(context_id, specification)
	return build_import_plan(workbook, specification)


@frappe.whitelist(methods=["POST"])
def revalidate_import_rows(workbook, specification, selection, context_id=None):
	from bimap_data_engine.services.context import validate_context_import_specification

	validate_context_import_specification(context_id, specification)
	return revalidate_rows(workbook, specification, selection)


@frappe.whitelist(methods=["POST"])
def start_preview(workbook, specification, batch_size=50, enqueue_now=1, context_id=None):
	from bimap_data_engine.services.context import validate_context_import_specification

	validate_context_import_specification(context_id, specification)
	job_name = create_preview_job(workbook, specification, batch_size=batch_size)
	if cint(enqueue_now):
		return enqueue_job(job_name)
	return get_job(job_name)


@frappe.whitelist(methods=["POST"])
def start_import(plan, batch_size=50, valid_only=0, enqueue_now=1, context_id=None):
	from bimap_data_engine.services.context import validate_context_import_plan

	validate_context_import_plan(context_id, plan)
	job_name = create_import_job(
		plan, batch_size=batch_size, valid_only=bool(cint(valid_only))
	)
	if cint(enqueue_now):
		return enqueue_job(job_name)
	return get_job(job_name)


@frappe.whitelist(methods=["POST"])
def save_profile(profile_title, target_doctype, mapping, defaults=None, profile_name=None, **values):
	return save_mapping_profile(
		profile_title, target_doctype, mapping, defaults, profile_name, **values
	)


@frappe.whitelist(methods=["GET"])
def get_profile(profile_name):
	return get_mapping_profile(profile_name)


@frappe.whitelist(methods=["POST"])
def save_work_session(session_title, mode, target_doctype, state, session_name=None, **values):
	return save_session(session_title, mode, target_doctype, state, session_name, **values)


@frappe.whitelist(methods=["GET"])
def get_work_session(session_name):
	return get_session(session_name)


@frappe.whitelist(methods=["GET"])
def list_work_sessions(limit=50):
	return list_sessions(limit)
