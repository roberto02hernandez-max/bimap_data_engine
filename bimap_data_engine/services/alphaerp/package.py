"""Read an allowlisted AlphaERP database folder as a versioned source package."""

from __future__ import annotations

import hashlib
from pathlib import Path

from bimap_data_engine.services.alphaerp.dbf import DBFError, DBFTable, read_schema


TABLE_FIELDS = {
	"CLIENTES": {
		"CVE_CTE", "NOM_CTE", "NOM_FAC", "RFC_CTE", "IDFISCAL", "CURP_CTE",
		"DIR_CTE", "NE_CTE", "NI_CTE", "COL_CTE", "CD_CTE", "DELEGA_CTE",
		"EDO_CTE", "CP_CTE", "PAIS_CTE", "EMAIL_CTE", "TEL1_CTE", "TEL2_CTE",
		"DIR_FAC", "NE_FAC", "NI_FAC", "COL_FAC", "CD_FAC", "DELEGA_FAC",
		"EDO_FAC", "CP_FAC", "PAIS_FAC",
		"CONTACTO", "NOM_ENT", "DIR_ENT", "NE_ENT", "NI_ENT", "COL_ENT", "CD_ENT",
		"DELEGA_ENT", "EDO_ENT", "CP_ENT", "RESI_ENT", "CVE_ZON", "CVE_SUB",
		"CVE_CAN", "CVE_AGE", "LISTA_PREC", "LIM_CRE", "DIA_CRE", "CVE_IVA",
		"CVE_MONSTA", "REGI_CTE", "REGI_CTERE", "USO_CTE", "METP_CTE",
		"CMETPSAT", "CONTADO", "FALTA_CTE", "TRANS",
	},
	"AGENTES": {
		"CVE_AGE", "NOM_AGE", "COM_AGE", "TIPO_AGE", "AREA_AGE", "EMAIL_AGE",
	},
	"CLIENXML": {
		"CVE_CTE", "REGI_CTE", "REGI_CTERE", "USO_CTE", "METP_CTE", "CMETPSAT",
		"RFC_OFI", "NOM_OFI", "DIR_OFI", "NE_OFI", "NI_OFI", "COL_OFI",
		"CD_OFI", "DELEGA_OFI", "EDO_OFI", "CP_OFI", "RESI_OFI", "REGI_OFI",
	},
	"CONTACTO": {
		"CVE_CTE", "NUM", "NOMBRE", "PUESTO", "LADA", "TEL1", "TEL2", "EXT",
		"MOVIL", "EMAIL", "FIRMARDOC", "NOTSAIERP",
	},
	"CTEDIR": {
		"CVEDIRENT", "CVE_CTE", "NOM_ENT", "DIR_ENT", "NE_ENT", "NI_ENT", "COL_ENT",
		"CD_ENT", "DELEGA_ENT", "EDO_ENT", "CP_ENT", "RESI_ENT",
	},
	"ZONAS": {"CVE_ZON", "NOM_ZON"},
	"SUBZONAS": {"CVE_ZON", "CVE_SUB", "NOM_SUB"},
	"TIPOIVAC": {
		"CVE_IVA", "DESC_IVA", "TASA_IVA", "TAS_RETIVA", "TAS_RETISR", "CONIEPS",
		"CTA_IVAPAG", "CTA_RETIVA", "CTA_RETISR", "CTA_IEPS", "TASAIMP1", "TASAIMP2",
	},
	"PROVEDOR": {
		"CVE_PROV", "NOM_PROV", "RFC_PROV", "IDFISCAL", "CURP_PROV", "DIR_PROV",
		"NE_PROV", "NI_PROV", "COL_PROV", "CD_PROV", "DELEGA_PRO", "EDO_PROV",
		"CP_PROV", "PAIS_PROV", "EMAIL_PROV", "TEL1_PROV", "TEL2_PROV", "CONTACTO",
		"NOM_ENT", "DIR_ENT", "NE_ENT", "NI_ENT", "COL_ENT", "CD_ENT", "DELEGA_ENT",
		"EDO_ENT", "CP_ENT", "PAIS_ENT", "LIM_CRE", "DIA_CRE", "CVE_IVA", "CVE_MONDES",
		"TOPERASAT", "PAISSAT", "NACIONSAT", "FALTA_PROV", "TRANS",
	},
	"TIPOIVAP": {
		"CVE_IVA", "DESC_IVA", "TASA_IVA", "TAS_RETIVA", "TAS_RETISR", "CONIEPS",
		"CTA_IVAACR", "CTA_IVAIMP", "CTA_RETIVA", "CTA_RETISR", "CTA_IEPS",
		"TOPERASAT", "EXENTO", "TASAIMP1", "TASAIMP2",
	},
	"PRODUCTO": {
		"CVE_PROD", "NOM_PROD", "DESC_PROD", "DESC_PROD2", "CSE_PROD", "SUB_CSE",
		"SUB_SUBCSE", "UNI_MED", "UNI_MED_P", "UNI_EMB", "PZAS", "CODBAR", "LISTA_MED",
		"STALOTE", "DIASVIDA", "C_PRDS", "USO_PRD", "STAIVA", "PORCENIVA", "STARETIVA",
		"PORRETIVA", "STARETISR", "PORRETISR", "STAIEPS", "PORCENIEPS", "TIPO_IEPS",
		"UNI_IEPS", "MONTO_IEPS", "IVA_IEPS", "STAPITEX", "NOOBJI", "CVE_PROV",
		"PROV_STD", "PESO", "PESOP", "ALTOP", "LARGOP", "ANCHOP", "TRANS",
	},
	"CLASES": {"CSE_PROD", "DES_CSE"},
	"SUBCLASE": {"CSE_PROD", "SUB_CSE", "DES_SUB"},
	"SUB2CLAS": {"CSE_PROD", "SUB_CSE", "SUB_SUBCSE", "DESSUBSUB"},
	"UNIDAD": {"UNIDAD", "DESCUNIDAD", "C_UNIS"},
	"MONEDAS": {"CVE_MON", "DES_MON", "MONSAT"},
	"PRODUNID": {
		"CVE_PROD", "UNIDAD", "FACTOR", "CONVER", "CODBAR1", "NEW_MED", "PESOE", "ALTOE", "LARGOE", "ANCHOE",
	},
	"PRODMED": {
		"LISTA_MED", "CVE_PROD", "NEW_MED", "CODBAR", "DATO_1", "DATO_2", "DATO_3",
		"DATO_4", "DATO_5", "DATO_6", "DATO_7", "DATO_8", "DATO_9", "DATO_10",
		"DATO_11", "DATO_12",
	},
	"ATRIBUTO": {"LISTA_MED", "NEW_MED", "IND_MED", "DESC_MED"},
	"CATLISPRE": {"NLISPRE", "DESLISPRE", "STA_LISTA"},
	"PRECIPROD": {"CVE_PROD", "NLISPRE", "LPRECPROD", "LEXCDESD", "LEXCHAST"},
	"PRECIMED": {"CVE_PROD", "MLISPRE", "NLISPRE", "LPRECPROD", "LEXCDESD", "LEXCHAST"},
	"CTEXPROD": {"CVE_CTE", "CVE_PROD", "NEW_MED", "CVE_MON", "U_PRECIO", "F_U_PRECIO"},
	"PROVXPRO": {
		"CVE_PROD", "CVE_PROV", "CVE_MON", "U_COSTO", "F_U_COSTO", "COTIZADO",
		"F_COTIZADO", "NEW_MED", "PROV_STN", "DIASE", "UNIDADXML", "FACTORXML", "CVESATXML",
	},
}


