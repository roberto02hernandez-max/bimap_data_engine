"""Normalize AlphaERP customer, supplier and item catalogs into a BIMAP workbook."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from bimap_data_engine.services.alphaerp.package import AlphaERPPackage


def _text(value) -> str:
	return str(value or "").strip()


def _key(value) -> str:
	if value is None:
		return ""
	if isinstance(value, Decimal):
		return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))
	return _text(value)


def _number(value):
	return float(value) if isinstance(value, Decimal) else value


def _truth(value) -> bool:
	if isinstance(value, Decimal):
		return bool(int(value))
	return bool(value)


def _sheet(name, rows):
	rows = list(rows)
	headers = []
	for row in rows:
		for field in row:
			if field not in headers:
				headers.append(field)
	return {"name": name, "headers": headers, "rows": rows, "row_count": len(rows)}


def _issue(entity, source_key, field, code, message, *, severity="error"):
	return {
		"entity": entity, "source_key": source_key, "source_field": field,
		"code": code, "severity": severity, "message": message, "error": message,
	}


def _unique_index(rows, field):
	index = {}
	duplicates = set()
	for row in rows:
		key = _key(row.get(field))
		if not key:
			continue
		if key in index:
			duplicates.add(key)
		else:
			index[key] = row
	return index, duplicates


def _tax_mode(value, *, withholding=False):
	mode = int(value or 0)
	labels = {
		1: "Por tipo de cliente/proveedor",
		2: "Por producto",
		3: "Sin retención" if withholding else "Exento",
	}
	return labels.get(mode, "")


def _currency_iso(source_key, currencies):
	# AlphaERP uses zero in the supplier catalog to mean the local/default
	# currency.  This database's currency 1 is MXN.
	if source_key in {"", "0"}:
		return "MXN"
	return _text(currencies.get(source_key, {}).get("MONSAT"))


def _address_row(party_key, party_type, address_type, title, row, prefix, *, country_field=None):
	values = {
		"Tipo de tercero": party_type,
		"Clave AlphaERP": party_key,
		"Identificador dirección": f"{party_type}:{party_key}:{address_type}",
		"Tipo de dirección": address_type,
		"Título": _text(title) or f"{party_type} {party_key}",
		"Calle": _text(row.get(f"DIR_{prefix}")),
		"Número exterior": _text(row.get(f"NE_{prefix}")),
		"Número interior": _text(row.get(f"NI_{prefix}")),
		"Colonia": _text(row.get(f"COL_{prefix}")),
		"Ciudad": _text(row.get(f"CD_{prefix}")),
		"Municipio": _text(row.get(f"DELEGA_{prefix}")),
		"Estado": _text(row.get(f"EDO_{prefix}")),
		"Código postal": _text(row.get(f"CP_{prefix}")),
		"País": _text(row.get(country_field)) if country_field else "",
	}
	return values


def normalize_tables(tables: dict[str, list[dict]], *, manifest=None) -> dict:
	"""Build a value-only workbook; no Frappe documents are created here."""
	issues = []
	customers, duplicate_customers = _unique_index(tables.get("CLIENTES", []), "CVE_CTE")
	agents, duplicate_agents = _unique_index(tables.get("AGENTES", []), "CVE_AGE")
	suppliers, duplicate_suppliers = _unique_index(tables.get("PROVEDOR", []), "CVE_PROV")
	items, duplicate_items = _unique_index(tables.get("PRODUCTO", []), "CVE_PROD")
	zones, _ = _unique_index(tables.get("ZONAS", []), "CVE_ZON")
	subzones = {
		(_key(row.get("CVE_ZON")), _key(row.get("CVE_SUB"))): row
		for row in tables.get("SUBZONAS", [])
	}
	price_lists, _ = _unique_index(tables.get("CATLISPRE", []), "NLISPRE")
	customer_taxes, _ = _unique_index(tables.get("TIPOIVAC", []), "CVE_IVA")
	supplier_taxes, _ = _unique_index(tables.get("TIPOIVAP", []), "CVE_IVA")
	currencies, _ = _unique_index(tables.get("MONEDAS", []), "CVE_MON")
	uoms, _ = _unique_index(tables.get("UNIDAD", []), "UNIDAD")

	for entity, duplicates in (
		("Cliente", duplicate_customers), ("Vendedor", duplicate_agents),
		("Proveedor", duplicate_suppliers), ("Producto", duplicate_items)
	):
		for key in sorted(duplicates):
			issues.append(_issue(entity, key, "Clave AlphaERP", "duplicate_key", f"Clave repetida: {key}."))

	customer_rows = []
	agent_rows = []
	for key, row in agents.items():
		agent_rows.append({
			"Clave vendedor AlphaERP": key,
			"Nombre": _text(row.get("NOM_AGE")) or f"Vendedor {key}",
			"Área": _text(row.get("AREA_AGE")),
			"Correo": _text(row.get("EMAIL_AGE")),
			"Comisión predeterminada": _number(row.get("COM_AGE")),
			"Tipo AlphaERP": _text(row.get("TIPO_AGE")),
		})
	address_rows = []
	for key, row in customers.items():
		tax_code = _text(row.get("CVE_IVA"))
		zone = _key(row.get("CVE_ZON"))
		subzone = _key(row.get("CVE_SUB"))
		price_list = _key(row.get("LISTA_PREC"))
		currency = _key(row.get("CVE_MONSTA"))
		customer_rows.append({
			"Clave AlphaERP": key,
			"Clave vendedor AlphaERP": _key(row.get("CVE_AGE")),
			"Nombre": _text(row.get("NOM_CTE")),
			"Razón social fiscal": _text(row.get("NOM_FAC")) or _text(row.get("NOM_CTE")),
			"RFC": _text(row.get("RFC_CTE")) or _text(row.get("IDFISCAL")),
			"CURP": _text(row.get("CURP_CTE")),
			"Correo": _text(row.get("EMAIL_CTE")),
			"Teléfono": _text(row.get("TEL1_CTE")),
			"Tipo fiscal AlphaERP": tax_code,
			"Descripción fiscal AlphaERP": _text(customer_taxes.get(tax_code, {}).get("DESC_IVA")),
			"Zona AlphaERP": zone,
			"Nombre zona": _text(zones.get(zone, {}).get("NOM_ZON")),
			"Subzona AlphaERP": subzone,
			"Nombre subzona": _text(subzones.get((zone, subzone), {}).get("NOM_SUB")),
			"Lista de precios AlphaERP": price_list,
			"Moneda AlphaERP": currency,
			"Moneda ISO": _currency_iso(currency, currencies),
			"Límite de crédito": _number(row.get("LIM_CRE")),
			"Días de crédito": _number(row.get("DIA_CRE")),
			"Régimen fiscal SAT": _text(row.get("REGI_CTE")) or _text(row.get("REGI_CTERE")),
			"Uso CFDI": _text(row.get("USO_CTE")),
			"Método de pago": _text(row.get("METP_CTE")),
			"Forma de pago": _text(row.get("CMETPSAT")),
			"Fecha alta": row.get("FALTA_CTE"),
			"Estado AlphaERP": _number(row.get("TRANS")),
		})
		address_rows.append(_address_row(
			key, "Cliente", "Principal", row.get("NOM_CTE"), row, "CTE",
			country_field="PAIS_CTE",
		))
		fiscal_prefix = "FAC" if any(_text(row.get(field)) for field in ("DIR_FAC", "COL_FAC", "CD_FAC", "CP_FAC")) else "CTE"
		address_rows.append(_address_row(
			key, "Cliente", "Fiscal", row.get("NOM_FAC") or row.get("NOM_CTE"), row, fiscal_prefix,
			country_field=f"PAIS_{fiscal_prefix}",
		))
		if any(_text(row.get(field)) for field in ("DIR_ENT", "COL_ENT", "CD_ENT", "CP_ENT")):
			address_rows.append(_address_row(
				key, "Cliente", "Envío", row.get("NOM_ENT") or row.get("NOM_CTE"), row, "ENT",
				country_field="RESI_ENT",
			))
		if not _text(row.get("NOM_CTE")):
			issues.append(_issue("Cliente", key, "Nombre", "missing_name", "El cliente no tiene nombre."))
		if tax_code and tax_code not in customer_taxes:
			issues.append(_issue("Cliente", key, "Tipo fiscal AlphaERP", "missing_reference", f"Tipo fiscal inexistente: {tax_code}."))
		if zone and zone not in zones:
			issues.append(_issue("Cliente", key, "Zona AlphaERP", "missing_reference", f"Zona inexistente: {zone}."))
		if subzone and (zone, subzone) not in subzones:
			issues.append(_issue("Cliente", key, "Subzona AlphaERP", "missing_reference", f"Subzona inexistente: {zone}/{subzone}."))
		agent_key = _key(row.get("CVE_AGE"))
		if agent_key and agent_key not in agents:
			issues.append(_issue("Cliente", key, "Clave vendedor AlphaERP", "missing_reference", f"Vendedor inexistente: {agent_key}."))
		if price_list and price_list not in price_lists:
			issues.append(_issue("Cliente", key, "Lista de precios AlphaERP", "missing_reference", f"Lista inexistente: {price_list}."))
		if currency not in {"", "0"} and currency not in currencies:
			issues.append(_issue("Cliente", key, "Moneda AlphaERP", "missing_reference", f"Moneda inexistente: {currency}."))

	for row in tables.get("CTEDIR", []):
		key = _key(row.get("CVE_CTE"))
		address_key = _key(row.get("CVEDIRENT")) or str(len(address_rows) + 1)
		address = _address_row(key, "Cliente", "Envío", row.get("NOM_ENT"), row, "ENT", country_field="RESI_ENT")
		address["Identificador dirección"] = f"Cliente:{key}:Envío:{address_key}"
		address_rows.append(address)
		if key not in customers:
			issues.append(_issue("Dirección", f"{key}:{address_key}", "Clave cliente AlphaERP", "orphan", f"Cliente inexistente: {key}."))

	contact_rows = []
	for row in tables.get("CONTACTO", []):
		key = _key(row.get("CVE_CTE"))
		contact_key = _key(row.get("NUM")) or str(len(contact_rows) + 1)
		contact_rows.append({
			"Clave cliente AlphaERP": key,
			"Identificador contacto": f"Cliente:{key}:{contact_key}",
			"Nombre": _text(row.get("NOMBRE")),
			"Puesto": _text(row.get("PUESTO")),
			"Teléfono": _text(row.get("TEL1")),
			"Teléfono alterno": _text(row.get("TEL2")),
			"Extensión": _text(row.get("EXT")),
			"Móvil": _text(row.get("MOVIL")),
			"Correo": _text(row.get("EMAIL")),
		})
		if key not in customers:
			issues.append(_issue("Contacto", f"{key}:{contact_key}", "Clave cliente AlphaERP", "orphan", f"Cliente inexistente: {key}."))

	supplier_rows = []
	for key, row in suppliers.items():
		tax_code = _text(row.get("CVE_IVA"))
		currency = _key(row.get("CVE_MONDES"))
		supplier_rows.append({
			"Clave AlphaERP": key,
			"Nombre": _text(row.get("NOM_PROV")),
			"RFC": _text(row.get("RFC_PROV")) or _text(row.get("IDFISCAL")),
			"CURP": _text(row.get("CURP_PROV")),
			"Correo": _text(row.get("EMAIL_PROV")),
			"Teléfono": _text(row.get("TEL1_PROV")),
			"Tipo fiscal AlphaERP": tax_code,
			"Descripción fiscal AlphaERP": _text(supplier_taxes.get(tax_code, {}).get("DESC_IVA")),
			"Moneda AlphaERP": currency,
			"Moneda ISO": _currency_iso(currency, currencies),
			"Límite de crédito": _number(row.get("LIM_CRE")),
			"Días de crédito": _number(row.get("DIA_CRE")),
			"Tipo de operación SAT": _text(row.get("TOPERASAT")),
			"País SAT": _text(row.get("PAISSAT")),
			"Fecha alta": row.get("FALTA_PROV"),
			"Estado AlphaERP": _number(row.get("TRANS")),
		})
		address_rows.append(_address_row(
			key, "Proveedor", "Principal", row.get("NOM_PROV"), row, "PROV",
			country_field="PAIS_PROV",
		))
		if any(_text(row.get(field)) for field in ("CONTACTO", "EMAIL_PROV", "TEL1_PROV", "TEL2_PROV")):
			contact_rows.append({
				"Clave proveedor AlphaERP": key,
				"Identificador contacto": f"Proveedor:{key}:Principal",
				"Nombre": _text(row.get("CONTACTO")) or _text(row.get("NOM_PROV")),
				"Teléfono": _text(row.get("TEL1_PROV")),
				"Teléfono alterno": _text(row.get("TEL2_PROV")),
				"Correo": _text(row.get("EMAIL_PROV")),
			})
		if not _text(row.get("NOM_PROV")):
			issues.append(_issue("Proveedor", key, "Nombre", "missing_name", "El proveedor no tiene nombre."))
		if tax_code and tax_code not in supplier_taxes:
			issues.append(_issue("Proveedor", key, "Tipo fiscal AlphaERP", "missing_reference", f"Tipo fiscal inexistente: {tax_code}."))
		if currency not in {"", "0"} and currency not in currencies:
			issues.append(_issue("Proveedor", key, "Moneda AlphaERP", "missing_reference", f"Moneda inexistente: {currency}."))

	classes, _ = _unique_index(tables.get("CLASES", []), "CSE_PROD")
	subclasses = {(_key(r.get("CSE_PROD")), _key(r.get("SUB_CSE"))): r for r in tables.get("SUBCLASE", [])}
	sub2 = {
		(_key(r.get("CSE_PROD")), _key(r.get("SUB_CSE")), _key(r.get("SUB_SUBCSE"))): r
		for r in tables.get("SUB2CLAS", [])
	}
	item_rows = []
	for key, row in items.items():
		class_key = _key(row.get("CSE_PROD"))
		subclass_key = _key(row.get("SUB_CSE"))
		sub2_key = _key(row.get("SUB_SUBCSE"))
		uom = _text(row.get("UNI_MED"))
		path = [
			_text(classes.get(class_key, {}).get("DES_CSE")),
			_text(subclasses.get((class_key, subclass_key), {}).get("DES_SUB")),
			_text(sub2.get((class_key, subclass_key, sub2_key), {}).get("DESSUBSUB")),
		]
		path = [value for value in path if value]
		item_rows.append({
			"Clave AlphaERP": key,
			# In the inspected AlphaERP version NOM_PROD exists but is unused;
			# DESC_PROD is the visible catalog name.
			"Nombre": _text(row.get("NOM_PROD")) or _text(row.get("DESC_PROD")),
			"Descripción": " ".join(filter(None, (_text(row.get("DESC_PROD")), _text(row.get("DESC_PROD2"))))),
			"Clase AlphaERP": class_key,
			"Subclase AlphaERP": subclass_key,
			"Tercer nivel AlphaERP": sub2_key,
			"Ruta grupo de artículos": " / ".join(path),
			"Unidad AlphaERP": uom,
			"Descripción unidad": _text(uoms.get(uom, {}).get("DESCUNIDAD")),
			"Unidad SAT": _text(uoms.get(uom, {}).get("C_UNIS")),
			"Unidad de compra": _text(row.get("UNI_MED_P")),
			"Unidad de empaque": _text(row.get("UNI_EMB")),
			"Piezas por empaque": _number(row.get("PZAS")),
			"Código de barras": _text(row.get("CODBAR")),
			"Lista de atributos": _text(row.get("LISTA_MED")),
			"Maneja lotes": _truth(row.get("STALOTE")),
			"Vida útil días": _number(row.get("DIASVIDA")),
			"Clave producto SAT": _text(row.get("C_PRDS")),
			"Modo IVA": _tax_mode(row.get("STAIVA")),
			"Tasa IVA producto": _number(row.get("PORCENIVA")),
			"No objeto de impuesto": _truth(row.get("NOOBJI")),
			"Maneja IEPS": _truth(row.get("STAIEPS")),
			"Tipo IEPS": "Monto por unidad" if int(row.get("TIPO_IEPS") or 0) == 1 else "Porcentaje",
			"Porcentaje IEPS": _number(row.get("PORCENIEPS")),
			"Unidad IEPS": _text(row.get("UNI_IEPS")),
			"Monto IEPS": _number(row.get("MONTO_IEPS")),
			"Excluir IEPS de base IVA": _truth(row.get("IVA_IEPS")),
			"IVA IMMEX": _truth(row.get("STAPITEX")),
			"Modo retención IVA": _tax_mode(row.get("STARETIVA"), withholding=True),
			"Tasa retención IVA producto": _number(row.get("PORRETIVA")),
			"Modo retención ISR": _tax_mode(row.get("STARETISR"), withholding=True),
			"Tasa retención ISR producto": _number(row.get("PORRETISR")),
			"Proveedor predeterminado AlphaERP": _key(row.get("PROV_STD") or row.get("CVE_PROV")),
			"Estado AlphaERP": _number(row.get("TRANS")),
		})
		if not (_text(row.get("NOM_PROD")) or _text(row.get("DESC_PROD"))):
			issues.append(_issue("Producto", key, "Nombre", "missing_name", "El producto no tiene nombre."))
		if class_key and class_key not in classes:
			issues.append(_issue("Producto", key, "Clase AlphaERP", "missing_reference", f"Clase inexistente: {class_key}."))
		if uom and uom not in uoms:
			issues.append(_issue("Producto", key, "Unidad AlphaERP", "missing_reference", f"Unidad inexistente: {uom}."))

	unit_rows = []
	for row in tables.get("PRODUNID", []):
		key = _text(row.get("CVE_PROD"))
		unit_rows.append({
			"Clave producto AlphaERP": key,
			"Unidad AlphaERP": _text(row.get("UNIDAD")),
			"Factor": _number(row.get("FACTOR")),
			"Unidad conversión AlphaERP": _text(row.get("CONVER")),
			"Código de barras": _text(row.get("CODBAR1")),
			"Código variante AlphaERP": _text(row.get("NEW_MED")),
		})
		if key not in items:
			issues.append(_issue("Unidad de producto", key, "Clave producto AlphaERP", "orphan", f"Producto inexistente: {key}."))

	variant_rows = []
	for row in tables.get("PRODMED", []):
		key = _text(row.get("CVE_PROD"))
		variant = _text(row.get("NEW_MED"))
		values = [_text(row.get(f"DATO_{index}")) for index in range(1, 13)]
		variant_rows.append({
			"Clave producto AlphaERP": key,
			"Código variante AlphaERP": variant,
			"Lista de atributos": _text(row.get("LISTA_MED")),
			"Código de barras": _text(row.get("CODBAR")),
			**{f"Atributo {index}": value for index, value in enumerate(values, start=1)},
		})
		if key not in items:
			issues.append(_issue("Variante", f"{key}:{variant}", "Clave producto AlphaERP", "orphan", f"Producto inexistente: {key}."))

	relation_rows = []
	for row in tables.get("PROVXPRO", []):
		item_key = _text(row.get("CVE_PROD"))
		supplier_key = _key(row.get("CVE_PROV"))
		relation_key = f"{item_key}:{supplier_key}:{_text(row.get('NEW_MED'))}"
		relation_rows.append({
			"Identificador relación": relation_key,
			"Clave producto AlphaERP": item_key,
			"Clave proveedor AlphaERP": supplier_key,
			"Código variante AlphaERP": _text(row.get("NEW_MED")),
			"Proveedor predeterminado": bool(row.get("PROV_STN")),
			"Días de entrega": _number(row.get("DIASE")),
			"Unidad del proveedor": _text(row.get("UNIDADXML")),
			"Factor unidad proveedor": _number(row.get("FACTORXML")),
			"Clave SAT proveedor": _text(row.get("CVESATXML")),
			"Moneda AlphaERP": _key(row.get("CVE_MON")),
			"Último costo": _number(row.get("U_COSTO")),
			"Fecha último costo": row.get("F_U_COSTO"),
		})
		if item_key not in items:
			issues.append(_issue("Relación proveedor-producto", relation_key, "Clave producto AlphaERP", "orphan", f"Producto inexistente: {item_key}."))
		if supplier_key not in suppliers:
			issues.append(_issue("Relación proveedor-producto", relation_key, "Clave proveedor AlphaERP", "orphan", f"Proveedor inexistente: {supplier_key}."))

	price_rows = []
	for source, rows, variant_field in (
		("General", tables.get("PRECIPROD", []), None),
		("Variante", tables.get("PRECIMED", []), "MLISPRE"),
	):
		for row in rows:
			item_key = _text(row.get("CVE_PROD"))
			list_key = _key(row.get("NLISPRE"))
			price_key = f"{source}:{item_key}:{_text(row.get(variant_field)) if variant_field else ''}:{list_key}"
			price_rows.append({
				"Identificador precio": price_key,
				"Origen": source,
				"Clave producto AlphaERP": item_key,
				"Código variante AlphaERP": _text(row.get(variant_field)) if variant_field else "",
				"Lista de precios AlphaERP": list_key,
				"Precio": _number(row.get("LPRECPROD")),
				"Cantidad desde": _number(row.get("LEXCDESD")),
				"Cantidad hasta": _number(row.get("LEXCHAST")),
			})
			if item_key not in items:
				issues.append(_issue("Precio", price_key, "Clave producto AlphaERP", "orphan", f"Producto inexistente: {item_key}."))
			if list_key not in price_lists:
				issues.append(_issue("Precio", price_key, "Lista de precios AlphaERP", "missing_reference", f"Lista inexistente: {list_key}."))

	for row in tables.get("CTEXPROD", []):
		customer_key = _key(row.get("CVE_CTE"))
		item_key = _text(row.get("CVE_PROD"))
		variant = _text(row.get("NEW_MED"))
		price_key = f"Cliente:{customer_key}:{item_key}:{variant}"
		price_rows.append({
			"Identificador precio": price_key,
			"Origen": "Especial cliente",
			"Clave cliente AlphaERP": customer_key,
			"Clave producto AlphaERP": item_key,
			"Código variante AlphaERP": variant,
			"Moneda AlphaERP": _key(row.get("CVE_MON")),
			"Precio": _number(row.get("U_PRECIO")),
			"Fecha precio": row.get("F_U_PRECIO"),
		})
		if customer_key not in customers:
			issues.append(_issue("Precio especial", price_key, "Clave cliente AlphaERP", "orphan", f"Cliente inexistente: {customer_key}."))
		if item_key not in items:
			issues.append(_issue("Precio especial", price_key, "Clave producto AlphaERP", "orphan", f"Producto inexistente: {item_key}."))

	zone_rows = [{
		"Clave zona AlphaERP": key,
		"Nombre": _text(row.get("NOM_ZON")),
	} for key, row in zones.items()]
	subzone_rows = [{
		"Clave zona AlphaERP": zone_key,
		"Clave subzona AlphaERP": subzone_key,
		"Nombre": _text(row.get("NOM_SUB")),
	} for (zone_key, subzone_key), row in subzones.items()]
	uom_rows = [{
		"Unidad AlphaERP": key,
		"Descripción": _text(row.get("DESCUNIDAD")),
		"Unidad SAT": _text(row.get("C_UNIS")),
	} for key, row in uoms.items()]
	currency_rows = [{
		"Moneda AlphaERP": key,
		"Descripción": _text(row.get("DES_MON")),
		"Moneda ISO": _text(row.get("MONSAT")),
	} for key, row in currencies.items()]
	price_list_rows = [{
		"Lista de precios AlphaERP": key,
		"Nombre": _text(row.get("DESLISPRE")),
		"Estado AlphaERP": _number(row.get("STA_LISTA")),
	} for key, row in price_lists.items()]
	attribute_rows = [{
		"Lista de atributos AlphaERP": _text(row.get("LISTA_MED")),
		"Orden": _number(row.get("IND_MED")),
		"Valor": _text(row.get("NEW_MED")),
		"Descripción": _text(row.get("DESC_MED")),
	} for row in tables.get("ATRIBUTO", [])]
	customer_tax_rows = [{
		"Tipo de tercero": "Cliente", "Clave fiscal AlphaERP": key,
		"Descripción": _text(row.get("DESC_IVA")),
		"IVA": _number(row.get("TASA_IVA")),
		"Retención IVA": _number(row.get("TAS_RETIVA")),
		"Retención ISR": _number(row.get("TAS_RETISR")),
		"Maneja IEPS": _truth(row.get("CONIEPS")),
	} for key, row in customer_taxes.items()]
	supplier_tax_rows = [{
		"Tipo de tercero": "Proveedor", "Clave fiscal AlphaERP": key,
		"Descripción": _text(row.get("DESC_IVA")),
		"IVA": _number(row.get("TASA_IVA")),
		"Retención IVA": _number(row.get("TAS_RETIVA")),
		"Retención ISR": _number(row.get("TAS_RETISR")),
		"Maneja IEPS": _truth(row.get("CONIEPS")),
		"Exento": _truth(row.get("EXENTO")),
	} for key, row in supplier_taxes.items()]

	sheets = [
		_sheet("Vendedores", agent_rows),
		_sheet("Clientes", customer_rows),
		_sheet("Direcciones", address_rows),
		_sheet("Contactos", contact_rows),
		_sheet("Proveedores", supplier_rows),
		_sheet("Productos", item_rows),
		_sheet("Unidades de producto", unit_rows),
		_sheet("Variantes", variant_rows),
		_sheet("Relaciones proveedor-producto", relation_rows),
		_sheet("Precios", price_rows),
		_sheet("Zonas", zone_rows),
		_sheet("Subzonas", subzone_rows),
		_sheet("Unidades", uom_rows),
		_sheet("Monedas", currency_rows),
		_sheet("Listas de precios", price_list_rows),
		_sheet("Valores de atributos", attribute_rows),
		_sheet("Perfiles fiscales", customer_tax_rows + supplier_tax_rows),
	]
	return {
		"format": "ALPHAERP",
		"source": {"system": "AlphaERP", "manifest": manifest or {}},
		"sheets": sheets,
		"issues": issues,
		"summary": {sheet["name"]: sheet["row_count"] for sheet in sheets},
		"issue_summary": dict(Counter(issue["code"] for issue in issues)),
	}


def normalize_package(source_directory) -> dict:
	package = AlphaERPPackage(source_directory)
	return normalize_tables(package.load(), manifest=package.manifest())
