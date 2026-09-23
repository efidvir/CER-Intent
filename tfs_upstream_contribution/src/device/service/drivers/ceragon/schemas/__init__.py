# Copyright 2026 Ceragon Networks Ltd. & ETSI TeraFlowSDN Authors
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
YANG Schema Registry for Ceragon Wireless Transport Devices
============================================================
Provides direct access to all 51 RFC-compliant YANG data models
extracted from physical Ceragon transport nodes (MultiHaul TG, EtherHaul, CeraOS).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

YANG_DIR = Path(__file__).parent / "yang"


def get_yang_directory() -> Path:
    """Return the absolute path to the directory containing YANG definitions."""
    return YANG_DIR


def list_available_schemas() -> List[str]:
    """Return a sorted list of all bundled YANG module names (without .yang extension)."""
    if not YANG_DIR.exists():
        return []
    return sorted([f.stem for f in YANG_DIR.glob("*.yang")])


def get_schema_content(module_name: str) -> Optional[str]:
    """Retrieve raw YANG schema text for a given module name."""
    clean_name = module_name.replace(".yang", "")
    target = YANG_DIR / f"{clean_name}.yang"
    if target.exists() and target.is_file():
        return target.read_text(encoding="utf-8")
    return None


def get_all_schemas() -> Dict[str, str]:
    """Return a dictionary mapping module_name -> raw YANG content."""
    schemas = {}
    for name in list_available_schemas():
        content = get_schema_content(name)
        if content is not None:
            schemas[name] = content
    return schemas
