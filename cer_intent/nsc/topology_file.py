"""
Planner topology from a TeraFlowSDN descriptor file
===================================================
The planner normally reads the topology from TeraFlowSDN. Without a controller
(dry runs, the dashboard demo, CI) it can read the same descriptor file that
would be loaded into TeraFlowSDN, for example
``emulation/containerlab/tfs-topology.json``:

  CER_INTENT_TOPOLOGY_FILE=emulation/containerlab/tfs-topology.json

Devices become nodes and each link becomes one undirected edge (TeraFlowSDN
descriptors list both directions). Link capacity comes from the optional
``attributes.total_capacity_gbps``; latency is left to the planner's default.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

ENV_VAR = "CER_INTENT_TOPOLOGY_FILE"

_RADIO_HINTS = ("radio", "wireless", "microwave", "ceragon")


def _uuid(obj: Dict[str, Any], key: str) -> str:
    return str(obj.get(key, {}).get(f"{key.split('_')[0]}_uuid", {}).get("uuid", ""))


def _is_radio(device_type: str) -> bool:
    t = device_type.lower()
    return any(h in t for h in _RADIO_HINTS)


def normalize_descriptor(data: Dict[str, Any], source: str = "file") -> Dict[str, Any]:
    """TeraFlowSDN descriptor (devices, links) -> planner topology {nodes, links, source}."""
    nodes: List[Dict[str, Any]] = []
    types: Dict[str, str] = {}
    for dev in data.get("devices", []):
        dev_id = _uuid(dev, "device_id")
        if not dev_id:
            continue
        dev_type = str(dev.get("device_type", ""))
        types[dev_id] = dev_type
        nodes.append({
            "id": dev.get("name") or dev_id,
            "tfs_uuid": dev_id,
            "type": dev_type,
            "role": "radio" if _is_radio(dev_type) else "transport",
            "drivers": list(dev.get("device_drivers", [])),
        })

    links: List[Dict[str, Any]] = []
    seen = set()
    for link in data.get("links", []):
        eps = link.get("link_endpoint_ids", [])
        if len(eps) < 2:
            continue
        a = eps[0].get("device_id", {}).get("device_uuid", {}).get("uuid", "")
        b = eps[1].get("device_id", {}).get("device_uuid", {}).get("uuid", "")
        a_ep = eps[0].get("endpoint_uuid", {}).get("uuid", "")
        b_ep = eps[1].get("endpoint_uuid", {}).get("uuid", "")
        key = frozenset({(a, a_ep), (b, b_ep)})
        if not a or not b or key in seen:
            continue
        seen.add(key)
        radio = _is_radio(types.get(a, "")) and _is_radio(types.get(b, ""))
        entry: Dict[str, Any] = {
            "id": link.get("link_id", {}).get("link_uuid", {}).get("uuid", f"{a}=={b}"),
            "source": a,
            "target": b,
            "source_port": a_ep,
            "target_port": b_ep,
            "type": "wireless-microwave" if radio else "ethernet",
        }
        cap = (link.get("attributes") or {}).get("total_capacity_gbps")
        if cap is not None:
            entry["capacity_mbps"] = float(cap) * 1000.0
        links.append(entry)

    return {"nodes": nodes, "links": links, "source": source}


def load_topology_file(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The topology from ``path`` (or $CER_INTENT_TOPOLOGY_FILE); None when unset or unreadable."""
    path = path or os.getenv(ENV_VAR, "").strip()
    if not path:
        return None
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return normalize_descriptor(data, source=f"file:{p.name}")
