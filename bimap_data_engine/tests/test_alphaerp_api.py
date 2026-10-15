import unittest
from unittest.mock import patch

from bimap_data_engine.api.alphaerp import _commercial_classifications, _tax_signatures, preview_summary


class TestAlphaERPApi(unittest.TestCase):
	def test_groups_tax_profiles_by_real_rates_and_party_type(self):
		profiles = [
			{"mapping_type": "Customer Tax", "party_type": "Cliente", "source_key": "A", "source_label": "UNO ORO", "iva": 16, "retention_vat": 0, "retention_income": 0, "has_ieps": False, "exempt": False, "impact": 2, "examples": []},
			{"mapping_type": "Customer Tax", "party_type": "Cliente", "source_key": "B", "source_label": "UNO AZUL", "iva": 16.0, "retention_vat": 0, "retention_income": 0, "has_ieps": False, "exempt": False, "impact": 3, "examples": []},
			{"mapping_type": "Supplier Tax", "party_type": "Proveedor", "source_key": "C", "source_label": "UNO", "iva": 16, "retention_vat": 0, "retention_income": 0, "has_ieps": False, "exempt": False, "impact": 1, "examples": []},
		]
		groups = _tax_signatures(profiles)
		self.assertEqual(len(groups), 2)
		customer = next(row for row in groups if row["party_type"] == "Cliente")
		self.assertEqual(customer["source_keys"], ["A", "B"])
		self.assertEqual(customer["impact"], 5)

	def test_commercial_classification_separates_group_from_tier(self):
		profiles = [
			{"mapping_type": "Customer Tax", "party_type": "Cliente", "source_key": "CIPLORO", "source_label": "CIRUJANO PLÁSTICO ORO", "impact": 5, "examples": []},
			{"mapping_type": "Customer Tax", "party_type": "Cliente", "source_key": "CIPLAZUL", "source_label": "CIRUJANO PLÁSTICO AZUL", "impact": 66, "examples": []},
		]
		groups = _commercial_classifications(profiles, {"Customer Commercial": {}, "Supplier Commercial": {}})
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["source_label"], "CIRUJANO PLÁSTICO")
		self.assertEqual(groups[0]["tiers"], ["ORO", "AZUL"])
		self.assertEqual(groups[0]["impact"], 71)

	@patch("bimap_data_engine.api.alphaerp.reconcile_workbook")
	@patch("bimap_data_engine.api.alphaerp.normalize_package")
	@patch("bimap_data_engine.api.alphaerp._configured_source", return_value="/tmp/alphaerp")
	def test_preview_summary_returns_the_analysis_payload(self, _source, normalize, reconcile):
		normalize.return_value = {
			"summary": {"Clientes": 5},
			"issue_summary": {"orphan": 1},
		}
		reconcile.return_value = {
			"source_fingerprint": "fingerprint",
			"company": "Empresa",
			"entities": {"Customer": {"create": 5}},
			"equivalences": {"uoms": [{"status": "reuse"}]},
			"fiscal": {"profiles": 2},
		}

		result = preview_summary()

		self.assertEqual(result["summary"]["Clientes"], 5)
		self.assertEqual(result["entities"]["Customer"]["create"], 5)
		self.assertEqual(result["equivalences"]["uoms"]["reuse"], 1)
		self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
	unittest.main()
