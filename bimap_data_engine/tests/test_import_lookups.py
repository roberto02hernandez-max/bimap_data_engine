import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from bimap_data_engine.api.lookups import resolve_import_keys


class TestImportLookups(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		suffix = uuid.uuid4().hex[:8]
		self.customer_key = f"CLI-{suffix}"
		self.item_code = f"P20-{suffix}"
		customer_group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0]
		item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
		self.customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": f"Cliente lookup {suffix}",
			"customer_type": "Company",
			"customer_group": customer_group,
			"territory": territory,
			"bimap_customer_number": self.customer_key,
		}).insert()
		self.item = frappe.get_doc({
			"doctype": "Item",
			"item_code": self.item_code,
			"item_name": f"Producto lookup {suffix}",
			"item_group": item_group,
			"stock_uom": stock_uom,
			"is_stock_item": 0,
		}).insert()

	def test_resolves_business_keys_and_returns_names(self):
		result = resolve_import_keys(
			"Quotation",
			[{
				"Clave de cliente": self.customer_key.lower(),
				"Clave de producto": self.item_code.lower(),
			}],
			[
				{"kind": "customer", "source": "Clave de cliente", "display_source": "Nombre del cliente"},
				{"kind": "item", "source": "Clave de producto", "display_source": "Nombre del producto"},
			],
		)
		self.assertEqual(result["rows"][0]["Clave de cliente"], self.customer.name)
		self.assertEqual(result["rows"][0]["Clave de producto"], self.item.name)
		self.assertEqual(result["display_rows"][0]["Nombre del cliente"], self.customer.customer_name)
		self.assertEqual(result["display_rows"][0]["Nombre del producto"], self.item.item_name)
		self.assertFalse(result["issues"])

	def test_unknown_key_is_reported_on_the_same_cell(self):
		result = resolve_import_keys(
			"Quotation",
			[{"Clave de cliente": "NO-EXISTE"}],
			[{"kind": "customer", "source": "Clave de cliente", "display_source": "Nombre del cliente"}],
		)
		self.assertEqual(result["issues"][0]["row"], 2)
		self.assertEqual(result["issues"][0]["source_field"], "Clave de cliente")
		self.assertEqual(result["issues"][0]["code"], "unknown_business_key")
