"""Small, dependency-free reader for the Visual FoxPro DBF subset AlphaERP uses."""

from __future__ import annotations

import datetime as dt
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, Iterator


SUPPORTED_VERSIONS = {0x03, 0x30, 0x31, 0x32, 0x43, 0x63, 0x83, 0x8B, 0xCB, 0xF5}


class DBFError(ValueError):
	"""Raised when a source table is invalid or uses an unsupported layout."""


@dataclass(frozen=True)
class DBFField:
	name: str
	type: str
	length: int
	decimals: int
	offset: int


@dataclass(frozen=True)
class DBFSchema:
	path: Path
	version: int
	record_count: int
	header_length: int
	record_length: int
	fields: tuple[DBFField, ...]
	encoding: str


def read_schema(path: str | Path, *, encoding: str = "cp1252") -> DBFSchema:
	path = Path(path)
	with path.open("rb") as source:
		header = source.read(32)
		if len(header) != 32:
			raise DBFError(f"Cabecera DBF incompleta: {path.name}")
		version = header[0]
		if version not in SUPPORTED_VERSIONS:
			raise DBFError(f"Versión DBF no soportada 0x{version:02x}: {path.name}")
		record_count = struct.unpack("<I", header[4:8])[0]
		header_length = struct.unpack("<H", header[8:10])[0]
		record_length = struct.unpack("<H", header[10:12])[0]
		fields: list[DBFField] = []
		offset = 1  # deletion marker
		while source.tell() < header_length:
			descriptor = source.read(32)
			if not descriptor or descriptor[0] == 0x0D:
				break
			if len(descriptor) != 32:
				raise DBFError(f"Descriptor DBF incompleto: {path.name}")
			name = descriptor[:11].split(b"\0", 1)[0].decode("ascii", "replace").strip()
			field_type = chr(descriptor[11])
			length = descriptor[16]
			decimals = descriptor[17]
			fields.append(DBFField(name, field_type, length, decimals, offset))
			offset += length
		if offset > record_length:
			raise DBFError(f"Longitud de campos inválida: {path.name}")
	return DBFSchema(
		path=path,
		version=version,
		record_count=record_count,
		header_length=header_length,
		record_length=record_length,
		fields=tuple(fields),
		encoding=encoding,
	)


class DBFTable:
	"""Stream DBF records without loading a complete AlphaERP table in memory."""

	def __init__(self, path: str | Path, *, encoding: str = "cp1252"):
		self.schema = read_schema(path, encoding=encoding)

	def records(self, fields: set[str] | None = None) -> Iterator[dict]:
		requested = {value.upper() for value in fields} if fields else None
		selected = [
			field for field in self.schema.fields
			if requested is None or field.name.upper() in requested
		]
		if requested is not None:
			available = {field.name.upper() for field in selected}
			missing = requested - available
			if missing:
				raise DBFError(f"Campos ausentes en {self.schema.path.stem}: {', '.join(sorted(missing))}")
		with self.schema.path.open("rb") as source:
			source.seek(self.schema.header_length)
			for _index in range(self.schema.record_count):
				record = source.read(self.schema.record_length)
				if len(record) != self.schema.record_length:
					raise DBFError(f"Registro DBF incompleto: {self.schema.path.name}")
				if record[:1] == b"*":
					continue
				yield {
					field.name: _decode_value(record, field, self.schema.encoding)
					for field in selected
				}


def _decode_value(record: bytes, field: DBFField, encoding: str):
	raw = record[field.offset : field.offset + field.length]
	if field.type in {"C", "V"}:
		return raw.rstrip(b" \0").decode(encoding, "replace")
	if field.type in {"N", "F"}:
		value = raw.strip(b" \0")
		if not value:
			return None
		try:
			return Decimal(value.decode("ascii"))
		except InvalidOperation as exc:
			raise DBFError(f"Número inválido en {field.name}") from exc
	if field.type == "L":
		value = raw[:1].upper()
		return True if value in {b"Y", b"T"} else False if value in {b"N", b"F"} else None
	if field.type == "D":
		value = raw.strip(b" \0")
		if not value:
			return None
		try:
			return dt.datetime.strptime(value.decode("ascii"), "%Y%m%d").date().isoformat()
		except ValueError as exc:
			raise DBFError(f"Fecha inválida en {field.name}") from exc
	if field.type == "I" and len(raw) == 4:
		return struct.unpack("<i", raw)[0]
	if field.type == "Y" and len(raw) == 8:
		return Decimal(struct.unpack("<q", raw)[0]) / Decimal(10000)
	if field.type == "B" and len(raw) == 8:
		return struct.unpack("<d", raw)[0]
	# Memo/general and uncommon binary fields need their companion parser.  They
	# are never decoded implicitly, so a malformed or sensitive memo cannot leak.
	return None
