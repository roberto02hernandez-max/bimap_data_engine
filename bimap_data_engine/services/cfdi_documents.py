"""Native ERPNext document preparation for Mexican CFDI sources."""

from datetime import datetime
from decimal import Decimal

import frappe
from frappe.utils import cstr, flt, getdate

from bimap_data_engine.services.adapters import prepare_import_document
from bimap_data_engine.services.audit import record_changes
from bimap_data_engine.services.cfdi import load_attached_cfdi
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


TOTAL_TOLERANCE = Decimal("0.02")


def _options(value):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if value is None:
		return {}
	if not isinstance(value, dict):
		frappe.throw("Las opciones CFDI deben ser un objeto JSON.")
	return value


def _rfc(value):
	return "".join(cstr(value).upper().split())


def _date(value):
	text = cstr(value).strip()
	if not text:
		return getdate()
	try:
		return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
	except ValueError:
		return getdate(text[:10])


def _issue(code, message, *, severity="error", row=None, source_field=None, target_field=None):
	return {
		"sheet": "CFDI" if row is None else "Conceptos",
		"row": row,
		"source_field": source_field,
		"target_field": target_field,
		"severity": severity,
		"code": code,
		"message": cstr(message),
		"error": cstr(message),
	}


def _permitted_exact(doctype, fieldname, value):
	if not value:
		return []
	return frappe.get_list(
		doctype,
		filters={fieldname: value},
		fields=["name", fieldname],
		limit_page_length=3,
	)


def _resolve_party(doctype, fiscal_rfc, explicit, issues):
	label = "empresa" if doctype == "Company" else "proveedor"
	if explicit:
		doc = frappe.get_doc(doctype, explicit)
		doc.check_permission("read")
		configured = _rfc(doc.get("tax_id"))
		if configured and fiscal_rfc and configured != fiscal_rfc:
			issues.append(_issue(
				f"{label}_rfc_mismatch",
				f"El RFC del CFDI ({fiscal_rfc}) no coincide con {label} {doc.name} ({configured}).",
				source_field="Receptor.Rfc" if doctype == "Company" else "Emisor.Rfc",
			))
		elif not configured:
			issues.append(_issue(
				f"{label}_without_rfc",
				f"{doc.name} no tiene RFC configurado; se usó la selección explícita.",
				severity="warning",
			))
		return doc.name
	rows = _permitted_exact(doctype, "tax_id", fiscal_rfc)
	if len(rows) == 1:
		return rows[0].name
	if not rows:
		issues.append(_issue(
			f"{label}_not_found",
			f"No existe un {label} accesible con RFC {fiscal_rfc or '(vacío)' }.",
			source_field="Receptor.Rfc" if doctype == "Company" else "Emisor.Rfc",
		))
	else:
		issues.append(_issue(
			f"{label}_ambiguous",
			f"Hay más de un {label} accesible con RFC {fiscal_rfc}.",
			source_field="Receptor.Rfc" if doctype == "Company" else "Emisor.Rfc",
		))
	return None


def _duplicate(doctype, uuid):
	if not uuid or not frappe.get_meta(doctype).has_field("bimap_cfdi_uuid"):
		return None
	return frappe.db.get_value(doctype, {"bimap_cfdi_uuid": uuid}, "name")


def _item_code(concept, options):
	mapping = options.get("item_map") or {}
	for key in (concept.get("NoIdentificacion"), concept.get("ClaveProdServ")):
		if key and mapping.get(key):
			return cstr(mapping[key]).strip()
	code = cstr(concept.get("NoIdentificacion")).strip()
	if code and frappe.db.exists("Item", code):
		return code
	return cstr(options.get("default_item_code")).strip()


