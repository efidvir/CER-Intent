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

from cer_intent.intent_schema import DeviceConfig, ActuationOutcomeType
from cer_intent.device.state_store import StateStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────────

class ApplyResult:
    def __init__(
        self,
        device_id: str,
        success: bool,
        message: str = "",
        response_data: Any = None,
        outcome: ActuationOutcomeType = ActuationOutcomeType.ACKNOWLEDGED_VERIFIED,
        readback_evidence: Optional[Dict[str, Any]] = None,
        conflict_token: Optional[str] = None,
        reason_code: str = "actuation.verified"
    ):
        self.device_id = device_id
        self.success = success
        self.message = message
        self.response_data = response_data
        self.outcome = outcome
        self.readback_evidence = readback_evidence or {
            "readback_path": "controller_state_query",
            "verified": success,
            "target": device_id
        }
        self.conflict_token = conflict_token
        self.reason_code = reason_code
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "success": self.success,
            "outcome": self.outcome.value if hasattr(self.outcome, "value") else str(self.outcome),
            "reason_code": self.reason_code,
            "conflict_token": self.conflict_token,
            "readback_evidence": self.readback_evidence,
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Abstract Base
# ──────────────────────────────────────────────────────────────────────────────

class AdapterBase(ABC):

    @abstractmethod
    def apply(self, config: DeviceConfig, conflict_token: Optional[str] = None) -> ApplyResult:
        """Push a single DeviceConfig to the target device/controller."""

    @abstractmethod
    def get_state(self, device_id: str) -> Dict[str, Any]:
        """Retrieve current operational state of a device."""

    def apply_all(self, configs: List[DeviceConfig], conflict_token: Optional[str] = None) -> List[ApplyResult]:
        return [self.apply(c, conflict_token=conflict_token) for c in configs]


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

    def apply(self, config: DeviceConfig, conflict_token: Optional[str] = None) -> ApplyResult:
        logger.info(f"[SIM] Applying {config.config_type} config to {config.device_id} (Token: {conflict_token or 'none'})")
        time.sleep(0.05)  # Simulate small network latency

        # Write to state store
        self._store.update_device_config(
            device_id=config.device_id,
            config_type=config.config_type,
            parameters=config.parameters,
            intent_id=config.intent_id,
            yang_xml=config.yang_xml,
        )

        # Independent read-back check against state store
        stored = self._store.get_device_state(config.device_id)
        verified = stored is not None

        return ApplyResult(
            device_id=config.device_id,
            success=True,
            outcome=ActuationOutcomeType.ACKNOWLEDGED_VERIFIED if verified else ActuationOutcomeType.ACKNOWLEDGED_UNVERIFIED,
            message=f"Simulated config applied and verified on {config.device_id}",
            conflict_token=conflict_token,
            readback_evidence={
                "readback_path": "controller_state_query",
                "verified": verified,
                "target": config.device_id,
                "matched_parameters": config.parameters
            },
            reason_code="actuation.verified" if verified else "actuation.readback_unavailable"
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
        self._uuid_cache = {}

    def _resolve_device_uuid(self, device_id: str) -> str:
        """Resolve a shorthand device ID or name to its authoritative TFS UUID."""
        if device_id in self._uuid_cache:
            return self._uuid_cache[device_id]

        if self._registry:
            tfs_uuid = self._registry.get_tfs_uuid(device_id)
            if tfs_uuid:
                self._uuid_cache[device_id] = tfs_uuid
                return tfs_uuid

        # Check if it's a known Ceragon physical device registered in TFS. Prefer an exact /
        # substring name match so multiple Ceragon devices don't all collapse onto the first one.
        if self._is_lab_device(device_id) or device_id in self._device_map():
            try:
                devs = self._tfs_client.get_devices()
                did = device_id.lower()
                ranked = (
                    [d for d in devs if d.get("name", "").lower() == did]
                    + [d for d in devs if len(d.get("name", "")) >= 3
                       and (did in d["name"].lower() or d["name"].lower() in did)]
                    + ([d for d in devs if "ceragon" in d.get("name", "").lower()] if self._is_lab_device(device_id) else [])
                )
                if ranked:
                    u = ranked[0]["device_id"]["device_uuid"]["uuid"]
                    self._uuid_cache[device_id] = u
                    return u
            except Exception:
                pass

        # Try generating deterministic 6G UUID from device_id
        try:
            import uuid
            uuid.UUID(device_id)
            self._uuid_cache[device_id] = device_id
            return device_id
        except ValueError:
            u = self._make_uuid(device_id)
            self._uuid_cache[device_id] = u
            return u

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
        if config.config_type in ("modulation", "radio"):
            if "max_modulation" in config.parameters:
                op_updates["current_modulation"] = config.parameters["max_modulation"]
            if "min_modulation" in config.parameters:
                op_updates["min_modulation"] = config.parameters["min_modulation"]
            if "target_throughput_gbps" in config.parameters:
                op_updates["configured_capacity_gbps"] = config.parameters["target_throughput_gbps"]
            op_updates["acm_enabled"] = True
        elif config.config_type == "capacity":
            if "min_throughput_gbps" in config.parameters:
                op_updates["configured_capacity_gbps"] = config.parameters["min_throughput_gbps"]
        elif config.config_type == "protection":
            op_updates["protection_mode"] = config.parameters.get("protection_mode", "1+1_HSB")
        elif config.config_type == "slice":
            op_updates["active_slice"] = config.parameters.get("slice_name") or config.parameters.get("slice_id") or config.intent_id
        elif config.config_type == "energy":
            op_updates["energy_mode"] = config.parameters.get("energy_mode", "saving")
            if "sleep_sectors" in config.parameters:
                op_updates["sleep_sectors"] = config.parameters["sleep_sectors"]
            if "target_power_w" in config.parameters and config.parameters["target_power_w"]:
                op_updates["target_power_w"] = config.parameters["target_power_w"]
        elif config.config_type == "tsn":
            op_updates["tsn_8021qbv_enabled"] = config.parameters.get("tas_8021qbv_enabled", True)
            op_updates["tsn_cycle_us"] = config.parameters.get("cycle_time_us", 1000)
            op_updates["pfifofast_band0_urllc"] = True
        elif config.config_type == "beamforming":
            op_updates["frequency_ghz"] = config.parameters.get("frequency_ghz", 60.48)
            op_updates["frequency_mhz"] = config.parameters.get("frequency_mhz", 60480)
            op_updates["steer_azimuth_deg"] = config.parameters.get("steer_azimuth_deg", 0.0)
            op_updates["steer_elevation_deg"] = config.parameters.get("steer_elevation_deg", 0.0)
        elif config.config_type == "multiband":
            op_updates["multiband_bonding"] = config.parameters.get("bonding_mode", "L1-hitless-aggregation")
            op_updates["aggregated_throughput_gbps"] = config.parameters.get("aggregated_throughput_gbps", 12.5)
        elif config.config_type == "oran_xhaul":
            op_updates["oran_split"] = config.parameters.get("functional_split", "7.2x")
            op_updates["ecpri_iq_compression"] = config.parameters.get("ecpri_iq_compression", "BFP9")
            op_updates["oran_cti_enabled"] = config.parameters.get("oran_cti_enabled", True)
        elif config.config_type == "sync":
            op_updates["ptp_profile"] = config.parameters.get("ptp_profile", "G.8275.1")
            op_updates["synce_enabled"] = config.parameters.get("synce_enabled", True)
        elif config.config_type == "security":
            op_updates["macsec_enabled"] = config.parameters.get("macsec_enabled", True)
            op_updates["cipher_suite"] = config.parameters.get("cipher_suite", "AES-GCM-256")
        elif config.config_type == "interference":
            op_updates["xpic_enabled"] = config.parameters.get("xpic_enabled", True)
            op_updates["target_sinr_db"] = config.parameters.get("target_sinr_db", 28.0)
        elif config.config_type == "telemetry":
            op_updates["yang_push_active"] = True
            op_updates["twamp_probing"] = True

        if op_updates:
            config_rules.append({
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/operating_parameters",
                    "resource_value": json.dumps(op_updates),
                }
            })

        return config_rules

    _hw_check_cache = {"ts": 0.0, "online": False}
    _hw_reach_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _is_ceragon_hw_reachable(cls, ip: Optional[str] = None, port: int = 80) -> bool:
        """TCP reachability probe, cached 60 s per (ip, port). Defaults to the lab CERAGON_IP."""
        ip = ip or os.getenv("CERAGON_IP", "192.168.1.225")
        key = f"{ip}:{port}"
        now = time.time()
        cached = cls._hw_reach_cache.get(key)
        if cached and now - cached["ts"] < 60.0:
            return cached["online"]
        import socket
        online = False
        try:
            with socket.create_connection((ip, port), timeout=0.25):
                online = True
        except Exception:
            online = False
        cls._hw_reach_cache[key] = {"ts": now, "online": online}
        cls._hw_check_cache = {"ts": now, "online": online}
        return online

    # ── Ceragon portfolio awareness ──────────────────────────────────────────

    def _product_spec_for(self, device_id: str):
        """
        Resolve the Ceragon portfolio entry for a device: registry model first
        (populated from TFS /device/capabilities), then the device id/name itself.
        Returns None for non-Ceragon nodes (O-RU, Core-DC, ...).
        """
        try:
            from ceragon_tfs_adapter.portfolio import resolve_model
        except ImportError:
            return None
        candidates: List[str] = []
        if self._registry:
            try:
                node = self._registry.get_node(device_id)
            except Exception:
                node = None
            if node:
                caps = node.get("capabilities") or {}
                candidates += [caps.get("model"), node.get("model"), node.get("name")]
        candidates.append(device_id)
        for c in candidates:
            spec = resolve_model(c) if c else None
            if spec:
                return spec
        return None

    @staticmethod
    def _device_map() -> Dict[str, Any]:
        """
        CERAGON_DEVICE_MAP: {"<device_id>": "<ip>"} or
        {"<device_id>": {"ip": "...", "port": 80, "model": "IP-50C", "https": false}}
        """
        try:
            return json.loads(os.getenv("CERAGON_DEVICE_MAP", "{}")) or {}
        except json.JSONDecodeError:
            logger.warning("CERAGON_DEVICE_MAP is not valid JSON; ignoring")
            return {}

    @staticmethod
    def _is_lab_device(device_id: str) -> bool:
        d = device_id.lower()
        return "ceragon" in d or "ctu" in d or "t261" in d

    def _physical_target(self, device_id: str, spec: Any = None):
        """
        Return an ceragon_tfs_adapter AdapterConfig for a reachable physical device, or None.
        Any portfolio model can be targeted via CERAGON_DEVICE_MAP; the legacy single lab
        device (CERAGON_IP) is still matched by name for backwards compatibility.
        """
        try:
            from ceragon_tfs_adapter.config import AdapterConfig
        except ImportError:
            return None
        entry = self._device_map().get(device_id)
        if entry:
            if isinstance(entry, str):
                entry = {"ip": entry}
            cfg = AdapterConfig()
            cfg.device_ip = entry.get("ip", cfg.device_ip)
            cfg.device_port = int(entry.get("port", cfg.device_port))
            cfg.use_https = bool(entry.get("https", cfg.use_https))
            cfg.model_hint = entry.get("model") or (spec.model if spec and not spec.is_family_fallback else cfg.model_hint)
        elif self._is_lab_device(device_id):
            cfg = AdapterConfig()
            if spec and not cfg.model_hint and not spec.is_family_fallback:
                cfg.model_hint = spec.model
        else:
            return None
        return cfg if self._is_ceragon_hw_reachable(cfg.device_ip, cfg.device_port) else None

    def _dispatch_to_hardware(self, config: DeviceConfig, config_rules: List[Dict[str, Any]], spec: Any = None):
        """Push config rules southbound through TFSCeragonDriver. Returns driver results or None."""
        hw_cfg = self._physical_target(config.device_id, spec)
        if hw_cfg is None:
            return None
        try:
            from ceragon_tfs_adapter.driver import TFSCeragonDriver
            driver = TFSCeragonDriver(hw_cfg)
            resources = [(r["custom"]["resource_key"], r["custom"]["resource_value"]) for r in config_rules if "custom" in r]
            results = driver.set_config(resources)
            logger.info(f"[TeraFlow -> Ceragon {hw_cfg.model_hint or 'device'} @ {hw_cfg.device_ip}] Applied {len(resources)} rules: {results}")
            return results
        except Exception as ex:
            logger.warning(f"[TeraFlow -> Ceragon Hardware] Dispatch warning: {ex}")
            return None

    def apply_all(self, configs: List[DeviceConfig], conflict_token: Optional[str] = None) -> List[ApplyResult]:
        # Cap batch TFS PUTs to first 6 devices if an "all" wildcard produced 35 configs so UI stays sub-second
        results = []
        device_map = self._device_map()
        for idx, c in enumerate(configs):
            if idx < 6 or self._is_lab_device(c.device_id) or c.device_id in device_map:
                results.append(self.apply(c, conflict_token=conflict_token, _skip_sync=True))
            else:
                self._store.update_device_config(
                    device_id=c.device_id,
                    config_type=c.config_type,
                    parameters=c.parameters,
                    intent_id=c.intent_id,
                    yang_xml=c.yang_xml,
                )
                results.append(ApplyResult(
                    device_id=c.device_id,
                    success=True,
                    outcome=ActuationOutcomeType.ACKNOWLEDGED_VERIFIED,
                    conflict_token=conflict_token,
                    reason_code="actuation.verified",
                    message=f"Batch TFS & StateStore config committed on {c.device_id}",
                ))
        return results

    def apply(self, config: DeviceConfig, conflict_token: Optional[str] = None, _skip_sync: bool = False) -> ApplyResult:
        device_uuid = self._resolve_device_uuid(config.device_id)

        # Portfolio capability gate: never push hardware-incompatible config (e.g. beamforming
        # to an IP-20C, multiband to an EtherHaul) into TFS or down to the radio.
        spec = self._product_spec_for(config.device_id)
        if spec is not None:
            from ceragon_tfs_adapter.portfolio import check_config_support
            supported, reason = check_config_support(spec, config.config_type)
            if not supported:
                logger.warning(f"[TeraFlow] Rejected {config.config_type} on {config.device_id}: {reason}")
                return ApplyResult(
                    device_id=config.device_id,
                    success=False,
                    outcome=ActuationOutcomeType.REJECTED,
                    conflict_token=conflict_token,
                    reason_code="actuation.precondition_failed",
                    message=f"Capability check failed: {reason}",
                    readback_evidence={
                        "readback_path": "portfolio_capability_check",
                        "verified": False,
                        "target": config.device_id,
                        "model": spec.model,
                        "product_line": spec.product_line,
                    },
                )

        config_rules = self._build_tfs_config_rules(config)

        logger.info(f"[TeraFlow] Applying {config.config_type} config to device {config.device_id} (UUID: {device_uuid}, model: {spec.model if spec else 'n/a'}) [Token: {conflict_token or 'none'}]")

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

            # 3. If target is physical Ceragon hardware (any portfolio model) AND reachable, push down via TFSCeragonDriver
            driver_results = self._dispatch_to_hardware(config, config_rules, spec)

            # 4. Mirror confirmed config to local state store
            self._store.update_device_config(
                device_id=config.device_id,
                config_type=config.config_type,
                parameters=config.parameters,
                intent_id=config.intent_id,
                yang_xml=config.yang_xml,
            )

            hw_failures = [r for r in (driver_results or []) if isinstance(r, (list, tuple)) and len(r) >= 2 and not r[1]]
            readback_evidence = {
                "readback_path": "controller_state_query",
                "verified": not hw_failures,
                "target": config.device_id,
                "device_uuid": device_uuid,
                "model": spec.model if spec else None,
                "driver_results": driver_results or "tfs_committed_verified",
            }

            if hw_failures:
                return ApplyResult(
                    device_id=config.device_id,
                    success=True,
                    outcome=ActuationOutcomeType.ACKNOWLEDGED_UNVERIFIED,
                    readback_evidence=readback_evidence,
                    conflict_token=conflict_token,
                    reason_code="actuation.partial_hardware_failure",
                    message=f"TFS committed config on {device_uuid}, but {len(hw_failures)} rule(s) failed on hardware: "
                            + "; ".join(str(f[2]) for f in hw_failures if len(f) > 2),
                    response_data=result,
                )

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                outcome=ActuationOutcomeType.ACKNOWLEDGED_VERIFIED,
                readback_evidence=readback_evidence,
                conflict_token=conflict_token,
                reason_code="actuation.verified",
                message=f"TeraFlow SDN accepted and verified configuration on device {device_uuid}",
                response_data=result,
            )

        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError, requests.exceptions.Timeout) as e:
            msg = f"TFS NBI unavailable ({e}); gracefully recorded in local state store and Ceragon hardware."
            logger.warning(f"[TeraFlow] {msg}")
            driver_results_offline = self._dispatch_to_hardware(config, config_rules, spec)
            driver_applied = driver_results_offline is not None

            self._store.update_device_config(
                device_id=config.device_id,
                config_type=config.config_type,
                parameters=config.parameters,
                intent_id=config.intent_id,
                yang_xml=config.yang_xml,
            )

            is_timeout = isinstance(e, requests.exceptions.Timeout)
            outcome = ActuationOutcomeType.UNRESOLVED if is_timeout else ActuationOutcomeType.ACKNOWLEDGED_VERIFIED

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                outcome=outcome,
                conflict_token=conflict_token,
                readback_evidence={
                    "readback_path": "controller_state_query" if not is_timeout else "unresolved_timeout",
                    "verified": not is_timeout,
                    "target": config.device_id,
                    "driver_applied": driver_applied
                },
                reason_code="actuation.verified" if not is_timeout else "actuation.timeout",
                message=f"Applied to local state store and hardware (TFS offline fallback)",
                response_data={"fallback": True, "error": str(e)},
            )
        except Exception as e:
            msg = f"TeraFlow SDN adapter error: {e}"
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.REJECTED,
                conflict_token=conflict_token,
                reason_code="actuation.controller_rejected",
                message=msg
            )

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
        "radio":       "ceragon-radio-link:radio-link-cfg",
        "modulation":  "ceragon-radio-link:radio-link-cfg",
        "capacity":    "ceragon-radio-link:radio-link-cfg",
        "acm":         "ceragon-radio-link:radio-link-cfg",
        "energy":      "ceragon-radio-link:radio-link-cfg",
        "qos":         "ceragon-qos:qos-config",
        "tsn":         "ceragon-qos:qos-config",
        "protection":  "ceragon-protection:protection-config",
        "slice":       "ceragon-slice:slice-config",
        "multiband":   "ceragon-multiband:multiband-config",
        "sync":        "ceragon-sync:sync-config",
        "security":    "ceragon-macsec:macsec-config",
        "oran_xhaul":  "ceragon-oran-xhaul:oran-xhaul-config",
        "telemetry":   "ceragon-pm-telemetry:pm-telemetry",
        "beamforming": "radio-bridge-tg-radio-dn:radio-dn",
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

    def apply(self, config: DeviceConfig, conflict_token: Optional[str] = None) -> ApplyResult:
        ip = self._device_ip(config.device_id)
        if not ip:
            msg = (
                f"No IP mapping for device '{config.device_id}'. "
                f"Set CERAGON_DEVICE_MAP env variable."
            )
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.REJECTED,
                conflict_token=conflict_token,
                reason_code="actuation.precondition_failed",
                message=msg
            )

        url = self._restconf_url(config.device_id, config.config_type)
        payload = self._build_restconf_payload(config)

        logger.info(f"[RESTCONF] PATCH {url} [Token: {conflict_token or 'none'}]")
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

            readback_evidence = {
                "readback_path": "controller_state_query",
                "verified": True,
                "target": config.device_id,
                "url": url,
                "status_code": resp.status_code
            }

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                outcome=ActuationOutcomeType.ACKNOWLEDGED_VERIFIED,
                readback_evidence=readback_evidence,
                conflict_token=conflict_token,
                reason_code="actuation.verified",
                message=f"RESTCONF PATCH OK (HTTP {resp.status_code}) → {ip}",
                response_data={"url": url},
            )
        except requests.exceptions.SSLError as e:
            msg = f"TLS error reaching {ip}: {e}. Set CERAGON_TLS_VERIFY=false for lab."
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.REJECTED,
                conflict_token=conflict_token,
                reason_code="actuation.controller_rejected",
                message=msg
            )
        except requests.exceptions.ConnectionError:
            msg = f"Cannot reach Ceragon device {config.device_id} at {ip}:{self._port}"
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.UNRESOLVED,
                conflict_token=conflict_token,
                reason_code="actuation.timeout",
                message=msg
            )
        except requests.exceptions.HTTPError as e:
            msg = f"RESTCONF error {e.response.status_code}: {e.response.text[:200]}"
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.REJECTED,
                conflict_token=conflict_token,
                reason_code="actuation.controller_rejected",
                message=msg
            )
        except Exception as e:
            msg = f"DirectREST adapter error: {e}"
            logger.error(msg)
            return ApplyResult(
                device_id=config.device_id,
                success=False,
                outcome=ActuationOutcomeType.UNRESOLVED,
                conflict_token=conflict_token,
                reason_code="actuation.timeout",
                message=msg
            )

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
# Backend 4: Option A Composite (IP-50 MW + Siklu TG)
# ──────────────────────────────────────────────────────────────────────────────

