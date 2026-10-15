"""Generic multi-sheet import plans with explicit dependency graphs."""

import json
import re
from collections import defaultdict

import frappe
from frappe.model import table_fields
from frappe.utils import cint, cstr

from bimap_data_engine.services.audit import record_changes
from bimap_data_engine.services.adapters import prepare_import_document
from bimap_data_engine.services.jobs import _json, _validated_batch_size, insert_job_records
from bimap_data_engine.services.mapping import map_row, validate_mapping
from bimap_data_engine.services.metadata import writable_fieldnames
from bimap_data_engine.services.native_mappers import get_native_mapper, make_related_document
from bimap_data_engine.services.policies import validate_import_policies


NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_IMPORT_RECORDS = 100_000
MAX_INCREMENTAL_ROWS = 10_000
MAX_PREVIEW_REQUEST_BYTES = 30 * 1024 * 1024


def _issue(*, node, sheet, row, message, source_field=None, target_field=None, code="validation"):
	"""Return a stable, cell-addressable issue while preserving the legacy error key."""
	return {
		"node": node,
		"sheet": sheet,
		"row": row,
		"source_field": source_field,
		"target_field": target_field,
		"severity": "error",
		"code": code,
		"message": cstr(message),
		"error": cstr(message),
	}


def _mapped_error_location(doctype, mapping, exc):
	"""Best-effort projection of a native ERPNext error back to its source column."""
	message = cstr(exc)
	message_lower = message.lower()
	meta = frappe.get_meta(doctype)
	for entry in mapping or []:
		target = cstr(entry.get("target")).strip()
		df = meta.get_field(target) if target else None
		needles = [target.lower()]
		if df and df.label:
			needles.append(cstr(df.label).lower())
		if any(needle and needle in message_lower for needle in needles):
			return entry.get("source"), target
	return None, getattr(exc, "fieldname", None)


def _object(value, label):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(value, dict):
		frappe.throw(f"{label}: formato inválido.")
	return value


def _selection_by_node(selection, node_ids):
	if selection is None:
		return None
	selection = frappe.parse_json(selection) if isinstance(selection, str) else selection
	if not isinstance(selection, list):
		frappe.throw("Selección incremental: formato inválido.")
	result = defaultdict(set)
	for entry in selection:
		if not isinstance(entry, dict) or entry.get("node") not in node_ids:
			frappe.throw("Selección incremental: nodo inválido.")
		row = cint(entry.get("row"))
		if row < 2:
			frappe.throw("Selección incremental: fila inválida.")
		result[entry["node"]].add(row)
	if sum(len(rows) for rows in result.values()) > MAX_INCREMENTAL_ROWS:
		frappe.throw(f"La revalidación incremental excede {MAX_INCREMENTAL_ROWS} filas.")
	return result


def _topological_nodes(nodes):
	by_id = {node.get("id"): node for node in nodes if isinstance(node, dict)}
	if len(by_id) != len(nodes) or any(not NODE_ID_PATTERN.fullmatch(cstr(node_id)) for node_id in by_id):
		frappe.throw("Cada nodo requiere un id único en minúsculas.")
	dependencies = {node_id: set() for node_id in by_id}
	for node_id, node in by_id.items():
		for reference in node.get("references") or []:
			target_node = reference.get("node")
			if target_node not in by_id:
				frappe.throw(f"Nodo {node_id}: dependencia inexistente {target_node}.")
			if target_node == node_id:
				frappe.throw(f"Nodo {node_id}: no puede depender de sí mismo.")
			dependencies[node_id].add(target_node)
	ordered = []
	remaining = {node_id: set(values) for node_id, values in dependencies.items()}
	while remaining:
		ready = [node_id for node_id, values in remaining.items() if not values]
		if not ready:
			frappe.throw("El grafo de importación contiene un ciclo.")
		for node_id in ready:
			ordered.append(by_id[node_id])
			remaining.pop(node_id)
		for values in remaining.values():
			values.difference_update(ready)
	return ordered


def _sheet_map(workbook):
	workbook = _object(workbook, "Libro")
	sheets = workbook.get("sheets")
	if not isinstance(sheets, list):
		frappe.throw("El libro no contiene hojas.")
	result = {}
	for sheet in sheets:
		if not isinstance(sheet, dict) or not sheet.get("name") or not isinstance(sheet.get("rows"), list):
			frappe.throw("El libro contiene una hoja inválida.")
		if sheet["name"] in result:
			frappe.throw(f"Hoja repetida: {sheet['name']}.")
		result[sheet["name"]] = sheet
	return result


