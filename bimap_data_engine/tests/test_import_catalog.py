import frappe
from frappe.tests.utils import FrappeTestCase

from bimap_data_engine.services.import_catalog import get_edit_catalog, get_import_catalog


class TestImportCatalog(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_catalog_is_grouped_in_spanish_and_templates_use_real_metadata(self):
		catalog = get_import_catalog()
		areas = {area["id"]: area for area in catalog["areas"]}
		self.assertEqual(areas["sales"]["label"], "Ventas")
		self.assertEqual(areas["purchases"]["label"], "Compras")
		self.assertEqual(areas["stock"]["label"], "Almacén e inventario")

		invoices = next(
			document for document in areas["sales"]["documents"]
			if document["doctype"] == "Sales Invoice"
		)
		self.assertEqual(invoices["label"], "Facturas de venta")
		self.assertEqual(invoices["child"]["table_field"], "items")
		self.assertIn("customer", {field["fieldname"] for field in invoices["fields"]})
		self.assertIn("item_code", {field["fieldname"] for field in invoices["child"]["fields"]})
		customer = next(field for field in invoices["fields"] if field["fieldname"] == "customer")
		item = next(field for field in invoices["child"]["fields"] if field["fieldname"] == "item_code")
		self.assertEqual(customer["label"], "Clave de cliente")
		self.assertTrue(customer["required"])
		self.assertEqual(customer["lookup"]["key_field"], "bimap_customer_number")
		self.assertEqual(item["label"], "Clave de producto")
		self.assertTrue(item["required"])
		self.assertEqual(item["lookup"]["label_field"], "item_name")

	def test_flat_catalog_template_has_no_child_sheet(self):
		catalog = get_import_catalog()
		catalogs = next(area for area in catalog["areas"] if area["id"] == "catalogs")
		items = next(document for document in catalogs["documents"] if document["doctype"] == "Item")
		self.assertIsNone(items["child"])
		self.assertEqual(items["fields"][0]["label"], "Clave del artículo")

		customers = next(document for document in catalogs["documents"] if document["doctype"] == "Customer")
		self.assertEqual(customers["fields"][0]["fieldname"], "bimap_customer_number")

	def test_edit_catalog_uses_same_spanish_groups_and_preferred_fields(self):
		catalog = get_edit_catalog()
		catalogs = next(area for area in catalog["areas"] if area["id"] == "catalogs")
		items = next(document for document in catalogs["documents"] if document["doctype"] == "Item")
		self.assertEqual(items["label"], "Artículos")
		self.assertTrue(next(field for field in items["fields"] if field["fieldname"] == "item_code")["preferred"])
		self.assertFalse(next(field for field in items["fields"] if field["fieldname"] == "disabled")["preferred"])

	def test_edit_catalog_exposes_each_existing_price_list_as_a_filtered_choice(self):
		catalog = get_edit_catalog()
		catalogs = next(area for area in catalog["areas"] if area["id"] == "catalogs")
		price_choices = [
			document for document in catalogs["documents"]
			if document.get("id", "").startswith("Item Price::")
		]
		expected = set(frappe.get_all("Price List", pluck="name"))
		self.assertEqual({choice["filters"]["price_list"] for choice in price_choices}, expected)
		self.assertTrue(all(choice["doctype"] == "Item Price" for choice in price_choices))
		self.assertTrue(all(choice["label"].startswith("Precios — ") for choice in price_choices))
