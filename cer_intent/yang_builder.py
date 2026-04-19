"""
YANG XML Builder
================
Assembles NETCONF <edit-config> XML payloads from DeviceConfig objects,
using a realistic (but simplified) Ceragon YANG namespace structure.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any

from cer_intent.intent_schema import DeviceConfig


# Ceragon YANG namespaces (based on CeraOS NETCONF model structure)
NS = {
    "base":  "urn:ietf:params:xml:ns:netconf:base:1.0",
    "radio": "urn:ceragon:params:xml:ns:yang:ceragon-radio-link:1.0",
    "qos":   "urn:ceragon:params:xml:ns:yang:ceragon-qos:1.0",
    "prot":  "urn:ceragon:params:xml:ns:yang:ceragon-protection:1.0",
    "slice": "urn:ceragon:params:xml:ns:yang:ceragon-slice:1.0",
    "iface": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
}


def _tag(ns_key: str, name: str) -> str:
    return f"{{{NS[ns_key]}}}{name}"


def _sub(parent: ET.Element, ns_key: str, tag: str, text: str = None) -> ET.Element:
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
    """Builds NETCONF edit-config XML for Ceragon device configurations."""

    def build(self, config: DeviceConfig) -> str:
        """Return a NETCONF <rpc> edit-config XML string."""
        builders = {
            "radio":      self._build_radio,
            "qos":        self._build_qos,
            "protection": self._build_protection,
            "slice":      self._build_slice,
        }
        builder = builders.get(config.config_type, self._build_generic)

        # Root RPC envelope
        rpc = ET.Element(_tag("base", "rpc"), **{
            "message-id": f"cer-intent-{config.intent_id[:8]}",
            f"xmlns": NS["base"],
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
        rl.set(f"xmlns", NS["radio"])

        link_id = ET.SubElement(rl, _tag("radio", "link-id"))
        link_id.text = config.device_id

        carrier = ET.SubElement(rl, _tag("radio", "carrier"))

        if "channel_bandwidth_mhz" in params and params["channel_bandwidth_mhz"]:
            _sub(carrier, "radio", "channel-bandwidth",
                 f"{params['channel_bandwidth_mhz']}MHz")

        if "mrmc_script_id" in params and params["mrmc_script_id"]:
            _sub(carrier, "radio", "mrmc-script-id", params["mrmc_script_id"])

        acm = ET.SubElement(carrier, _tag("radio", "acm"))
        _sub(acm, "radio", "enabled", "true" if params.get("acm_enabled", True) else "false")
        if "min_modulation" in params:
            _sub(acm, "radio", "min-modulation", params["min_modulation"])
        if "max_modulation" in params:
            _sub(acm, "radio", "max-modulation", params["max_modulation"])

        if "tx_power_dbm" in params and params["tx_power_dbm"] is not None:
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
            _sub(policy, "qos", "guaranteed-bandwidth-mbps",
                 params["bandwidth_guaranteed_mbps"])

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

        bw = ET.SubElement(slc, _tag("slice", "bandwidth"))
        if params.get("bandwidth_pct"):
            _sub(bw, "slice", "percentage", params["bandwidth_pct"])
        if params.get("bandwidth_mbps"):
            _sub(bw, "slice", "absolute-mbps", params["bandwidth_mbps"])

        if params.get("vlan_id"):
            _sub(slc, "slice", "vlan-id", params["vlan_id"])

    # ─────────────────────────────────────────────────────────────────────────
    # Generic fallback
    # ─────────────────────────────────────────────────────────────────────────

    def _build_generic(self, container: ET.Element, config: DeviceConfig):
        generic = ET.SubElement(container, f"{{urn:ceragon:generic}}{config.config_type}")
        generic.set("device-id", config.device_id)
        for k, v in config.parameters.items():
            el = ET.SubElement(generic, k.replace("_", "-"))
            el.text = str(v)