def _purchase_invoice(parsed, file_url, options, issues):
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	uuid = cstr(parsed.get("uuid")).upper()
	if not uuid:
		issues.append(_issue("missing_uuid", "El CFDI no contiene UUID; no se puede controlar duplicidad."))
	duplicate = _duplicate("Purchase Invoice", uuid)
	if duplicate:
		issues.append(_issue(
			"duplicate_cfdi", f"El CFDI ya está registrado en Purchase Invoice {duplicate}.",
			source_field="Timbre.UUID", target_field="bimap_cfdi_uuid",
		))
	company = _resolve_party("Company", _rfc(parsed["receiver"].get("Rfc")), options.get("company"), issues)
	supplier = _resolve_party("Supplier", _rfc(parsed["emitter"].get("Rfc")), options.get("supplier"), issues)
	if not company or not supplier:
		return None
	header = parsed["header"]
	series_folio = "-".join(filter(None, [cstr(header.get("Serie")).strip(), cstr(header.get("Folio")).strip()]))
	doc = frappe.get_doc({
		"doctype": "Purchase Invoice",
		"company": company,
		"supplier": supplier,
		"posting_date": _date(header.get("Fecha")),
		"bill_date": _date(header.get("Fecha")),
		"bill_no": series_folio or uuid,
		"currency": header.get("Moneda") or frappe.get_cached_value("Company", company, "default_currency"),
		"conversion_rate": flt(header.get("TipoCambio") or 1),
		"bimap_cfdi_uuid": uuid,
		"bimap_cfdi_file": file_url,
	})
	for index, concept in enumerate(parsed.get("concepts") or [], start=1):
		item_code = _item_code(concept, options)
		if not item_code or not frappe.db.exists("Item", item_code):
			issues.append(_issue(
				"unmapped_cfdi_concept",
				f"El concepto {concept.get('NoIdentificacion') or concept.get('ClaveProdServ') or index} no tiene artículo ERPNext.",
				row=index + 1, source_field="NoIdentificacion", target_field="item_code",
			))
			continue
		frappe.get_doc("Item", item_code).check_permission("read")
		doc.append("items", {
			"item_code": item_code,
			"qty": flt(concept.get("Cantidad") or 1),
			"rate": flt(concept.get("ValorUnitario")),
			"description": concept.get("Descripcion"),
		})
	if not doc.items:
		return None
	return doc


def _prepare_candidate(doc):
	"""Run the same insert lifecycle used by the generic importer, without a write."""
	doc.check_permission("create")
	savepoint = f"bde_cfdi_preview_{frappe.generate_hash(length=10)}"
	previous = getattr(frappe.flags, "in_bimap_data_engine_preview", False)
	frappe.db.savepoint(savepoint)
	try:
		frappe.flags.in_bimap_data_engine_preview = True
		doc.set("__islocal", True)
		doc._action = "save"
		doc._set_defaults()
		doc.set_user_and_timestamp()
		doc.set_docstatus()
		doc._validate_links()
		doc.run_method("before_insert")
		doc.set_new_name(set_child_names=True)
		doc.set_parent_in_children()
		doc.set_name_in_children()
		doc.validate_higher_perm_levels()
		doc.flags.in_insert = True
		prepare_import_document(doc)
		doc.run_before_save_methods()
		doc._validate()
	finally:
		doc.flags.in_insert = False
		frappe.db.rollback(save_point=savepoint)
		frappe.flags.in_bimap_data_engine_preview = previous
	return doc


def _serialized_invoice(doc):
	return {
		"doctype": doc.doctype,
		"name": None,
		"supplier": doc.supplier,
		"company": doc.company,
		"posting_date": doc.posting_date,
		"bill_no": doc.bill_no,
		"currency": doc.currency,
		"bimap_cfdi_uuid": doc.bimap_cfdi_uuid,
		"items": [{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"description": row.description,
			"qty": row.qty,
			"uom": row.uom,
			"rate": row.rate,
			"amount": row.amount,
			"expense_account": row.expense_account,
		} for row in doc.items],
		"taxes": [{
			"description": row.description,
			"account_head": row.account_head,
			"rate": row.rate,
			"tax_amount": row.tax_amount,
		} for row in doc.taxes],
		"net_total": doc.net_total,
		"total_taxes_and_charges": doc.total_taxes_and_charges,
		"grand_total": doc.grand_total,
	}


def _payment_key(uuid, payment_index):
	return f"{cstr(uuid).upper()}#{int(payment_index)}"


def _serialized_payment(doc):
	return {
		"doctype": doc.doctype,
		"name": None,
		"company": doc.company,
		"party_type": doc.party_type,
		"party": doc.party,
		"posting_date": doc.posting_date,
		"payment_type": doc.payment_type,
		"paid_from": doc.paid_from,
		"paid_to": doc.paid_to,
		"paid_amount": doc.paid_amount,
		"received_amount": doc.received_amount,
		"bimap_cfdi_uuid": doc.bimap_cfdi_uuid,
		"bimap_cfdi_payment_index": doc.bimap_cfdi_payment_index,
		"references": [{
			"reference_doctype": row.reference_doctype,
			"reference_name": row.reference_name,
			"bill_no": row.bill_no,
			"total_amount": row.total_amount,
			"outstanding_amount": row.outstanding_amount,
			"allocated_amount": row.allocated_amount,
		} for row in doc.references],
	}


