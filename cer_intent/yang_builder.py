"""
YANG XML Builder
================
Assembles NETCONF <edit-config> XML payloads from DeviceConfig objects,
using Ceragon, IEEE, IETF, ITU-T, and O-RAN YANG namespace structures.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, Any

from cer_intent.intent_schema import DeviceConfig


# Ceragon, IEEE, IETF, ITU-T & O-RAN YANG namespaces
NS = {
    "base":      "urn:ietf:params:xml:ns:netconf:base:1.0",
    "radio":     "urn:ceragon:params:xml:ns:yang:ceragon-radio-link:1.0",
    "qos":       "urn:ceragon:params:xml:ns:yang:ceragon-qos:1.0",
    "prot":      "urn:ceragon:params:xml:ns:yang:ceragon-protection:1.0",
    "slice":     "urn:ceragon:params:xml:ns:yang:ceragon-slice:1.0",
    "energy":    "urn:tid:params:xml:ns:yang:instantaneous-device-energy-tid:1.0",
    "sync":      "urn:itu:t:rec:g8275:yang:ceragon-sync-ptp:1.0",
    "sec":       "urn:ieee:std:802.1AE:yang:ieee802-dot1ae-macsec",
    "tsn":       "urn:ieee:std:802.1Q:yang:ieee802-dot1q-sched",
    "beam":      "http://siklu.com/ns/yang/tg/radio-dn",
    "multiband": "urn:ceragon:params:xml:ns:yang:ceragon-multiband-booster:1.0",
    "oran":      "urn:o-ran:ecpri-xhaul:1.0",
    "xpic":      "urn:ceragon:params:xml:ns:yang:ceragon-xpic-interference:1.0",
    "telem":     "urn:ietf:params:xml:ns:yang:ietf-yang-push",
    "iface":     "urn:ietf:params:xml:ns:yang:ietf-interfaces",
}


def _tag(ns_key: str, name: str) -> str:
    return f"{{{NS[ns_key]}}}{name}"


def _sub(parent: ET.Element, ns_key: str, tag: str, text: Any = None) -> ET.Element:
    el = ET.SubElement(parent, _tag(ns_key, tag))
    if text is not None:
        el.text = str(text)
    return el


def _indent(elem: ET.Element, level: int = 0):
    """Add pretty-print indentation to XML tree."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


