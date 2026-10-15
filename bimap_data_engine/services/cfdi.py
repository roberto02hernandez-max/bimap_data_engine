"""Safe CFDI 4.0 / Pagos 2.0 source adapter for the generic import engine."""

from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import cstr
from lxml import etree


MAX_CFDI_BYTES = 5 * 1024 * 1024
CFDI_NAMESPACES = {
	"cfdi": "http://www.sat.gob.mx/cfd/4",
	"cfdi33": "http://www.sat.gob.mx/cfd/3",
	"tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
	"pago20": "http://www.sat.gob.mx/Pagos20",
}


def _decimal(value):
	if value in (None, ""):
		return None
	try:
		return float(Decimal(cstr(value)))
	except (InvalidOperation, ValueError):
		return cstr(value)


def _attributes(element, numeric=()):
	if element is None:
		return {}
	values = {key: value for key, value in element.attrib.items()}
	for key in numeric:
		if key in values:
			values[key] = _decimal(values[key])
	return values


def _local_name(element):
	return etree.QName(element).localname if element is not None else ""


def _first(root, local_name):
	values = root.xpath(f".//*[local-name()='{local_name}']")
	return values[0] if values else None


def _all(root, local_name):
	return root.xpath(f".//*[local-name()='{local_name}']")


def _parse_xml(content):
	if isinstance(content, str):
		content = content.encode("utf-8")
	if not isinstance(content, bytes):
		frappe.throw("El CFDI debe proporcionarse como XML binario.")
	if len(content) > MAX_CFDI_BYTES:
		frappe.throw("El CFDI excede 5 MB.")
	lowered = content[:4096].lower()
	if b"<!doctype" in lowered or b"<!entity" in lowered:
		frappe.throw("El XML contiene declaraciones no permitidas.")
	parser = etree.XMLParser(
		resolve_entities=False, no_network=True, load_dtd=False, recover=False, huge_tree=False
	)
	try:
		root = etree.fromstring(content, parser=parser)
	except (etree.XMLSyntaxError, ValueError) as exc:
		frappe.throw(f"XML CFDI inválido: {exc}")
	if _local_name(root) != "Comprobante":
		frappe.throw("El XML no contiene un Comprobante CFDI.")
	return root


def _tax_rows(container, *, scope, concept_index=None, payment_index=None, document_index=None):
	rows = []
	if container is None:
		return rows
	for kind, local_name in (("Traslado", "Traslado"), ("Retención", "Retencion")):
		for element in container.xpath(f".//*[local-name()='{local_name}']"):
			row = {
				"Alcance": scope,
				"Tipo": kind,
				"Concepto": concept_index,
				"Pago": payment_index,
				"DocumentoRelacionado": document_index,
				**_attributes(
					element,
					numeric=("Base", "TasaOCuota", "Importe"),
				),
			}
			rows.append(row)
	return rows


