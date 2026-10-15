"""Whitelisted CFDI source endpoints."""

import frappe

from bimap_data_engine.services.cfdi import parse_attached_cfdi
from bimap_data_engine.services.cfdi_documents import create_cfdi_draft, preview_cfdi_document


@frappe.whitelist(methods=["POST"])
def inspect_cfdi(file_url):
	return parse_attached_cfdi(file_url)


@frappe.whitelist(methods=["POST"])
def preview_document(file_url, options=None):
	return preview_cfdi_document(file_url, options)


@frappe.whitelist(methods=["POST"])
def create_draft(file_url, options=None, operation_id=None):
	return create_cfdi_draft(file_url, options, operation_id)