def _reference_copy(row, allocated_amount):
	values = row.as_dict(no_nulls=True)
	for field in ("name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "idx", "doctype", "docstatus"):
		values.pop(field, None)
	values["allocated_amount"] = allocated_amount
	return values


def _payment_entries(parsed, file_url, options, issues):
	frappe.has_permission("Payment Entry", "create", throw=True)
	uuid = cstr(parsed.get("uuid")).upper()
	if not uuid:
		issues.append(_issue("missing_uuid", "El complemento de pago no contiene UUID."))
		return []
	documents_by_payment = {}
	for source in parsed.get("payment_documents") or []:
		documents_by_payment.setdefault(int(source.get("Pago") or 0), []).append(source)
	entries = []
	for payment in parsed.get("payments") or []:
		payment_index = int(payment.get("Pago") or 0)
		key = _payment_key(uuid, payment_index)
		duplicate = frappe.db.get_value("Payment Entry", {"bimap_cfdi_payment_key": key}, "name")
		if duplicate:
			issues.append(_issue(
				"duplicate_cfdi_payment",
				f"El pago {payment_index} del CFDI ya está registrado en Payment Entry {duplicate}.",
				target_field="bimap_cfdi_payment_key",
			))
			continue
		related = documents_by_payment.get(payment_index) or []
		if not related:
			issues.append(_issue("payment_without_documents", f"El pago {payment_index} no contiene documentos relacionados."))
			continue
		templates = []
		expected_company = None
		expected_supplier = None
		allocated_total = Decimal("0")
		for document_index, source in enumerate(related, start=1):
			related_uuid = cstr(source.get("IdDocumento")).upper()
			invoice_name = frappe.db.get_value("Purchase Invoice", {"bimap_cfdi_uuid": related_uuid}, "name")
			if not invoice_name:
				issues.append(_issue(
					"related_invoice_not_found",
					f"No existe una Purchase Invoice con UUID {related_uuid}.",
					row=document_index + 1, source_field="IdDocumento", target_field="reference_name",
				))
				continue
			invoice = frappe.get_doc("Purchase Invoice", invoice_name)
			invoice.check_permission("read")
			if invoice.docstatus != 1:
				issues.append(_issue(
					"related_invoice_not_submitted",
					f"La factura {invoice.name} debe estar enviada antes de conciliar un pago.",
					row=document_index + 1, source_field="IdDocumento", target_field="reference_name",
				))
				continue
			if expected_company and invoice.company != expected_company or expected_supplier and invoice.supplier != expected_supplier:
				issues.append(_issue(
					"mixed_payment_parties",
					"Un mismo pago CFDI no puede mezclar empresas o proveedores.",
					row=document_index + 1, source_field="IdDocumento",
				))
				continue
			expected_company = invoice.company
			expected_supplier = invoice.supplier
			allocated = Decimal(cstr(source.get("ImpPagado") or 0))
			if allocated <= 0 or allocated - Decimal(cstr(invoice.outstanding_amount or 0)) > TOTAL_TOLERANCE:
				issues.append(_issue(
					"invalid_payment_allocation",
					f"El importe {allocated} no es válido para el saldo {invoice.outstanding_amount} de {invoice.name}.",
					row=document_index + 1, source_field="ImpPagado", target_field="allocated_amount",
				))
				continue
			try:
				template = get_payment_entry(
					"Purchase Invoice", invoice.name,
					bank_account=options.get("bank_account"),
					reference_date=_date(payment.get("FechaPago")),
				)
			except Exception as exc:
				issues.append(_issue("native_payment_setup", exc, row=document_index + 1))
				frappe.clear_messages()
				continue
			if not template.references:
				issues.append(_issue("missing_native_reference", f"ERPNext no devolvió referencia para {invoice.name}."))
				continue
			templates.append((template, _reference_copy(template.references[0], float(allocated))))
			allocated_total += allocated
		amount = Decimal(cstr(payment.get("Monto") or 0))
		if abs(allocated_total - amount) > TOTAL_TOLERANCE:
			issues.append(_issue(
				"payment_total_mismatch",
				f"El pago {payment_index} declara {amount} pero sus documentos suman {allocated_total}.",
				source_field="Monto", target_field="paid_amount",
			))
			continue
		if not templates:
			continue
		supplier_rfc = _rfc(frappe.get_cached_value("Supplier", expected_supplier, "tax_id"))
		company_rfc = _rfc(frappe.get_cached_value("Company", expected_company, "tax_id"))
		if supplier_rfc and supplier_rfc != _rfc(parsed["emitter"].get("Rfc")):
			issues.append(_issue(
				"payment_supplier_rfc_mismatch",
				f"El emisor del complemento no corresponde al proveedor {expected_supplier}.",
				source_field="Emisor.Rfc",
			))
			continue
		if company_rfc and company_rfc != _rfc(parsed["receiver"].get("Rfc")):
			issues.append(_issue(
				"payment_company_rfc_mismatch",
				f"El receptor del complemento no corresponde a la empresa {expected_company}.",
				source_field="Receptor.Rfc",
			))
			continue
		pe = templates[0][0]
		pe.set("references", [])
		for _template, reference in templates:
			pe.append("references", reference)
		pe.posting_date = _date(payment.get("FechaPago"))
		pe.reference_date = pe.posting_date
		pe.reference_no = f"{uuid}/{payment_index}"
		pe.paid_amount = float(amount)
		pe.received_amount = float(amount)
		mode_map = options.get("mode_of_payment_map") or {}
		pe.mode_of_payment = mode_map.get(payment.get("FormaDePagoP")) or options.get("mode_of_payment") or pe.mode_of_payment
		pe.bimap_cfdi_uuid = uuid
		pe.bimap_cfdi_payment_index = payment_index
		pe.bimap_cfdi_payment_key = key
		pe.bimap_cfdi_file = file_url
		pe.set_missing_ref_details(force=True)
		pe.set_amounts()
		entries.append(pe)
	return entries


def _preview_payment(parsed, file_url, options, issues):
	entries = _payment_entries(parsed, file_url, options, issues)
	if not any(issue["severity"] == "error" for issue in issues):
		for index, doc in enumerate(entries, start=1):
			try:
				_prepare_candidate(doc)
			except Exception as exc:
				issues.append(_issue("native_payment_validation", f"Pago {index}: {exc}"))
				frappe.clear_messages()
	return {
		"valid": bool(entries) and not any(issue["severity"] == "error" for issue in issues),
		"document_type": "payment",
		"uuid": parsed.get("uuid"),
		"issues": issues,
		"documents": [_serialized_payment(doc) for doc in entries],
		"document": _serialized_payment(entries[0]) if entries else None,
	}


def preview_cfdi_document(file_url, options=None):
	parsed, _file_doc = load_attached_cfdi(file_url)
	options = _options(options)
	issues = [_issue("cfdi_warning", warning, severity="warning") for warning in parsed.get("warnings") or []]
	if parsed.get("document_type") == "payment":
		return _preview_payment(parsed, file_url, options, issues)
	doc = _purchase_invoice(parsed, file_url, options, issues)
	if doc and not any(issue["severity"] == "error" for issue in issues):
		try:
			_prepare_candidate(doc)
		except Exception as exc:
			issues.append(_issue("native_validation", exc))
			frappe.clear_messages()
	if doc and doc.get("grand_total") is not None:
		expected = Decimal(cstr(parsed["header"].get("Total") or 0))
		actual = Decimal(cstr(doc.grand_total or 0))
		if abs(expected - actual) > TOTAL_TOLERANCE:
			issues.append(_issue(
				"total_mismatch",
				f"ERPNext calculó {actual} y el CFDI declara {expected}. Revisa impuestos, artículos y cuentas antes de crear.",
				target_field="grand_total",
			))
	return {
		"valid": not any(issue["severity"] == "error" for issue in issues),
		"document_type": "invoice",
		"uuid": parsed.get("uuid"),
		"issues": issues,
		"document": _serialized_invoice(doc) if doc else None,
		"documents": [_serialized_invoice(doc)] if doc else [],
	}


def create_cfdi_draft(file_url, options=None, operation_id=None):
	preview = preview_cfdi_document(file_url, options)
	if not preview["valid"]:
		frappe.throw("El CFDI contiene errores; corrige el preview antes de crear el borrador.")
	parsed, file_doc = load_attached_cfdi(file_url)
	file_doc.check_permission("write")
	if parsed.get("document_type") == "payment":
		docs = _payment_entries(parsed, file_url, _options(options), [])
	else:
		docs = [_purchase_invoice(parsed, file_url, _options(options), [])]
	operation_id = cstr(operation_id).strip() or frappe.generate_hash(length=20)
	created = []
	for doc in docs:
		if doc.doctype == "Purchase Invoice":
			prepare_import_document(doc)
		doc.insert()
		record_changes(operation_id, doc.doctype, doc.name, [{
			"operation": "insert",
			"value": {"source": "CFDI", "uuid": parsed.get("uuid"), "file_url": file_url},
		}])
		created.append({"doctype": doc.doctype, "name": doc.name})
	if created:
		file_doc.db_set({"attached_to_doctype": created[0]["doctype"], "attached_to_name": created[0]["name"]}, update_modified=False)
	return {
		**created[0], "uuid": parsed.get("uuid"), "operation_id": operation_id,
		"documents": created,
	}