def _validate_references(node, node_ids):
	meta = frappe.get_meta(node["doctype"])
	allowed = writable_fieldnames(meta)
	validated = []
	for index, reference in enumerate(node.get("references") or [], start=1):
		if not isinstance(reference, dict):
			frappe.throw(f"Nodo {node['id']}, referencia {index}: formato inválido.")
		source = cstr(reference.get("source")).strip()
		target = cstr(reference.get("target")).strip()
		target_node = cstr(reference.get("node")).strip()
		df = meta.get_field(target)
		if not source or target_node not in node_ids or not df or target not in allowed:
			frappe.throw(f"Nodo {node['id']}, referencia {index}: configuración inválida.")
		if df.fieldtype not in {"Link", "Dynamic Link"}:
			frappe.throw(f"Nodo {node['id']}: {target} no es una referencia Link.")
		validated.append({"source": source, "target": target, "node": target_node})
	return validated


def _children_by_parent(
	node, sheets, parent_keys, errors, *, active_parent_keys=None, report_orphans=True
):
	children_by_key = defaultdict(lambda: defaultdict(list))
	for child_spec in node.get("children") or []:
		if not isinstance(child_spec, dict):
			frappe.throw(f"Nodo {node['id']}: configuración hija inválida.")
		table_field = cstr(child_spec.get("table_field")).strip()
		sheet_name = child_spec.get("sheet")
		parent_key_field = child_spec.get("parent_key")
		if sheet_name not in sheets or not parent_key_field:
			frappe.throw(f"Nodo {node['id']}: hoja o clave padre hija inválida.")
		validate_mapping(
			node["doctype"], child_spec.get("mapping"), child_spec.get("defaults"), table_field
		)
		for row_number, row in enumerate(sheets[sheet_name]["rows"], start=2):
			parent_key = cstr(row.get(parent_key_field)).strip()
			if not parent_key or parent_key not in parent_keys:
				if report_orphans:
					errors.append(_issue(
						node=node["id"], sheet=sheet_name, row=row_number,
						source_field=parent_key_field, code="orphan_child",
						message=f"Fila hija sin padre válido: {parent_key or '(vacío)' }.",
					))
				continue
			if active_parent_keys is not None and parent_key not in active_parent_keys:
				continue
			try:
				values = map_row(
					node["doctype"], row, child_spec.get("mapping"), child_spec.get("defaults"), table_field
				)
				children_by_key[parent_key][table_field].append(values)
			except Exception as exc:
				source_field, target_field = _mapped_error_location(
					node["doctype"], child_spec.get("mapping"), exc
				)
				errors.append(_issue(
					node=node["id"], sheet=sheet_name, row=row_number,
					source_field=source_field, target_field=target_field,
					message=exc, code="child_mapping",
				))
				frappe.clear_messages()
	return children_by_key


def _candidate_document(payload):
	native_source = payload.get("native_source")
	if native_source:
		doc = make_related_document(
			native_source["doctype"], native_source["name"], payload["doctype"],
			args=native_source.get("args"),
		)
		doc.update(payload["values"])
	else:
		values = {"doctype": payload["doctype"], **payload["values"]}
		doc = frappe.get_doc(values)
	for table_field, rows in payload.get("children", {}).items():
		for row in rows:
			doc.append(table_field, row)
	return doc


def _validate_submit_mode(doctype, submit):
	if not submit:
		return
	if not frappe.get_meta(doctype).is_submittable:
		frappe.throw(f"{doctype} no admite el estado Enviado.")
	frappe.has_permission(doctype, "submit", throw=True)


def _validate_native_candidate(payload):
	"""Validate a new independent document and rollback validation side effects."""
	doc = _candidate_document(payload)
	doc.check_permission("create")
	savepoint = f"bde_import_preview_{frappe.generate_hash(length=10)}"
	previous_flag = getattr(frappe.flags, "in_bimap_data_engine_preview", False)
	frappe.db.savepoint(savepoint)
	try:
		frappe.flags.in_bimap_data_engine_preview = True
		if payload.get("submit"):
			prepare_import_document(doc)
			doc.insert()
			doc.submit()
			return
		doc.set("__islocal", True)
		doc._action = "save"
		doc._set_defaults()
		doc.set_user_and_timestamp()
		doc.set_docstatus()
		doc.check_if_latest()
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
		doc.set_docstatus()
	finally:
		doc.flags.in_insert = False
		frappe.db.rollback(save_point=savepoint)
		frappe.flags.in_bimap_data_engine_preview = previous_flag


