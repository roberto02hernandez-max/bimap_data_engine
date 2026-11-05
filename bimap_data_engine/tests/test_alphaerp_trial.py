import unittest
from decimal import Decimal

from bimap_data_engine.services.alphaerp.trial import item_code, item_kind, warehouse_company


class TestAlphaERPTrialRules(unittest.TestCase):
	def test_classifies_product_service_and_kit_without_overlap(self):
		self.assertEqual(item_kind({"STACLAS1": Decimal(0), "KIT": Decimal(0)}), "Producto")
		self.assertEqual(item_kind({"STACLAS1": Decimal(1), "KIT": Decimal(0)}), "Servicio")
		self.assertEqual(item_kind({"STACLAS1": Decimal(1), "KIT": Decimal(1)}), "Kit")

	def test_assigns_iso_only_from_source_company_name(self):
		self.assertEqual(warehouse_company({"NOM_COM": "ISTITUTO STUDI ODONTODIATRICI MEXICO"}), "ISO")
		self.assertEqual(warehouse_company({"DES_LUG": "Almacén ISO 3", "NOM_COM": "TIR DEN"}), "TIR")

	def test_variant_code_is_stable(self):
		self.assertEqual(item_code("BASE", "ROJO"), "BASE::ROJO")
		self.assertEqual(item_code("BASE"), "BASE")


if __name__ == "__main__":
	unittest.main()
