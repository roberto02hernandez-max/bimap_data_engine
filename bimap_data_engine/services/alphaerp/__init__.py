"""AlphaERP (Visual FoxPro) source support for BIMAP Data Engine.

This package only reads and normalizes source data.  Creation and validation of
ERPNext documents remains the responsibility of the generic import engine.
"""

from bimap_data_engine.services.alphaerp.catalog import inspect_source
from bimap_data_engine.services.alphaerp.normalize import normalize_package, normalize_tables

__all__ = ["inspect_source", "normalize_package", "normalize_tables"]