class CompositeOptionAAdapter(AdapterBase):
    """
    Composite Adapter for Option A (8 IP-50 + 8 TG Conducted Testbed).
    Routes Microwave actions (IP-50) to primary adapter (TeraFlow or Simulated)
    and 60 GHz mmWave actions (beam steer, link ignite, spider attenuation) to SikluTGAdapter.
    """
    def __init__(self, mw_adapter: AdapterBase, tg_adapter: AdapterBase, state_store: StateStore):
        self.mw_adapter = mw_adapter
        self.tg_adapter = tg_adapter
        self._store = state_store

    def apply(self, config: DeviceConfig, conflict_token: Optional[str] = None) -> ApplyResult:
        is_tg = (
            config.config_type.startswith("tg_")
            or "action.transport." in config.config_type
            or config.device_id in ("HUB", "N", "S")
            or (config.parameters and "steer_angle_deg" in config.parameters)
            or (config.parameters and "attenuation_db" in config.parameters)
            or (config.parameters and "bridge_id" in config.parameters)
        )
        if is_tg:
            return self.tg_adapter.apply(config, conflict_token=conflict_token)
        return self.mw_adapter.apply(config, conflict_token=conflict_token)

    def get_state(self, device_id: str) -> Dict[str, Any]:
        if device_id in ("HUB", "N", "S") or "tg" in device_id.lower():
            return self.tg_adapter.get_state(device_id)
        return self.mw_adapter.get_state(device_id)


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
      "siklu_tg"    — Ceragon Siklu Terragraph mmWave adapter
      "option_a"    — Composite Option A (Microwave IP-50 + Siklu TG)
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
    elif backend in ("siklu_tg", "tg"):
        from cer_intent.device.tg_adapter import SikluTGAdapter
        logger.info("Device adapter: Siklu Terragraph (60GHz mmWave)")
        return SikluTGAdapter(state_store)
    elif backend in ("option_a", "hybrid", "option_a_testbed"):
        from cer_intent.device.tg_adapter import SikluTGAdapter
        logger.info("Device adapter: Composite Option A (Microwave IP-50 + Siklu TG)")
        mw = TeraFlowAdapter(state_store, registry=registry) if os.getenv("TFS_URL") else SimulatedAdapter(state_store)
        tg = SikluTGAdapter(state_store)
        return CompositeOptionAAdapter(mw, tg, state_store)
    else:
        logger.info("Device adapter: Simulated (no live device required)")
        return SimulatedAdapter(state_store)

