import frappe
from frappe.tests.utils import FrappeTestCase

from bimap_data_engine.services.alphaerp.equivalences import (
	DOCTYPE,
	get_saved_equivalences,
	mapping_key,
	save_equivalences,
)
from bimap_data_engine.services.alphaerp.migration import preview_catalog


class TestAlphaERPEquivalences(FrappeTestCase):
	def tearDown(self):
		frappe.db.delete(DOCTYPE, {"source_key": "__BDE_TEST_UOM__"})
		frappe.db.rollback()

	def test_saves_validated_uom_mapping_idempotently(self):
		values = [{
			"mapping_type": "UOM",
			"source_key": "__BDE_TEST_UOM__",
			"source_label": "Unidad de prueba",
			"resolution": "Reuse",
			"target_name": "Kg",
			"settings": {},
		}]
		kwargs = {
			"allowed_sources": {"UOM": {"__BDE_TEST_UOM__"}},
			"fingerprint": "test-fingerprint",
			"company": frappe.defaults.get_global_default("company"),
		}
		first = save_equivalences(values, **kwargs)
		second = save_equivalences(values, **kwargs)
		self.assertEqual(first, second)
		row = get_saved_equivalences()[mapping_key("UOM", "__BDE_TEST_UOM__")]
		self.assertEqual(row["target_name"], "Kg")
		self.assertEqual(row["resolution"], "Reuse")

	def test_paged_preview_reports_missing_required_equivalence_without_writing(self):
		workbook = {"sheets": [{
			"name": "Productos",
			"rows": [{
				"Clave AlphaERP": "__BDE_PREVIEW_ITEM__",
				"Nombre": "Vista previa",
				"Descripción": "",
				"Ruta grupo de artículos": "Productos",
				"Unidad AlphaERP": "__MISSING__",
			}],
		}]}
		result = preview_catalog(workbook, "Item", page_length=1)
		self.assertFalse(result["writes_performed"])
		self.assertEqual(result["blocking_rows"], 1)
		self.assertEqual(result["rows"][0]["issues"][0]["code"], "missing_equivalence")
