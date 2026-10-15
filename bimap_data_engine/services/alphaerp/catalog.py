"""Allowlisted AlphaERP sources and privacy-safe structural inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bimap_data_engine.services.alphaerp.dbf import DBFError, read_schema


SENSITIVE_FIELDS = {
	"PASSWORD", "USERNAME", "CLABE", "CTACLABE", "PRVCLABE", "CUENTABAN",
	"PRVCUENTA",
}


@dataclass(frozen=True)
class SourceTable:
	name: str
	purpose: str
	required_fields: tuple[str, ...]
	optional_fields: tuple[str, ...] = ()

	@property
	def allowed_fields(self) -> frozenset[str]:
		return frozenset((*self.required_fields, *self.optional_fields)) - SENSITIVE_FIELDS


TABLES = (
	SourceTable("PRODUCTO", "Artículos", (
		"CVE_PROD", "NOM_PROD", "UNI_MED", "CSE_PROD",
	), (
		"DESC_PROD", "DESC_PROD2", "SUB_CSE", "SUB_SUBCSE", "CODBAR", "STALOTE",
		"LISTA_MED", "C_PRDS", "CVE_IVA", "STAIVA", "PORCENIVA", "STAIEPS",
		"PORCENIEPS", "UNI_EMB", "CVE_PROV",
	)),
	SourceTable("PRODMED", "Variantes y atributos por artículo", (
		"LISTA_MED", "CVE_PROD", "NEW_MED",
	), tuple(f"DATO_{index}" for index in range(1, 13)) + ("CODBAR",)),
	SourceTable("ATRIBUTO", "Valores de atributos", (
		"LISTA_MED", "NEW_MED", "IND_MED", "DESC_MED",
	)),
	SourceTable("PRODUNID", "Unidades alternativas", (
		"CVE_PROD", "UNIDAD", "FACTOR",
	), ("CODBAR1", "NEW_MED", "CONVER")),
	SourceTable("PRECIPROD", "Precios por artículo", (
		"CVE_PROD", "NLISPRE", "LPRECPROD",
	)),
	SourceTable("PRECIMED", "Precios por variante", (
		"CVE_PROD", "MLISPRE", "NLISPRE", "LPRECPROD",
	)),
	SourceTable("CATLISPRE", "Catálogo de listas de precios", (
		"NLISPRE", "DESLISPRE",
	), ("STA_LISTA",)),
	SourceTable("CLASES", "Categorías de artículos", ("CSE_PROD", "DES_CSE")),
	SourceTable("SUBCLASE", "Subcategorías de artículos", ("CSE_PROD", "SUB_CSE", "DES_SUB")),
	SourceTable("SUB2CLAS", "Tercer nivel de artículos", (
		"CSE_PROD", "SUB_CSE", "SUB_SUBCSE", "DESSUBSUB",
	)),
	SourceTable("UNIDAD", "Unidades de medida", ("UNIDAD", "DESCUNIDAD"), ("C_UNIS",)),
	SourceTable("MONEDAS", "Monedas", ("CVE_MON", "DES_MON"), ("MONSAT",)),
	SourceTable("CLIENTES", "Clientes", (
		"CVE_CTE", "NOM_CTE",
	), (
		"RFC_CTE", "DIR_CTE", "COL_CTE", "CD_CTE", "EDO_CTE", "CP_CTE",
		"PAIS_CTE", "EMAIL_CTE", "TEL1_CTE", "CONTACTO", "CVE_ZON", "CVE_SUB", "CURP_CTE",
		"LISTA_PREC", "LIM_CRE", "DIA_CRE", "CVE_IVA", "REGI_CTE", "USO_CTE",
	)),
	SourceTable("AGENTES", "Vendedores", (
		"CVE_AGE", "NOM_AGE",
	), ("COM_AGE", "TIPO_AGE", "AREA_AGE", "EMAIL_AGE")),
	SourceTable("ZONAS", "Zonas de clientes", ("CVE_ZON", "NOM_ZON")),
	SourceTable("SUBZONAS", "Subzonas de clientes", ("CVE_ZON", "CVE_SUB", "NOM_SUB")),
	SourceTable("PROVEDOR", "Proveedores", (
		"CVE_PROV", "NOM_PROV",
	), (
		"RFC_PROV", "DIR_PROV", "COL_PROV", "CD_PROV", "EDO_PROV", "CP_PROV",
		"PAIS_PROV", "EMAIL_PROV", "TEL1_PROV", "CONTACTO", "LIM_CRE", "DIA_CRE", "CURP_PROV",
		"CVE_IVA", "TOPERASAT",
	)),
	SourceTable("PROVXPRO", "Relación artículo-proveedor", (
		"CVE_PROD", "CVE_PROV",
	), ("CVE_MON", "U_COSTO", "NEW_MED", "PROV_STN", "DIASE", "UNIDADXML", "FACTORXML")),
)


def inspect_source(source_directory: str | Path) -> dict:
	"""Return structural readiness only; never return source record values."""
	root = Path(source_directory).expanduser().resolve(strict=True)
	if not root.is_dir():
		raise DBFError("El origen AlphaERP debe ser una carpeta.")
	dbf_files = {path.stem.upper(): path for path in root.rglob("*.DBF")}
	tables = []
	ready = True
	for spec in TABLES:
		path = dbf_files.get(spec.name)
		if not path:
			tables.append({"table": spec.name, "purpose": spec.purpose, "status": "missing"})
			ready = False
			continue
		schema = read_schema(path)
		available = {field.name.upper() for field in schema.fields}
		missing = sorted(set(spec.required_fields) - available)
		blocked = sorted(available & SENSITIVE_FIELDS)
		if missing:
			ready = False
		tables.append({
			"table": spec.name,
			"purpose": spec.purpose,
			"status": "ready" if not missing else "incompatible",
			"records": schema.record_count,
			"required_missing": missing,
			"allowed_fields": sorted(available & spec.allowed_fields),
			"blocked_fields": blocked,
		})
	return {"ready": ready, "table_count": len(tables), "tables": tables}
