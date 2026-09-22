"""
TeraFlowSDN (TFS) Client
========================
High-level client for the ETSI TeraFlowSDN Northbound Interface (NBI) REST API.
Serves as the primary bridge establishing TFS as the authoritative Source of Truth (SoT)
for network topology, device inventory, capabilities, operational parameters, and slicing.
"""
from __future__ import annotations

import json
import logging
import math
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Deterministic UUID Namespace used by 6G generator for shorthand node/link names
NAMESPACE_6G = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def make_uuid(name: str) -> str:
    """Generate a deterministic UUID string based on node/link name."""
    return str(uuid.uuid5(NAMESPACE_6G, str(name)))


class TFSClient:
    """
    Client for interacting with ETSI TeraFlowSDN Northbound Interface (NBI).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        context_name: Optional[str] = None,
        topology_name: Optional[str] = None,
        timeout: int = 10,
    ):
        self.base_url = (base_url or os.getenv("TERAFLOW_URL", "http://localhost:8088")).rstrip("/")
        self.context_name = context_name or os.getenv("TFS_CONTEXT", "admin")
        self.topology_name = topology_name or os.getenv("TFS_TOPOLOGY", "admin")
        self.timeout = int(os.getenv("TERAFLOW_TIMEOUT_SEC", str(timeout)))
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        token = os.getenv("TERAFLOW_TOKEN")
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    # ── Health & Connection Check ─────────────────────────────────────────────

    def check_connection(self) -> Tuple[bool, str]:
        """Test whether TFS NBI is accessible."""
        url = f"{self.base_url}/tfs-api/contexts"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return True, f"Connected to TFS at {self.base_url}"
            return False, f"TFS responded with HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to TFS NBI at {self.base_url} (Connection refused/unreachable)"
        except Exception as e:
            return False, f"TFS connection error: {e}"

    # ── Topology Retrieval ───────────────────────────────────────────────────

    def get_topology_details(
        self,
        context_uuid: Optional[str] = None,
        topology_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch full topology details (devices, links) from TFS NBI.
        """
        ctx = context_uuid or self.context_name
        topo = topology_uuid or self.topology_name
        url = f"{self.base_url}/tfs-api/context/{ctx}/topology_details/{topo}"
        logger.info(f"[TFS] GET {url}")
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_devices(self) -> List[Dict[str, Any]]:
        """Fetch all devices registered in TFS."""
        url = f"{self.base_url}/tfs-api/devices"
        logger.info(f"[TFS] GET {url}")
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("devices", [])

    def get_device(self, device_uuid: str) -> Dict[str, Any]:
        """Fetch a specific device by UUID from TFS."""
        url = f"{self.base_url}/tfs-api/device/{device_uuid}"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_links(self) -> List[Dict[str, Any]]:
        """Fetch all links registered in TFS."""
        url = f"{self.base_url}/tfs-api/links"
        logger.info(f"[TFS] GET {url}")
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("links", [])

    def get_link(self, link_uuid: str) -> Dict[str, Any]:
        """Fetch a specific link by UUID from TFS."""
        url = f"{self.base_url}/tfs-api/link/{link_uuid}"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── Device Configuration ──────────────────────────────────────────────────

    def configure_device(self, device_uuid: str, config_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update configuration rules on a device in TFS via PUT /tfs-api/device/{device_uuid}.
        Sends config_rules to TFS DeviceService, which merges them into device configuration.
        """
        payload = {
            "device_id": {"device_uuid": {"uuid": device_uuid}},
            "device_config": {"config_rules": config_rules},
        }

        url = f"{self.base_url}/tfs-api/device/{device_uuid}"
        logger.info(f"[TFS] PUT {url} with {len(config_rules)} config rules")
        resp = self._session.put(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {"status": "success"}

    # ── Slicing Management ───────────────────────────────────────────────────

    def get_slices(self, context_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all network slices in the specified context."""
        ctx = context_uuid or self.context_name
        url = f"{self.base_url}/tfs-api/context/{ctx}/slices"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("slices", [])

    def create_or_update_slice(self, slice_payload: Dict[str, Any], context_uuid: Optional[str] = None) -> Dict[str, Any]:
        """Create or update a network slice in TFS."""
        ctx = context_uuid or self.context_name
        url = f"{self.base_url}/tfs-api/context/{ctx}/slices"
        logger.info(f"[TFS] POST {url}")
        resp = self._session.post(url, json={"slices": [slice_payload]}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ── Normalized Topology Mapping ──────────────────────────────────────────

    def fetch_normalized_topology(self) -> Dict[str, Any]:
        """
        Queries TFS and returns a fully normalized CER-Intent topology dict:
        {
            "nodes": [...],
            "links": [...],
            "source": "TeraFlowSDN",
            "context": self.context_name,
            "topology": self.topology_name
        }
        """
        tfs_data = self.get_topology_details()
        tfs_devices = tfs_data.get("devices", [])
        tfs_links = tfs_data.get("links", [])

        # Load known metadata template if available (for exact layout positions)
        metadata_nodes = {}
        metadata_links = {}
        ref_path = "data/6g_transport_tfs_descriptors.json"
        if os.path.exists(ref_path):
            try:
                with open(ref_path, "r", encoding="utf-8") as f:
                    ref_data = json.load(f)
                    cer_meta = ref_data.get("_cer_intent_topology", {})
                    for n in cer_meta.get("nodes", []):
                        metadata_nodes[n["id"]] = n
                        metadata_nodes[make_uuid(n["id"])] = n
                        metadata_nodes[n["name"]] = n
                    for l in cer_meta.get("links", []):
                        metadata_links[l["id"]] = l
                        metadata_links[make_uuid(l["id"])] = l
                        if "name" in l:
                            metadata_links[l["name"]] = l
            except Exception as e:
                logger.warning(f"Could not load reference layout metadata: {e}")

        # 1. Transform Devices -> Nodes
        nodes = []
        for i, dev in enumerate(tfs_devices):
            dev_uuid = dev.get("device_id", {}).get("device_uuid", {}).get("uuid", f"dev-{i}")
            dev_name = dev.get("name", dev_uuid)
            dev_type = dev.get("device_type", "emu-packet-router")
            dev_status = dev.get("device_operational_status", "DEVICEOPERATIONALSTATUS_ENABLED")

            # Extract capabilities from config rules if present
            caps = {}
            op_params = {}
            for rule in dev.get("device_config", {}).get("config_rules", []):
                custom = rule.get("custom", {})
                k = custom.get("resource_key", "")
                v = custom.get("resource_value", "")
                if k == "/device/capabilities" and isinstance(v, str):
                    try: caps = json.loads(v)
                    except Exception: pass
                elif k == "/device/operating_parameters" and isinstance(v, str):
                    try: op_params = json.loads(v)
                    except Exception: pass

            meta = metadata_nodes.get(dev_uuid) or metadata_nodes.get(dev_name) or {}
            
            # If config rules were omitted by topology_details (standard TFS optimization),
            # fetch full device details for physical Ceragon hardware
            if not caps and ("ceragon" in dev_name.lower() or "ctu" in dev_name.lower()):
                try:
                    full_dev = self.get_device(dev_uuid)
                    for rule in full_dev.get("device_config", {}).get("config_rules", []):
                        custom = rule.get("custom", {})
                        k = custom.get("resource_key", "")
                        v = custom.get("resource_value", "")
                        if k == "/device/capabilities" and isinstance(v, str):
                            try: caps = json.loads(v)
                            except Exception: pass
                        elif k == "/device/operating_parameters" and isinstance(v, str):
                            try: op_params = json.loads(v)
                            except Exception: pass
                        elif k == "/device/hardware_info" and isinstance(v, str):
                            try: caps["hardware_info"] = json.loads(v)
                            except Exception: pass
                except Exception as ex:
                    logger.debug(f"Could not fetch full details for device {dev_uuid}: {ex}")

            node_id = meta.get("id") or dev_name.lower().replace(" ", "-").replace("&", "and")
            
            # Model resolution
            model = caps.get("model") or meta.get("model")
            if not model:
                if "MH-T261" in dev_name or "T261" in dev_name:
                    model = "MH-T261"
                elif "IP-50C" in dev_name:
                    model = "IP-50C"
                elif "IP-50E" in dev_name:
                    model = "IP-50E"
                elif "router" in dev_type:
                    model = "IP-50FX"
                else:
                    model = "Generic"

            # Role & Sector resolution
            role = caps.get("role") or meta.get("role")
            if not role:
                if "mmwave" in str(model).lower() or "mh-t" in str(model).lower():
                    role = "mmwave_transport"
                else:
                    role = "transport"

            is_physical = "ceragon" in dev_name.lower() or "ctu" in dev_name.lower()
            sector = meta.get("sector") or ("sector-physical-lab" if is_physical else "sector-teraflow")
            max_tp = float(caps.get("max_throughput_gbps") or meta.get("max_throughput_gbps", 1.0 if is_physical else 10.0))

            # Coordinates: use reference layout, or calculate circular layout
            if "x" in meta and "y" in meta:
                x, y = meta["x"], meta["y"]
            else:
                angle = 2 * math.pi * i / max(len(tfs_devices), 1)
                x = int(500 + 300 * math.cos(angle))
                y = int(350 + 250 * math.sin(angle))

            nodes.append({
                "id": node_id,
                "tfs_uuid": dev_uuid,
                "name": dev_name,
                "model": model,
                "role": role,
                "sector": sector,
                "x": x,
                "y": y,
                "max_throughput_gbps": max_tp,
                "status": "active" if "ENABLED" in dev_status else "disabled",
                "endpoints": [
                    {
                        "uuid": ep.get("endpoint_id", {}).get("endpoint_uuid", {}).get("uuid"),
                        "name": ep.get("name", "port"),
                        "type": ep.get("endpoint_type", "ethernet"),
                    }
                    for ep in dev.get("device_endpoints", [])
                ],
                "capabilities": caps,
                "operating_parameters": op_params,
            })

        # Map device UUID to node_id for clean link resolution
        uuid_to_node_id = {n["tfs_uuid"]: n["id"] for n in nodes}

        # 2. Transform Links
        links = []
        for j, link in enumerate(tfs_links):
            link_uuid = link.get("link_id", {}).get("link_uuid", {}).get("uuid", f"link-{j}")
            link_name = link.get("name", link_uuid)
            link_type = link.get("link_type", "LINKTYPE_COPPER")
            attrs = link.get("attributes", {})
            endpoints = link.get("link_endpoint_ids", [])

            if len(endpoints) < 2:
                continue

            src_dev_uuid = endpoints[0].get("device_id", {}).get("device_uuid", {}).get("uuid")
            dst_dev_uuid = endpoints[1].get("device_id", {}).get("device_uuid", {}).get("uuid")

            src_node = uuid_to_node_id.get(src_dev_uuid, src_dev_uuid)
            dst_node = uuid_to_node_id.get(dst_dev_uuid, dst_dev_uuid)

            meta = metadata_links.get(link_uuid) or metadata_links.get(link_name) or {}
            link_id = meta.get("id") or link_name

            role = meta.get("role")
            if not role:
                if "mw" in link_name or "radio" in link_type.lower():
                    role = "mw"
                elif "eband" in link_name or "mmwave" in link_name:
                    role = "eband"
                else:
                    role = "ethernet"

            cap = float(meta.get("capacity_gbps") or attrs.get("total_capacity_gbps") or (20.0 if role == "eband" else (10.0 if role == "mw" else 100.0)))
            dist = float(meta.get("distance_km") or (1.5 if role == "mw" else 0.5))

            links.append({
                "id": link_id,
                "tfs_uuid": link_uuid,
                "name": link_name,
                "src": src_node,
                "dst": dst_node,
                "role": role,
                "capacity_gbps": cap,
                "distance_km": dist,
                "status": "active",
                "src_endpoint_uuid": endpoints[0].get("endpoint_uuid", {}).get("uuid"),
                "dst_endpoint_uuid": endpoints[1].get("endpoint_uuid", {}).get("uuid"),
            })

        return {
            "nodes": nodes,
            "links": links,
            "source": "TeraFlowSDN",
            "context": self.context_name,
            "topology": self.topology_name,
            "device_count": len(nodes),
            "link_count": len(links),
        }
