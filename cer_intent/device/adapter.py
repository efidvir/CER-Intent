"""
Device Adapter — Multi-Backend
================================
Pluggable adapter layer for pushing DeviceConfig objects to Ceragon devices.

Three backends are available, selected via ADAPTER_BACKEND env variable:
  - "simulated"  (default) — in-memory state simulation, no live device needed
  - "teraflow"             — pushes config via TeraFlow SDN controller REST API
  - "direct_rest"          — calls Ceragon RESTCONF/REST API directly on devices

All backends implement the same AdapterBase interface.
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from cer_intent.intent_schema import DeviceConfig
from cer_intent.device.state_store import StateStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────────

class ApplyResult:
    def __init__(self, device_id: str, success: bool,
                 message: str = "", response_data: Any = None):
        self.device_id = device_id
        self.success = success
        self.message = message
        self.response_data = response_data
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Abstract Base
# ──────────────────────────────────────────────────────────────────────────────

class AdapterBase(ABC):

    @abstractmethod
    def apply(self, config: DeviceConfig) -> ApplyResult:
        """Push a single DeviceConfig to the target device/controller."""

    @abstractmethod
    def get_state(self, device_id: str) -> Dict[str, Any]:
        """Retrieve current operational state of a device."""

    def apply_all(self, configs: List[DeviceConfig]) -> List[ApplyResult]:
        return [self.apply(c) for c in configs]


# ──────────────────────────────────────────────────────────────────────────────
# Backend 1: Simulated Adapter
# ──────────────────────────────────────────────────────────────────────────────

class SimulatedAdapter(AdapterBase):
    """
    Simulates Ceragon device configuration in memory.
    Applied configs are written to the StateStore for persistence and dashboard visibility.
    """

    def __init__(self, state_store: StateStore):
        self._store = state_store

    def apply(self, config: DeviceConfig) -> ApplyResult:
        logger.info(f"[SIM] Applying {config.config_type} config to {config.device_id}")
        time.sleep(0.05)  # Simulate small network latency

        # Write to state store
        self._store.update_device_config(
            device_id=config.device_id,
            config_type=config.config_type,
            parameters=config.parameters,
            intent_id=config.intent_id,
            yang_xml=config.yang_xml,
        )

        return ApplyResult(
            device_id=config.device_id,
            success=True,
            message=f"Simulated apply OK — {config.config_type} on {config.device_id}",
            response_data={"yang_xml_length": len(config.yang_xml or "")},
        )

    def get_state(self, device_id: str) -> Dict[str, Any]:
        return self._store.get_device_state(device_id)


# ──────────────────────────────────────────────────────────────────────────────
# Backend 2: TeraFlow SDN Adapter
# ──────────────────────────────────────────────────────────────────────────────

class TeraFlowAdapter(AdapterBase):
    """
    Pushes configurations through a TeraFlow SDN controller via its REST API.

    TeraFlow exposes device management via its Context/Device service.
    We use the TeraFlow REST gateway to configure devices southbound.

    Environment variables required:
      TERAFLOW_URL    — base URL of TeraFlow REST gateway (e.g. http://localhost:8080)
      TERAFLOW_TOKEN  — Bearer token for authentication (optional)
      TFS_CONTEXT     — Context UUID or name (default: admin)
      TFS_TOPOLOGY    — Topology UUID or name (default: admin)
    """

    def __init__(self, state_store: StateStore, registry: Any = None):
        self._store = state_store
        self._registry = registry
        from cer_intent.device.tfs_client import TFSClient, make_uuid
        self._tfs_client = TFSClient()
        self._make_uuid = make_uuid
        self._base_url = self._tfs_client.base_url

    def _resolve_device_uuid(self, device_id: str) -> str:
        """Resolve a shorthand device ID or name to its authoritative TFS UUID."""
        if self._registry:
            tfs_uuid = self._registry.get_tfs_uuid(device_id)
            if tfs_uuid:
                return tfs_uuid

        # Check if it's a known Ceragon physical device registered in TFS
        if "ceragon" in device_id.lower() or "ctu" in device_id.lower():
            try:
                for dev in self._tfs_client.get_devices():
                    if "ceragon" in dev.get("name", "").lower():
                        return dev["device_id"]["device_uuid"]["uuid"]
            except Exception:
                pass

        # Try generating deterministic 6G UUID from device_id
        try:
            import uuid
            uuid.UUID(device_id)
            return device_id
        except ValueError:
            return self._make_uuid(device_id)

    def _build_tfs_config_rules(self, config: DeviceConfig) -> List[Dict[str, Any]]:
        """
        Build TeraFlow-compliant CONFIGACTION_SET config rules from DeviceConfig.
        Maps intent parameters to standard TFS resource keys:
          - /interface[name=...]/...
          - /device/operating_parameters
          - /device/capabilities
        """
        config_rules = []

        # 1. Custom interface/feature parameters (JSON dict)
        valid_params = {k: v for k, v in config.parameters.items() if v is not None}
        if valid_params:
            resource_key = f"/interface[name={config.device_id}]/{config.config_type}"
            config_rules.append({
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": resource_key,
                    "resource_value": json.dumps(valid_params),
                }
            })

        # 2. Operating parameters reflection in TFS
        op_updates = {}
        if config.config_type == "modulation":
            if "max_modulation" in config.parameters:
                op_updates["current_modulation"] = config.parameters["max_modulation"]
            if "min_modulation" in config.parameters:
                op_updates["min_modulation"] = config.parameters["min_modulation"]
            op_updates["acm_enabled"] = True
        elif config.config_type == "capacity":
            if "min_throughput_gbps" in config.parameters:
                op_updates["configured_capacity_gbps"] = config.parameters["min_throughput_gbps"]
        elif config.config_type == "protection":
            op_updates["protection_mode"] = config.parameters.get("protection_mode", "1+1_HSB")
        elif config.config_type == "slice":
            op_updates["active_slice"] = config.parameters.get("slice_id") or config.intent_id

        if op_updates:
            config_rules.append({
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/operating_parameters",
                    "resource_value": json.dumps(op_updates),
                }
            })

        return config_rules

    def apply(self, config: DeviceConfig) -> ApplyResult:
        device_uuid = self._resolve_device_uuid(config.device_id)
        config_rules = self._build_tfs_config_rules(config)

        logger.info(f"[TeraFlow] Applying {config.config_type} config to device {config.device_id} (UUID: {device_uuid})")

        try:
            # 1. Push to TeraFlowSDN device via NBI
            result = self._tfs_client.configure_device(device_uuid, config_rules)

            # 2. If it is a slice intent, also register/update slice in TFS context
            if config.config_type == "slice":
                slice_uuid = self._make_uuid(config.parameters.get("slice_name", f"slice-{config.intent_id[:8]}"))
                slice_payload = {
                    "slice_id": {
                        "context_id": {"context_uuid": {"uuid": self._tfs_client.context_name}},
                        "slice_uuid": {"uuid": slice_uuid}
                    },
                    "name": config.parameters.get("slice_name", f"Slice-{config.intent_id[:8]}"),
                    "slice_status": {"slice_status": "SLICESTATUS_ACTIVE"},
                    "slice_endpoint_ids": [
                        {
                            "device_id": {"device_uuid": {"uuid": device_uuid}},
                            "endpoint_uuid": {"uuid": self._make_uuid(f"{config.device_id}-eth-1/10G")}
                        }
                    ],
                    "slice_config": {"config_rules": config_rules},
                }
                try:
                    self._tfs_client.create_or_update_slice(slice_payload)
                    logger.info(f"[TeraFlow] Slicing successfully registered in TFS for slice_uuid={slice_uuid}")
                except Exception as ex:
                    logger.warning(f"[TeraFlow] Slice API registration warning: {ex}")

            # 3. If target is physical Ceragon hardware, push down to device via TFSCeragonDriver
            if "ceragon" in config.device_id.lower() or "ctu" in config.device_id.lower() or "t261" in config.device_id.lower():
                try:
                    from ceragon_tfs_adapter.driver import TFSCeragonDriver
                    driver = TFSCeragonDriver()
                    resources = [(r["custom"]["resource_key"], r["custom"]["resource_value"]) for r in config_rules if "custom" in r]
                    driver_results = driver.set_config(resources)
                    logger.info(f"[TeraFlow -> Ceragon Hardware] Applied {len(resources)} rules: {driver_results}")
                except Exception as ex:
                    logger.warning(f"[TeraFlow -> Ceragon Hardware] Dispatch warning: {ex}")

            # 4. Mirror confirmed config to local state store
            self._store.update_device_config(
                device_id=config.device_id,
                config_type=config.config_type,
                parameters=config.parameters,
                intent_id=config.intent_id,
                yang_xml=config.yang_xml,
            )

            # 5. Trigger registry sync to ensure live topology stays updated
            if self._registry and hasattr(self._registry, "sync_from_tfs"):
                self._registry.sync_from_tfs()

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                message=f"TeraFlow SDN accepted and applied configuration to device {device_uuid}",
                response_data=result,
            )

        except requests.exceptions.ConnectionError:
            msg = f"Cannot reach TeraFlow SDN at {self._base_url} — is the NBI service or SSH tunnel active?"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except requests.exceptions.HTTPError as e:
            error_body = e.response.text[:300] if e.response is not None else str(e)
            msg = f"TeraFlow SDN HTTP error {e.response.status_code if e.response else 'Unknown'}: {error_body}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except Exception as e:
            msg = f"TeraFlow SDN adapter error: {e}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

    def get_state(self, device_id: str) -> Dict[str, Any]:
        device_uuid = self._resolve_device_uuid(device_id)
        try:
            device_data = self._tfs_client.get_device(device_uuid)
            # Extract config rules and operating state
            configs = {}
            for rule in device_data.get("device_config", {}).get("config_rules", []):
                custom = rule.get("custom", {})
                k = custom.get("resource_key", "")
                v = custom.get("resource_value", "")
                configs[k] = v

            return {
                "device_id": device_id,
                "tfs_uuid": device_uuid,
                "name": device_data.get("name"),
                "status": device_data.get("device_operational_status"),
                "type": device_data.get("device_type"),
                "endpoints_count": len(device_data.get("device_endpoints", [])),
                "configs": configs,
                "source": "TeraFlowSDN",
            }
        except Exception as e:
            logger.warning(f"[TeraFlow] state fetch failed for {device_id} ({device_uuid}): {e}")
            return self._store.get_device_state(device_id)


# ──────────────────────────────────────────────────────────────────────────────
# Backend 3: Direct Ceragon RESTCONF/REST Adapter
# ──────────────────────────────────────────────────────────────────────────────

class DirectRESTAdapter(AdapterBase):
    """
    Configures Ceragon devices directly via their RESTCONF (RFC 8040) API.

    Ceragon CeraOS exposes RESTCONF at:
      https://<device-ip>/restconf/data/<yang-module>:<container>

    Environment variables required:
      CERAGON_DEVICE_MAP  — JSON string: {"node-A": "192.168.1.10", ...}
      CERAGON_USER        — RESTCONF username (default: admin)
      CERAGON_PASSWORD    — RESTCONF password
      CERAGON_PORT        — RESTCONF port (default: 443)
      CERAGON_TLS_VERIFY  — "false" to skip TLS verification (lab use)
    """

    YANG_URL_MAP = {
        "radio":      "ceragon-radio-link:radio-link-cfg",
        "qos":        "ceragon-qos:qos-config",
        "protection": "ceragon-protection:protection-config",
        "slice":      "ceragon-slice:slice-config",
    }

    def __init__(self, state_store: StateStore):
        self._store = state_store
        raw_map = os.getenv("CERAGON_DEVICE_MAP", "{}")
        try:
            self._device_map: Dict[str, str] = json.loads(raw_map)
        except json.JSONDecodeError:
            logger.warning("CERAGON_DEVICE_MAP is not valid JSON; direct REST will fail")
            self._device_map = {}

        self._user = os.getenv("CERAGON_USER", "admin")
        self._password = os.getenv("CERAGON_PASSWORD", "admin")
        self._port = int(os.getenv("CERAGON_PORT", "443"))
        self._tls_verify = os.getenv("CERAGON_TLS_VERIFY", "true").lower() == "true"
        self._timeout = int(os.getenv("CERAGON_TIMEOUT_SEC", "15"))

    def _device_ip(self, device_id: str) -> Optional[str]:
        return self._device_map.get(device_id)

    def _restconf_url(self, device_id: str, config_type: str) -> str:
        ip = self._device_ip(device_id)
        yang_path = self.YANG_URL_MAP.get(config_type, f"ceragon-generic:{config_type}")
        scheme = "https" if self._port == 443 else "http"
        return f"{scheme}://{ip}:{self._port}/restconf/data/{yang_path}"

    def _build_restconf_payload(self, config: DeviceConfig) -> dict:
        """Convert DeviceConfig parameters to RESTCONF JSON body (RFC 8040)."""
        yang_path = self.YANG_URL_MAP.get(config.config_type, "ceragon-generic:config")
        container_name = yang_path.split(":")[1]

        # Build RESTCONF-style JSON (uses YANG key→kebab-case)
        body = {}
        for key, value in config.parameters.items():
            if value is None:
                continue
            body[key.replace("_", "-")] = value

        return {container_name: body}

    def apply(self, config: DeviceConfig) -> ApplyResult:
        ip = self._device_ip(config.device_id)
        if not ip:
            msg = (
                f"No IP mapping for device '{config.device_id}'. "
                f"Set CERAGON_DEVICE_MAP env variable."
            )
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

        url = self._restconf_url(config.device_id, config.config_type)
        payload = self._build_restconf_payload(config)

        logger.info(f"[RESTCONF] PATCH {url}")
        try:
            resp = requests.patch(
                url,
                json=payload,
                auth=HTTPBasicAuth(self._user, self._password),
                headers={
                    "Content-Type": "application/yang-data+json",
                    "Accept": "application/yang-data+json",
                },
                verify=self._tls_verify,
                timeout=self._timeout,
            )
            resp.raise_for_status()

            # Mirror to state store
            self._store.update_device_config(
                device_id=config.device_id,
                config_type=config.config_type,
                parameters=config.parameters,
                intent_id=config.intent_id,
                yang_xml=config.yang_xml,
            )

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                message=f"RESTCONF PATCH OK (HTTP {resp.status_code}) → {ip}",
                response_data={"url": url},
            )
        except requests.exceptions.SSLError as e:
            msg = f"TLS error reaching {ip}: {e}. Set CERAGON_TLS_VERIFY=false for lab."
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except requests.exceptions.ConnectionError:
            msg = f"Cannot reach Ceragon device {config.device_id} at {ip}:{self._port}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except requests.exceptions.HTTPError as e:
            msg = f"RESTCONF error {e.response.status_code}: {e.response.text[:200]}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except Exception as e:
            msg = f"DirectREST adapter error: {e}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

    def get_state(self, device_id: str) -> Dict[str, Any]:
        ip = self._device_ip(device_id)
        if not ip:
            return self._store.get_device_state(device_id)
        url = f"https://{ip}:{self._port}/restconf/data/ceragon-radio-link:radio-link-cfg"
        try:
            resp = requests.get(
                url,
                auth=HTTPBasicAuth(self._user, self._password),
                headers={"Accept": "application/yang-data+json"},
                verify=self._tls_verify,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[RESTCONF] state fetch failed for {device_id}: {e}")
            return self._store.get_device_state(device_id)


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_adapter(state_store: StateStore, registry: Any = None) -> AdapterBase:
    """
    Instantiate the correct adapter based on ADAPTER_BACKEND env variable.
    
    Values:
      "teraflow"    — TeraFlow SDN controller (Source of Truth)
      "simulated"   — In-memory state simulation (fallback)
      "direct_rest" — Ceragon RESTCONF directly
      "xml_ip50c"   — Ceragon IP-50C XML configuration
    """
    backend = os.getenv("ADAPTER_BACKEND", "teraflow").lower()

    if backend == "teraflow":
        logger.info("Device adapter: TeraFlow SDN (Live Source of Truth)")
        return TeraFlowAdapter(state_store, registry=registry)
    elif backend == "direct_rest":
        logger.info("Device adapter: Direct Ceragon RESTCONF")
        return DirectRESTAdapter(state_store)
    elif backend == "xml_ip50c":
        logger.info("Device adapter: Ceragon IP-50C XML configuration")
        from cer_intent.device.xml_adapter import IP50CXMLAdapter
        return IP50CXMLAdapter(state_store)
    else:
        logger.info("Device adapter: Simulated (no live device required)")
        return SimulatedAdapter(state_store)
