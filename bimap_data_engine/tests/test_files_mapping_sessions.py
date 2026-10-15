import io
import uuid

import frappe
from frappe.tests.utils import FrappeTestCase
from openpyxl import Workbook

from bimap_data_engine.services.files import parse_file_bytes
from bimap_data_engine.services.mapping import map_row, suggest_mapping, validate_mapping
from bimap_data_engine.services.sessions import (
	get_mapping_profile,
	get_session,
	save_mapping_profile,
	save_session,
)


class TestFilesMappingAndSessions(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_csv_parser_handles_utf8_and_ignores_empty_rows(self):
		result = parse_file_bytes(
			"items.csv",
			"Código,Descripción\nITEM-1, Uno \n,\nITEM-2,Dos\n".encode(),
		)
		sheet = result["sheets"][0]
		self.assertEqual(result["format"], "CSV")
		self.assertEqual(sheet["headers"], ["Código", "Descripción"])
		self.assertEqual(sheet["row_count"], 2)
		self.assertEqual(sheet["rows"][0]["Descripción"], "Uno")

	def test_xlsx_parser_reads_multiple_sheets(self):
		workbook = Workbook()
		items = workbook.active
		items.title = "Items"
		items.append(["Code", "Description"])
		items.append(["ITEM-1", "One"])
		barcodes = workbook.create_sheet("Barcodes")
		barcodes.append(["Item", "Barcode"])
		barcodes.append(["ITEM-1", "ABC"])
		buffer = io.BytesIO()
		workbook.save(buffer)
		result = parse_file_bytes("book.xlsx", buffer.getvalue())
		self.assertEqual([sheet["name"] for sheet in result["sheets"]], ["Items", "Barcodes"])
		self.assertEqual(result["sheets"][1]["rows"][0]["Barcode"], "ABC")

	def test_duplicate_headers_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			parse_file_bytes("bad.csv", b"Code,Code\nA,B\n")

	def test_mapping_suggestion_and_declarative_transforms(self):
		suggestions = suggest_mapping("Item", ["Description", "Stock UOM"])
		by_source = {entry["source"]: entry for entry in suggestions}
		self.assertEqual(by_source["Description"]["target"], "description")
		mapped = map_row(
			"Item",
			{"Description": "  mixed Case  ", "Disabled": "1"},
			[
				{"source": "Description", "target": "description", "transform": "trim"},
				{"source": "Disabled", "target": "disabled"},
			],
			{"is_stock_item": 0},
		)
		self.assertEqual(mapped["description"], "mixed Case")
		self.assertEqual(mapped["disabled"], 1)
		self.assertEqual(mapped["is_stock_item"], 0)

	def test_empty_import_cell_does_not_override_default(self):
		mapped = map_row(
			"Item",
			{"Description": ""},
			[{"source": "Description", "target": "description"}],
			{"description": "Valor predeterminado"},
		)
		self.assertEqual(mapped["description"], "Valor predeterminado")

	def test_mapping_rejects_system_fields_and_arbitrary_transforms(self):
		with self.assertRaises(frappe.ValidationError):
			validate_mapping("Item", [{"source": "Modified", "target": "modified"}])
		with self.assertRaises(frappe.ValidationError):
			validate_mapping(
				"Item",
				[{"source": "Description", "target": "description", "transform": "python"}],
			)

	def test_mapping_profiles_are_reusable_and_sessions_round_trip(self):
		profile = save_mapping_profile(
			"Item descriptions",
			"Item",
			[{"source": "Description", "target": "description", "transform": "trim"}],
			{"disabled": 0},
			source_format="CSV",
		)
		loaded_profile = get_mapping_profile(profile["name"])
		self.assertEqual(loaded_profile["mapping"][0]["target"], "description")

		state = {
			"fields": ["description"],
			"filters": {"disabled": 0},
			"pending_changes": [],
		}
		session = save_session(
			"My item work",
			"Edit",
			"Item",
			state,
			mapping_profile=profile["name"],
			row_count=25,
		)
		loaded = get_session(session["name"])
		self.assertEqual(loaded["state"], state)
		self.assertEqual(loaded["row_count"], 25)

	def test_other_user_cannot_open_private_session(self):
		session = save_session("Private", "Edit", "Item", {"pending_changes": []})
		email = f"bde-session-{uuid.uuid4().hex[:10]}@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "BDE session outsider",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			get_session(session["name"])
