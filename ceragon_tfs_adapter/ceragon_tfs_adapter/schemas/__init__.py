"""
Ceragon YANG Schema Repository & Accessor
==========================================
Bundles the complete 84-module YANG 1.1 schema catalog covering the entire
Ceragon & Siklu product portfolio:
  - MultiHaul TG (N366, T261, T265, T280, TU-260) — radio-bridge-tg-* + Clixon/NACM/SNMP
  - EtherHaul (EH-500TX .. EH-8010FX)             — radio-bridge-eh-radio + radio-bridge-tg-*
  - FibeAir IP-20, IP-50, IP-100 (CeraOS)         — ceragon-* + RFC 8561 ietf-microwave-radio-link
  - Standard IETF / IEEE / IANA transport modules — ietf-interfaces, ietf-hardware, ietf-system,
    ietf-ip, ietf-ptp, ieee802-dot1q-sched (802.1Qbv), ieee802-dot1ae-macsec (802.1AE)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMAS_DIR = Path(__file__).resolve().parent / "yang"

_COMMENT_AND_STR_RE = re.compile(
    r'/\*.*?\*/|//[^\r\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
    re.DOTALL,
)
_IMPORT_INCLUDE_RE = re.compile(
    r"^\s*(import|include)\s+([A-Za-z0-9_\-\.]+)\s*\{",
    re.MULTILINE,
)
_HEADER_RE = re.compile(
    r"^\s*(module|submodule)\s+([A-Za-z0-9_\-\.]+)\s*\{",
    re.MULTILINE,
)
_NAMESPACE_RE = re.compile(r'\bnamespace\s+"([^"]+)"\s*;')
_PREFIX_RE = re.compile(r'\bprefix\s+"?([A-Za-z0-9_\-\.]+)"?\s*;')
_REVISION_RE = re.compile(r'\brevision\s+"?(\d{4}-\d{2}-\d{2})"?\s*\{')
_RPC_RE = re.compile(r"^\s*rpc\s+([A-Za-z0-9_\-\.]+)\s*(?:\{|;)", re.MULTILINE)
_NOTIFICATION_RE = re.compile(r"^\s*notification\s+([A-Za-z0-9_\-\.]+)\s*(?:\{|;)", re.MULTILINE)
_FEATURE_RE = re.compile(r"^\s*feature\s+([A-Za-z0-9_\-\.]+)\s*(?:\{|;)", re.MULTILINE)


def list_schemas() -> List[str]:
    """Return a sorted list of all available YANG module/submodule names."""
    if not SCHEMAS_DIR.exists():
        return []
    return sorted([f.stem.split("@")[0] for f in SCHEMAS_DIR.glob("*.yang")])


def get_schema_path(module_name: str) -> Optional[Path]:
    """Return the absolute Path to a given YANG module file, or None if not found."""
    clean_name = module_name.removesuffix(".yang").split("@")[0]
    path = SCHEMAS_DIR / f"{clean_name}.yang"
    if path.exists():
        return path
    matches = list(SCHEMAS_DIR.glob(f"{clean_name}@*.yang"))
    return matches[0] if matches else None


def get_schema_content(module_name: str) -> Optional[str]:
    """Read and return the raw YANG schema text for a module."""
    path = get_schema_path(module_name)
    if not path:
        return None
    return path.read_text(encoding="utf-8")


def get_all_schemas() -> Dict[str, str]:
    """Return a dictionary mapping module_name -> raw YANG content for all bundled modules."""
    res: Dict[str, str] = {}
    for mod in list_schemas():
        content = get_schema_content(mod)
        if content:
            res[mod] = content
    return res


def _strip_comments_and_strings(yang_text: str) -> str:
    """Remove C-style comments and string literals to safely parse structural YANG keywords."""
    return _COMMENT_AND_STR_RE.sub(" ", yang_text)


def get_schema_metadata(module_name: str) -> Optional[Dict[str, Any]]:
    """Parse structural metadata (kind, namespace, prefix, revisions, imports, includes, RPCs, notifications)."""
    raw = get_schema_content(module_name)
    if not raw:
        return None

    stripped = _strip_comments_and_strings(raw)
    hdr = _HEADER_RE.search(stripped)
    kind = hdr.group(1) if hdr else "module"
    name = hdr.group(2) if hdr else module_name.removesuffix(".yang")

    ns_match = _NAMESPACE_RE.search(raw)
    pfx_match = _PREFIX_RE.search(raw)
    revisions = sorted(set(_REVISION_RE.findall(raw)), reverse=True)

    imports: List[str] = []
    includes: List[str] = []
    for stmt, dep in _IMPORT_INCLUDE_RE.findall(stripped):
        if stmt == "import" and dep not in imports:
            imports.append(dep)
        elif stmt == "include" and dep not in includes:
            includes.append(dep)

    rpcs = _RPC_RE.findall(stripped)
    notifications = _NOTIFICATION_RE.findall(stripped)
    features = _FEATURE_RE.findall(stripped)

    if name.startswith("ceragon-") or name.startswith("ietf-microwave"):
        family_scope = "ceraos"
    elif name.startswith("radio-bridge-eh-"):
        family_scope = "siklu_eh"
    elif name.startswith("radio-bridge-tg-") or name.startswith("clixon-"):
        family_scope = "siklu_tg"
    else:
        family_scope = "standard"

    return {
        "name": name,
        "kind": kind,
        "family_scope": family_scope,
        "namespace": ns_match.group(1) if ns_match else None,
        "prefix": pfx_match.group(1) if pfx_match else None,
        "latest_revision": revisions[0] if revisions else None,
        "revisions": revisions,
        "imports": imports,
        "includes": includes,
        "rpcs": rpcs,
        "notifications": notifications,
        "features": features,
    }


def list_schema_catalog() -> List[Dict[str, Any]]:
    """Return metadata for every bundled YANG module and submodule."""
    out: List[Dict[str, Any]] = []
    for mod in list_schemas():
        meta = get_schema_metadata(mod)
        if meta:
            out.append(meta)
    return out


def get_schemas_for_family(family_or_flavor: str) -> List[str]:
    """
    Return the list of YANG modules applicable to a portfolio family or API flavor:
      - 'siklu_tg' / 'MultiHaul TG': radio-bridge-tg-* + clixon-* + standard IETF/MIB
      - 'siklu_eh' / 'EtherHaul':    radio-bridge-eh-radio + radio-bridge-tg-* + standard IETF/MIB
      - 'ceraos' / 'IP-20' / 'IP-50' / 'IP-100': ceragon-* + ietf-microwave-* + IEEE + standard IETF
    """
    token = (family_or_flavor or "").strip().lower()
    all_mods = list_schemas()
    if token in ("ceraos", "ip-20", "ip-50", "ip-100"):
        return [
            m for m in all_mods
            if m.startswith(("ceragon-", "ietf-", "iana-", "ieee802-"))
        ]
    if token in ("siklu_eh", "etherhaul"):
        return [
            m for m in all_mods
            if m.startswith(("radio-bridge-eh-", "radio-bridge-tg-", "ietf-", "iana-", "ieee802-", "IF-MIB", "SNMP", "IANA"))
        ]
    if token in ("siklu_tg", "multihaul tg", "terragraph"):
        return [
            m for m in all_mods
            if not m.startswith(("ceragon-", "radio-bridge-eh-"))
        ]
    return all_mods


def validate_schema_closure() -> Tuple[bool, Dict[str, Any]]:
    """
    Verify that:
      1. Every 'import' and 'include' across all bundled YANG files resolves to a bundled file.
      2. Every YANG file has balanced curly braces '{' and '}'.
    """
    available = set(list_schemas())
    missing_deps: Dict[str, List[str]] = {}
    unbalanced: List[str] = []
    total_rpcs = 0
    total_notifications = 0

    for mod in sorted(available):
        raw = get_schema_content(mod) or ""
        stripped = _strip_comments_and_strings(raw)
        if stripped.count("{") != stripped.count("}") or stripped.count("{") == 0:
            unbalanced.append(mod)
        meta = get_schema_metadata(mod)
        if not meta:
            continue
        total_rpcs += len(meta["rpcs"])
        total_notifications += len(meta["notifications"])
        for dep in meta["imports"] + meta["includes"]:
            if dep not in available:
                missing_deps.setdefault(dep, []).append(mod)

    ok = (len(missing_deps) == 0) and (len(unbalanced) == 0) and (len(available) > 0)
    return ok, {
        "closure_complete": ok,
        "total_schemas": len(available),
        "total_rpcs": total_rpcs,
        "total_notifications": total_notifications,
        "missing_dependencies": missing_deps,
        "unbalanced_modules": unbalanced,
    }
