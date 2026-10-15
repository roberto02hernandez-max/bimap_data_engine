import uuid

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cstr

from bimap_data_engine.services.change_engine import apply_changes, preview_changes


class TestItemPriceAndStructuralPolicies(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		item_group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
		stock_uom = frappe.get_all("UOM", pluck="name", limit=1)[0]
		self.item_code = f"BDE-PRICE-{uuid.uuid4().hex[:10].upper()}"
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": self.item_code,
				"item_name": "BIMAP price test item",
				"item_group": item_group,
				"stock_uom": stock_uom,
				"is_stock_item": 0,
			}
		).insert()
		price_list = frappe.get_all(
			"Price List", filters={"enabled": 1, "selling": 1}, fields=["name", "currency"], limit=1
		)[0]
		self.price = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item_code,
				"price_list": price_list.name,
				"price_list_rate": 100,
				"currency": price_list.currency,
				"uom": stock_uom,
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_item_price_updates_only_rate(self):
		before = frappe.db.get_value(
			"Item Price", self.price.name, ["item_code", "price_list", "currency", "uom"], as_dict=True
		)
		change = {
			"operation": "set",
			"doctype": "Item Price",
			"name": self.price.name,
			"fieldname": "price_list_rate",
			"original": self.price.price_list_rate,
			"value": 123.45,
			"snapshot_modified": cstr(self.price.modified),
		}
		apply_changes([change])
		after = frappe.db.get_value(
			"Item Price",
			self.price.name,
			["item_code", "price_list", "currency", "uom", "price_list_rate"],
			as_dict=True,
		)
		self.assertEqual(after.price_list_rate, 123.45)
		self.assertEqual(after.item_code, before.item_code)
		self.assertEqual(after.price_list, before.price_list)
		self.assertEqual(after.currency, before.currency)
		self.assertEqual(after.uom, before.uom)

	def test_safe_item_attribute_is_editable_but_variant_structure_is_blocked(self):
		item = frappe.get_doc("Item", self.item_code)
		safe_change = {
			"operation": "set",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "weight_per_unit",
			"original": item.weight_per_unit,
			"value": 2.5,
			"snapshot_modified": cstr(item.modified),
		}
		self.assertTrue(preview_changes([safe_change])["valid"])
		apply_changes([safe_change])
		item.reload()
		self.assertEqual(item.weight_per_unit, 2.5)

		structural_change = {
			"operation": "set",
			"doctype": "Item",
			"name": item.name,
			"fieldname": "has_variants",
			"original": item.has_variants,
			"value": 1,
			"snapshot_modified": cstr(item.modified),
		}
		result = preview_changes([structural_change])
		self.assertFalse(result["valid"])
		self.assertTrue(any("estructural" in error for error in result["documents"][0]["errors"]))
