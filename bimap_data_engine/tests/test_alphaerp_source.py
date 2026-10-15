from pathlib import Path
import struct
import tempfile
import unittest

from bimap_data_engine.services.alphaerp.catalog import SENSITIVE_FIELDS, TABLES
from bimap_data_engine.services.alphaerp.dbf import DBFTable, read_schema


def _write_dbf(path: Path):
	fields = [("CODE", "C", 8, 0), ("AMOUNT", "N", 8, 2), ("ACTIVE", "L", 1, 0)]
	header_length = 32 + (32 * len(fields)) + 1
	record_length = 1 + sum(field[2] for field in fields)
	header = bytearray(32)
	header[0] = 0x30
	header[4:8] = struct.pack("<I", 2)
	header[8:10] = struct.pack("<H", header_length)
	header[10:12] = struct.pack("<H", record_length)
	descriptors = bytearray()
	for name, field_type, length, decimals in fields:
		descriptor = bytearray(32)
		descriptor[: len(name)] = name.encode("ascii")
		descriptor[11] = ord(field_type)
		descriptor[16] = length
		descriptor[17] = decimals
		descriptors.extend(descriptor)
	records = b" " + b"A-01    " + b"   12.50" + b"T"
	records += b"*" + b"OLD     " + b"   1.00" + b"F"
	path.write_bytes(bytes(header) + bytes(descriptors) + b"\r" + records + b"\x1a")


class TestAlphaERPSource(unittest.TestCase):
	def test_streams_active_visual_foxpro_records(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "SAMPLE.DBF"
			_write_dbf(path)
			schema = read_schema(path)
			self.assertEqual(schema.record_count, 2)
			self.assertEqual([field.name for field in schema.fields], ["CODE", "AMOUNT", "ACTIVE"])
			self.assertEqual(
				list(DBFTable(path).records()),
				[{"CODE": "A-01", "AMOUNT": 12.50, "ACTIVE": True}],
			)

	def test_sensitive_fields_are_never_allowlisted(self):
		for table in TABLES:
			self.assertFalse(table.allowed_fields & SENSITIVE_FIELDS)
