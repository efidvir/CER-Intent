"""
What the network at hand says about itself
==========================================
Reads each device's details through TeraFlowSDN (the views the Ceragon driver
reports: hardware, capabilities, radio sectors, the radio link, bridges) and
turns them into what the intent manager understands and checks with:

  * names and words for the devices: host names, models, product families,
    roles, bands ("V-band", "60 GHz"), ports
  * live radio state: current modulation, SNR, receive level, link speed,
    transmit power control, frequency (a read-back through the driver)
  * limits: port speed, the bands a radio can tune to

Details are cached (CER_IMF_DISCOVERY_TTL_S, default 15 s) so a conversation
does not read every radio on every sentence.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional

from cer_intent.imf.radio import mcs_for_snr


def _val(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def parse_device(dev: Dict[str, Any]) -> Dict[str, Any]:
    """One TFS device (with its config rules) -> the facts the intent manager uses."""
    rules = {}
    for r in (dev.get("device_config") or {}).get("config_rules", []):
        c = r.get("custom") or {}
        if c.get("resource_key"):
            rules[c["resource_key"]] = _val(c.get("resource_value"))
    hw = rules.get("/device/hardware_info") or {}
    caps = rules.get("/device/capabilities") or {}
    out: Dict[str, Any] = {
        "name": dev.get("name") or ((dev.get("device_id") or {}).get("device_uuid") or {}).get("uuid"),
        "type": dev.get("device_type"),
        "status": dev.get("device_operational_status"),
        "endpoints": [e.get("name") or ((e.get("endpoint_id") or {}).get("endpoint_uuid") or {}).get("uuid")
                      for e in dev.get("device_endpoints", []) or []],
        "hostname": hw.get("node_name") or hw.get("hostname"),
        "model": hw.get("model") or caps.get("model"),
        "vendor": hw.get("vendor") or caps.get("vendor"),
        "software": hw.get("software_version"),
        "family": caps.get("product_line") or caps.get("family"),
        "role": caps.get("role"),
        "features": caps.get("features") or [],
        "bands": [{"name": b.get("name"), "min_ghz": b.get("freq_min_ghz"), "max_ghz": b.get("freq_max_ghz")}
                  for b in caps.get("bands") or [] if isinstance(b, dict)],
        "max_mbps": float(caps["max_throughput_gbps"]) * 1000.0 if caps.get("max_throughput_gbps") else None,
        "channel_widths_mhz": caps.get("channel_bandwidths_mhz") or [],
    }
    live: Dict[str, Any] = {}
    for key, v in rules.items():
        if key.startswith("/radio/sector[") and isinstance(v, dict):
            m = re.search(r"(\d+)", str(v.get("current_modulation") or ""))
            if m:
                live["mcs"] = f"MCS{int(m.group(1))}"
            for src, dst in (("snr_db", "snr_db"), ("rsl_dbm", "rsl_dbm"), ("frequency_mhz", "freq_mhz"),
                             ("tx_power_control", "tx_power_control"), ("admin_status", "admin")):
                if v.get(src) is not None:
                    live[dst] = v[src]
        if key.endswith("radio-common") and isinstance(v, dict):
            common = next(iter(v.values()), {}) if len(v) == 1 else v
            active = ((common.get("links") or {}).get("active") or [])
            if active:
                a = active[0]
                if a.get("mcs-tx") is not None:
                    live["mcs"] = f"MCS{int(a['mcs-tx'])}"
                if a.get("snr") is not None:
                    live["snr_db"] = a["snr"]
                if a.get("speed-tx") is not None:
                    live["speed_mbps"] = a["speed-tx"]
            node_cfg = common.get("node-config") or {}
            if node_cfg.get("tx-power-control") is not None:
                live["tx_power_control"] = node_cfg["tx-power-control"]
        if key.endswith("user-bridge") and isinstance(v, dict):
            ub = next(iter(v.values()), {}) if len(v) == 1 else v
            vlans = sorted({p.get("c-vlan") for br in ub.get("bridge", []) for p in br.get("bridge-port", []) if p.get("c-vlan")})
            out["bridged_vlans"] = vlans
    if "mcs" not in live and live.get("snr_db") is not None:
        live["mcs"] = mcs_for_snr(float(live["snr_db"]))
    if live:
        live["at"] = time.time()
    out["live"] = live
    return out


class Discovery:
    """Device details from TeraFlowSDN, cached; radios are read back through their driver."""

    def __init__(self, client: Optional[Callable[[], Any]] = None, ttl_s: Optional[float] = None):
        self._client = client
        self.ttl = float(ttl_s if ttl_s is not None else os.getenv("CER_IMF_DISCOVERY_TTL_S", "15"))
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.errors: Dict[str, str] = {}

    def client(self):
        if self._client is None:
            from cer_intent.device.tfs_client import TFSClient
            c = TFSClient()
            self._client = lambda: c
        return self._client()

    def details(self, names: Iterable[str], radios: Iterable[str] = (), force: bool = False) -> Dict[str, Dict[str, Any]]:
        radios = set(radios)
        out: Dict[str, Dict[str, Any]] = {}
        now = time.time()
        for name in names:
            with self._lock:
                hit = self._cache.get(name)
            if hit and not force and now - hit["_t"] < self.ttl:
                out[name] = hit
                continue
            try:
                c = self.client()
                try:
                    dev = c.get_device(name, fresh=name in radios)
                except TypeError:
                    dev = c.get_device(name)
                info = parse_device(dev or {})
                info["_t"] = now
                with self._lock:
                    self._cache[name] = info
                self.errors.pop(name, None)
                out[name] = info
            except Exception as exc:  # pylint: disable=broad-except
                self.errors[name] = exc.__class__.__name__
                if hit:
                    out[name] = hit
        return out

    def forget(self) -> None:
        with self._lock:
            self._cache.clear()