class YANGBuilder:
    """Builds NETCONF edit-config XML for Ceragon & 6G xHaul device configurations."""

    def build(self, config: DeviceConfig) -> str:
        """Return a NETCONF <rpc> edit-config XML string."""
        builders = {
            "radio":        self._build_radio,
            "qos":          self._build_qos,
            "protection":   self._build_protection,
            "slice":        self._build_slice,
            "energy":       self._build_energy,
            "sync":         self._build_sync,
            "security":     self._build_security,
            "tsn":          self._build_tsn,
            "beamforming":  self._build_beamforming,
            "multiband":    self._build_multiband,
            "oran_xhaul":   self._build_oran_xhaul,
            "interference": self._build_interference,
            "telemetry":    self._build_telemetry,
        }
        builder = builders.get(config.config_type, self._build_generic)

        rpc = ET.Element(_tag("base", "rpc"), **{
            "message-id": f"cer-intent-{config.intent_id[:8]}",
            "xmlns": NS["base"],
        })
        edit_config = ET.SubElement(rpc, _tag("base", "edit-config"))
        target_el = ET.SubElement(edit_config, _tag("base", "target"))
        ET.SubElement(target_el, _tag("base", "running"))

        config_container = ET.SubElement(edit_config, _tag("base", "config"))
        builder(config_container, config)

        _indent(rpc)
        return ET.tostring(rpc, encoding="unicode", xml_declaration=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Radio Link (capacity / modulation)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_radio(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        rl = ET.SubElement(container, _tag("radio", "radio-link-cfg"))
        rl.set("xmlns", NS["radio"])

        _sub(rl, "radio", "link-id", config.device_id)
        carrier = ET.SubElement(rl, "carrier")

        if params.get("channel_bandwidth_mhz"):
            _sub(carrier, "radio", "channel-bandwidth", f"{params['channel_bandwidth_mhz']}MHz")
        if params.get("mrmc_script_id"):
            _sub(carrier, "radio", "mrmc-script-id", params["mrmc_script_id"])

        acm = ET.SubElement(carrier, _tag("radio", "acm"))
        _sub(acm, "radio", "enabled", "true" if params.get("acm_enabled", True) else "false")
        if "min_modulation" in params:
            _sub(acm, "radio", "min-modulation", params["min_modulation"])
        if "max_modulation" in params:
            _sub(acm, "radio", "max-modulation", params["max_modulation"])
        if params.get("tx_power_dbm") is not None:
            _sub(carrier, "radio", "tx-power", params["tx_power_dbm"])

    # ─────────────────────────────────────────────────────────────────────────
    # QoS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_qos(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        qos_root = ET.SubElement(container, _tag("qos", "qos-config"))
        qos_root.set("xmlns", NS["qos"])
        qos_root.set("target-device", config.device_id)

        policy = ET.SubElement(qos_root, _tag("qos", "policy"))
        _sub(policy, "qos", "name", f"cer-intent-{config.intent_id[:8]}")
        _sub(policy, "qos", "traffic-class", params.get("traffic_class", "AF2"))

        if params.get("max_latency_ms"):
            _sub(policy, "qos", "max-latency-ms", params["max_latency_ms"])
        if params.get("max_jitter_ms"):
            _sub(policy, "qos", "max-jitter-ms", params["max_jitter_ms"])
        if params.get("max_packet_loss_pct"):
            _sub(policy, "qos", "max-packet-loss-pct", params["max_packet_loss_pct"])
        if params.get("dscp_marking") is not None:
            _sub(policy, "qos", "dscp-marking", params["dscp_marking"])
        if params.get("bandwidth_guaranteed_mbps"):
            _sub(policy, "qos", "guaranteed-bandwidth-mbps", params["bandwidth_guaranteed_mbps"])
        if params.get("preferred_path"):
            _sub(policy, "qos", "preferred-path", ",".join(str(x) for x in params["preferred_path"]))

    # ─────────────────────────────────────────────────────────────────────────
    # Protection
    # ─────────────────────────────────────────────────────────────────────────

    def _build_protection(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        prot_root = ET.SubElement(container, _tag("prot", "protection-config"))
        prot_root.set("xmlns", NS["prot"])
        prot_root.set("target-device", config.device_id)

        group = ET.SubElement(prot_root, _tag("prot", "protection-group"))
        _sub(group, "prot", "id", f"pg-{config.device_id}")
        _sub(group, "prot", "mode", params.get("protection_mode", "1+1-hsb"))
        _sub(group, "prot", "revert-mode", params.get("revert_mode", "revertive"))
        _sub(group, "prot", "wait-to-restore-seconds", params.get("wtr_seconds", 300))
        _sub(group, "prot", "hold-off-ms", params.get("holdoff_ms", 0))

    # ─────────────────────────────────────────────────────────────────────────
    # Slice
    # ─────────────────────────────────────────────────────────────────────────

    def _build_slice(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        slice_root = ET.SubElement(container, _tag("slice", "slice-config"))
        slice_root.set("xmlns", NS["slice"])
        slice_root.set("target-device", config.device_id)

        slc = ET.SubElement(slice_root, _tag("slice", "slice"))
        _sub(slc, "slice", "name", params.get("slice_name", "default"))
        _sub(slc, "slice", "type", params.get("slice_type", "eMBB"))
        _sub(slc, "slice", "priority", params.get("priority_level", 5))
        if params.get("sst"):
            _sub(slc, "slice", "sst", params["sst"])
        if params.get("dscp_midhaul") is not None:
            _sub(slc, "slice", "dscp-midhaul-f1u", params["dscp_midhaul"])

        bw = ET.SubElement(slc, _tag("slice", "bandwidth"))
        if params.get("bandwidth_pct"):
            _sub(bw, "slice", "percentage", params["bandwidth_pct"])
        if params.get("bandwidth_mbps"):
            _sub(bw, "slice", "absolute-mbps", params["bandwidth_mbps"])
        if params.get("vlan_id"):
            _sub(slc, "slice", "vlan-id", params["vlan_id"])

    # ─────────────────────────────────────────────────────────────────────────
    # Energy (UNITY-6G D3.1 instantaneous-device-energy-tid)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_energy(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("energy", "device-energy-policy"))
        root.set("xmlns", NS["energy"])
        _sub(root, "energy", "device-id", config.device_id)
        _sub(root, "energy", "energy-mode", params.get("energy_mode", "saving"))
        if params.get("target_power_w") is not None:
            _sub(root, "energy", "target-power-watts", params["target_power_w"])
        _sub(root, "energy", "off-peak-window", params.get("off_peak_window", "02:00-05:00"))
        for sec in params.get("sleep_sectors", []):
            _sub(root, "energy", "sleep-sector", sec)

    # ─────────────────────────────────────────────────────────────────────────
    # Sync (ITU-T G.8275.1 / SyncE)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_sync(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("sync", "ptp-synce-config"))
        root.set("xmlns", NS["sync"])
        _sub(root, "sync", "device-id", config.device_id)
        _sub(root, "sync", "ptp-profile", params.get("ptp_profile", "G.8275.1"))
        _sub(root, "sync", "ptp-domain", params.get("ptp_domain", 24))
        _sub(root, "sync", "clock-mode", params.get("clock_mode", "T-BC"))
        _sub(root, "sync", "synce-enabled", str(params.get("synce_enabled", True)).lower())
        _sub(root, "sync", "esmc-ssm-quality-level", params.get("esmc_ssm_ql", "QL-PRC"))
        _sub(root, "sync", "max-phase-error-ns", params.get("max_phase_error_ns", 1500))

    # ─────────────────────────────────────────────────────────────────────────
    # Security (IEEE 802.1AE MACsec + PQC)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_security(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("sec", "macsec-secy-config"))
        root.set("xmlns", NS["sec"])
        _sub(root, "sec", "interface", config.device_id)
        _sub(root, "sec", "controlled-port-enabled", str(params.get("macsec_enabled", True)).lower())
        _sub(root, "sec", "cipher-suite", params.get("cipher_suite", "AES-GCM-256"))
        _sub(root, "sec", "mka-sak-rekey-seconds", params.get("mka_sak_rekey_seconds", 3600))
        _sub(root, "sec", "quantum-safe-kex", params.get("quantum_safe_kex", "ML-KEM-768-Hybrid"))
        _sub(root, "sec", "replay-protection-window", params.get("replay_protection_window", 64))

    # ─────────────────────────────────────────────────────────────────────────
    # TSN (IEEE 802.1Qbv TAS / 802.1Qbu Preemption / PfifoFast)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tsn(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("tsn", "gate-parameter-table"))
        root.set("xmlns", NS["tsn"])
        _sub(root, "tsn", "interface", config.device_id)
        _sub(root, "tsn", "gate-enabled", str(params.get("tas_8021qbv_enabled", True)).lower())
        _sub(root, "tsn", "frame-preemption-8021qbu", str(params.get("frame_preemption_8021qbu", True)).lower())
        _sub(root, "tsn", "pfifofast-band0-strict-urllc", "true")
        _sub(root, "tsn", "admin-cycle-time-us", params.get("cycle_time_us", 1000))
        _sub(root, "tsn", "max-e2e-latency-ms", params.get("max_e2e_latency_ms", 0.5))

        gcl = ET.SubElement(root, _tag("tsn", "admin-control-list"))
        for entry in params.get("gate_control_list", []):
            item = ET.SubElement(gcl, _tag("tsn", "gate-control-entry"))
            _sub(item, "tsn", "slot-name", entry.get("slot"))
            _sub(item, "tsn", "gate-states-value", entry.get("gate_mask"))
            _sub(item, "tsn", "time-interval-us", entry.get("duration_us"))

    # ─────────────────────────────────────────────────────────────────────────
    # Beamforming (Siklu TG 60 GHz V-Band massive2 array)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_beamforming(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("beam", "radio-common"))
        root.set("xmlns", NS["beam"])
        _sub(root, "beam", "node-id", config.device_id)
        _sub(root, "beam", "antenna-array-profile", params.get("antenna_array_profile", "massive2"))
        _sub(root, "beam", "frequency-mhz", params.get("frequency_mhz", 60480))
        _sub(root, "beam", "vband-channel", params.get("vband_channel", 2))
        _sub(root, "beam", "steer-azimuth-deg", params.get("steer_azimuth_deg", 0.0))
        _sub(root, "beam", "steer-elevation-deg", params.get("steer_elevation_deg", 0.0))
        _sub(root, "beam", "beam-tracking-mode", params.get("beam_tracking_mode", "adaptive-closed-loop"))
        if params.get("ignite_candidate_bridge"):
            _sub(root, "beam", "ignite-candidate-bridge", params["ignite_candidate_bridge"])

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Band Carrier Aggregation (80 GHz E-Band + Microwave)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_multiband(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("multiband", "multiband-bonding-group"))
        root.set("xmlns", NS["multiband"])
        _sub(root, "multiband", "group-id", params.get("bonding_group_id", f"mb-{config.device_id}"))
        _sub(root, "multiband", "bonding-mode", params.get("bonding_mode", "L1-hitless-aggregation"))
        _sub(root, "multiband", "aggregated-throughput-gbps", params.get("aggregated_throughput_gbps", 12.5))
        _sub(root, "multiband", "urllc-pinning", params.get("urllc_pinning", "microwave-anchor"))

        eb = params.get("eband_carrier", {})
        eb_el = ET.SubElement(root, _tag("multiband", "eband-carrier"))
        _sub(eb_el, "multiband", "frequency-ghz", eb.get("frequency_ghz", 80.0))
        _sub(eb_el, "multiband", "channel-bw-mhz", eb.get("bw_mhz", 2000))

        mw = params.get("microwave_carrier", {})
        mw_el = ET.SubElement(root, _tag("multiband", "microwave-carrier"))
        _sub(mw_el, "multiband", "frequency-ghz", mw.get("frequency_ghz", 18.0))
        _sub(mw_el, "multiband", "channel-bw-mhz", mw.get("bw_mhz", 112))

    # ─────────────────────────────────────────────────────────────────────────
    # O-RAN xHaul (Split 7.2x eCPRI + F1-U + CTI)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_oran_xhaul(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("oran", "oran-xhaul-profile"))
        root.set("xmlns", NS["oran"])
        _sub(root, "oran", "device-id", config.device_id)
        _sub(root, "oran", "functional-split", params.get("functional_split", "7.2x"))
        _sub(root, "oran", "ecpri-iq-compression", params.get("ecpri_iq_compression", "BFP9"))
        _sub(root, "oran", "compression-ratio", params.get("compression_ratio", "2.9:1"))
        _sub(root, "oran", "f1u-midhaul-dscp", params.get("f1u_midhaul_dscp_socket", 46))
        _sub(root, "oran", "cti-enabled", str(params.get("oran_cti_enabled", True)).lower())
        dmp = params.get("delay_management_profile", {})
        if dmp:
            d_el = ET.SubElement(root, _tag("oran", "delay-window-us"))
            _sub(d_el, "oran", "t12-max-oneway-us", dmp.get("T12_max_oneway_us", 100))
            _sub(d_el, "oran", "t2a-max-dl-uplane-us", dmp.get("T2a_max_dl_uplane_us", 220))

    # ─────────────────────────────────────────────────────────────────────────
    # Interference & XPIC
    # ─────────────────────────────────────────────────────────────────────────

    def _build_interference(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("xpic", "interference-mitigation-cfg"))
        root.set("xmlns", NS["xpic"])
        _sub(root, "xpic", "device-id", config.device_id)
        _sub(root, "xpic", "xpic-enabled", str(params.get("xpic_enabled", True)).lower())
        _sub(root, "xpic", "cross-pol-isolation-db", params.get("xpic_cross_pol_isolation_db", 30.0))
        _sub(root, "xpic", "atpc-coordinated", str(params.get("atpc_coordinated", True)).lower())
        _sub(root, "xpic", "dynamic-channel-switch-dfc", str(params.get("dynamic_channel_switch_dfc", True)).lower())
        _sub(root, "xpic", "target-sinr-db", params.get("target_sinr_db", 28.0))

    # ─────────────────────────────────────────────────────────────────────────
    # Telemetry & Digital Twin Pre-Flight
    # ─────────────────────────────────────────────────────────────────────────

    def _build_telemetry(self, container: ET.Element, config: DeviceConfig):
        params = config.parameters
        root = ET.SubElement(container, _tag("telem", "establish-subscription"))
        root.set("xmlns", NS["telem"])
        _sub(root, "telem", "target-device", config.device_id)
        yp = params.get("yang_push_rfc8641", {})
        _sub(root, "telem", "period-ms", yp.get("periodic_cadence_ms", 1000))
        _sub(root, "telem", "dampening-period-ms", yp.get("on_change_dampening_ms", 200))
        tw = params.get("twamp_rfc5357_probe", {})
        _sub(root, "telem", "twamp-light-enabled", str(tw.get("enabled", True)).lower())
        dt = params.get("digital_twin_ns3_preflight", {})
        _sub(root, "telem", "ns3-digital-twin-preflight", str(dt.get("enabled", True)).lower())
        _sub(root, "telem", "what-if-scenario", dt.get("what_if_scenario", "traffic_surge"))

    # ─────────────────────────────────────────────────────────────────────────
    # Generic fallback
    # ─────────────────────────────────────────────────────────────────────────

    def _build_generic(self, container: ET.Element, config: DeviceConfig):
        generic = ET.SubElement(container, f"{{urn:ceragon:generic}}{config.config_type}")
        generic.set("device-id", config.device_id)
        for k, v in config.parameters.items():
            el = ET.SubElement(generic, k.replace("_", "-"))
            el.text = str(v)