def build_import_plan(workbook, specification, selection=None):
	"""Map source sheets into ordered, explicit parent document payloads."""
	sheets = _sheet_map(workbook)
	specification = _object(specification, "Especificación")
	nodes = specification.get("nodes")
	if not isinstance(nodes, list) or not nodes:
		frappe.throw("La especificación requiere al menos un nodo.")
	ordered_nodes = _topological_nodes(nodes)
	node_ids = {node["id"] for node in ordered_nodes}
	selected_rows = _selection_by_node(selection, node_ids)
	errors = []
	records = []
	node_summary = []
	for node in ordered_nodes:
		doctype = cstr(node.get("doctype")).strip()
		sheet_name = node.get("sheet")
		external_key_field = node.get("external_key")
		if not doctype or sheet_name not in sheets or not external_key_field:
			frappe.throw(f"Nodo {node['id']}: DocType, hoja o clave externa inválida.")
		frappe.has_permission(doctype, "create", throw=True)
		submit = bool(cint(node.get("submit")))
		_validate_submit_mode(doctype, submit)
		validate_mapping(doctype, node.get("mapping"), node.get("defaults"))
		references = _validate_references(node, node_ids)
		native_source_spec = node.get("native_source")
		if native_source_spec:
			if not isinstance(native_source_spec, dict):
				frappe.throw(f"Nodo {node['id']}: origen nativo inválido.")
			source_doctype = cstr(native_source_spec.get("doctype")).strip()
			source_field = cstr(native_source_spec.get("source")).strip()
			if not source_doctype or not source_field:
				frappe.throw(f"Nodo {node['id']}: origen nativo incompleto.")
			get_native_mapper(source_doctype, doctype)
			if node.get("children"):
				frappe.throw(
					f"Nodo {node['id']}: una conversión nativa no admite partidas externas todavía."
				)
		parent_rows = sheets[sheet_name]["rows"]
		keys = [cstr(row.get(external_key_field)).strip() for row in parent_rows]
		key_counts = defaultdict(int)
		for key in keys:
			if key:
				key_counts[key] += 1
		rows_in_scope = selected_rows.get(node["id"], set()) if selected_rows is not None else None
		if rows_in_scope is not None and any(row > len(parent_rows) + 1 for row in rows_in_scope):
			frappe.throw(f"Nodo {node['id']}: la selección contiene una fila inexistente.")
		valid_parent_keys = {key for key, count in key_counts.items() if count == 1}
		active_parent_keys = None
		if rows_in_scope is not None:
			active_parent_keys = {
				keys[row_number - 2]
				for row_number in rows_in_scope
				if row_number <= len(parent_rows) + 1 and keys[row_number - 2] in valid_parent_keys
			}
		children_by_key = _children_by_parent(
			node, sheets, valid_parent_keys, errors,
			active_parent_keys=active_parent_keys,
			report_orphans=rows_in_scope is None,
		)
		valid_count = 0
		for row_number, (external_key, row) in enumerate(zip(keys, parent_rows, strict=True), start=2):
			if rows_in_scope is not None and row_number not in rows_in_scope:
				continue
			if not external_key:
				errors.append(_issue(
					node=node["id"], sheet=sheet_name, row=row_number,
					source_field=external_key_field, code="missing_external_key",
					message="La clave externa es obligatoria.",
				))
				continue
			if key_counts[external_key] > 1:
				errors.append(_issue(
					node=node["id"], sheet=sheet_name, row=row_number,
					source_field=external_key_field, code="duplicate_external_key",
					message=f"La clave externa {external_key} está repetida.",
				))
				continue
			try:
				values = map_row(doctype, row, node.get("mapping"), node.get("defaults"))
				native_source = None
				if native_source_spec:
					source_name = cstr(row.get(native_source_spec["source"])).strip()
					if not source_name:
						frappe.throw("El documento origen de la conversión nativa está vacío.")
					native_source = {
						"doctype": native_source_spec["doctype"],
						"name": source_name,
						"args": native_source_spec.get("args") or {},
					}
				resolved_references = []
				for reference in references:
					reference_key = cstr(row.get(reference["source"])).strip()
					if not reference_key:
						frappe.throw(f"Referencia vacía para {reference['target']}.")
					resolved_references.append({**reference, "external_key": reference_key})
					values.pop(reference["target"], None)
				payload = {
					"node_id": node["id"],
					"external_key": external_key,
					"doctype": doctype,
					"values": values,
					"children": dict(children_by_key.get(external_key, {})),
					"references": resolved_references,
					"source_sheet": sheet_name,
					"source_row": row_number,
					"native_source": native_source,
					"submit": submit,
				}
				policy_errors = validate_import_policies(payload)
				if policy_errors:
					frappe.throw("; ".join(policy_errors))
				if not resolved_references:
					_validate_native_candidate(payload)
				records.append(payload)
				valid_count += 1
			except Exception as exc:
				source_field, target_field = _mapped_error_location(doctype, node.get("mapping"), exc)
				errors.append(_issue(
					node=node["id"], sheet=sheet_name, row=row_number,
					source_field=source_field, target_field=target_field,
					message=exc,
				))
				frappe.clear_messages()
		node_summary.append({
			"id": node["id"], "doctype": doctype, "rows": len(parent_rows),
			"validated_rows": len(rows_in_scope) if rows_in_scope is not None else len(parent_rows),
			"valid_rows": valid_count,
		})
	if len(records) > MAX_IMPORT_RECORDS:
		frappe.throw(f"El plan excede {MAX_IMPORT_RECORDS} documentos.")
	return {
		"valid": not errors,
		"records": records,
		"errors": errors,
		"nodes": node_summary,
		"scope": {
			"partial": selected_rows is not None,
			"rows": [
				{"node": node_id, "row": row}
				for node_id, rows in (selected_rows or {}).items()
				for row in sorted(rows)
			],
		},
	}


