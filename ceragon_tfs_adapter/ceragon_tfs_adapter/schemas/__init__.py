"""
Ceragon YANG Schema Repository & Accessor.
Bundles the complete 51-module YANG schema definitions extracted from Ceragon devices.
"""

from pathlib import Path
from typing import List, Dict, Optional

SCHEMAS_DIR = Path(__file__).resolve().parent / "yang"


def list_schemas() -> List[str]:
    """Return a sorted list of all available YANG module names."""
    if not SCHEMAS_DIR.exists():
        return []
    return sorted([f.stem for f in SCHEMAS_DIR.glob("*.yang")])


def get_schema_path(module_name: str) -> Optional[Path]:
    """Return the absolute Path to a given YANG module file, or None if not found."""
    clean_name = module_name.removesuffix(".yang")
    path = SCHEMAS_DIR / f"{clean_name}.yang"
    return path if path.exists() else None


def get_schema_content(module_name: str) -> Optional[str]:
    """Read and return the raw YANG schema text for a module."""
    path = get_schema_path(module_name)
    if not path:
        return None
    return path.read_text(encoding="utf-8")


def get_all_schemas() -> Dict[str, str]:
    """Return a dictionary mapping module_name -> raw YANG content for all bundled modules."""
    res = {}
    for mod in list_schemas():
        content = get_schema_content(mod)
        if content:
            res[mod] = content
    return res
