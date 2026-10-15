"""Idempotent navigation entries for BIMAP Data Engine."""

from __future__ import annotations

import json

import frappe


DATA_ENGINE_LABEL = "BIMAP Data Engine"
DATA_ENGINE_PAGE = "bimap-data-engine"
BUYING_WORKSPACE = "Buying"
BUYING_BLOCK_ID = "bimap-data-engine-buying-shortcut"


def sync_buying_workspace():
	"""Expose Data Engine in Buying without replacing native workspace content."""
	if not frappe.db.exists("Page", DATA_ENGINE_PAGE) or not frappe.db.exists("Workspace", BUYING_WORKSPACE):
		return False

	workspace = frappe.get_doc("Workspace", BUYING_WORKSPACE)
	changed = False
	shortcut = next((row for row in workspace.shortcuts if row.label == DATA_ENGINE_LABEL), None)
	if not shortcut:
		shortcut = workspace.append("shortcuts", {})
		changed = True

	desired = {
		"type": "Page",
		"link_to": DATA_ENGINE_PAGE,
		"url": None,
		"label": DATA_ENGINE_LABEL,
		"color": "Orange",
	}
	for fieldname, value in desired.items():
		if shortcut.get(fieldname) != value:
			shortcut.set(fieldname, value)
			changed = True

	content = frappe.parse_json(workspace.content or "[]")
	block = next(
		(
			entry for entry in content
			if entry.get("id") == BUYING_BLOCK_ID
			or (
				entry.get("type") == "shortcut"
				and entry.get("data", {}).get("shortcut_name") == DATA_ENGINE_LABEL
			)
		),
		None,
	)
	desired_data = {"shortcut_name": DATA_ENGINE_LABEL, "col": 3}
	if block:
		if block.get("id") != BUYING_BLOCK_ID or block.get("data") != desired_data:
			block["id"] = BUYING_BLOCK_ID
			block["type"] = "shortcut"
			block["data"] = desired_data
			changed = True
	else:
		block = {"id": BUYING_BLOCK_ID, "type": "shortcut", "data": desired_data}
		first_shortcut = next(
			(index for index, entry in enumerate(content) if entry.get("type") == "shortcut"),
			len(content),
		)
		content.insert(first_shortcut, block)
		changed = True

	serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
	if workspace.content != serialized:
		workspace.content = serialized
		changed = True

	if not changed:
		return False

	# Avoid exporting this ERPNext-owned standard Workspace into its source app.
	was_migrating = getattr(frappe.flags, "in_migrate", False)
	frappe.flags.in_migrate = True
	try:
		workspace.save(ignore_permissions=True)
	finally:
		frappe.flags.in_migrate = was_migrating
	return True