def revalidate_import_rows(workbook, specification, selection):
	"""Validate only changed parent rows; complex child graphs safely fall back to a full preview."""
	specification = _object(specification, "Especificación")
	nodes = specification.get("nodes") or []
	selection_value = frappe.parse_json(selection) if isinstance(selection, str) else selection
	selected_node_ids = {
		entry.get("node") for entry in (selection_value or []) if isinstance(entry, dict)
	}
	selected_nodes = [node for node in nodes if node.get("id") in selected_node_ids]
	if not selected_nodes or any(node.get("children") for node in selected_nodes):
		return build_import_plan(workbook, specification)
	return build_import_plan(workbook, specification, selection=selection_value)


def _preview_structure_plan(workbook, specification, node_id):
	"""Return orphan child issues once per node, outside per-parent preview records."""
	sheets = _sheet_map(workbook)
	nodes = _object(specification, "Especificación").get("nodes") or []
	node = next((candidate for candidate in nodes if candidate.get("id") == node_id), None)
	if not node:
		frappe.throw("El nodo estructural del preview no existe.")
	parent_rows = sheets[node["sheet"]]["rows"]
	keys = [cstr(row.get(node["external_key"])).strip() for row in parent_rows]
	counts = defaultdict(int)
	for key in keys:
		if key:
			counts[key] += 1
	valid_keys = {key for key, count in counts.items() if count == 1}
	errors = []
	_children_by_parent(
		node, sheets, valid_keys, errors, active_parent_keys=set(), report_orphans=True
	)
	return {
		"valid": not errors,
		"records": [],
		"errors": errors,
		"nodes": [],
		"scope": {"partial": True, "rows": []},
	}


def create_preview_job(workbook, specification, *, batch_size=50):
	"""Persist raw preview work without synchronously running native document validation."""
	workbook = _object(workbook, "Libro")
	sheets = _sheet_map(workbook)
	specification = _object(specification, "Especificación")
	nodes = specification.get("nodes")
	if not isinstance(nodes, list) or not nodes:
		frappe.throw("La especificación requiere al menos un nodo.")
	ordered_nodes = _topological_nodes(nodes)
	node_ids = {node["id"] for node in ordered_nodes}
	records = []
	sequence = 0
	for node in ordered_nodes:
		doctype = cstr(node.get("doctype")).strip()
		sheet_name = node.get("sheet")
		external_key_field = node.get("external_key")
		if not doctype or sheet_name not in sheets or not external_key_field:
			frappe.throw(f"Nodo {node['id']}: DocType, hoja o clave externa inválida.")
		frappe.has_permission(doctype, "create", throw=True)
		_validate_submit_mode(doctype, bool(cint(node.get("submit"))))
		validate_mapping(doctype, node.get("mapping"), node.get("defaults"))
		_validate_references(node, node_ids)
		native_source_spec = node.get("native_source")
		if native_source_spec:
			if not isinstance(native_source_spec, dict):
				frappe.throw(f"Nodo {node['id']}: origen nativo inválido.")
			source_doctype = cstr(native_source_spec.get("doctype")).strip()
			source_field = cstr(native_source_spec.get("source")).strip()
			if not source_doctype or not source_field:
				frappe.throw(f"Nodo {node['id']}: origen nativo incompleto.")
			get_native_mapper(source_doctype, doctype)
			if node.get("children"):
				frappe.throw(
					f"Nodo {node['id']}: una conversión nativa no admite partidas externas todavía."
				)
		for child_spec in node.get("children") or []:
			validate_mapping(
				doctype, child_spec.get("mapping"), child_spec.get("defaults"),
				child_spec.get("table_field"),
			)
		parent_rows = sheets[sheet_name]["rows"]
		for row_number, row in enumerate(parent_rows, start=2):
			sequence += 1
			records.append({
				"sequence": sequence,
				"node_id": node["id"],
				"external_key": cstr(row.get(external_key_field)).strip(),
				"reference_doctype": doctype,
				"changes_json": _json({"kind": "document", "node": node["id"], "row": row_number}),
			})
		if node.get("children"):
			sequence += 1
			records.append({
				"sequence": sequence,
				"node_id": node["id"],
				"external_key": "__structure__",
				"reference_doctype": doctype,
				"changes_json": _json({"kind": "structure", "node": node["id"]}),
			})
	if not records:
		frappe.throw("El preview no contiene filas para validar.")
	if len(records) > MAX_IMPORT_RECORDS:
		frappe.throw(f"El preview excede {MAX_IMPORT_RECORDS} unidades de validación.")
	request_json = _json({"workbook": workbook, "specification": specification})
	if len(request_json.encode("utf-8")) > MAX_PREVIEW_REQUEST_BYTES:
		frappe.throw("La solicitud de preview excede 30 MB.")
	batch_size = _validated_batch_size(batch_size)
	job = frappe.get_doc({
		"doctype": "BIMAP Data Job",
		"status": "Draft",
		"job_type": "Preview",
		"requested_by": frappe.session.user,
		"operation_id": frappe.generate_hash(length=20),
		"batch_size": batch_size,
		"total_documents": len(records),
		"request_json": request_json,
	}).insert(ignore_permissions=True)
	insert_job_records(job.name, records)
	job.db_set("status", "Queued", update_modified=True)
	return job.name


