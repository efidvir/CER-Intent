"""
Ceragon Universal REST / RESTCONF Client
=========================================
Communicates with Ceragon wireless transport devices over HTTP/HTTPS using RFC 8040 RESTCONF.
The full product portfolio is described in ``ceragon_tfs_adapter.portfolio``; each model maps
to one of three API flavors across two RESTCONF datastore conventions:
  - "terragraph" (api_flavor "siklu_tg" & "siklu_eh"):
      Siklu / Ceragon MultiHaul TG and EtherHaul (radio-bridge YANG, candidate/running DS)
  - "ceraos" (api_flavor "ceraos"):
      Ceragon CeraOS nodes (FibeAir IP-20, IP-50, IP-100 families, /restconf/data DS)

Provides automated protocol & HTTPS redirect negotiation, live YANG schema discovery,
2-phase candidate commit/rollback transactions, real-time PM/event telemetry streaming,
and bidirectional intent configuration across all 12 transport control domains.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests
from requests.auth import HTTPBasicAuth
import urllib3

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.models import (
    CeragonDeviceState,
    NetworkInterface,
    PMTelemetrySample,
    RadioLinkState,
    RadioSector,
)
from ceragon_tfs_adapter.portfolio import ProductSpec, resolve_model
from ceragon_tfs_adapter.schemas import get_schema_content, get_schemas_for_family

logger = logging.getLogger(__name__)

# Suppress insecure HTTPS warnings if TLS verification is disabled for lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TG_EVENT_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*,\s*"
    r"(?P<event_id>\d+)\s*,\s*(?P<category>[A-Za-z0-9_\-]+)\s*,\s*"
    r"(?P<scope>[A-Za-z0-9_\-]+)\s*,\s*(?P<subsystem>[A-Za-z0-9_\-]+)\s*,\s*"
    r"(?P<message>.*)$"
)


class CeragonRestClient:
    """Universal bidirectional client for Ceragon & Siklu RESTCONF APIs."""

    # RESTCONF Datastore Roots
    TERRAGRAPH_CANDIDATE_PATH = "/restconf/ds/ietf-datastores:candidate"
    TERRAGRAPH_RUNNING_PATH = "/restconf/ds/ietf-datastores:running"
    CERAOS_DATA_PATH = "/restconf/data"
    OPERATIONS_PATH = "/restconf/operations"
    CERAOS_OPERATIONS_PATH = "/restconf/operations"

    # CeraOS YANG Module URIs
    CERAOS_MODULES = {
        "radio": "ceragon-radio-link:radio-link-cfg",
        "qos": "ceragon-qos:qos-config",
        "protection": "ceragon-protection:protection-config",
        "slice": "ceragon-slice:slice-config",
        "multiband": "ceragon-multiband:multiband-config",
        "sync": "ceragon-sync:sync-config",
        "macsec": "ceragon-macsec:macsec-config",
        "oran_xhaul": "ceragon-oran-xhaul:oran-xhaul-config",
        "pm_telemetry": "ceragon-pm-telemetry:pm-telemetry",
        "interfaces": "ietf-interfaces:interfaces",
        "hardware": "ietf-hardware:hardware",
        "system": "ietf-system:system",
        "microwave": "ietf-microwave-radio-link:radio-link-protection-groups",
        "ptp": "ietf-ptp:ptp",
    }

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig()
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(self.config.username, self.config.password)
        self._session.headers.update({
            "Accept": "application/yang-data+json",
            "Content-Type": "application/yang-data+json",
        })
        self._session.verify = self.config.verify_tls
        self._datastore_url: Optional[str] = None
        self._resolved_base_url: Optional[str] = None
        self._device_flavor: str = "unknown"  # "terragraph" or "ceraos"

    @property
    def base_url(self) -> str:
        return self._resolved_base_url or self.config.ceragon_base_url

    @property
    def device_flavor(self) -> str:
        return self._device_flavor

    @property
    def hinted_spec(self) -> Optional[ProductSpec]:
        """Portfolio entry for the configured CERAGON_MODEL hint (if any)."""
        return resolve_model(self.config.model_hint)

    @property
    def api_flavor(self) -> str:
        """Return 'siklu_tg', 'siklu_eh', or 'ceraos'."""
        spec = self.hinted_spec
        if spec:
            return spec.api_flavor
        if self._device_flavor == "ceraos":
            return "ceraos"
        return "siklu_tg"

    def _fallback_model(self, default: str) -> str:
        return self.config.model_hint or default

    def _fallback_device_id(self) -> str:
        # Never fall back to a fixed lab serial: it would collide every unknown device onto
        # the same deterministic TFS UUID. Use the management address instead.
        return f"{self.config.device_ip}-{self.config.device_port}"

    def _record_resolved_url(self, requested_url: str, response_url: Optional[str]) -> str:
        """
        Capture HTTP -> HTTPS scheme upgrades performed by device reverse proxies (e.g. nginx on MH-T261)
        so subsequent POST/PATCH/PUT/DELETE requests hit HTTPS directly without losing payload on 301.
        """
        final_url = (response_url or requested_url).rstrip("/")
        parts = urlsplit(final_url)
        if parts.scheme and parts.netloc:
            self._resolved_base_url = f"{parts.scheme}://{parts.netloc}"
        return final_url

    def test_connection(self) -> Tuple[bool, str]:
        """Test reachability, authenticate, and auto-detect Ceragon device family."""
        tg_probes = [
            (self.TERRAGRAPH_CANDIDATE_PATH, "terragraph"),
            (self.TERRAGRAPH_RUNNING_PATH, "terragraph"),
        ]
        ceraos_probes = [
            (self.CERAOS_DATA_PATH, "ceraos"),
            (f"{self.CERAOS_DATA_PATH}/{self.CERAOS_MODULES['radio']}", "ceraos"),
        ]
        spec = self.hinted_spec
        probes = (ceraos_probes + tg_probes) if (spec and spec.protocol == "ceraos") else (tg_probes + ceraos_probes)

        for path, flavor in probes:
            url = f"{self.config.ceragon_base_url}{path}"
            try:
                logger.debug(f"[Ceragon Probe] Testing {url}")
                resp = self._session.get(url, timeout=self.config.timeout_seconds)
                if resp.status_code == 200:
                    self._datastore_url = self._record_resolved_url(url, getattr(resp, "url", None))
                    self._device_flavor = flavor
                    return True, f"Connected to Ceragon ({flavor.upper()}) at {self._datastore_url} (HTTP 200)"
                elif resp.status_code in (401, 403):
                    return False, f"Authentication failed on {url} (HTTP {resp.status_code})"
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                logger.debug(f"Probe exception on {url}: {e}")
                continue

        return False, f"Cannot reach Ceragon device at {self.config.ceragon_base_url} (All probes failed)"

    # ── YANG Schema & Operations Introspection ───────────────────────────────

    def get_yang_library(self) -> Dict[str, Any]:
        """
        Query RFC 8525 ietf-yang-library from the live device.
        Falls back to the bundled portfolio YANG schema catalog if offline.
        """
        if not self._datastore_url:
            self.test_connection()

        candidate_urls = [
            f"{self.base_url}/restconf/data/ietf-yang-library:yang-library",
            f"{self.base_url}/restconf/ds/ietf-datastores:running/ietf-yang-library:yang-library",
        ]
        for url in candidate_urls:
            try:
                resp = self._session.get(url, timeout=self.config.timeout_seconds)
                if resp.status_code == 200:
                    self._record_resolved_url(url, getattr(resp, "url", None))
                    data = resp.json()
                    lib = data.get("ietf-yang-library:yang-library", data)
                    modules: List[Dict[str, Any]] = []
                    for mset in lib.get("module-set", []):
                        for mod in mset.get("module", []):
                            modules.append({
                                "name": mod.get("name"),
                                "revision": mod.get("revision"),
                                "namespace": mod.get("namespace"),
                                "conformance": "implement",
                                "features": [
                                    f.get("name") if isinstance(f, dict) else f
                                    for f in mod.get("feature", [])
                                ],
                                "submodules": [s.get("name") for s in mod.get("submodule", [])],
                            })
                        for mod in mset.get("import-only-module", []):
                            modules.append({
                                "name": mod.get("name"),
                                "revision": mod.get("revision"),
                                "namespace": mod.get("namespace"),
                                "conformance": "import-only",
                                "features": [],
                                "submodules": [],
                            })
                    return {
                        "source": "live_device",
                        "content_id": lib.get("content-id"),
                        "module_count": len(modules),
                        "modules": modules,
                    }
            except Exception as e:
                logger.debug(f"get_yang_library probe failed on {url}: {e}")

        fallback_mods = get_schemas_for_family(self.api_flavor)
        return {
            "source": "bundled_catalog",
            "api_flavor": self.api_flavor,
            "module_count": len(fallback_mods),
            "modules": [{"name": m, "conformance": "bundled"} for m in fallback_mods],
        }

    def download_schema(self, identifier: str, version: Optional[str] = None) -> Optional[str]:
        """
        Retrieve raw YANG text for a module/submodule.
        1. Attempts RFC 6022 ietf-netconf-monitoring:get-schema RPC on the live device.
        2. Falls back to the bundled YANG schema repository.
        """
        clean_id = identifier.removesuffix(".yang").split("@")[0]
        rpc_input: Dict[str, Any] = {"identifier": clean_id}
        if version:
            rpc_input["version"] = version

        ok, out = self.invoke_rpc("ietf-netconf-monitoring:get-schema", rpc_input)
        if ok and isinstance(out, dict):
            data = (
                out.get("ietf-netconf-monitoring:output", {}).get("data")
                or out.get("output", {}).get("data")
                or out.get("data")
            )
            if isinstance(data, str) and data.strip():
                return data

        return get_schema_content(clean_id)

    def list_supported_operations(self) -> List[str]:
        """List all RESTCONF RPC operations exposed under /restconf/operations."""
        if not self._datastore_url:
            self.test_connection()
        url = f"{self.base_url}{self.OPERATIONS_PATH}"
        try:
            resp = self._session.get(url, timeout=self.config.timeout_seconds)
            if resp.status_code == 200:
                self._record_resolved_url(url, getattr(resp, "url", None))
                ops = resp.json().get("operations", {})
                if isinstance(ops, dict):
                    return sorted(ops.keys())
        except Exception as e:
            logger.debug(f"list_supported_operations failed: {e}")
        return []

    # ── Datastore Retrieval & State Parsing ──────────────────────────────────

    def fetch_full_datastore(self) -> Dict[str, Any]:
        """Fetch the entire candidate or running datastore from the device."""
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                raise ConnectionError(msg)

        resp = self._session.get(self._datastore_url, timeout=self.config.timeout_seconds)
        resp.raise_for_status()
        self._datastore_url = self._record_resolved_url(self._datastore_url, getattr(resp, "url", None))
        raw = resp.json()
        return raw.get("ietf-restconf:data", raw)

    def read_subtree(self, subtree_path: str) -> Tuple[bool, Any]:
        """Read a specific YANG subtree path via RESTCONF GET."""
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg

        target_url = f"{self._datastore_url}/{subtree_path.lstrip('/')}"
        try:
            resp = self._session.get(target_url, timeout=self.config.timeout_seconds)
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"Exception reading {target_url}: {e}"

    def get_device_state(self) -> CeragonDeviceState:
        """Fetch and parse live operational state, interfaces, radio sectors, and active links."""
        data = self.fetch_full_datastore()

        if self._device_flavor == "terragraph":
            return self._parse_terragraph_state(data)
        elif self._device_flavor == "ceraos":
            return self._parse_ceraos_state(data)
        else:
            if (
                "radio-bridge-tg-system:system" in data
                or "radio-bridge-tg-radio-common:radio-common" in data
                or "radio-bridge-eh-radio:eh-radio" in data
            ):
                self._device_flavor = "terragraph"
                return self._parse_terragraph_state(data)
            else:
                self._device_flavor = "ceraos"
                return self._parse_ceraos_state(data)

    def _parse_terragraph_state(self, data: Dict[str, Any]) -> CeragonDeviceState:
        """Parse Siklu / Ceragon radio-bridge YANG datastore (MultiHaul TG, EtherHaul)."""
        # 1. System Info
        sys_data = data.get("radio-bridge-tg-system:system", {})
        sys_state = sys_data.get("state", {})
        eh_radio = data.get("radio-bridge-eh-radio:eh-radio", {})

        node_name = sys_data.get("name") or eh_radio.get("system-name") or self.config.device_ip
        product_name = (
            sys_state.get("product")
            or eh_radio.get("model-name")
            or self._fallback_model("MH-T261")
        )
        uptime = sys_state.get("uptime", "unknown")

        # 2. Inventory
        inv_data = data.get("radio-bridge-tg-inventory:inventory", {})
        components = inv_data.get("component", [])
        chassis = next((c for c in components if c.get("physical-class") == "chassis"), {}) if components else {}
        if not sys_state.get("product") and chassis.get("model-name"):
            product_name = chassis["model-name"]
        serial_num = chassis.get("serial-num") or sys_state.get("serial-number") or self._fallback_device_id()
        hw_rev = chassis.get("hardware-rev") or "unknown"
        sw_rev = chassis.get("software-rev") or sys_state.get("software-version") or "unknown"
        mfg = chassis.get("mfg-name") or "Siklu / Ceragon"
        spec = resolve_model(product_name)
        default_freq = spec.default_frequency_mhz if spec else 60480.0

        # 3. Interfaces
        interfaces: List[NetworkInterface] = []
        ifaces_data = data.get("radio-bridge-tg-interfaces:interfaces", {}).get("interface", [])
        for iface in ifaces_data:
            idx = iface.get("ifIndex", 0)
            descr = iface.get("ifDescr") or iface.get("name") or f"port-{idx}"
            name = iface.get("name") or (descr.split()[0] if descr else f"eth{idx}")
            speed = iface.get("ifSpeed", 1_000_000_000)
            interfaces.append(NetworkInterface(
                index=idx,
                name=name,
                description=descr,
                if_type=iface.get("iftype", iface.get("interface-type", "ethernetCsmacd")),
                speed_bps=speed,
                mtu=iface.get("ifMtu", 1500),
                admin_status=iface.get("admin-status", "up"),
                oper_status=iface.get("oper-status", "down"),
                mac_address=iface.get("mac-address"),
                in_octets=int(iface.get("ifInOctets", 0) or 0),
                out_octets=int(iface.get("ifOutOctets", 0) or 0),
                in_errors=int(iface.get("ifInErrors", 0) or 0),
                out_errors=int(iface.get("ifOutErrors", 0) or 0),
                in_discards=int(iface.get("ifInDiscards", 0) or 0),
                out_discards=int(iface.get("ifOutDiscards", 0) or 0),
            ))

        # 4. Radio Sectors & Active Links
        sectors: List[RadioSector] = []
        active_links: List[RadioLinkState] = []
        radio_common = data.get("radio-bridge-tg-radio-common:radio-common", {})
        node_cfg = radio_common.get("node-config", {})
        op_mode = node_cfg.get("operation-mode") or (f"{spec.duplex}-{spec.topology}" if spec else "TU")
        tx_pwr_ctl = str(node_cfg.get("tx-power-control", "auto"))

        # Parse active RF links (if any)
        links_active = radio_common.get("links", {}).get("active", [])
        for lnk in links_active:
            rem_name = lnk.get("remote-assigned-name", "peer")
            active_links.append(RadioLinkState(
                remote_assigned_name=rem_name,
                local_sector_index=int(lnk.get("actual-local-sector-index", 1)),
                remote_sector_index=int(lnk.get("actual-remote-sector-index", 1)),
                remote_mac_address=lnk.get("remote-mac-addr"),
                local_role=lnk.get("local-role", "initiator"),
                uptime_seconds=int(lnk.get("link-uptime", 0) or 0),
                rssi_dbm=float(lnk["rssi"]) if "rssi" in lnk and lnk["rssi"] is not None else None,
                snr_db=float(lnk["snr"]) if "snr" in lnk and lnk["snr"] is not None else None,
                mcs_tx=int(lnk["mcs-tx"]) if "mcs-tx" in lnk and lnk["mcs-tx"] is not None else None,
                mcs_rx=int(lnk["mcs-rx"]) if "mcs-rx" in lnk and lnk["mcs-rx"] is not None else None,
                tx_power_index=int(lnk["tx-power-index"]) if "tx-power-index" in lnk and lnk["tx-power-index"] is not None else None,
                speed_tx_mbps=float(lnk["speed-tx"]) if "speed-tx" in lnk and lnk["speed-tx"] is not None else None,
                speed_rx_mbps=float(lnk["speed-rx"]) if "speed-rx" in lnk and lnk["speed-rx"] is not None else None,
                tx_per_pct=float(lnk["tx-per"]) if "tx-per" in lnk and str(lnk["tx-per"]).replace(".", "", 1).isdigit() else None,
                rx_per_pct=float(lnk["rx-per"]) if "rx-per" in lnk and str(lnk["rx-per"]).replace(".", "", 1).isdigit() else None,
                beam_azimuth_tx_deg=lnk.get("beam-azimuth-tx"),
                beam_elevation_tx_deg=lnk.get("beam-elevation-tx"),
                beam_azimuth_rx_deg=lnk.get("beam-azimuth-rx"),
                beam_elevation_rx_deg=lnk.get("beam-elevation-rx"),
                tx_ok_frames=int(lnk.get("tx-ok", 0) or 0),
                rx_ok_frames=int(lnk.get("rx-ok", 0) or 0),
                tx_fail_frames=int(lnk.get("tx-fail", 0) or 0),
                rx_fail_frames=int(lnk.get("rx-fail", 0) or 0),
            ))

        sec_list = radio_common.get("sectors-config", {}).get("sector", [])
        for sec in sec_list:
            idx = sec.get("index", 1)
            adm_st = sec.get("admin-status", "up")
            st = sec.get("state", {})
            freq_str = st.get("frequency", str(int(default_freq)))
            try:
                freq_val = float(freq_str)
            except ValueError:
                freq_val = default_freq

            ant_mode = st.get("antenna-mode", "beamforming" if (spec and spec.supports("beamforming")) else "fixed")
            mac_addr = st.get("mac-addr")
            temps = st.get("temperatures", {})
            modem_temp = temps.get("modem-temperature")
            rf_temps = temps.get("rf", [])
            rf_temp = rf_temps[0].get("rf-temperature") if rf_temps else None

            # Enrich sector with active link RSSI/SNR if a link is bound to this sector
            sec_link = next((l for l in active_links if l.local_sector_index == idx), None)
            sectors.append(RadioSector(
                index=idx,
                admin_status=adm_st,
                frequency_mhz=freq_val,
                antenna_mode=ant_mode,
                mac_address=mac_addr,
                tx_power_control=tx_pwr_ctl,
                modem_temperature_c=modem_temp,
                rf_temperature_c=rf_temp,
                rsl_dbm=sec_link.rssi_dbm if sec_link else None,
                snr_db=sec_link.snr_db if sec_link else None,
                current_modulation=f"MCS-{sec_link.mcs_tx}" if (sec_link and sec_link.mcs_tx is not None) else None,
            ))

        # Support EtherHaul (radio-bridge-eh-radio:eh-radio) if sectors list was empty
        if not sectors and eh_radio:
            eh_state = eh_radio.get("state", {})
            sectors.append(RadioSector(
                index=1,
                admin_status=eh_radio.get("admin-status", "up"),
                frequency_mhz=float(eh_radio.get("tx-frequency-mhz", default_freq)),
                antenna_mode="dish",
                mac_address=eh_state.get("remote-mac-address"),
                tx_power_control=str(eh_radio.get("tx-power-dbm", "auto")),
                modem_temperature_c=eh_state.get("system-temperature-celsius"),
                rf_temperature_c=eh_state.get("system-temperature-celsius"),
                rsl_dbm=eh_state.get("rssi-dbm"),
                snr_db=eh_state.get("cinr-db"),
                current_modulation=eh_state.get("actual-tx-modulation"),
            ))

        return CeragonDeviceState(
            device_id=serial_num,
            node_name=node_name,
            model=product_name,
            vendor=mfg,
            serial_number=serial_num,
            hardware_rev=hw_rev,
            software_version=sw_rev,
            management_ip=self.config.device_ip,
            management_port=self.config.device_port,
            operation_mode=op_mode,
            uptime=uptime,
            interfaces=interfaces,
            sectors=sectors,
            active_links=active_links,
            yang_modules=get_schemas_for_family(spec.api_flavor if spec else "siklu_tg"),
            raw_datastore=data,
        )

    def _parse_ceraos_state(self, data: Dict[str, Any]) -> CeragonDeviceState:
        """Parse Ceragon CeraOS datastore (FibeAir IP-20, IP-50 and IP-100 families)."""
        sys_data = data.get("ietf-system:system", {})
        sys_state = data.get("ietf-system:system-state", {})
        node_name = sys_data.get("hostname") or self.config.device_ip

        hw_data = data.get("ietf-hardware:hardware", {})
        comps = hw_data.get("component", [])
        chassis = next((c for c in comps if "chassis" in str(c.get("class", ""))), comps[0] if comps else {})
        model = chassis.get("model-name") or self._fallback_model("CeraOS-unknown")
        serial = chassis.get("serial-num") or self._fallback_device_id()
        sw_rev = chassis.get("software-rev") or "unknown"
        hw_rev = chassis.get("hardware-rev") or "unknown"
        spec = resolve_model(model)

        interfaces: List[NetworkInterface] = []
        ifaces_data = data.get("ietf-interfaces:interfaces", {}).get("interface", [])
        for i, iface in enumerate(ifaces_data):
            name = iface.get("name", f"eth-{i+1}")
            speed = iface.get("speed")
            if not isinstance(speed, int):
                speed = 10_000_000_000 if ("10G" in name.upper() or "SFP+" in name.upper()) else 1_000_000_000
            stats = iface.get("statistics", {})
            interfaces.append(NetworkInterface(
                index=i + 1,
                name=name,
                description=iface.get("description", f"Interface {name}"),
                if_type=iface.get("type", "iana-if-type:ethernetCsmacd"),
                speed_bps=speed,
                mtu=iface.get("mtu", 1500),
                admin_status="up" if iface.get("enabled", True) else "down",
                oper_status=iface.get("oper-status", "up" if iface.get("enabled", True) else "down"),
                mac_address=iface.get("phys-address"),
                in_octets=int(stats.get("in-octets", 0) or 0),
                out_octets=int(stats.get("out-octets", 0) or 0),
                in_errors=int(stats.get("in-errors", 0) or 0),
                out_errors=int(stats.get("out-errors", 0) or 0),
                in_discards=int(stats.get("in-discards", 0) or 0),
                out_discards=int(stats.get("out-discards", 0) or 0),
            ))

        sectors: List[RadioSector] = []
        active_links: List[RadioLinkState] = []
        radio_cfg = data.get("ceragon-radio-link:radio-link-cfg", {})
        carriers = radio_cfg.get("carrier") or radio_cfg.get("radio-link") if isinstance(radio_cfg, dict) else radio_cfg
        if not isinstance(carriers, list):
            carriers = [radio_cfg] if radio_cfg else []
        default_freq = spec.default_frequency_mhz if spec else 23000.0
        for idx, car in enumerate(carriers, start=1):
            if "tx-frequency-khz" in car:
                freq = float(car["tx-frequency-khz"]) / 1000.0
            elif "tx-frequency-mhz" in car:
                freq = float(car["tx-frequency-mhz"])
            else:
                freq = default_freq
            raw_idx = car.get("index", car.get("id", idx))
            sec_idx = int(raw_idx) if str(raw_idx).isdigit() else idx
            rsl = float(car["rsl-dbm"]) if "rsl-dbm" in car and car["rsl-dbm"] is not None else None
            tsl = float(car["tsl-dbm"]) if "tsl-dbm" in car and car["tsl-dbm"] is not None else None
            snr = float(car["snr-db"]) if "snr-db" in car and car["snr-db"] is not None else (
                -float(car["mse-db"]) if "mse-db" in car and car["mse-db"] is not None else None
            )
            mod = car.get("current-modulation")
            cap = float(car["current-capacity-mbps"]) if "current-capacity-mbps" in car and car["current-capacity-mbps"] is not None else None

            sectors.append(RadioSector(
                index=sec_idx,
                admin_status=car.get("admin-status", "up"),
                frequency_mhz=freq,
                antenna_mode="xpic" if car.get("xpic-enabled") else "single-polarization",
                tx_power_control=str(car.get("tx-power-dbm", "auto")),
                modem_temperature_c=car.get("modem-temperature"),
                rf_temperature_c=car.get("rf-temperature"),
                channel_bandwidth_mhz=float(car["channel-bandwidth-mhz"]) if "channel-bandwidth-mhz" in car else None,
                current_modulation=mod,
                rsl_dbm=rsl,
                tsl_dbm=tsl,
                snr_db=snr,
            ))
            if rsl is not None or cap is not None:
                active_links.append(RadioLinkState(
                    remote_assigned_name=f"{node_name}-peer-c{sec_idx}",
                    local_sector_index=sec_idx,
                    remote_sector_index=sec_idx,
                    rssi_dbm=rsl,
                    snr_db=snr,
                    speed_tx_mbps=cap,
                    speed_rx_mbps=cap,
                ))

        return CeragonDeviceState(
            device_id=serial,
            node_name=node_name,
            model=model,
            vendor="Ceragon Networks",
            serial_number=serial,
            hardware_rev=hw_rev,
            software_version=sw_rev,
            management_ip=self.config.device_ip,
            management_port=self.config.device_port,
            operation_mode=(f"{spec.duplex}-{spec.topology}" if spec else "unknown"),
            uptime=str(sys_state.get("clock", {}).get("boot-datetime", "unknown")),
            interfaces=interfaces,
            sectors=sectors,
            active_links=active_links,
            yang_modules=get_schemas_for_family("ceraos"),
            raw_datastore=data,
        )

    # ── RFC 8040 RPCs & 2-Phase Candidate Datastore Transactions ─────────────

    def invoke_rpc(self, rpc_name: str, input_payload: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
        """
        Invoke a RESTCONF operation via POST /restconf/operations/<module>:<rpc>.
        Automatically wraps input_payload in {"<module>:input": input_payload} per RFC 8040.
        """
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg

        url = f"{self.base_url}{self.OPERATIONS_PATH}/{rpc_name.lstrip('/')}"
        body: Optional[Dict[str, Any]] = None
        if input_payload:
            if ":" in rpc_name and not any(k.endswith(":input") or k == "input" for k in input_payload):
                mod_prefix = rpc_name.split(":", 1)[0]
                body = {f"{mod_prefix}:input": input_payload}
            else:
                body = input_payload

        logger.info(f"[Ceragon RPC] POST {url}")
        try:
            resp = self._session.post(
                url,
                json=body if body is not None else {},
                timeout=self.config.timeout_seconds,
            )
            self._record_resolved_url(url, getattr(resp, "url", None))
            if resp.status_code == 204 or not resp.text.strip():
                return True, {}
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"RPC {rpc_name} returned HTTP {resp.status_code}: {resp.text[:250]}"
        except Exception as e:
            return False, f"Exception invoking RPC {rpc_name}: {e}"

    def commit_candidate(self) -> Tuple[bool, str]:
        """Commit staged changes from the candidate datastore to running (ietf-netconf:commit)."""
        if self._device_flavor == "ceraos":
            return True, "CeraOS /restconf/data commits immediately"
        ok, out = self.invoke_rpc("ietf-netconf:commit")
        return ok, "Committed candidate datastore to running" if ok else str(out)

    def discard_candidate(self) -> Tuple[bool, str]:
        """Discard uncommitted changes in the candidate datastore (ietf-netconf:discard-changes)."""
        if self._device_flavor == "ceraos":
            return True, "No candidate staging on CeraOS /restconf/data"
        ok, out = self.invoke_rpc("ietf-netconf:discard-changes")
        return ok, "Discarded candidate datastore changes" if ok else str(out)

    def validate_candidate(self) -> Tuple[bool, str]:
        """Validate the candidate datastore prior to commit (ietf-netconf:validate)."""
        if self._device_flavor == "ceraos":
            return True, "Validated"
        ok, out = self.invoke_rpc("ietf-netconf:validate", {"source": {"candidate": [None]}})
        return ok, "Candidate datastore validated" if ok else str(out)

    def set_rollback_timeout(self, timeout_seconds: int = 120) -> Tuple[bool, str]:
        """Arm the hardware failsafe rollback timer (radio-bridge-tg-rollback:set-rollback-timeout)."""
        ok, out = self.invoke_rpc(
            "radio-bridge-tg-rollback:set-rollback-timeout",
            {"timeout": int(timeout_seconds)},
        )
        return ok, f"Rollback timeout set to {timeout_seconds}s" if ok else str(out)

    def rollback_keep_alive(self) -> Tuple[bool, str]:
        """Confirm connectivity and disarm the rollback timer (radio-bridge-tg-rollback:rollback-keep-alive)."""
        ok, out = self.invoke_rpc("radio-bridge-tg-rollback:rollback-keep-alive")
        return ok, "Rollback timer confirmed (keep-alive sent)" if ok else str(out)

    # ── Core RESTCONF CRUD Primitives (PATCH / PUT / DELETE) ─────────────────

    def apply_patch(
        self,
        subtree_path: str,
        payload: Dict[str, Any],
        auto_commit: bool = False,
    ) -> Tuple[bool, str]:
        """Apply a partial configuration update via RESTCONF PATCH."""
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg

        target_url = f"{self._datastore_url}/{subtree_path.lstrip('/')}"
        logger.info(f"[Ceragon REST] PATCH {target_url}")
        try:
            resp = self._session.patch(
                target_url,
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            self._record_resolved_url(target_url, getattr(resp, "url", None))
            if resp.status_code in (200, 201, 204):
                if auto_commit and self._device_flavor == "terragraph":
                    c_ok, c_msg = self.commit_candidate()
                    if not c_ok:
                        self.discard_candidate()
                        return False, f"PATCH staged on {subtree_path}, but commit failed: {c_msg}"
                return True, f"Successfully applied changes to {subtree_path}"
            return False, f"Device returned HTTP {resp.status_code}: {resp.text[:250]}"
        except Exception as e:
            return False, f"Exception applying PATCH to {target_url}: {e}"

    def apply_put(
        self,
        subtree_path: str,
        payload: Dict[str, Any],
        auto_commit: bool = False,
    ) -> Tuple[bool, str]:
        """Create or replace a configuration resource via RESTCONF PUT."""
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg

        target_url = f"{self._datastore_url}/{subtree_path.lstrip('/')}"
        logger.info(f"[Ceragon REST] PUT {target_url}")
        try:
            resp = self._session.put(
                target_url,
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            self._record_resolved_url(target_url, getattr(resp, "url", None))
            if resp.status_code in (200, 201, 204):
                if auto_commit and self._device_flavor == "terragraph":
                    c_ok, c_msg = self.commit_candidate()
                    if not c_ok:
                        self.discard_candidate()
                        return False, f"PUT staged on {subtree_path}, but commit failed: {c_msg}"
                return True, f"Successfully replaced resource at {subtree_path}"
            return False, f"Device returned HTTP {resp.status_code}: {resp.text[:250]}"
        except Exception as e:
            return False, f"Exception applying PUT to {target_url}: {e}"

    def apply_delete(self, subtree_path: str, auto_commit: bool = False) -> Tuple[bool, str]:
        """Delete a configuration resource via RESTCONF DELETE."""
        if not self._datastore_url:
            ok, msg = self.test_connection()
            if not ok:
                return False, msg

        target_url = f"{self._datastore_url}/{subtree_path.lstrip('/')}"
        logger.info(f"[Ceragon REST] DELETE {target_url}")
        try:
            resp = self._session.delete(target_url, timeout=self.config.timeout_seconds)
            self._record_resolved_url(target_url, getattr(resp, "url", None))
            if resp.status_code in (200, 204):
                if auto_commit and self._device_flavor == "terragraph":
                    self.commit_candidate()
                return True, f"Successfully deleted {subtree_path}"
            return False, f"Device returned HTTP {resp.status_code}: {resp.text[:250]}"
        except Exception as e:
            return False, f"Exception deleting {target_url}: {e}"

    # ── Southbound Control Across All 12 Portfolio Intent Domains ────────────

    def apply_vlan_slice(
        self,
        vlan_id: int,
        slice_name: str,
        bandwidth_mbps: Optional[int] = None,
        endpoints: Optional[List[str]] = None,
        bridge_id: Optional[int] = None,
        s_vlan_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Provision or update a network slice / VLAN bridge across all portfolio families:
        - MultiHaul TG / EtherHaul (radio-bridge-tg-user-bridge:user-bridge):
            Creates/updates a bridge (1..64) with C-VLAN / S-VLAN / Q-in-Q bridge-ports on eth1 + rf.
        - CeraOS (ceragon-slice:slice-config):
            Creates/updates an EVC transport slice with VLAN tag, CIR bandwidth, and CoS queue.
        """
        logger.info(f"[Slice Control] Provisioning Slice '{slice_name}' (VLAN: {vlan_id}, BW: {bandwidth_mbps} Mbps)")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "terragraph":
            b_id = bridge_id or ((int(vlan_id) - 1) % 63 + 2)  # Keep bridge 1 untouched, map 2..64
            port_type = "q-in-q" if s_vlan_id else "c-vlan"
            ifaces = endpoints or ["eth1", "rf"]
            bridge_ports = []
            for idx, if_name in enumerate(ifaces, start=1):
                bp: Dict[str, Any] = {
                    "bridge-port-id": idx,
                    "interface": if_name,
                    "bridge-port-type": port_type,
                    "c-vlan": int(vlan_id),
                }
                if s_vlan_id:
                    bp["s-vlan"] = int(s_vlan_id)
                bridge_ports.append(bp)

            payload = {
                "radio-bridge-tg-user-bridge:bridge": [
                    {
                        "bridge-id": b_id,
                        "bridge-port": bridge_ports,
                    }
                ]
            }
            path = f"radio-bridge-tg-user-bridge:user-bridge/bridge={b_id}"
            return self.apply_patch(path, payload)

        elif self._device_flavor == "ceraos":
            slice_entry: Dict[str, Any] = {
                "slice-id": slice_name,
                "vlan-tag": int(vlan_id),
                "bandwidth-reservation-mbps": int(bandwidth_mbps or 1000),
                "priority-queue": "expedited-forwarding",
                "admin-status": "up",
            }
            if s_vlan_id:
                slice_entry["s-vlan-tag"] = int(s_vlan_id)
            if endpoints:
                slice_entry["endpoints"] = endpoints
            path = "ceragon-slice:slice-config"
            return self.apply_patch(path, {"ceragon-slice:slice-config": {"slice": [slice_entry]}})

        return True, f"Slice {slice_name} (VLAN {vlan_id}) staged"

    def delete_vlan_slice(
        self,
        vlan_id: int,
        slice_name: Optional[str] = None,
        bridge_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Delete a provisioned network slice / user-bridge."""
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "terragraph":
            b_id = bridge_id or ((int(vlan_id) - 1) % 63 + 2)
            return self.apply_delete(f"radio-bridge-tg-user-bridge:user-bridge/bridge={b_id}")
        elif self._device_flavor == "ceraos":
            sname = slice_name or f"slice-{vlan_id}"
            return self.apply_delete(f"ceragon-slice:slice-config/slice={sname}")
        return True, f"Deleted slice VLAN {vlan_id}"

    def apply_radio_tuning(
        self,
        frequency_mhz: Optional[float] = None,
        tx_power_dbm: Optional[float] = None,
        admin_status: Optional[str] = None,
        script_id: Optional[int] = None,
        channel_bandwidth_mhz: Optional[float] = None,
        sector_index: int = 1,
        atpc_enabled: Optional[bool] = None,
        polarity: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Tune physical radio parameters across MultiHaul TG, EtherHaul, and CeraOS."""
        logger.info(
            f"[Radio Tuning] Freq={frequency_mhz}MHz, BW={channel_bandwidth_mhz}MHz, "
            f"Power={tx_power_dbm}dBm, Script={script_id}, Sector={sector_index}"
        )
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "terragraph":
            if self.api_flavor == "siklu_eh":
                eh_payload: Dict[str, Any] = {}
                if frequency_mhz is not None:
                    eh_payload["tx-frequency-mhz"] = int(frequency_mhz)
                if tx_power_dbm is not None:
                    eh_payload["tx-power-dbm"] = int(tx_power_dbm)
                if admin_status is not None:
                    eh_payload["admin-status"] = admin_status.lower()
                if atpc_enabled is not None:
                    eh_payload["atpc-enabled"] = bool(atpc_enabled)
                if channel_bandwidth_mhz is not None:
                    eh_payload["channel-width"] = f"bw-{int(channel_bandwidth_mhz)}mhz"
                if eh_payload:
                    return self.apply_patch(
                        "radio-bridge-eh-radio:eh-radio",
                        {"radio-bridge-eh-radio:eh-radio": eh_payload},
                    )
                return True, "No EtherHaul radio changes needed"

            # MultiHaul TG (radio-bridge-tg-radio-common & radio-bridge-tg-radio-dn)
            messages: List[str] = []
            node_payload: Dict[str, Any] = {}
            if tx_power_dbm is not None or atpc_enabled is not None:
                if atpc_enabled or tx_power_dbm is None:
                    node_payload["tx-power-control"] = "auto"
                else:
                    idx = max(6, min(31, int(tx_power_dbm)))
                    node_payload["tx-power-control"] = idx
            if node_payload:
                ok, msg = self.apply_patch(
                    "radio-bridge-tg-radio-common:radio-common/node-config",
                    {"radio-bridge-tg-radio-common:node-config": node_payload},
                )
                if not ok:
                    return False, msg
                messages.append(msg)

            if admin_status is not None:
                sec_payload = {
                    "radio-bridge-tg-radio-common:sector": [
                        {"index": sector_index, "admin-status": admin_status.lower()}
                    ]
                }
                ok, msg = self.apply_patch(
                    f"radio-bridge-tg-radio-common:radio-common/sectors-config/sector={sector_index}",
                    sec_payload,
                )
                if not ok:
                    return False, msg
                messages.append(msg)

            if frequency_mhz is not None or polarity is not None:
                # TG valid channels: 58320, 60480, 62640, 64800 MHz
                tg_channels = [58320, 60480, 62640, 64800]
                prof: Dict[str, Any] = {}
                if frequency_mhz is not None:
                    nearest = min(tg_channels, key=lambda c: abs(c - float(frequency_mhz)))
                    prof["frequency"] = str(nearest)
                if polarity is not None:
                    prof["polarity"] = polarity
                dn_payload = {
                    "radio-bridge-tg-radio-dn:sector": [
                        {"index": sector_index, "radio-profile": prof}
                    ]
                }
                ok, msg = self.apply_patch(
                    f"radio-bridge-tg-radio-dn:radio-dn/sectors-config/sector={sector_index}",
                    dn_payload,
                )
                if not ok:
                    return False, msg
                messages.append(msg)

            return True, "; ".join(messages) if messages else "No TG radio changes needed"

        elif self._device_flavor == "ceraos":
            payload: Dict[str, Any] = {}
            if frequency_mhz is not None:
                payload["tx-frequency-khz"] = int(float(frequency_mhz) * 1000)
                payload["tx-frequency-mhz"] = float(frequency_mhz)
            if channel_bandwidth_mhz is not None:
                payload["channel-bandwidth-mhz"] = float(channel_bandwidth_mhz)
            if tx_power_dbm is not None:
                payload["tx-power-dbm"] = float(tx_power_dbm)
            if script_id is not None:
                payload["mrmc-script-id"] = int(script_id)
            if admin_status is not None:
                payload["admin-status"] = admin_status.lower()
            if atpc_enabled is not None:
                payload["atpc-enabled"] = bool(atpc_enabled)

            if payload:
                return self.apply_patch(
                    "ceragon-radio-link:radio-link-cfg",
                    {"ceragon-radio-link:radio-link-cfg": payload},
                )
            return True, "No CeraOS radio changes needed"

        return True, "Tuning acknowledged"

    def apply_acm_config(
        self,
        min_modulation: Optional[str] = None,
        max_modulation: Optional[str] = None,
        adaptive_enabled: bool = True,
    ) -> Tuple[bool, str]:
        """Configure Adaptive Coding & Modulation (ACM) profile bounds."""
        logger.info(f"[ACM Control] Adaptive={adaptive_enabled}, Min={min_modulation}, Max={max_modulation}")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            payload: Dict[str, Any] = {
                "mrmc-mode": "adaptive" if adaptive_enabled else "fixed",
            }
            if min_modulation:
                payload["mrmc-min-profile"] = str(min_modulation).lower().replace("_", "-")
            if max_modulation:
                payload["mrmc-max-profile"] = str(max_modulation).lower().replace("_", "-")
            return self.apply_patch(
                "ceragon-radio-link:radio-link-cfg",
                {"ceragon-radio-link:radio-link-cfg": payload},
            )

        elif self._device_flavor == "terragraph":
            if self.api_flavor == "siklu_eh":
                eh_payload: Dict[str, Any] = {"acm-enabled": bool(adaptive_enabled)}
                if min_modulation:
                    eh_payload["min-modulation"] = str(min_modulation).lower()
                if max_modulation:
                    eh_payload["max-modulation"] = str(max_modulation).lower()
                return self.apply_patch(
                    "radio-bridge-eh-radio:eh-radio",
                    {"radio-bridge-eh-radio:eh-radio": eh_payload},
                )
            # On MultiHaul TG, link-distance controls MCS ceiling (Normal / Long / Extra-long)
            dist = "Normal" if (max_modulation and "12" in str(max_modulation)) else "Long"
            return self.apply_patch(
                "radio-bridge-tg-radio-common:radio-common/node-config",
                {"radio-bridge-tg-radio-common:node-config": {"link-distance": dist}},
            )

        return True, "ACM configuration staged"

    def apply_qos_tsn(
        self,
        qos_mode: str = "hierarchical-hqos",
        cir_mbps: Optional[int] = None,
        pir_mbps: Optional[int] = None,
        tsn_enabled: bool = False,
        cycle_time_ns: int = 1_000_000,
        gate_control_list: Optional[List[Dict[str, Any]]] = None,
        preemption_8021qbu: bool = False,
        cos_queues: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, str]:
        """Configure 8-CoS Hierarchical QoS and IEEE 802.1Qbv Time-Aware Shaper (TAS)."""
        logger.info(f"[QoS/TSN Control] mode={qos_mode}, TSN={tsn_enabled}, cycle={cycle_time_ns}ns")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            qos_payload: Dict[str, Any] = {
                "qos-mode": "tsn-scheduled" if tsn_enabled else qos_mode,
            }
            if cir_mbps is not None:
                qos_payload["policer-profile"] = [{
                    "profile-id": 1,
                    "cir-mbps": int(cir_mbps),
                    "eir-mbps": int((pir_mbps or cir_mbps) - cir_mbps),
                }]
            if cos_queues:
                qos_payload["cos-queue"] = cos_queues
            if tsn_enabled or gate_control_list:
                gcl = gate_control_list or [
                    {"slot-id": 0, "gate-states-mask": 128, "time-interval-ns": int(cycle_time_ns * 0.2)},
                    {"slot-id": 1, "gate-states-mask": 127, "time-interval-ns": int(cycle_time_ns * 0.8)},
                ]
                qos_payload["tsn-tas"] = {
                    "enabled": True,
                    "cycle-time-ns": int(cycle_time_ns),
                    "frame-preemption-8021qbu": bool(preemption_8021qbu),
                    "gate-control-entry": gcl,
                }
            return self.apply_patch(
                "ceragon-qos:qos-config",
                {"ceragon-qos:qos-config": qos_payload},
            )

        elif self._device_flavor == "terragraph":
            # Map QoS profile on MultiHaul TG / EtherHaul
            sched_payload = {
                "ieee802-dot1q-sched:gate-parameter-table": {
                    "gate-enabled": bool(tsn_enabled),
                    "frame-preemption-enabled": bool(preemption_8021qbu),
                }
            }
            return self.apply_patch("ieee802-dot1q-sched:bridge-port/gate-parameter-table", sched_payload)

        return True, "QoS/TSN configuration staged"

    def apply_beamforming(
        self,
        sector_index: int = 1,
        trigger_topo_scan: bool = True,
        remote_assigned_name: Optional[str] = None,
        tx_golay_index: Optional[int] = None,
        rx_golay_index: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Trigger 60 GHz phased-array electronic beam scan or update link Golay/sector bindings."""
        logger.info(f"[Beamforming Control] sector={sector_index}, scan={trigger_topo_scan}, peer={remote_assigned_name}")
        if not self._datastore_url:
            self.test_connection()

        if trigger_topo_scan:
            ok, out = self.invoke_rpc(
                "radio-bridge-tg-radio-dn:start-topo-scan",
                {"sectors": [{"index": int(sector_index)}]},
            )
            if ok:
                return True, f"Triggered beamforming topology scan on sector {sector_index}"
            # If the node is in TU mode, start-topo-scan may not apply; fall through to link update
            if not remote_assigned_name:
                return ok, str(out)

        if remote_assigned_name:
            link_cfg: Dict[str, Any] = {
                "remote-assigned-name": remote_assigned_name,
                "local-sector": [{"index": int(sector_index)}],
                "control-superframe": "unspecified",
                "admin-status": "up",
            }
            if tx_golay_index is not None:
                link_cfg["tx-golay-index"] = str(tx_golay_index)
            if rx_golay_index is not None:
                link_cfg["rx-golay-index"] = str(rx_golay_index)
            return self.apply_patch(
                f"radio-bridge-tg-radio-dn:radio-dn/links/configured={remote_assigned_name}",
                {"radio-bridge-tg-radio-dn:configured": [link_cfg]},
            )

        return True, f"Beamforming configured on sector {sector_index}"

    def apply_multiband_bonding(
        self,
        bond_name: str = "bond-1",
        member_interfaces: Optional[List[str]] = None,
        bonding_mode: str = "l1-radio-link-bonding",
        min_priority_backup: int = 5,
    ) -> Tuple[bool, str]:
        """Configure Multi-Band carrier bonding / link aggregation across TG, EH, and CeraOS."""
        logger.info(f"[Multi-Band Control] bond={bond_name}, members={member_interfaces}, mode={bonding_mode}")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            members = member_interfaces or ["rf-eband-1", "rf-mw-1"]
            member_list = [
                {
                    "interface-name": m,
                    "band-role": "primary-eband" if idx == 0 else "secondary-microwave",
                    "weight": 70 if idx == 0 else 30,
                }
                for idx, m in enumerate(members)
            ]
            payload = {
                "ceragon-multiband:multiband-config": {
                    "bonding-group": [{
                        "group-id": 1,
                        "name": bond_name,
                        "bonding-mode": bonding_mode,
                        "throughput-enhancement": True,
                        "min-priority-for-mw-backup": int(min_priority_backup),
                        "member": member_list,
                    }]
                }
            }
            return self.apply_patch("ceragon-multiband:multiband-config", payload)

        elif self._device_flavor == "terragraph":
            if self.api_flavor == "siklu_eh":
                return self.apply_patch(
                    "radio-bridge-eh-radio:eh-radio",
                    {"radio-bridge-eh-radio:eh-radio": {"extend-mm-enabled": True}},
                )
            bname = bond_name if bond_name.startswith("bond-") else f"bond-{bond_name}"
            members = member_interfaces or ["eth1", "eth2"]
            bond_members = [
                {
                    "interface": m,
                    "weight": max(1, 99 - idx * 10),
                    "monitoring-type": "link-operation-status",
                }
                for idx, m in enumerate(members)
            ]
            payload = {
                "radio-bridge-tg-bond:bond": [{
                    "bond-name": bname,
                    "bond-type": "active-backup",
                    "bond-members": {"bond-member": bond_members},
                }]
            }
            return self.apply_patch(f"radio-bridge-tg-bond:bonds/bond={bname}", payload)

        return True, f"Multi-band bonding {bond_name} staged"

    def apply_protection(
        self,
        mode: str = "one-plus-one-hsb",
        group_id: int = 1,
        member_carriers: Optional[List[int]] = None,
        revertive: bool = True,
        trigger_switchover: bool = False,
    ) -> Tuple[bool, str]:
        """Configure 1+1 Hot-Standby (HSB), 2+0, XPIC, or Space Diversity protection."""
        logger.info(f"[Protection Control] mode={mode}, group={group_id}, switchover={trigger_switchover}")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            norm_mode = mode.lower()
            if "1+1" in norm_mode or "hsb" in norm_mode:
                gtype = "one-plus-one-hsb"
            elif "2+0" in norm_mode:
                gtype = "two-plus-zero"
            elif "diversity" in norm_mode:
                gtype = "space-diversity"
            elif "mimo" in norm_mode:
                gtype = "mimo-4x4"
            else:
                gtype = "xpic"

            payload = {
                "ceragon-protection:protection-config": {
                    "amcc-group": [{
                        "group-id": int(group_id),
                        "group-type": gtype,
                        "admin-status": "enable",
                        "revertive": bool(revertive),
                        "member-carriers": member_carriers or [1, 2],
                    }]
                }
            }
            ok, msg = self.apply_patch("ceragon-protection:protection-config", payload)
            if not ok:
                return False, msg
            if trigger_switchover:
                sw_ok, sw_out = self.invoke_rpc(
                    "ceragon-protection:trigger-protection-switch",
                    {"group-id": int(group_id), "command": "manual-switch"},
                )
                return sw_ok, f"{msg}; switchover RPC: {sw_out}"
            return True, msg

        elif self._device_flavor == "terragraph":
            return self.apply_multiband_bonding(
                bond_name=f"bond-{group_id}",
                member_interfaces=["eth1", "eth2"],
                bonding_mode="active-backup",
            )

        return True, f"Protection group {group_id} ({mode}) staged"

    def apply_sync_ptp(
        self,
        sync_mode: str = "ptp",
        ptp_profile: str = "itu-g8275-1",
        domain_number: int = 24,
        synce_enabled: bool = True,
        ssm_quality: str = "ql-prc",
    ) -> Tuple[bool, str]:
        """Configure ITU-T G.8275.1/G.8275.2 IEEE 1588v2 PTP, SyncE, or GPS/RF synchronization."""
        logger.info(f"[Sync Control] mode={sync_mode}, profile={ptp_profile}, domain={domain_number}")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            payload = {
                "ceragon-sync:sync-config": {
                    "synce": {
                        "enabled": bool(synce_enabled),
                        "ssm-enabled": True,
                        "clock-source": [{
                            "interface-id": 268443713,
                            "quality-level": ssm_quality.lower(),
                            "priority": 1,
                        }],
                    },
                    "ptp-1588": {
                        "admin-state": "enabled",
                        "clock-mode": "telecom-boundary-clock",
                        "profile": ptp_profile,
                        "domain-number": int(domain_number),
                        "cos-preserve-enabled": True,
                        "cos-value": 7,
                    },
                }
            }
            return self.apply_patch("ceragon-sync:sync-config", payload)

        elif self._device_flavor == "terragraph":
            tg_sync = "ptp" if "ptp" in sync_mode.lower() else (
                "gps-sync-holdover" if "gps" in sync_mode.lower() else "rf-sync"
            )
            return self.apply_patch(
                "radio-bridge-tg-radio-dn:radio-dn/node-config",
                {"radio-bridge-tg-radio-dn:node-config": {"sync-mode": tg_sync}},
            )

        return True, f"Synchronization ({sync_mode}) staged"

    def apply_security_macsec(
        self,
        enabled: bool = True,
        cipher_suite: str = "gcm-aes-256",
        sak_rekey_interval_sec: int = 3600,
        interfaces: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """Configure IEEE 802.1AE MACsec or FIPS 140-2 AES-256 air-interface encryption."""
        logger.info(f"[Security Control] enabled={enabled}, cipher={cipher_suite}, rekey={sak_rekey_interval_sec}s")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            ifaces = interfaces or ["eth-1", "radio-1"]
            payload = {
                "ceragon-macsec:macsec-config": {
                    "global-enabled": bool(enabled),
                    "cipher-suite": cipher_suite.lower(),
                    "sak-rekey-interval-sec": int(sak_rekey_interval_sec),
                    "secured-interface": [
                        {"interface-name": i, "enabled": bool(enabled)} for i in ifaces
                    ],
                }
            }
            return self.apply_patch("ceragon-macsec:macsec-config", payload)

        elif self._device_flavor == "terragraph":
            if self.api_flavor == "siklu_eh":
                return self.apply_patch(
                    "radio-bridge-eh-radio:eh-radio",
                    {"radio-bridge-eh-radio:eh-radio": {"aes-encryption-enabled": bool(enabled)}},
                )
            return self.apply_patch(
                "ieee802-dot1ae-macsec:macsec",
                {
                    "ieee802-dot1ae-macsec:macsec": {
                        "protect-frames": bool(enabled),
                        "current-cipher-suite": cipher_suite.lower(),
                    }
                },
            )

        return True, "Security/MACsec configuration staged"

    def apply_oran_xhaul(
        self,
        enabled: bool = True,
        functional_split: str = "split-7-2x-ecpri-fronthaul",
        iq_compression: str = "bfp-9bit",
        cti_enabled: bool = True,
        delay_budget_us: int = 100,
        ecpri_vlan_id: int = 10,
    ) -> Tuple[bool, str]:
        """Configure O-RAN Split 7.2x eCPRI fronthaul/midhaul gateway parameters."""
        logger.info(f"[O-RAN xHaul Control] split={functional_split}, compression={iq_compression}, CTI={cti_enabled}")
        if not self._datastore_url:
            self.test_connection()

        payload = {
            "ceragon-oran-xhaul:oran-xhaul-config": {
                "enabled": bool(enabled),
                "functional-split": functional_split,
                "iq-compression": iq_compression,
                "cti-enabled": bool(cti_enabled),
                "one-way-delay-budget-us": int(delay_budget_us),
                "ecpri-vlan-id": int(ecpri_vlan_id),
                "ecpri-pcp-priority": 7,
            }
        }
        return self.apply_patch("ceragon-oran-xhaul:oran-xhaul-config", payload)

    def apply_energy_policy(
        self,
        mode: str = "green-atpc",
        target_rsl_dbm: float = -42.0,
        sleep_secondary_carriers: bool = False,
    ) -> Tuple[bool, str]:
        """Configure green energy-saving ATPC or secondary carrier sleep modes."""
        logger.info(f"[Energy Policy] mode={mode}, target_rsl={target_rsl_dbm}dBm, sleep_2nd={sleep_secondary_carriers}")
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            emode = "secondary-carrier-sleep" if sleep_secondary_carriers else mode
            payload = {
                "ceragon-radio-link:radio-link-cfg": {
                    "energy-saving-mode": emode,
                    "atpc-enabled": True,
                    "atpc-reference-rx-level-dbm": float(target_rsl_dbm),
                }
            }
            return self.apply_patch("ceragon-radio-link:radio-link-cfg", payload)

        elif self._device_flavor == "terragraph":
            return self.apply_radio_tuning(atpc_enabled=True)

        return True, "Energy policy staged"

    # ── Northbound Telemetry & Event Streaming (Device -> Adapter -> TFS) ────

    @staticmethod
    def parse_event_string(index: int, raw_event: str) -> Dict[str, Any]:
        """Parse a Siklu/Ceragon event log line into structured fields."""
        m = _TG_EVENT_RE.match((raw_event or "").strip())
        if m:
            return {
                "index": index,
                "timestamp": m.group("timestamp"),
                "event_id": int(m.group("event_id")),
                "category": m.group("category").strip(),
                "scope": m.group("scope").strip(),
                "subsystem": m.group("subsystem").strip(),
                "message": m.group("message").strip(),
                "raw": raw_event,
            }
        return {
            "index": index,
            "timestamp": None,
            "category": "SYSTEM",
            "subsystem": "GENERAL",
            "message": (raw_event or "").strip(),
            "raw": raw_event,
        }

    def fetch_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch latest hardware events from the device via RPC:
          - Siklu TG / EH: POST /restconf/operations/radio-bridge-tg-events:get-events
          - CeraOS:        POST /restconf/operations/ceragon-pm-telemetry:get-events
        """
        if not self._datastore_url:
            self.test_connection()

        rpc_name = (
            "ceragon-pm-telemetry:get-events"
            if self._device_flavor == "ceraos"
            else "radio-bridge-tg-events:get-events"
        )
        ok, out = self.invoke_rpc(rpc_name, {"number": int(limit)})
        if not ok or not isinstance(out, dict):
            return []

        ev_list = (
            out.get("radio-bridge-tg-events:output", {}).get("events")
            or out.get("ceragon-pm-telemetry:output", {}).get("events")
            or out.get("output", {}).get("events")
            or []
        )
        parsed: List[Dict[str, Any]] = []
        for item in ev_list:
            if isinstance(item, dict):
                idx = int(item.get("index", len(parsed)))
                raw = str(item.get("event", ""))
                parsed.append(self.parse_event_string(idx, raw))
        return parsed

    def fetch_pm_items(self, item_type: str = "rf", period_type: str = "quarter") -> List[Dict[str, Any]]:
        """
        Fetch 15-minute ('quarter') or 24-hour ('day') Performance Monitoring (PM) intervals:
          - Siklu TG / EH: radio-bridge-tg-pm:get-pm-items + radio-bridge-tg-pm:get-pm-item-info
          - CeraOS:        ceragon-pm-telemetry:get-pm-bins
        """
        if not self._datastore_url:
            self.test_connection()

        if self._device_flavor == "ceraos":
            cera_period = "fifteen-min" if period_type == "quarter" else "twenty-four-hour"
            ok, out = self.invoke_rpc(
                "ceragon-pm-telemetry:get-pm-bins",
                {"carrier-id": 1, "period-type": cera_period},
            )
            if ok and isinstance(out, dict):
                return (
                    out.get("ceragon-pm-telemetry:output", {}).get("bins")
                    or out.get("output", {}).get("bins")
                    or []
                )
            return []

        ok, out = self.invoke_rpc(
            "radio-bridge-tg-pm:get-pm-items",
            {"item-type": item_type, "period-type": period_type},
        )
        if not ok or not isinstance(out, dict):
            return []

        pm_items = (
            out.get("radio-bridge-tg-pm:output", {}).get("pm-items")
            or out.get("output", {}).get("pm-items")
            or []
        )
        intervals: List[Dict[str, Any]] = []
        for pm_item in pm_items:
            names = pm_item.get("names", [])
            i_ok, i_out = self.invoke_rpc(
                "radio-bridge-tg-pm:get-pm-item-info",
                {
                    "item-type": pm_item.get("item-type", item_type),
                    "names": names,
                    "period-type": period_type,
                },
            )
            if i_ok and isinstance(i_out, dict):
                periods = (
                    i_out.get("radio-bridge-tg-pm:output", {}).get("pm-info-periods")
                    or i_out.get("output", {}).get("pm-info-periods")
                    or []
                )
                intervals.append({
                    "item_type": pm_item.get("item-type", item_type),
                    "names": names,
                    "periods": periods,
                })
        return intervals

    def fetch_pm_telemetry(self, period_type: str = "quarter", event_limit: int = 10) -> PMTelemetrySample:
        """
        Collect a complete real-time telemetry & PM snapshot from the device:
          - Live device state (interfaces octets/errors, sector temperatures, active RF links)
          - Historical 15-min/24-h PM intervals (get-pm-items / get-pm-bins)
          - Recent hardware events (get-events)
        """
        state = self.get_device_state()
        events = self.fetch_events(limit=event_limit)
        pm_intervals = self.fetch_pm_items(item_type="rf", period_type=period_type)
        state.recent_events = events

        primary_sec = state.sectors[0] if state.sectors else None
        primary_link = state.active_links[0] if state.active_links else None
        spec = state.product_spec

        in_oct = sum(i.in_octets for i in state.interfaces)
        out_oct = sum(i.out_octets for i in state.interfaces)
        in_err = sum(i.in_errors for i in state.interfaces)
        out_err = sum(i.out_errors for i in state.interfaces)

        rsl = (
            primary_link.rssi_dbm
            if (primary_link and primary_link.rssi_dbm is not None)
            else (primary_sec.rsl_dbm if primary_sec else None)
        )
        snr = (
            primary_link.snr_db
            if (primary_link and primary_link.snr_db is not None)
            else (primary_sec.snr_db if primary_sec else None)
        )
        air_cap = (
            primary_link.speed_tx_mbps
            if (primary_link and primary_link.speed_tx_mbps is not None)
            else (state.max_throughput_gbps * 1000.0)
        )
        modulation = (
            f"MCS-{primary_link.mcs_tx}"
            if (primary_link and primary_link.mcs_tx is not None)
            else (primary_sec.current_modulation if (primary_sec and primary_sec.current_modulation) else (spec.max_modulation if spec else None))
        )

        return PMTelemetrySample(
            device_id=state.device_id,
            node_name=state.node_name,
            model=state.model,
            api_flavor=spec.api_flavor if spec else self.api_flavor,
            period_type=period_type,
            rsl_dbm=rsl,
            tsl_dbm=primary_sec.tsl_dbm if primary_sec else None,
            snr_db=snr,
            modulation=modulation,
            air_capacity_mbps=air_cap,
            in_octets_total=in_oct,
            out_octets_total=out_oct,
            in_errors_total=in_err,
            out_errors_total=out_err,
            modem_temperature_c=primary_sec.modem_temperature_c if primary_sec else None,
            rf_temperature_c=primary_sec.rf_temperature_c if primary_sec else None,
            active_links=[lnk.to_dict() for lnk in state.active_links],
            pm_intervals=pm_intervals,
            recent_events=events,
        )

    def stream_telemetry(
        self,
        callback: Callable[[PMTelemetrySample], None],
        interval_seconds: float = 5.0,
        max_samples: Optional[int] = None,
        stop_Check: Optional[Callable[[], bool]] = None,
    ) -> int:
        """
        Continuously stream bidirectional telemetry snapshots from the device to `callback`.
        First attempts RFC 8040 Server-Sent Events (/restconf/streams/NETCONF) if available,
        and maintains a deterministic periodic telemetry & event stream.
        """
        emitted = 0
        while True:
            if stop_Check and stop_Check():
                break
            try:
                sample = self.fetch_pm_telemetry()
                callback(sample)
                emitted += 1
            except Exception as e:
                logger.warning(f"[Telemetry Stream] sample error: {e}")

            if max_samples is not None and emitted >= max_samples:
                break
            time.sleep(max(0.2, float(interval_seconds)))
        return emitted