class AlphaERPPackage:
	"""A filesystem package whose exposed surface is restricted to TABLE_FIELDS."""

	def __init__(self, source_directory: str | Path, *, encoding: str = "cp1252"):
		self.root = Path(source_directory).expanduser().resolve(strict=True)
		if not self.root.is_dir():
			raise DBFError("El origen AlphaERP debe ser una carpeta.")
		self.encoding = encoding
		self.paths = {path.stem.upper(): path for path in self.root.rglob("*.DBF")}

	def rows(self, table: str) -> list[dict]:
		table = table.upper()
		if table not in TABLE_FIELDS:
			raise DBFError(f"Tabla AlphaERP no autorizada: {table}")
		path = self.paths.get(table)
		if not path:
			return []
		available = {field.name.upper() for field in read_schema(path, encoding=self.encoding).fields}
		fields = TABLE_FIELDS[table] & available
		return list(DBFTable(path, encoding=self.encoding).records(fields))

	def manifest(self) -> dict:
		entries = []
		hash_value = hashlib.sha256()
		for table in sorted(TABLE_FIELDS):
			path = self.paths.get(table)
			if not path:
				entries.append({"table": table, "present": False, "records": 0})
				continue
			schema = read_schema(path, encoding=self.encoding)
			relative = path.relative_to(self.root).as_posix()
			stat = path.stat()
			hash_value.update(f"{relative}\0{stat.st_size}\0{schema.record_count}\n".encode())
			entries.append({
				"table": table, "present": True, "records": schema.record_count,
				"size": stat.st_size,
			})
		return {"fingerprint": hash_value.hexdigest(), "tables": entries}

	def load(self) -> dict[str, list[dict]]:
		return {table: self.rows(table) for table in TABLE_FIELDS}