def apply_preview_record(job, record):
	request = json.loads(job.request_json)
	address = json.loads(record.changes_json)
	if address.get("kind") == "structure":
		return _preview_structure_plan(
			request["workbook"], request["specification"], address["node"]
		)
	return build_import_plan(
		request["workbook"], request["specification"],
		selection=[{"node": address["node"], "row": address["row"]}],
	)


def create_import_job(plan, *, batch_size=50, valid_only=False):
	plan = _object(plan, "Plan")
	records = plan.get("records")
	if not isinstance(records, list) or not records:
		frappe.throw("El plan no contiene registros válidos.")
	if plan.get("errors") and not valid_only:
		frappe.throw("El plan contiene errores; confirma valid_only para ejecutar sólo registros válidos.")
	batch_size = _validated_batch_size(batch_size)
	job = frappe.get_doc(
		{
			"doctype": "BIMAP Data Job",
			"status": "Draft",
			"job_type": "Import",
			"requested_by": frappe.session.user,
			"operation_id": frappe.generate_hash(length=20),
			"batch_size": batch_size,
			"total_documents": len(records),
		}
	).insert(ignore_permissions=True)
	for payload in records:
		frappe.has_permission(payload["doctype"], "create", throw=True)
		_validate_submit_mode(payload["doctype"], bool(payload.get("submit")))
	insert_job_records(
		job.name,
		(
			{
				"sequence": sequence,
				"node_id": payload["node_id"],
				"external_key": payload["external_key"],
				"reference_doctype": payload["doctype"],
				"changes_json": _json(payload),
				"dependencies_json": _json(payload.get("references") or []),
			}
			for sequence, payload in enumerate(records, start=1)
		),
	)
	job.db_set("status", "Queued", update_modified=True)
	return job.name


def apply_import_record(job, record):
	payload = json.loads(record.changes_json)
	for reference in payload.get("references") or []:
		result_document = frappe.db.get_value(
			"BIMAP Data Job Record",
			{
				"job": job.name,
				"node_id": reference["node"],
				"external_key": reference["external_key"],
				"status": "Success",
			},
			"result_document",
		)
		if not result_document:
			frappe.throw(
				f"Dependencia no resuelta: {reference['node']}:{reference['external_key']}."
			)
		payload["values"][reference["target"]] = result_document
	doc = _candidate_document(payload)
	prepare_import_document(doc)
	doc.insert()
	if payload.get("submit"):
		_validate_submit_mode(doc.doctype, True)
		doc.submit()
	record_changes(
		job.operation_id,
		doc.doctype,
		doc.name,
		[{"operation": "insert", "value": {
			"values": payload["values"], "children": payload.get("children"),
			"lifecycle": "Submitted" if payload.get("submit") else "Draft",
		}}],
	)
	return {"doctype": doc.doctype, "document_name": doc.name, "external_key": payload["external_key"]}
