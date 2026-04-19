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
      TERAFLOW_URL    — base URL of TeraFlow REST gateway (e.g. http://10.0.0.1:8080)
      TERAFLOW_TOKEN  — Bearer token for authentication (optional)
    """

    def __init__(self, state_store: StateStore):
        self._store = state_store
        self._base_url = os.getenv("TERAFLOW_URL", "http://localhost:8080").rstrip("/")
        self._token = os.getenv("TERAFLOW_TOKEN", "")
        self._timeout = int(os.getenv("TERAFLOW_TIMEOUT_SEC", "10"))

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _device_config_endpoint(self, device_id: str) -> str:
        return f"{self._base_url}/api/v1/devices/{device_id}/config"

    def _build_teraflow_payload(self, config: DeviceConfig) -> dict:
        """
        Build a TeraFlow-compatible configuration request.
        TeraFlow uses its own config-rules format that wraps YANG parameters.

        Reference: TeraFlow SDN controller REST API /api/v1/devices/{id}/config
        """
        config_rules = []

        # Convert DeviceConfig parameters to TeraFlow config-rule format
        for key, value in config.parameters.items():
            if value is None:
                continue
            # TeraFlow uses JSON config-rules with resource paths
            resource_key = f"/interface[name={config.device_id}]/{config.config_type}/{key.replace('_', '-')}"
            config_rules.append({
                "action": "CONFIGRULE_ACTION_SET",
                "resource": {
                    "resource_key": resource_key,
                    "resource_value": json.dumps(value),
                }
            })

        return {
            "device_uuid": {"uuid": config.device_id},
            "config_rules": config_rules,
            "intent_id": config.intent_id,
            "yang_module": config.yang_module,
        }

    def apply(self, config: DeviceConfig) -> ApplyResult:
        url = self._device_config_endpoint(config.device_id)
        payload = self._build_teraflow_payload(config)

        logger.info(f"[TeraFlow] POST {url}")
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            resp.raise_for_status()
            result_data = resp.json() if resp.content else {}

            # Mirror to local state store for dashboard visibility
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
                message=f"TeraFlow accepted config (HTTP {resp.status_code})",
                response_data=result_data,
            )
        except requests.exceptions.ConnectionError:
            msg = f"Cannot reach TeraFlow at {self._base_url} — is it running?"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except requests.exceptions.HTTPError as e:
            msg = f"TeraFlow HTTP error {e.response.status_code}: {e.response.text[:200]}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)
        except Exception as e:
            msg = f"TeraFlow adapter error: {e}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

    def get_state(self, device_id: str) -> Dict[str, Any]:
        url = f"{self._base_url}/api/v1/devices/{device_id}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[TeraFlow] state fetch failed for {device_id}: {e}")
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

def create_adapter(state_store: StateStore) -> AdapterBase:
    """
    Instantiate the correct adapter based on ADAPTER_BACKEND env variable.
    
    Values:
      "simulated"   — default, no live device needed
      "teraflow"    — TeraFlow SDN controller
      "direct_rest" — Ceragon RESTCONF directly
    """
    backend = os.getenv("ADAPTER_BACKEND", "simulated").lower()

    if backend == "teraflow":
        logger.info("Device adapter: TeraFlow SDN")
        return TeraFlowAdapter(state_store)
    elif backend == "direct_rest":
        logger.info("Device adapter: Direct Ceragon RESTCONF")
        return DirectRESTAdapter(state_store)
    else:
        logger.info("Device adapter: Simulated (no live device required)")
        return SimulatedAdapter(state_store)
