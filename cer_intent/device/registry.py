"""
Device Registry
===============
In-memory registry of the simulated 6G transport topology.
Holds 8 Ceragon nodes across 3 sectors with 10 bidirectional links.
"""
from __future__ import annotations

import copy
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


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





import logging
logger = logging.getLogger(__name__)


class DeviceRegistry:
    """
    Central registry for the transport topology.
    Uses ETSI TeraFlowSDN (TFS) as the authoritative Source of Truth (SoT).
    Provides helpers to look up nodes/links by ID, name, TFS UUID, sector, or target spec.
    """

    def __init__(self, tfs_client: Optional[Any] = None):
        self._topology = copy.deepcopy(INITIAL_TOPOLOGY)
        self._source_of_truth = "InitialStatic"
        self._id_to_tfs_uuid: Dict[str, str] = {}
        self._tfs_uuid_to_id: Dict[str, str] = {}
        self._nodes: Dict[str, dict] = {}
        self._links: Dict[str, dict] = {}

        from cer_intent.device.tfs_client import TFSClient
        self._tfs_client = tfs_client or TFSClient()

        # 1. Attempt live sync from TeraFlowSDN (Source of Truth)
        synced = self.sync_from_tfs()

        # 2. If TFS is unreachable, fallback to cached state files
        if not synced:
            self._load_fallback_topology()

        # Twin with default XML if present
        default_xml = os.getenv(
            "IP50C_TEMPLATE_XML",
            "c:/CER_Intent/Yossi/IP-50C_AI_chat_configuration_tool/IP50c_default_5.xml"
        )
        self.twin_with_xml(default_xml)

    def sync_from_tfs(self) -> bool:
        """
        Query TeraFlowSDN NBI live and update the internal registry state.
        Returns True if successfully synchronized from TFS.
        """
        import os
        import json

        try:
            is_connected, msg = self._tfs_client.check_connection()
            if not is_connected:
                logger.warning(f"[Registry] TFS unreachable: {msg}. Using fallback topology.")
                return False

            logger.info("[Registry] Syncing topology live from TeraFlowSDN...")
            tfs_topo = self._tfs_client.fetch_normalized_topology()

            if tfs_topo.get("nodes"):
                self._topology = {
                    "nodes": tfs_topo["nodes"],
                    "links": tfs_topo["links"],
                    "source": "TeraFlowSDN",
                    "context": tfs_topo.get("context", "admin"),
                    "topology": tfs_topo.get("topology", "admin"),
                }
                self._source_of_truth = "TeraFlowSDN"
                self._rebuild_indices()

                # Cache fresh state to local file for offline resilience
                try:
                    os.makedirs("data", exist_ok=True)
                    state_file = os.getenv("STATE_FILE", "data/topology_state.json")
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "nodes": self._topology["nodes"],
                            "links": self._topology["links"],
                            "source": "TeraFlowSDN",
                            "last_synced": datetime.now(timezone.utc).isoformat() if "datetime" in globals() else ""
                        }, f, indent=2)
                except Exception as ex:
                    logger.warning(f"[Registry] Failed to cache topology to {state_file}: {ex}")

                logger.info(f"[Registry] Successfully synced from TFS: {len(self._topology['nodes'])} nodes, {len(self._topology['links'])} links.")
                return True

        except Exception as e:
            logger.error(f"[Registry] Error syncing topology from TFS: {e}")

        return False

    def _load_fallback_topology(self):
        """Fallback loader for offline or cold-start scenarios."""
        import os
        import json

        tf_topo_paths = [
            os.getenv("STATE_FILE", "data/topology_state.json"),
            "data/6g_transport_tfs_descriptors.json",
            "data/tf_topology_details.json",
        ]
        for tf_topo_path in tf_topo_paths:
            if os.path.exists(tf_topo_path):
                try:
                    with open(tf_topo_path, "r", encoding="utf-8") as f:
                        tf_data = json.load(f)

                    cer_topo = tf_data.get("_cer_intent_topology")
                    if cer_topo and cer_topo.get("nodes") and cer_topo.get("links"):
                        self._topology = cer_topo
                        self._source_of_truth = f"File:{tf_topo_path} (_cer_intent_topology)"
                        break

                    if "nodes" in tf_data and "links" in tf_data:
                        self._topology = {
                            "nodes": tf_data["nodes"],
                            "links": tf_data["links"],
                        }
                        self._source_of_truth = f"File:{tf_topo_path}"
                        break
                except Exception:
                    pass

        self._rebuild_indices()

    def _rebuild_indices(self):
        """Rebuild internal lookup tables supporting shorthand IDs, names, and TFS UUIDs."""
        self._nodes = {}
        self._links = {}
        self._id_to_tfs_uuid = {}
        self._tfs_uuid_to_id = {}

        for n in self._topology.get("nodes", []):
            nid = n["id"]
            self._nodes[nid] = n
            # Alias by name
            name = n.get("name")
            if name:
                self._nodes[name] = n
            # Alias by TFS UUID if present
            tfs_uuid = n.get("tfs_uuid")
            if tfs_uuid:
                self._nodes[tfs_uuid] = n
                self._id_to_tfs_uuid[nid] = tfs_uuid
                self._tfs_uuid_to_id[tfs_uuid] = nid

        for l in self._topology.get("links", []):
            lid = l["id"]
            self._links[lid] = l
            lname = l.get("name")
            if lname:
                self._links[lname] = l
            tfs_uuid = l.get("tfs_uuid")
            if tfs_uuid:
                self._links[tfs_uuid] = l

    def get_source_of_truth(self) -> str:
        """Returns the current Source of Truth for the topology (e.g. 'TeraFlowSDN')."""
        return self._source_of_truth

    def get_tfs_uuid(self, identifier: str) -> Optional[str]:
        """Resolve any shorthand ID or name to its official TFS UUID."""
        if identifier in self._id_to_tfs_uuid:
            return self._id_to_tfs_uuid[identifier]
        node = self._nodes.get(identifier)
        if node and "tfs_uuid" in node:
            return node["tfs_uuid"]
        return None

    def get_shorthand_id(self, identifier: str) -> Optional[str]:
        """Resolve a TFS UUID or name to its canonical shorthand ID."""
        if identifier in self._tfs_uuid_to_id:
            return self._tfs_uuid_to_id[identifier]
        node = self._nodes.get(identifier)
        if node and "id" in node:
            return node["id"]
        return None

    def twin_with_xml(self, xml_path: str):
        """
        Twins the registry topology with a physical Ceragon device's XML configuration.
        """
        import os
        import xml.etree.ElementTree as ET
        
        # Translate Windows paths for WSL/Linux compatibility
        if os.name != 'nt' and xml_path.lower().startswith("c:"):
            xml_path = "/mnt/c" + xml_path[2:]

        if not os.path.exists(xml_path):
            return

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Find device elements
            for device_el in root.findall(".//Device"):
                dev_id = f"xml-dev-{device_el.get('id')}"
                dev_type = device_el.get("type", "IP-50C")
                
                # Extract unit name from Platform params
                unit_name = dev_type
                name_param = device_el.find(".//Platform/Param[@id='UNIT_NAME']")
                if name_param is not None:
                    unit_name = name_param.get("value", dev_type)

                # Check if we already have this node in topology
                if dev_id not in self._nodes:
                    # Dynamically add to topology
                    node_data = {
                        "id": dev_id,
                        "name": f"{unit_name} (Physical)",
                        "role": "transport",
                        "model": dev_type,
                        "sector": "physical-sector",
                        "x": 500,
                        "y": 400,
                        "max_throughput_gbps": 2.5
                    }
                    self._topology["nodes"].append(node_data)
                    self._nodes[dev_id] = node_data
                else:
                    self._nodes[dev_id]["name"] = f"{unit_name} (Physical)"
                    self._nodes[dev_id]["model"] = dev_type

                # Dynamically add link connecting physical node to mw-agg-1 to plug it into the network
                link_id = f"link-{dev_id}-to-mw-agg-1"
                if link_id not in self._links:
                    link_data = {
                        "id": link_id,
                        "src": dev_id,
                        "dst": "mw-agg-1",
                        "role": "mw",
                        "capacity_gbps": 2.5,
                        "distance_km": 2.0,
                        "status": "active"
                    }
                    self._topology["links"].append(link_data)
                    self._links[link_id] = link_data
        except Exception as e:
            pass

    # ── Topology Accessors ────────────────────────────────────────────────────

    def get_topology(self) -> dict:
        return self._topology

    def get_node(self, node_id: str) -> Optional[dict]:
        return self._nodes.get(node_id)

    def get_link(self, link_id: str) -> Optional[dict]:
        return self._links.get(link_id)

    def get_all_nodes(self) -> List[dict]:
        return list(self._topology.get("nodes", []))

    def get_all_links(self) -> List[dict]:
        return list(self._topology.get("links", []))

    def get_nodes_in_sector(self, sector: str) -> List[dict]:
        return [n for n in self._topology.get("nodes", []) if n.get("sector") == sector]

    def get_links_for_node(self, node_id: str) -> List[dict]:
        # Resolve to both shorthand ID and TFS UUID for matching
        node = self.get_node(node_id)
        valid_ids = {node_id}
        if node:
            valid_ids.add(node.get("id"))
            valid_ids.add(node.get("name"))
            valid_ids.add(node.get("tfs_uuid"))
        valid_ids.discard(None)
        return [l for l in self._topology.get("links", [])
                if l["src"] in valid_ids or l["dst"] in valid_ids]

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

        if target_type in ("node", "device"):
            node = self.get_node(identifier)
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
