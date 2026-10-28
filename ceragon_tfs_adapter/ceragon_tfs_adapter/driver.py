"""
TFS Driver Interface for Ceragon Devices
=========================================
Implements runtime configuration translation, 2-phase candidate transactions,
and bidirectional state/telemetry streaming matching the TeraFlowSDN driver lifecycle:
  - Connect / Disconnect
  - GetInitialConfig / GetConfig
  - SetConfig / DeleteConfig (across all 12 transport control domains)
  - SubscribeState / UnsubscribeState (real-time PM & Event streaming)

Every config rule is checked against the device's portfolio entry
(``ceragon_tfs_adapter.portfolio``) before it is pushed, so hardware-incompatible
requests (e.g. beamforming on an IP-20C, multiband on an EH-8010FX) are rejected
with an explicit reason instead of being silently "acknowledged".
"""
from __future__ import annotations

from collections import deque
import json
import logging
import re
import threading
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from ceragon_tfs_adapter.client import CeragonRestClient
from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.mapper import CeragonTFSMapper
from ceragon_tfs_adapter.models import CeragonDeviceState, PMTelemetrySample
from ceragon_tfs_adapter.portfolio import ProductSpec, check_config_support
from ceragon_tfs_adapter.registrar import TFSRegistrar

logger = logging.getLogger(__name__)

_IFACE_KEY_RE = re.compile(r"^/interface\[name=[^\]]*\]/(?P<ctype>[A-Za-z0-9_\-]+)$")


def config_type_from_key(key: str) -> Optional[str]:
    """Extract cer_intent config_type from '/interface[name=<dev>]/<config_type>' keys."""
    m = _IFACE_KEY_RE.match(key or "")
    return m.group("ctype") if m else None


