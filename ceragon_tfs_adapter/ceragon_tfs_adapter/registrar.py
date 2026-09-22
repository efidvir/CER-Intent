"""
TFS Registrar
=============
Registers and synchronizes physical Ceragon devices into ETSI TeraFlowSDN Northbound Interface.
Establishes network links to topology peers for end-to-end path computation.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Tuple

import requests

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.mapper import CeragonTFSMapper, generate_tfs_uuid
from ceragon_tfs_adapter.models import CeragonDeviceState

logger = logging.getLogger(__name__)


class TFSRegistrar:
    """Manages registration and updates of Ceragon devices inside TeraFlowSDN."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig()
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if self.config.tfs_token:
            self._session.headers["Authorization"] = f"Bearer {self.config.tfs_token}"
        self.base_url = self.config.tfs_url

    def test_tfs_connection(self) -> Tuple[bool, str]:
        """Verify reachability of the TFS Northbound REST API."""
        url = f"{self.base_url}/tfs-api/contexts"
        try:
            resp = self._session.get(url, timeout=self.config.timeout_seconds)
            if resp.status_code == 200:
                return True, f"Connected to TeraFlowSDN at {self.base_url}"
            return False, f"TFS responded with HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot reach TFS NBI at {self.base_url} (Connection refused)"
        except Exception as e:
            return False, f"TFS connection error: {e}"

    def register_or_update_device(self, state: CeragonDeviceState) -> Dict[str, Any]:
        """
        Registers or updates the Ceragon device in TFS.
        Step 1: POST /tfs-api/devices with AddDevice descriptor (_connect/ rules only).
        Step 2: PUT /tfs-api/device/{uuid} with operational config rules and ENABLED status.
        Step 3: Ensure device is added to target Context and Topology.
        Step 4: Create topology link to adjacent peer node if available.
        """
        add_descriptor = CeragonTFSMapper.to_tfs_add_device_descriptor(state)
        dev_uuid = add_descriptor["device_id"]["device_uuid"]["uuid"]
        op_rules = CeragonTFSMapper.to_tfs_operational_config_rules(state)

        # Check if device exists in TFS
        existing = self.get_registered_device(dev_uuid)
        if not existing:
            # 1. Add device
            url_devices = f"{self.base_url}/tfs-api/devices"
            logger.info(f"[TFS Registrar] Adding device {dev_uuid} at {url_devices}")
            resp = self._session.post(
                url_devices,
                json={"devices": [add_descriptor]},
                timeout=self.config.timeout_seconds,
            )
            if resp.status_code not in (200, 201):
                logger.warning(f"[TFS Registrar] AddDevice returned {resp.status_code}: {resp.text[:200]}")
            else:
                logger.info(f"[TFS Registrar] AddDevice successfully created {dev_uuid}")

        # 2. Push operational configuration rules & status
        url_device = f"{self.base_url}/tfs-api/device/{dev_uuid}"
        logger.info(f"[TFS Registrar] Pushing {len(op_rules)} operational rules to {url_device}")
        oper_status = "DEVICEOPERATIONALSTATUS_ENABLED" if state.is_operational else "DEVICEOPERATIONALSTATUS_DISABLED"
        put_payload = {
            "device_id": {"device_uuid": {"uuid": dev_uuid}},
            "device_operational_status": oper_status,
            "device_config": {"config_rules": op_rules},
        }
        put_resp = self._session.put(
            url_device,
            json=put_payload,
            timeout=self.config.timeout_seconds,
        )
        put_resp.raise_for_status()

        # 3. Associate with Context and Topology
        self._add_device_to_topology(dev_uuid)

        # 4. Link into topology
        self._ensure_peer_link(dev_uuid, state)

        return {
            "status": "success",
            "device_uuid": dev_uuid,
            "device_name": add_descriptor["name"],
            "endpoints_count": len(state.interfaces) + len(state.sectors),
            "config_rules_count": len(op_rules),
        }

    def _add_device_to_topology(self, device_uuid: str) -> None:
        """Associate device with the active Context and Topology in TFS."""
        ctx = self.config.tfs_context
        topo = self.config.tfs_topology

        url = f"{self.base_url}/tfs-api/context/{ctx}/topology/{topo}"
        try:
            resp = self._session.get(url, timeout=self.config.timeout_seconds)
            if resp.status_code == 200:
                topo_data = resp.json()
                dev_ids = topo_data.get("device_ids", [])
                existing_uuids = [d.get("device_uuid", {}).get("uuid") for d in dev_ids]

                if device_uuid not in existing_uuids:
                    dev_ids.append({"device_uuid": {"uuid": device_uuid}})
                    topo_data["device_ids"] = dev_ids
                    put_resp = self._session.put(url, json=topo_data, timeout=self.config.timeout_seconds)
                    if put_resp.status_code in (200, 204):
                        logger.info(f"[TFS Registrar] Bound device {device_uuid} to Topology {ctx}/{topo}")
        except Exception as e:
            logger.debug(f"[TFS Registrar] Topology binding note: {e}")

    def _ensure_peer_link(self, device_uuid: str, state: CeragonDeviceState) -> None:
        """Ensure a physical/logical transport link exists in TFS connecting the Ceragon node."""
        ctx = self.config.tfs_context
        topo = self.config.tfs_topology
        
        # Determine local endpoint (eth1)
        local_ep_name = state.interfaces[0].name if state.interfaces else "eth1"
        local_ep_uuid = generate_tfs_uuid(f"{device_uuid}-{local_ep_name}")

        # Find candidate peer device in TFS
        url_topo = f"{self.base_url}/tfs-api/context/{ctx}/topology_details/{topo}"
        try:
            r = self._session.get(url_topo, timeout=self.config.timeout_seconds)
            if r.status_code != 200:
                return
            tfs_devices = r.json().get("devices", [])
            peer = next((d for d in tfs_devices if d.get("device_id", {}).get("device_uuid", {}).get("uuid") != device_uuid and len(d.get("device_endpoints", [])) > 0), None)
            if not peer:
                return

            peer_dev_uuid = peer["device_id"]["device_uuid"]["uuid"]
            peer_ep = peer["device_endpoints"][0]
            peer_ep_uuid = peer_ep.get("endpoint_id", {}).get("endpoint_uuid", {}).get("uuid")

            link_name = f"ceragon-uplink-{state.node_name}-to-{peer.get('name', 'peer')[:10]}"
            link_uuid = generate_tfs_uuid(f"link-{device_uuid}-{peer_dev_uuid}")

            link_payload = {
                "link_id": {"link_uuid": {"uuid": link_uuid}},
                "name": link_name,
                "link_type": "LINKTYPE_COPPER",
                "attributes": {
                    "total_capacity_gbps": state.max_throughput_gbps,
                    "used_capacity_gbps": 0.0,
                    "is_bidirectional": True,
                },
                "link_endpoint_ids": [
                    {
                        "device_id": {"device_uuid": {"uuid": device_uuid}},
                        "endpoint_uuid": {"uuid": local_ep_uuid},
                        "topology_id": {
                            "context_id": {"context_uuid": {"uuid": ctx}},
                            "topology_uuid": {"uuid": topo},
                        }
                    },
                    {
                        "device_id": {"device_uuid": {"uuid": peer_dev_uuid}},
                        "endpoint_uuid": {"uuid": peer_ep_uuid},
                        "topology_id": {
                            "context_id": {"context_uuid": {"uuid": ctx}},
                            "topology_uuid": {"uuid": topo},
                        }
                    }
                ]
            }

            # Post link to TFS
            url_links = f"{self.base_url}/tfs-api/links"
            resp_link = self._session.post(url_links, json={"links": [link_payload]}, timeout=self.config.timeout_seconds)
            if resp_link.status_code in (200, 201):
                logger.info(f"[TFS Registrar] Successfully registered topology Link '{link_name}' (UUID: {link_uuid})")
        except Exception as e:
            logger.debug(f"[TFS Registrar] Peer link creation note: {e}")

    def get_registered_device(self, device_uuid: str) -> Optional[Dict[str, Any]]:
        """Fetch the registered device from TFS by UUID."""
        url = f"{self.base_url}/tfs-api/device/{device_uuid}"
        try:
            resp = self._session.get(url, timeout=self.config.timeout_seconds)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"Device {device_uuid} check: {e}")
        return None
