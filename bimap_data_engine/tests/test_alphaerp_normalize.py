import unittest
from decimal import Decimal

from bimap_data_engine.services.alphaerp.catalog import SENSITIVE_FIELDS
from bimap_data_engine.services.alphaerp.normalize import normalize_tables
from bimap_data_engine.services.alphaerp.package import TABLE_FIELDS


class TestAlphaERPNormalize(unittest.TestCase):
	def test_package_allowlist_never_exposes_credentials_or_bank_accounts(self):
		for fields in TABLE_FIELDS.values():
			self.assertFalse(fields & SENSITIVE_FIELDS)

	def test_builds_catalog_workbook_without_creating_documents(self):
		result = normalize_tables({
			"AGENTES": [{
				"CVE_AGE": Decimal("7"), "NOM_AGE": "Vendedor de prueba",
			}],
			"CLIENTES": [{
				"CVE_CTE": Decimal("10"), "NOM_CTE": "Cliente de prueba",
				"CVE_AGE": Decimal("7"),
				"CVE_ZON": Decimal("1"), "CVE_SUB": Decimal("2"),
				"CVE_MONSTA": Decimal("1"), "CVE_IVA": "A",
			}],
			"PROVEDOR": [{
				"CVE_PROV": Decimal("20"), "NOM_PROV": "Proveedor de prueba",
				"CVE_MONDES": Decimal("0"), "CVE_IVA": "P",
			}],
			"PRODUCTO": [{
				"CVE_PROD": "P-1", "NOM_PROD": "", "DESC_PROD": "Producto visible",
				"UNI_MED": "PZA", "STAIVA": Decimal("2"), "STAIEPS": Decimal("1"),
				"TIPO_IEPS": Decimal("1"), "MONTO_IEPS": Decimal("1.25"),
			}],
			"ZONAS": [{"CVE_ZON": Decimal("1"), "NOM_ZON": "Norte"}],
			"SUBZONAS": [{"CVE_ZON": Decimal("1"), "CVE_SUB": Decimal("2"), "NOM_SUB": "Centro"}],
			"MONEDAS": [{"CVE_MON": Decimal("1"), "DES_MON": "Pesos", "MONSAT": "MXN"}],
			"UNIDAD": [{"UNIDAD": "PZA", "DESCUNIDAD": "Pieza", "C_UNIS": "H87"}],
			"TIPOIVAC": [{"CVE_IVA": "A", "DESC_IVA": "Ventas", "TASA_IVA": Decimal("16")}],
			"TIPOIVAP": [{"CVE_IVA": "P", "DESC_IVA": "Compras", "TASA_IVA": Decimal("16")}],
			"CTEXPROD": [{
				"CVE_CTE": Decimal("10"), "CVE_PROD": "P-1", "NEW_MED": "",
				"CVE_MON": Decimal("1"), "U_PRECIO": Decimal("99.50"),
			}],
		})

		sheets = {sheet["name"]: sheet for sheet in result["sheets"]}
		self.assertEqual(sheets["Productos"]["rows"][0]["Nombre"], "Producto visible")
		self.assertEqual(sheets["Productos"]["rows"][0]["Modo IVA"], "Por producto")
		self.assertEqual(sheets["Productos"]["rows"][0]["Tipo IEPS"], "Monto por unidad")
		self.assertEqual(sheets["Proveedores"]["rows"][0]["Moneda ISO"], "MXN")
		self.assertEqual(sheets["Vendedores"]["rows"][0]["Clave vendedor AlphaERP"], "7")
		self.assertEqual(sheets["Clientes"]["rows"][0]["Clave vendedor AlphaERP"], "7")
		self.assertIn("Clave cliente AlphaERP", sheets["Precios"]["headers"])
		self.assertEqual(result["issue_summary"], {})


if __name__ == "__main__":
	unittest.main()