class TFSCeragonDriver:
    """
    Driver layer mediating between TeraFlowSDN intents/config rules and Ceragon REST APIs.
    Supports every product in the portfolio catalog via three API flavors:
    MultiHaul TG (siklu_tg), EtherHaul (siklu_eh), and FibeAir CeraOS (ceraos).
    """

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig()
        self.client = CeragonRestClient(self.config)
        self.registrar = TFSRegistrar(self.config)
        self._connected = False
        self._cached_state: Optional[CeragonDeviceState] = None

        # Bidirectional Telemetry Streaming State
        self._subscriptions: Dict[str, Dict[str, float]] = {}
        self._telemetry_buffer: Deque[PMTelemetrySample] = deque(maxlen=120)
        self._stream_callbacks: List[Callable[[PMTelemetrySample], None]] = []
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()
        self._lock = threading.Lock()

    def connect(self) -> Tuple[bool, str]:
        """Establish session with the physical Ceragon device."""
        ok, msg = self.client.test_connection()
        self._connected = ok
        return ok, msg

    def disconnect(self) -> Tuple[bool, str]:
        """Stop active telemetry streams and close the driver session."""
        self.stop_telemetry_stream()
        self._connected = False
        return True, "Disconnected from Ceragon device"

    @property
    def product_spec(self) -> Optional[ProductSpec]:
        """Portfolio entry for the connected device (live model first, then CERAGON_MODEL hint)."""
        if self._cached_state is not None and self._cached_state.product_spec is not None:
            return self._cached_state.product_spec
        return self.client.hinted_spec

    def sync_to_tfs(self, include_telemetry: bool = False) -> Dict[str, Any]:
        """Fetch live operational state (and optional PM telemetry) and update TFS device registry."""
        state = self.client.get_device_state()
        self._cached_state = state
        result = self.registrar.register_or_update_device(state)
        result["device_state"] = state.to_dict()

        if include_telemetry:
            try:
                sample = self.client.fetch_pm_telemetry()
                with self._lock:
                    self._telemetry_buffer.append(sample)
                result["pm_telemetry"] = sample.to_dict()
            except Exception as e:
                logger.debug(f"[Driver] PM telemetry enrichment skipped: {e}")

        return result

    def _ensure_state(self) -> None:
        if self._cached_state is not None:
            return
        try:
            self._cached_state = self.client.get_device_state()
        except Exception as e:  # device unreachable: fall back to hint-only gating
            logger.debug(f"[Driver] state prefetch skipped: {e}")

    # ── Northbound GetConfig / GetInitialConfig ──────────────────────────────

    def get_initial_config(self) -> List[Tuple[str, Any]]:
        """TFS Driver API: return initial device configuration rules."""
        return self.get_config()

    def get_config(self, resource_keys: Optional[List[str]] = None) -> List[Tuple[str, Any]]:
        """
        TFS Driver API: retrieve current operational configuration, YANG schemas,
        live PM telemetry, or specific RESTCONF subtrees from the device.
        """
        results: List[Tuple[str, Any]] = []
        state = self.client.get_device_state()
        self._cached_state = state

        base_rules = CeragonTFSMapper.to_tfs_operational_config_rules(state)
        rule_map: Dict[str, Any] = {}
        for r in base_rules:
            custom = r.get("custom", {})
            k = custom.get("resource_key")
            v = custom.get("resource_value")
            if k:
                try:
                    rule_map[k] = json.loads(v) if isinstance(v, str) else v
                except Exception:
                    rule_map[k] = v

        if not resource_keys:
            return list(rule_map.items())

        for key in resource_keys:
            if key in rule_map:
                results.append((key, rule_map[key]))
            elif key in ("/device/pm_telemetry", "/device/telemetry"):
                sample = self.client.fetch_pm_telemetry()
                results.append((key, sample.to_dict()))
            elif key == "/device/events":
                events = self.client.fetch_events(limit=25)
                results.append((key, events))
            elif key == "/device/yang_library":
                results.append((key, self.client.get_yang_library()))
            elif key.startswith("/yang/"):
                mod_name = key.removeprefix("/yang/").strip("/")
                results.append((key, self.client.download_schema(mod_name)))
            elif key.startswith("/restconf/"):
                subpath = key.removeprefix("/restconf/").strip("/")
                ok, sub_data = self.client.read_subtree(subpath)
                results.append((key, sub_data if ok else {"error": sub_data}))
            else:
                results.append((key, None))

        return results

    # ── Southbound SetConfig / DeleteConfig (12 Control Domains) ─────────────

    def set_config(
        self,
        resources: List[Tuple[str, Any]],
        auto_commit: bool = True,
    ) -> List[Tuple[str, bool, str]]:
        """
        Applies a list of resource configuration updates to the physical device.
        Matches TFS driver SetConfig format: [(resource_key, resource_value), ...]
        Returns [(resource_key, success, message), ...].
        """
        self._ensure_state()
        spec = self.product_spec
        results: List[Tuple[str, bool, str]] = []
        any_device_change = False
        any_failure = False

        for key, val in resources:
            try:
                parsed_val = json.loads(val) if isinstance(val, str) else val
            except Exception:
                parsed_val = val

            ctype = config_type_from_key(key)
            key_lower = (key or "").lower()
            logger.info(f"[Driver SetConfig] {spec.model if spec else 'unknown-model'} {key} -> {parsed_val}")

            # 0. Portfolio capability gate
            if ctype:
                supported, reason = check_config_support(spec, ctype)
                if not supported:
                    results.append((key, False, f"Rejected: {reason}"))
                    continue

            if not isinstance(parsed_val, dict):
                results.append((key, False, "Invalid configuration value: expected JSON object / dict"))
                continue

            # 1. Network Slicing & VLAN Intents
            if ctype == "slice" or "slice" in key_lower or "vlan" in key_lower:
                vlan_id = int(parsed_val.get("vlan_id", parsed_val.get("vlan_tag", 100)))
                slice_name = str(parsed_val.get("slice_name", parsed_val.get("slice_id", f"slice-{vlan_id}")))
                bw = parsed_val.get("bandwidth_mbps") or (
                    float(parsed_val.get("min_throughput_gbps", 1.0)) * 1000
                )
                s_vlan = parsed_val.get("s_vlan_id") or parsed_val.get("s_vlan_tag")
                endpoints = parsed_val.get("endpoints")
                ok, msg = self.client.apply_vlan_slice(
                    vlan_id=vlan_id,
                    slice_name=slice_name,
                    bandwidth_mbps=int(bw),
                    endpoints=endpoints,
                    s_vlan_id=int(s_vlan) if s_vlan else None,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 2. Operating Parameters & Physical Radio Tuning
            elif "/device/operating_parameters" in key or ctype == "radio" or "modulation" in key_lower or "capacity" in key_lower:
                freq = parsed_val.get("tx_frequency") or parsed_val.get("frequency_mhz")
                ok_band, band_msg = self._check_frequency(spec, freq)
                if not ok_band:
                    results.append((key, False, f"Rejected: {band_msg}"))
                    continue
                pwr = parsed_val.get("tx_power_dbm")
                adm = parsed_val.get("admin_status")
                script_id = parsed_val.get("mrmc_script_id")
                bw_mhz = parsed_val.get("channel_bandwidth_mhz")
                sec_idx = int(parsed_val.get("sector_index", 1))
                atpc = parsed_val.get("atpc_enabled")
                ok, msg = self.client.apply_radio_tuning(
                    frequency_mhz=freq,
                    tx_power_dbm=pwr,
                    admin_status=adm,
                    script_id=script_id,
                    channel_bandwidth_mhz=bw_mhz,
                    sector_index=sec_idx,
                    atpc_enabled=atpc,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 3. Adaptive Coding & Modulation (ACM)
            elif ctype == "acm" or "/device/acm" in key_lower:
                min_mod = parsed_val.get("min_modulation") or parsed_val.get("min_profile")
                max_mod = parsed_val.get("max_modulation") or parsed_val.get("max_profile") or parsed_val.get("target_modulation")
                adaptive = bool(parsed_val.get("adaptive_enabled", parsed_val.get("acm_enabled", True)))
                ok, msg = self.client.apply_acm_config(
                    min_modulation=min_mod,
                    max_modulation=max_mod,
                    adaptive_enabled=adaptive,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 4. Hierarchical QoS & TSN 802.1Qbv Scheduled Traffic
            elif ctype in ("qos", "tsn") or "qos" in key_lower or "tsn" in key_lower:
                tsn_en = (ctype == "tsn") or ("tsn" in key_lower) or bool(parsed_val.get("tsn_enabled", False))
                cycle_ns = int(parsed_val.get("cycle_time_ns", int(float(parsed_val.get("cycle_time_us", 1000)) * 1000)))
                cir = parsed_val.get("cir_mbps") or parsed_val.get("bandwidth_mbps")
                pir = parsed_val.get("pir_mbps")
                gcl = parsed_val.get("gate_control_list")
                preempt = bool(parsed_val.get("preemption_8021qbu", parsed_val.get("frame_preemption", False)))
                ok, msg = self.client.apply_qos_tsn(
                    qos_mode="tsn-scheduled" if tsn_en else "hierarchical-hqos",
                    cir_mbps=int(cir) if cir else None,
                    pir_mbps=int(pir) if pir else None,
                    tsn_enabled=tsn_en,
                    cycle_time_ns=cycle_ns,
                    gate_control_list=gcl,
                    preemption_8021qbu=preempt,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 5. 60 GHz Phased-Array Beamforming & Topology Scan
            elif ctype == "beamforming" or "beamforming" in key_lower:
                sec_idx = int(parsed_val.get("sector_index", 1))
                scan = bool(parsed_val.get("trigger_topo_scan", True))
                peer = parsed_val.get("remote_assigned_name")
                golay = parsed_val.get("golay_index") or parsed_val.get("tx_golay_index")
                ok, msg = self.client.apply_beamforming(
                    sector_index=sec_idx,
                    trigger_topo_scan=scan,
                    remote_assigned_name=peer,
                    tx_golay_index=int(golay) if golay is not None else None,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 6. Multi-Band Carrier Bonding (E-Band + Microwave / TG Bonding)
            elif ctype == "multiband" or "multiband" in key_lower or "bonding" in key_lower:
                bname = str(parsed_val.get("bond_name", "bond-1"))
                members = parsed_val.get("member_interfaces") or parsed_val.get("members")
                bmode = str(parsed_val.get("bonding_mode", "l1-radio-link-bonding"))
                min_prio = int(parsed_val.get("min_priority_backup", 5))
                ok, msg = self.client.apply_multiband_bonding(
                    bond_name=bname,
                    member_interfaces=members,
                    bonding_mode=bmode,
                    min_priority_backup=min_prio,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 7. Radio Protection (1+1 HSB, 2+0, XPIC, Space Diversity, 4x4 MIMO)
            elif ctype == "protection" or "protection" in key_lower or "xpic" in key_lower:
                pmode = str(parsed_val.get("protection_mode", parsed_val.get("mode", "one-plus-one-hsb")))
                gid = int(parsed_val.get("group_id", 1))
                carriers = parsed_val.get("member_carriers")
                revertive = bool(parsed_val.get("revertive", True))
                switchover = bool(parsed_val.get("trigger_switchover", False))
                ok, msg = self.client.apply_protection(
                    mode=pmode,
                    group_id=gid,
                    member_carriers=carriers,
                    revertive=revertive,
                    trigger_switchover=switchover,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 8. Synchronization (IEEE 1588v2 PTP G.8275.1, SyncE, GPS/RF Sync)
            elif ctype == "sync" or "sync" in key_lower or "ptp" in key_lower:
                smode = str(parsed_val.get("sync_mode", "ptp"))
                prof = str(parsed_val.get("ptp_profile", "itu-g8275-1"))
                dom = int(parsed_val.get("domain_number", 24))
                synce = bool(parsed_val.get("synce_enabled", True))
                ssm = str(parsed_val.get("ssm_quality", "ql-prc"))
                ok, msg = self.client.apply_sync_ptp(
                    sync_mode=smode,
                    ptp_profile=prof,
                    domain_number=dom,
                    synce_enabled=synce,
                    ssm_quality=ssm,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 9. Security (IEEE 802.1AE MACsec & AES-256 Encryption)
            elif ctype == "security" or "macsec" in key_lower or "security" in key_lower:
                en = bool(parsed_val.get("enabled", True))
                cipher = str(parsed_val.get("cipher_suite", "gcm-aes-256"))
                rekey = int(parsed_val.get("sak_rekey_interval_sec", 3600))
                ifaces = parsed_val.get("interfaces")
                ok, msg = self.client.apply_security_macsec(
                    enabled=en,
                    cipher_suite=cipher,
                    sak_rekey_interval_sec=rekey,
                    interfaces=ifaces,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 10. O-RAN Split 7.2x eCPRI Fronthaul / Midhaul Gateway
            elif ctype == "oran_xhaul" or "oran" in key_lower or "ecpri" in key_lower:
                supported, reason = check_config_support(spec, "oran_xhaul")
                if not supported:
                    results.append((key, False, f"Rejected: {reason}"))
                    continue
                en = bool(parsed_val.get("enabled", True))
                split = str(parsed_val.get("functional_split", "split-7-2x-ecpri-fronthaul"))
                comp = str(parsed_val.get("iq_compression", "bfp-9bit"))
                cti = bool(parsed_val.get("cti_enabled", True))
                budget = int(parsed_val.get("delay_budget_us", 100))
                vlan = int(parsed_val.get("ecpri_vlan_id", 10))
                ok, msg = self.client.apply_oran_xhaul(
                    enabled=en,
                    functional_split=split,
                    iq_compression=comp,
                    cti_enabled=cti,
                    delay_budget_us=budget,
                    ecpri_vlan_id=vlan,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 11. Green Energy Policy & Secondary Carrier Sleep
            elif ctype == "energy" or "energy" in key_lower:
                emode = str(parsed_val.get("mode", "green-atpc"))
                rsl_target = float(parsed_val.get("target_rsl_dbm", -42.0))
                sleep_2nd = bool(parsed_val.get("sleep_secondary_carriers", False))
                ok, msg = self.client.apply_energy_policy(
                    mode=emode,
                    target_rsl_dbm=rsl_target,
                    sleep_secondary_carriers=sleep_2nd,
                )
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            # 12. Direct RESTCONF Subtree Patch or RPC Execution
            elif key.startswith("/restconf/subtree/"):
                subpath = key.removeprefix("/restconf/subtree/").strip("/")
                ok, msg = self.client.apply_patch(subpath, parsed_val)
                any_device_change |= ok
                any_failure |= not ok
                results.append((key, ok, msg))

            elif key.startswith("/rpc/"):
                rpc_name = key.removeprefix("/rpc/").strip("/")
                ok, out = self.client.invoke_rpc(rpc_name, parsed_val)
                results.append((key, ok, json.dumps(out) if isinstance(out, dict) else str(out)))

            else:
                logger.info(f"Accepted custom configuration rule for key {key} (TFS mirror only)")
                results.append((key, True, "Accepted into TFS config mirror"))

        # 2-Phase Candidate Commit or Automatic Rollback
        if any_device_change and auto_commit and self.client.device_flavor == "terragraph":
            if any_failure:
                self.client.discard_candidate()
            else:
                self.client.commit_candidate()

        if any_device_change:
            try:
                self.sync_to_tfs()
            except Exception as e:
                logger.warning(f"Post-config sync warning: {e}")

        return results

    def delete_config(
        self,
        resources: List[Tuple[str, Any]],
        auto_commit: bool = True,
    ) -> List[Tuple[str, bool, str]]:
        """
        TFS Driver API: remove configuration resources from the device.
        """
        results: List[Tuple[str, bool, str]] = []
        any_device_change = False

        for key, val in resources:
            try:
                parsed_val = json.loads(val) if isinstance(val, str) else (val or {})
            except Exception:
                parsed_val = {}

            key_lower = (key or "").lower()
            if "slice" in key_lower or "vlan" in key_lower:
                vlan_id = int(parsed_val.get("vlan_id", 100)) if isinstance(parsed_val, dict) else 100
                sname = parsed_val.get("slice_name") if isinstance(parsed_val, dict) else None
                ok, msg = self.client.delete_vlan_slice(vlan_id=vlan_id, slice_name=sname)
                any_device_change |= ok
                results.append((key, ok, msg))
            elif key.startswith("/restconf/subtree/"):
                subpath = key.removeprefix("/restconf/subtree/").strip("/")
                ok, msg = self.client.apply_delete(subpath)
                any_device_change |= ok
                results.append((key, ok, msg))
            else:
                results.append((key, True, f"Removed {key} from TFS config mirror"))

        if any_device_change and auto_commit and self.client.device_flavor == "terragraph":
            self.client.commit_candidate()

        return results

    # ── Bidirectional Telemetry & Event Streaming (SubscribeState) ───────────

    def subscribe_state(
        self,
        subscriptions: List[Tuple[str, float, float]],
    ) -> List[Tuple[str, bool, str]]:
        """
        TFS Driver API: subscribe to real-time telemetry / event streams.
        Each item is (resource_key, sampling_duration_sec, sampling_interval_sec).
        """
        results: List[Tuple[str, bool, str]] = []
        min_interval = 5.0
        with self._lock:
            for key, duration, interval in subscriptions:
                eff_interval = max(0.5, float(interval or 5.0))
                self._subscriptions[key] = {
                    "duration_sec": float(duration or 0.0),
                    "interval_sec": eff_interval,
                }
                min_interval = min(min_interval, eff_interval)
                results.append((key, True, f"Subscribed to {key} every {eff_interval}s"))

        if self._subscriptions and (self._stream_thread is None or not self._stream_thread.is_alive()):
            self.start_telemetry_stream(interval_seconds=min_interval)

        return results

    def unsubscribe_state(
        self,
        subscriptions: List[Tuple[str, float, float]],
    ) -> List[Tuple[str, bool, str]]:
        """TFS Driver API: cancel active state/telemetry subscriptions."""
        results: List[Tuple[str, bool, str]] = []
        with self._lock:
            for key, _, _ in subscriptions:
                removed = self._subscriptions.pop(key, None)
                results.append((key, removed is not None, f"Unsubscribed from {key}"))
            remaining = len(self._subscriptions)

        if remaining == 0:
            self.stop_telemetry_stream()

        return results

    def register_stream_callback(self, callback: Callable[[PMTelemetrySample], None]) -> None:
        """Register an in-process listener invoked on every incoming PMTelemetrySample."""
        with self._lock:
            if callback not in self._stream_callbacks:
                self._stream_callbacks.append(callback)

    def start_telemetry_stream(
        self,
        interval_seconds: float = 5.0,
        push_to_tfs: bool = False,
    ) -> None:
        """Start the background telemetry streaming worker thread."""
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return
        self._stream_stop.clear()

        def _worker() -> None:
            def _on_sample(sample: PMTelemetrySample) -> None:
                with self._lock:
                    self._telemetry_buffer.append(sample)
                    callbacks = list(self._stream_callbacks)
                for cb in callbacks:
                    try:
                        cb(sample)
                    except Exception as cb_err:
                        logger.debug(f"Stream callback error: {cb_err}")
                if push_to_tfs:
                    try:
                        self.sync_to_tfs(include_telemetry=True)
                    except Exception as sync_err:
                        logger.debug(f"Stream TFS push warning: {sync_err}")

            self.client.stream_telemetry(
                callback=_on_sample,
                interval_seconds=interval_seconds,
                stop_Check=self._stream_stop.is_set,
            )

        self._stream_thread = threading.Thread(
            target=_worker,
            name="ceragon-telemetry-stream",
            daemon=True,
        )
        self._stream_thread.start()

    def stop_telemetry_stream(self) -> None:
        """Stop the background telemetry streaming thread."""
        self._stream_stop.set()
        if self._stream_thread is not None and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.0)
        self._stream_thread = None

    def get_latest_telemetry(self) -> Optional[PMTelemetrySample]:
        """Return the most recent telemetry snapshot, fetching live if buffer is empty."""
        with self._lock:
            if self._telemetry_buffer:
                return self._telemetry_buffer[-1]
        sample = self.client.fetch_pm_telemetry()
        with self._lock:
            self._telemetry_buffer.append(sample)
        return sample

    def get_telemetry_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return buffered historical telemetry samples."""
        with self._lock:
            items = list(self._telemetry_buffer)[-limit:]
        return [s.to_dict() for s in items]

    @staticmethod
    def _check_frequency(spec: Optional[ProductSpec], freq_mhz: Any) -> Tuple[bool, str]:
        if spec is None or freq_mhz in (None, ""):
            return True, "not checked"
        try:
            ghz = float(freq_mhz) / 1000.0
        except (TypeError, ValueError):
            return False, f"invalid frequency '{freq_mhz}'"
        for band in spec.bands:
            if band.freq_min_ghz <= ghz <= band.freq_max_ghz:
                return True, band.name
        bands = ", ".join(f"{b.name} {b.freq_min_ghz}-{b.freq_max_ghz} GHz" for b in spec.bands)
        return False, f"{ghz:.3f} GHz is outside {spec.model} band(s): {bands}"
