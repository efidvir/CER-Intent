"""
Device Registry
===============
In-memory registry of the simulated 6G transport topology.
Holds 8 Ceragon nodes across 3 sectors with 10 bidirectional links.
"""
from __future__ import annotations

import copy
from typing import Dict, List, Optional, Set


# ──────────────────────────────────────────────────────────────────────────────
# Simulated 6G Transport Topology
# ──────────────────────────────────────────────────────────────────────────────

INITIAL_TOPOLOGY = {
    "nodes": [
        {
            "id": "mw-agg-1",
            "name": "Agg Node 1",
            "role": "transport",
            "model": "IP-50FX",
            "sector": "core-0",
            "x": 400,
            "y": 300,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-agg-2",
            "name": "Agg Node 2",
            "role": "transport",
            "model": "IP-50FX",
            "sector": "core-1",
            "x": 600,
            "y": 300,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-agg-3",
            "name": "Agg Node 3",
            "role": "transport",
            "model": "IP-50FX",
            "sector": "core-2",
            "x": 600,
            "y": 500,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-agg-4",
            "name": "Agg Node 4",
            "role": "transport",
            "model": "IP-50FX",
            "sector": "core-3",
            "x": 400,
            "y": 500,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "oran-core",
            "name": "5G Core",
            "role": "oran",
            "model": "Core-DC",
            "sector": "core-0",
            "x": 300,
            "y": 200,
            "max_throughput_gbps": 100.0
        },
        {
            "id": "oran-cu1",
            "name": "CU-NE",
            "role": "oran",
            "model": "O-CU",
            "sector": "core-1",
            "x": 700,
            "y": 200,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "oran-cu2",
            "name": "CU-SE",
            "role": "oran",
            "model": "O-CU",
            "sector": "core-2",
            "x": 700,
            "y": 600,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "oran-cu3",
            "name": "CU-SW",
            "role": "oran",
            "model": "O-CU",
            "sector": "core-3",
            "x": 300,
            "y": 600,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-hub-1",
            "name": "Hub Node 1",
            "role": "transport",
            "model": "IP-20N",
            "sector": "sector-1",
            "x": 250,
            "y": 300,
            "max_throughput_gbps": 5.0
        },
        {
            "id": "oran-du1",
            "name": "DU-1",
            "role": "oran",
            "model": "O-DU",
            "sector": "sector-1",
            "x": 180,
            "y": 300,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-hub-2",
            "name": "Hub Node 2",
            "role": "transport",
            "model": "IP-20N",
            "sector": "sector-2",
            "x": 750,
            "y": 300,
            "max_throughput_gbps": 5.0
        },
        {
            "id": "oran-du2",
            "name": "DU-2",
            "role": "oran",
            "model": "O-DU",
            "sector": "sector-2",
            "x": 820,
            "y": 300,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-hub-3",
            "name": "Hub Node 3",
            "role": "transport",
            "model": "IP-20N",
            "sector": "sector-3",
            "x": 750,
            "y": 500,
            "max_throughput_gbps": 5.0
        },
        {
            "id": "oran-du3",
            "name": "DU-3",
            "role": "oran",
            "model": "O-DU",
            "sector": "sector-3",
            "x": 820,
            "y": 500,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-hub-4",
            "name": "Hub Node 4",
            "role": "transport",
            "model": "IP-20N",
            "sector": "sector-4",
            "x": 250,
            "y": 500,
            "max_throughput_gbps": 5.0
        },
        {
            "id": "oran-du4",
            "name": "DU-4",
            "role": "oran",
            "model": "O-DU",
            "sector": "sector-4",
            "x": 180,
            "y": 500,
            "max_throughput_gbps": 10.0
        },
        {
            "id": "mw-tail-1",
            "name": "Tail 1",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-1",
            "x": 200,
            "y": 200,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru1",
            "name": "RU-1",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-1",
            "x": 175,
            "y": 150,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-2",
            "name": "Tail 2",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-1",
            "x": 300,
            "y": 200,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru2",
            "name": "RU-2",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-1",
            "x": 325,
            "y": 150,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-3",
            "name": "Tail 3",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-2",
            "x": 700,
            "y": 200,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru3",
            "name": "RU-3",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-2",
            "x": 675,
            "y": 150,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-4",
            "name": "Tail 4",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-2",
            "x": 800,
            "y": 200,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru4",
            "name": "RU-4",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-2",
            "x": 825,
            "y": 150,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-5",
            "name": "Tail 5",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-3",
            "x": 700,
            "y": 600,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru5",
            "name": "RU-5",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-3",
            "x": 675,
            "y": 650,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-6",
            "name": "Tail 6",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-3",
            "x": 800,
            "y": 600,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru6",
            "name": "RU-6",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-3",
            "x": 825,
            "y": 650,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-7",
            "name": "Tail 7",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-4",
            "x": 200,
            "y": 600,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru7",
            "name": "RU-7",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-4",
            "x": 175,
            "y": 650,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "mw-tail-8",
            "name": "Tail 8",
            "role": "transport",
            "model": "IP-20C",
            "sector": "sector-4",
            "x": 300,
            "y": 600,
            "max_throughput_gbps": 2.5
        },
        {
            "id": "oran-ru8",
            "name": "RU-8",
            "role": "oran",
            "model": "O-RU",
            "sector": "sector-4",
            "x": 325,
            "y": 650,
            "max_throughput_gbps": 2.5
        }
    ],
    "links": [
        {
            "id": "mw-ring-1",
            "src": "mw-agg-1",
            "dst": "mw-agg-2",
            "role": "mw",
            "capacity_gbps": 10.0,
            "distance_km": 5.0,
            "status": "active"
        },
        {
            "id": "mw-ring-2",
            "src": "mw-agg-2",
            "dst": "mw-agg-3",
            "role": "mw",
            "capacity_gbps": 10.0,
            "distance_km": 5.0,
            "status": "active"
        },
        {
            "id": "mw-ring-3",
            "src": "mw-agg-3",
            "dst": "mw-agg-4",
            "role": "mw",
            "capacity_gbps": 10.0,
            "distance_km": 5.0,
            "status": "active"
        },
        {
            "id": "mw-ring-4",
            "src": "mw-agg-4",
            "dst": "mw-agg-1",
            "role": "mw",
            "capacity_gbps": 10.0,
            "distance_km": 5.0,
            "status": "active"
        },
        {
            "id": "eth-core",
            "src": "oran-core",
            "dst": "mw-agg-1",
            "role": "ethernet",
            "capacity_gbps": 100.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "eth-cu1",
            "src": "oran-cu1",
            "dst": "mw-agg-2",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "eth-cu2",
            "src": "oran-cu2",
            "dst": "mw-agg-3",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "eth-cu3",
            "src": "oran-cu3",
            "dst": "mw-agg-4",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-branch-1",
            "src": "mw-agg-1",
            "dst": "mw-hub-1",
            "role": "mw",
            "capacity_gbps": 5.0,
            "distance_km": 3.0,
            "status": "active"
        },
        {
            "id": "eth-du1",
            "src": "oran-du1",
            "dst": "mw-hub-1",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-branch-2",
            "src": "mw-agg-2",
            "dst": "mw-hub-2",
            "role": "mw",
            "capacity_gbps": 5.0,
            "distance_km": 3.0,
            "status": "active"
        },
        {
            "id": "eth-du2",
            "src": "oran-du2",
            "dst": "mw-hub-2",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-branch-3",
            "src": "mw-agg-3",
            "dst": "mw-hub-3",
            "role": "mw",
            "capacity_gbps": 5.0,
            "distance_km": 3.0,
            "status": "active"
        },
        {
            "id": "eth-du3",
            "src": "oran-du3",
            "dst": "mw-hub-3",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-branch-4",
            "src": "mw-agg-4",
            "dst": "mw-hub-4",
            "role": "mw",
            "capacity_gbps": 5.0,
            "distance_km": 3.0,
            "status": "active"
        },
        {
            "id": "eth-du4",
            "src": "oran-du4",
            "dst": "mw-hub-4",
            "role": "ethernet",
            "capacity_gbps": 10.0,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-1",
            "src": "mw-hub-1",
            "dst": "mw-tail-1",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru1",
            "src": "oran-ru1",
            "dst": "mw-tail-1",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-2",
            "src": "mw-hub-1",
            "dst": "mw-tail-2",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru2",
            "src": "oran-ru2",
            "dst": "mw-tail-2",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-3",
            "src": "mw-hub-2",
            "dst": "mw-tail-3",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru3",
            "src": "oran-ru3",
            "dst": "mw-tail-3",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-4",
            "src": "mw-hub-2",
            "dst": "mw-tail-4",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru4",
            "src": "oran-ru4",
            "dst": "mw-tail-4",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-5",
            "src": "mw-hub-3",
            "dst": "mw-tail-5",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru5",
            "src": "oran-ru5",
            "dst": "mw-tail-5",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-6",
            "src": "mw-hub-3",
            "dst": "mw-tail-6",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru6",
            "src": "oran-ru6",
            "dst": "mw-tail-6",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-7",
            "src": "mw-hub-4",
            "dst": "mw-tail-7",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru7",
            "src": "oran-ru7",
            "dst": "mw-tail-7",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        },
        {
            "id": "mw-tail-link-8",
            "src": "mw-hub-4",
            "dst": "mw-tail-8",
            "role": "mw",
            "capacity_gbps": 2.5,
            "distance_km": 1.5,
            "status": "active"
        },
        {
            "id": "eth-ru8",
            "src": "oran-ru8",
            "dst": "mw-tail-8",
            "role": "ethernet",
            "capacity_gbps": 2.5,
            "distance_km": 0.1,
            "status": "active"
        }
    ]
}