def parse_cfdi(content, *, filename=None):
	"""Parse fiscal facts only; signature/status verification remains a separate SAT integration."""
	root = _parse_xml(content)
	version = root.get("Version") or root.get("version") or ""
	warnings = []
	if version != "4.0":
		warnings.append(f"Versión CFDI {version or 'desconocida'}: se leyó en modo compatible.")
	header = _attributes(
		root,
		numeric=("TipoCambio", "SubTotal", "Descuento", "Total"),
	)
	emitter = _attributes(_first(root, "Emisor"))
	receiver = _attributes(_first(root, "Receptor"))
	timbre = _attributes(_first(root, "TimbreFiscalDigital"))
	uuid = cstr(timbre.get("UUID")).upper()
	if not uuid:
		warnings.append("El XML no contiene TimbreFiscalDigital ni UUID.")

	concepts = []
	concept_taxes = []
	concept_nodes = root.xpath("./*[local-name()='Conceptos']/*[local-name()='Concepto']")
	for index, concept in enumerate(concept_nodes, start=1):
		concepts.append({
			"CFDI UUID": uuid,
			"Concepto": index,
			**_attributes(
				concept,
				numeric=("Cantidad", "ValorUnitario", "Importe", "Descuento"),
			),
		})
		concept_taxes.extend(_tax_rows(
			_first(concept, "Impuestos"), scope="Concepto", concept_index=index
		))

	global_tax_container = next(
		(iter(root.xpath("./*[local-name()='Impuestos']"))), None
	)
	global_taxes = _tax_rows(global_tax_container, scope="Comprobante")
	related = []
	for group in root.xpath("./*[local-name()='CfdiRelacionados']"):
		for relation in group.xpath("./*[local-name()='CfdiRelacionado']"):
			related.append({
				"CFDI UUID": uuid,
				"TipoRelacion": group.get("TipoRelacion"),
				"UUIDRelacionado": relation.get("UUID"),
			})

	payments = []
	payment_documents = []
	payment_taxes = []
	payment_totals = {}
	pagos_node = _first(root, "Pagos")
	if pagos_node is not None:
		totales = next(iter(pagos_node.xpath("./*[local-name()='Totales']")), None)
		payment_totals = _attributes(totales)
		for payment_index, payment in enumerate(
			pagos_node.xpath("./*[local-name()='Pago']"), start=1
		):
			payments.append({
				"CFDI UUID": uuid,
				"Pago": payment_index,
				**_attributes(payment, numeric=("TipoCambioP", "Monto")),
			})
			for document_index, document in enumerate(
				payment.xpath("./*[local-name()='DoctoRelacionado']"), start=1
			):
				payment_documents.append({
					"CFDI UUID": uuid,
					"Pago": payment_index,
					"DocumentoRelacionado": document_index,
					**_attributes(
						document,
						numeric=("EquivalenciaDR", "ImpSaldoAnt", "ImpPagado", "ImpSaldoInsoluto"),
					),
				})
			payment_taxes.extend(_tax_rows(
				_first(payment, "ImpuestosP"), scope="Pago", payment_index=payment_index
			))

	document_type = "payment" if header.get("TipoDeComprobante") == "P" or payments else "invoice"
	return {
		"source_type": "CFDI",
		"document_type": document_type,
		"filename": filename,
		"version": version,
		"uuid": uuid,
		"header": header,
		"emitter": emitter,
		"receiver": receiver,
		"timbre": timbre,
		"concepts": concepts,
		"taxes": concept_taxes + global_taxes,
		"related": related,
		"payments": payments,
		"payment_documents": payment_documents,
		"payment_taxes": payment_taxes,
		"payment_totals": payment_totals,
		"warnings": warnings,
	}


def cfdi_to_workbook(parsed):
	"""Expose CFDI data through the same workbook contract used by CSV/XLSX."""
	uuid = parsed.get("uuid") or "CFDI-SIN-UUID"
	main_row = {
		"External ID": uuid,
		**{f"Comprobante.{key}": value for key, value in parsed["header"].items()},
		**{f"Emisor.{key}": value for key, value in parsed["emitter"].items()},
		**{f"Receptor.{key}": value for key, value in parsed["receiver"].items()},
		**{f"Timbre.{key}": value for key, value in parsed["timbre"].items()},
	}
	collections = [
		("CFDI", [main_row]),
		("Conceptos", parsed["concepts"]),
		("Impuestos", parsed["taxes"]),
		("Relacionados", parsed["related"]),
		("Pagos", parsed["payments"]),
		("Documentos Relacionados", parsed["payment_documents"]),
		("Impuestos de Pago", parsed["payment_taxes"]),
	]
	sheets = []
	for name, rows in collections:
		headers = list(dict.fromkeys(key for row in rows for key in row))
		sheets.append({"name": name, "headers": headers, "rows": rows, "row_count": len(rows)})
	return {
		"format": "CFDI XML",
		"source": {key: parsed.get(key) for key in ("document_type", "version", "uuid", "warnings")},
		"sheets": sheets,
	}


def load_attached_cfdi(file_url):
	"""Return the parsed fiscal payload and its permission-checked File document."""
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw("El archivo CFDI adjunto no existe.")
	file_doc = frappe.get_doc("File", file_name)
	file_doc.check_permission("read")
	if not cstr(file_doc.file_name).lower().endswith(".xml"):
		frappe.throw("El archivo no tiene extensión XML.")
	return parse_cfdi(file_doc.get_content(), filename=file_doc.file_name), file_doc


def parse_attached_cfdi(file_url):
	parsed, _file_doc = load_attached_cfdi(file_url)
	return cfdi_to_workbook(parsed)