class DeviceRegistry:
    """
    Central registry for the transport topology.
    Provides helpers to look up nodes/links by ID, sector, or target spec.
    """

    def __init__(self):
        self._topology = copy.deepcopy(INITIAL_TOPOLOGY)
        # Build lookup indices
        self._nodes: Dict[str, dict] = {n["id"]: n for n in self._topology["nodes"]}
        self._links: Dict[str, dict] = {l["id"]: l for l in self._topology["links"]}

    # ── Topology Accessors ────────────────────────────────────────────────────

    def get_topology(self) -> dict:
        return self._topology

    def get_node(self, node_id: str) -> Optional[dict]:
        return self._nodes.get(node_id)

    def get_link(self, link_id: str) -> Optional[dict]:
        return self._links.get(link_id)

    def get_all_nodes(self) -> List[dict]:
        return list(self._nodes.values())

    def get_all_links(self) -> List[dict]:
        return list(self._links.values())

    def get_nodes_in_sector(self, sector: str) -> List[dict]:
        return [n for n in self._nodes.values() if n.get("sector") == sector]

    def get_links_for_node(self, node_id: str) -> List[dict]:
        return [l for l in self._links.values()
                if l["src"] == node_id or l["dst"] == node_id]

    def get_all_identifiers(self) -> Set[str]:
        ids: Set[str] = set()
        ids.update(self._nodes.keys())
        ids.update(self._links.keys())
        ids.update({n["sector"] for n in self._nodes.values()})
        return ids

    # ── Target Resolution ─────────────────────────────────────────────────────

    def get_devices_for_target(self, target_type: str, identifier: str) -> List[dict]:
        """
        Resolve a target spec to a list of device dicts suitable for translators.
        Devices here represent either a node or endpoints of a link.
        """
        if target_type == "all":
            return self._all_device_dicts()

        if target_type == "link":
            link = self._links.get(identifier)
            if not link:
                return []
            # Return both endpoint nodes as the configurable devices
            src = self._nodes.get(link["src"])
            dst = self._nodes.get(link["dst"])
            devs = []
            for node in [src, dst]:
                if node:
                    devs.append(self._node_to_device(node, link_id=identifier))
            return devs

        if target_type == "node":
            node = self._nodes.get(identifier)
            return [self._node_to_device(node)] if node else []

        if target_type == "sector":
            nodes = self.get_nodes_in_sector(identifier)
            return [self._node_to_device(n) for n in nodes]

        return []

    def _all_device_dicts(self) -> List[dict]:
        return [self._node_to_device(n) for n in self._nodes.values()]

    def _node_to_device(self, node: dict, link_id: str = None) -> dict:
        return {
            "id": node["id"],
            "name": node["name"],
            "model": node.get("model", "IP-50FX"),
            "sector": node.get("sector", "unknown"),
            "max_throughput_gbps": node.get("max_throughput_gbps", 10.0),
            "link_id": link_id,
        }

    # ── State Mutation (called by adapters after config apply) ────────────────

    def update_link_status(self, link_id: str, status: str):
        if link_id in self._links:
            self._links[link_id]["status"] = status
            self._topology["links"] = list(self._links.values())

    def update_node_config(self, node_id: str, key: str, value):
        if node_id in self._nodes:
            self._nodes[node_id][key] = value
