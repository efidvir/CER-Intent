"""
Intent Parser
=============
Converts raw input (natural language or structured JSON) into a validated Intent object.

Supports all 14 canonical IntentTypes:
  capacity, qos, modulation, resilience, slice, energy, sync, security,
  tsn, beamforming, multiband, oran_xhaul, interference, telemetry

Two parsing paths:
  1. LLM Path  — uses Google Gemini to parse free-text into the canonical intent schema
  2. Rule Path — keyword & regex-based parser (works deterministically without any API key)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from cer_intent.intent_schema import (
    Intent, IntentTarget, IntentType,
    TargetType, QoSClass, ProtectionMode, SliceType
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Gemini LLM Parser
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert network engineer specialising in 6G transport networks, O-RAN xHaul, TSN, and Ceragon microwave/millimeter-wave equipment.
Your task is to parse a natural-language or semi-structured network management intent and return a single JSON object.

The JSON must conform to this schema:
{
  "intent_type": one of [
    "capacity", "qos", "modulation", "resilience", "slice", "energy",
    "sync", "security", "tsn", "beamforming", "multiband", "oran_xhaul",
    "interference", "telemetry"
  ],
  "target": {
    "target_type": one of ["link", "node", "sector", "all"],
    "identifier": "the link ID, node ID, sector name, or 'all'",
    "direction": null or "tx" or "rx" or "both"
  },
  "parameters": {
    // For capacity: min_throughput_gbps (float), max_throughput_gbps (float|null), channel_bandwidth_mhz (int|null), slice_type (null|"eMBB"|"URLLC"|"mMTC")
    // For qos: max_latency_ms (float|null), max_jitter_ms (float|null), max_packet_loss_pct (float|null), traffic_class ("EF"|"AF4"|"AF3"|"AF2"|"AF1"|"BE"), dscp_marking (int|null), bandwidth_guaranteed_mbps (float|null)
    // For modulation: min_modulation (str), max_modulation (str), acm_enabled (bool), tx_power_dbm (float|null), rain_rate_mm_hr (float|null)
    // For resilience: protection_mode ("1+1-hsb"|"1+1-cold"|"space-diversity"|"frequency-diversity"|"marl-autonomic-mesh"|"ti-lfa-fast-reroute"|"none"), revert_mode ("revertive"|"non-revertive"), wtr_seconds (int), holdoff_ms (int)
    // For slice: slice_name (str), slice_type ("eMBB"|"URLLC"|"mMTC"|"custom"), bandwidth_pct (float|null), bandwidth_mbps (float|null), priority_level (int 1-8), vlan_id (int|null)
    // For energy: sleep_mode_enabled (bool), tx_power_reduction_db (float|null), schedule (str|null), energy_mode ("saving"|"eco-sleep")
    // For sync: ptp_profile ("G.8275.1"|"G.8275.2"), synce_enabled (bool), clock_mode ("T-BC"|"T-TC"|"T-GM"), max_phase_error_ns (int), ssm_quality_level ("QL-PRC")
    // For security: macsec_enabled (bool), encryption_algorithm ("AES-GCM-256"|"AES-GCM-128"), key_rotation_seconds (int), quantum_safe_kex (bool)
    // For tsn: tas_8021qbv_enabled (bool), frame_preemption_8021qbu (bool), cycle_time_us (int), urllc_slot_us (int), guard_band_us (int), max_e2e_latency_ms (float), frer_8021cb_enabled (bool)
    // For beamforming: antenna_array_profile ("massive2"), frequency_ghz (float), steer_azimuth_deg (float), steer_elevation_deg (float), beam_tracking_mode (str), ignite_candidate_bridge (str|null)
    // For multiband: eband_carrier_ghz (float), microwave_carrier_ghz (float), aggregated_throughput_gbps (float), bonding_mode ("L1-hitless-aggregation"), urllc_pinning ("microwave-anchor")
    // For oran_xhaul: functional_split ("7.2x"|"F1-U"), iq_compression_format ("BFP9"|"BFP12"), max_fronthaul_oneway_us (int), cti_enabled (bool), f1u_dscp_mapping (int)
    // For interference: xpic_enabled (bool), atpc_coordinated (bool), dynamic_channel_switch (bool), target_sinr_db (float)
    // For telemetry: yang_push_cadence_ms (int), twamp_probe_enabled (bool), digital_twin_preflight (bool), what_if_scenario ("traffic_surge"|"channel_degradation"|"link_failure")
  },
  "priority": integer 1-10 (default 5),
  "ttl_seconds": null or integer,
  "tags": []
}

Rules:
- Extract identifiers from the text (e.g. "link A-B" -> identifier="link-A-B", "sector-north" -> identifier="sector-north", "ctu-96" or "ceragon-mh-t261-ctu-96" -> target_type="node", identifier="ceragon-mh-t261-ctu-96")
- Respond ONLY with the JSON object. No explanation, no markdown fences.
- CRITICAL: If the user provides text that is nonsensical, adversarial, or completely unrelated to telecom network management, return: {"error": "Unrecognized or nonsensical intent"}.
"""

FEW_SHOTS = [
    {
        "role": "user",
        "parts": ["Increase the capacity of the backhaul link between site-A and site-B to at least 5 Gbps for the eMBB slice"]
    },
    {
        "role": "model",
        "parts": [json.dumps({
            "intent_type": "capacity",
            "target": {"target_type": "link", "identifier": "link-A-B", "direction": "both"},
            "parameters": {"min_throughput_gbps": 5.0, "max_throughput_gbps": None, "channel_bandwidth_mhz": None, "slice_type": "eMBB"},
            "priority": 6, "ttl_seconds": None, "tags": ["eMBB", "backhaul"]
        })]
    },
    {
        "role": "user",
        "parts": ["Enable IEEE 802.1Qbv TSN time-aware shaper with 1000us cycle and 250us URLLC window on ceragon-mh-t261-ctu-96"]
    },
    {
        "role": "model",
        "parts": [json.dumps({
            "intent_type": "tsn",
            "target": {"target_type": "node", "identifier": "ceragon-mh-t261-ctu-96", "direction": "both"},
            "parameters": {"tas_8021qbv_enabled": True, "frame_preemption_8021qbu": True, "cycle_time_us": 1000, "urllc_slot_us": 250, "guard_band_us": 15, "max_e2e_latency_ms": 0.5, "frer_8021cb_enabled": False},
            "priority": 9, "ttl_seconds": None, "tags": ["tsn", "802.1qbv", "urllc"]
        })]
    },
    {
        "role": "user",
        "parts": ["Steer 60.48 GHz massive2 phased array beam to +15 deg azimuth and +2 deg elevation on ceragon-mh-t261-ctu-96"]
    },
    {
        "role": "model",
        "parts": [json.dumps({
            "intent_type": "beamforming",
            "target": {"target_type": "node", "identifier": "ceragon-mh-t261-ctu-96", "direction": "both"},
            "parameters": {"antenna_array_profile": "massive2", "frequency_ghz": 60.48, "steer_azimuth_deg": 15.0, "steer_elevation_deg": 2.0, "beam_tracking_mode": "adaptive-closed-loop", "ignite_candidate_bridge": None},
            "priority": 7, "ttl_seconds": None, "tags": ["beamforming", "60ghz", "massive2"]
        })]
    },
]


class LLMParser:
    """Parses intents using Google Gemini API."""

    def __init__(self, model_name: Optional[str] = None):
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY not configured")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model_name or os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            system_instruction=SYSTEM_PROMPT,
        )

    def parse_text(self, text: str) -> Dict[str, Any]:
        history = FEW_SHOTS.copy()
        chat = self._model.start_chat(history=history)
        response = chat.send_message(text)
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)

        if "error" in parsed:
            raise ValueError(parsed["error"])

        return parsed


# ──────────────────────────────────────────────────────────────────────────────
# Keyword & Regex-based Rule Parser (no API key required)
# ──────────────────────────────────────────────────────────────────────────────

_MODULATION_LEVELS = ["QPSK", "16QAM", "32QAM", "64QAM", "128QAM", "256QAM", "512QAM", "1024QAM", "2048QAM"]


def _extract_identifier(text: str) -> tuple[str, str]:
    """Return (target_type, identifier) from text heuristics."""
    text_l = text.lower()

    # Specific physical / TFS node names first
    if any(k in text_l for k in ["ceragon-mh-t261-ctu-96", "ctu-96", "mh-t261", "ceragon-0"]):
        return "node", "ceragon-mh-t261-ctu-96"
    if "oran-cu1" in text_l or "o-cu north" in text_l:
        return "node", "oran-cu1"

    # Sector
    sector_m = re.search(r"sector[- _]?(\w+)", text_l)
    if sector_m:
        return "sector", f"sector-{sector_m.group(1)}"

    # Explicit Link e.g. "link A-B", "link-A-B", "between A and B"
    link_m = re.search(r"link[- ]([A-Za-z0-9]+)[- ]([A-Za-z0-9]+)", text)
    if link_m:
        return "link", f"link-{link_m.group(1)}-{link_m.group(2)}"
    between_m = re.search(r"between\s+(?:site[- ]?|node[- ]?)?(\w+)\s+and\s+(?:site[- ]?|node[- ]?)?(\w+)", text, re.IGNORECASE)
    if between_m:
        return "link", f"link-{between_m.group(1)}-{between_m.group(2)}"

    # Explicit Node e.g. "node-A", "site-B", "O-DU-1"
    node_m = re.search(r"(?:node|site|gnb)[- _]?([A-Za-z0-9_-]+)", text)
    if node_m:
        val = node_m.group(1)
        if val.lower() not in ("all", "every", "across"):
            return "node", f"node-{val}" if not val.lower().startswith("node-") else val

    if "all" in text_l or "every" in text_l or "network" in text_l or "global" in text_l:
        return "all", "all"

    return "all", "all"


def _extract_float(text: str, patterns: list[str]) -> Optional[float]:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if "mbps" in p.lower() or ("mbps" in text[m.start():m.end()+5].lower()):
                val /= 1000.0
            return val
    return None


class RuleParser:
    """Deterministic keyword & regex intent parser supporting all 14 IntentTypes & 17 Skills."""

    def parse_text(self, text: str) -> Dict[str, Any]:
        text_l = text.lower()
        target_type, identifier = _extract_identifier(text)

        # 1. TSN (IEEE 802.1Qbv / 802.1Qbu / PfifoFast / Frame Preemption / Time-Aware Shaper)
        if any(k in text_l for k in [
            "tsn", "802.1qbv", "802.1qbu", "802.1cb", "time-aware shaper", "gate control",
            "frame preemption", "pfifofast", "deterministic", "bufferbloat", "frer"
        ]):
            return self._parse_tsn(text, target_type, identifier)

        # 2. Multi-Band Carrier Aggregation (80 GHz E-Band + Microwave L1 Bonding)
        if any(k in text_l for k in [
            "multiband", "multi-band", "carrier aggregation", "l1 bonding", "l1 hitless",
            "bond 80", "e-band and", "eband and", "microwave anchor", "multi-band booster"
        ]):
            return self._parse_multiband(text, target_type, identifier)

        # 3. O-RAN 7.2x Fronthaul & F1-U Midhaul
        if any(k in text_l for k in [
            "o-ran", "oran", "ecpri", "7.2x", "split 7.2", "bfp9", "bfp12",
            "iq compression", "f1-u", "f1u", "cti", "t12 delay"
        ]):
            return self._parse_oran_xhaul(text, target_type, identifier)

        # 4. Telemetry, TWAMP & NS-3 Digital Twin Pre-Flight
        if any(k in text_l for k in [
            "yang push", "rfc 8641", "twamp", "telemetry", "co-simulation",
            "digital twin", "ns-3", "what-if simulation"
        ]):
            return self._parse_telemetry(text, target_type, identifier)

        # 5. Resilience, Protection & MARL Self-Healing
        if any(k in text_l for k in [
            "hsb", "hot standby", "protection", "revert", "diversity", "redundan",
            "marl", "dpir", "disaster", "self-healing", "mesh healing", "autonomic",
            "ignite", "emergency bridge", "backup bridge", "isolated topology",
            "spanning tree", "ti-lfa"
        ]):
            return self._parse_resilience(text, target_type, identifier)

        # 6. 60 GHz Millimeter-Wave Beamforming & Phased-Array Steering
        if any(k in text_l for k in [
            "beamforming", "beam steering", "steer", "azimuth", "elevation",
            "massive2", "phased array", "phased-array", "60.48", "64.80", "58.32", "62.64",
            "v-band", "vband", "oxygen absorption", "tune radio frequency"
        ]):
            return self._parse_beamforming(text, target_type, identifier)

        # 7. Interference Mitigation & XPIC
        if any(k in text_l for k in [
            "xpic", "cross-pol", "cross-polarization", "co-channel", "interference",
            "sinr", "dynamic channel switch", "dfc", "jamming"
        ]):
            return self._parse_interference(text, target_type, identifier)

        # 8. Timing & Synchronization (PTP G.8275.1 / SyncE)
        if any(k in text_l for k in ["ptp", "synce", "1588", "g.8275", "timing", "clock", "sync", "t-bc", "phase error"]):
            return self._parse_sync(text, target_type, identifier)

        # 9. Security (MACsec 802.1AE / AES-256 / PQC)
        if any(k in text_l for k in ["macsec", "802.1ae", "encryption", "secure", "cipher", "security", "aes-", "quantum-safe", "mka"]):
            return self._parse_security(text, target_type, identifier)

        # 10. Modulation / ACM / Rain Fade / Spectral Efficiency
        if any(k in text_l for k in [
            "qam", "modulation", "acm", "mrmc", "constellation", "rain", "weather",
            "fade", "storm", "itu-r p.838", "spectral efficiency", "bits per hz"
        ]):
            return self._parse_modulation(text, target_type, identifier)

        # 11. QoS / Latency / Jitter / Traffic Engineering
        if any(k in text_l for k in [
            "latency", "jitter", "packet loss", "qos", "delay", "dscp",
            "reroute", "steer", "vpn", "congested", "overall network", "diagnose", "health"
        ]):
            return self._parse_qos(text, target_type, identifier)

        # 12. Energy / Green-6G
        if any(k in text_l for k in ["sleep", "green", "power saving", "power reduction", "energy", "off-peak", "opex"]):
            return self._parse_energy(text, target_type, identifier)

        # 13. Capacity vs Slice
        if any(k in text_l for k in ["slice", "vlan"]) and not any(k in text_l for k in ["increase capacity", "upgrade backhaul"]):
            return self._parse_slice(text, target_type, identifier)

        if any(k in text_l for k in ["gbps", "mbps", "throughput", "capacity", "bandwidth", "channel bandwidth"]):
            return self._parse_capacity(text, target_type, identifier)

        if any(k in text_l for k in ["embb", "urllc", "mmtc", "allocat"]):
            return self._parse_slice(text, target_type, identifier)

        raise ValueError(
            "Could not map request to a known network intent type "
            "(capacity, qos, modulation, resilience, slice, energy, sync, security, "
            "tsn, beamforming, multiband, oran_xhaul, interference, telemetry)"
        )

    # ── Type parsers ───────────────────────────────────────────────────────────

    def _parse_capacity(self, text: str, ttype: str, ident: str) -> Dict:
        gbps = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*gbps", r"(\d+(?:\.\d+)?)\s*mbps"]) or 1.0
        bw_m = re.search(r"(\d+)\s*mhz", text, re.IGNORECASE)
        bw = int(bw_m.group(1)) if bw_m else None
        slice_type = None
        for s in ["eMBB", "URLLC", "mMTC"]:
            if s.lower() in text.lower():
                slice_type = s
                break
        return {
            "intent_type": "capacity",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "min_throughput_gbps": gbps,
                "max_throughput_gbps": None,
                "channel_bandwidth_mhz": bw,
                "slice_type": slice_type,
            },
            "priority": 6, "ttl_seconds": None, "tags": ["capacity"],
        }

    def _parse_qos(self, text: str, ttype: str, ident: str) -> Dict:
        latency = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*ms", r"(\d+(?:\.\d+)?)\s*millisecond"])
        jitter = _extract_float(text, [r"jitter[^\d]*(\d+(?:\.\d+)?)\s*ms"])
        loss = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*%\s*(?:packet\s+)?loss", r"loss[^\d]*(\d+(?:\.\d+)?)"])
        dscp_m = re.search(r"dscp\s*(\d+)", text, re.IGNORECASE)
        dscp = int(dscp_m.group(1)) if dscp_m else None
        tc = "EF" if any(k in text.lower() for k in ["high priority", "urllc", "critical", "ef", "sub-ms"]) else "AF2"
        return {
            "intent_type": "qos",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "max_latency_ms": latency or 2.0,
                "max_jitter_ms": jitter,
                "max_packet_loss_pct": loss,
                "traffic_class": tc,
                "dscp_marking": dscp,
                "bandwidth_guaranteed_mbps": None,
            },
            "priority": 7, "ttl_seconds": None, "tags": ["qos"],
        }

    def _parse_modulation(self, text: str, ttype: str, ident: str) -> Dict:
        found = [m for m in _MODULATION_LEVELS if m.lower() in text.lower()]
        min_mod = found[0] if found else "64QAM"
        max_mod = found[-1] if len(found) > 1 else "2048QAM"
        pwr = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*dbm"])
        rain_m = re.search(r"(\d+(?:\.\d+)?)\s*mm/hr", text, re.IGNORECASE)
        params: Dict[str, Any] = {
            "min_modulation": min_mod,
            "max_modulation": max_mod,
            "acm_enabled": True,
            "tx_power_dbm": pwr,
        }
        if rain_m:
            params["rain_rate_mm_hr"] = float(rain_m.group(1))
        return {
            "intent_type": "modulation",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": params,
            "priority": 6, "ttl_seconds": None, "tags": ["acm", "mrmc"],
        }

    def _parse_resilience(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        if any(k in text_l for k in ["marl", "dpir", "island", "emergency bridge", "ignite"]):
            mode = "1+1-hsb"
        elif "frequency diversity" in text_l or "fd " in text_l:
            mode = "frequency-diversity"
        elif "space diversity" in text_l or "sd " in text_l:
            mode = "space-diversity"
        elif "cold" in text_l:
            mode = "1+1-cold"
        else:
            mode = "1+1-hsb"
        revert = "non-revertive" if "non-revert" in text_l else "revertive"
        wtr_m = re.search(r"(\d+)\s*(?:s|sec|second)", text)
        wtr = int(wtr_m.group(1)) if wtr_m else 300
        bridge_m = re.search(r"(bridge-\d+)", text_l)
        params: Dict[str, Any] = {
            "protection_mode": mode,
            "revert_mode": revert,
            "wtr_seconds": wtr,
            "holdoff_ms": 0,
        }
        if bridge_m:
            params["ignite_candidate_bridge"] = bridge_m.group(1)
        return {
            "intent_type": "resilience",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": params,
            "priority": 9, "ttl_seconds": None, "tags": ["protection", "resilience"],
        }

    def _parse_slice(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        stype = "eMBB"
        for s in ["urllc", "mmtc", "embb"]:
            if s in text_l:
                stype = s.upper() if s != "embb" else "eMBB"
                break
        if "uran" in text_l:
            stype = "URLLC"
        pct = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*%"])
        mbps_m = re.search(r"(\d+(?:\.\d+)?)\s*mbps", text, re.IGNORECASE)
        gbps_m = re.search(r"(\d+(?:\.\d+)?)\s*gbps", text, re.IGNORECASE)
        mbps = float(mbps_m.group(1)) if mbps_m else (float(gbps_m.group(1)) * 1000.0 if gbps_m else 1000.0)
        vlan_m = re.search(r"vlan[- ]?(\d+)", text_l)
        vlan = int(vlan_m.group(1)) if vlan_m else 200
        name_m = re.search(r"(slice-[A-Za-z0-9_-]+)", text_l)
        name = name_m.group(1) if name_m else f"slice-{stype.lower()}"
        return {
            "intent_type": "slice",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {
                "slice_name": name,
                "slice_type": stype,
                "bandwidth_pct": pct,
                "bandwidth_mbps": mbps,
                "priority_level": 7 if stype == "URLLC" else 5,
                "vlan_id": vlan,
            },
            "priority": 7, "ttl_seconds": None, "tags": ["slice", stype],
        }

    def _parse_energy(self, text: str, ttype: str, ident: str) -> Dict:
        tx_db = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*db"])
        win_m = re.search(r"(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})", text)
        window = win_m.group(1).replace(" ", "") if win_m else "02:00-05:00"
        return {
            "intent_type": "energy",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {
                "sleep_mode_enabled": "sleep" in text.lower(),
                "energy_mode": "eco-sleep" if "sleep" in text.lower() else "saving",
                "tx_power_reduction_db": tx_db or 6.0,
                "schedule": window,
                "window": window,
            },
            "priority": 4, "ttl_seconds": None, "tags": ["energy", "green"],
        }

    def _parse_sync(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        profile = "G.8275.2" if "8275.2" in text_l else "G.8275.1"
        ns_m = re.search(r"(\d+)\s*ns", text_l)
        max_ns = int(ns_m.group(1)) if ns_m else 1500
        return {
            "intent_type": "sync",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "ptp_profile": profile,
                "synce_enabled": True,
                "clock_mode": "T-BC",
                "max_phase_error_ns": max_ns,
                "ssm_quality_level": "QL-PRC",
            },
            "priority": 9, "ttl_seconds": None, "tags": ["timing", "sync", profile],
        }

    def _parse_security(self, text: str, ttype: str, ident: str) -> Dict:
        alg = "AES-GCM-128" if "128" in text else "AES-GCM-256"
        rot_m = re.search(r"(\d+)\s*s(?:ec)?", text.lower())
        rot_s = int(rot_m.group(1)) if rot_m else 3600
        return {
            "intent_type": "security",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "macsec_enabled": True,
                "encryption_algorithm": alg,
                "key_rotation_seconds": rot_s,
                "quantum_safe_kex": True,
            },
            "priority": 10, "ttl_seconds": None, "tags": ["security", "macsec", "pqc"],
        }

    def _parse_tsn(self, text: str, ttype: str, ident: str) -> Dict:
        cycle_m = re.search(r"(\d+)\s*(?:us|µs)\s*cycle", text, re.IGNORECASE)
        slot_m = re.search(r"(\d+)\s*(?:us|µs)\s*(?:urllc|window|slot)", text, re.IGNORECASE)
        lat_m = re.search(r"(\d+(?:\.\d+)?)\s*ms", text, re.IGNORECASE)
        cycle_us = int(cycle_m.group(1)) if cycle_m else 1000
        default_slot = min(250, max(25, int(cycle_us * 0.25)))
        slot_us = int(slot_m.group(1)) if slot_m else default_slot
        if slot_us >= cycle_us:
            slot_us = max(25, int(cycle_us * 0.25))
        max_lat = float(lat_m.group(1)) if lat_m else 0.5
        return {
            "intent_type": "tsn",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "tas_8021qbv_enabled": True,
                "frame_preemption_8021qbu": True,
                "cycle_time_us": cycle_us,
                "urllc_slot_us": slot_us,
                "guard_band_us": 15,
                "max_e2e_latency_ms": max_lat,
                "frer_8021cb_enabled": "frer" in text.lower() or "802.1cb" in text.lower(),
            },
            "priority": 9, "ttl_seconds": None, "tags": ["tsn", "802.1qbv", "urllc"],
        }

    def _parse_beamforming(self, text: str, ttype: str, ident: str) -> Dict:
        if ident == "all":
            ttype, ident = "node", "ceragon-mh-t261-ctu-96"
        freq_m = re.search(r"(58\.32|60\.48|62\.64|64\.80|60)\s*ghz", text, re.IGNORECASE)
        freq = float(freq_m.group(1)) if freq_m else 60.48
        if freq == 60.0:
            freq = 60.48
        az_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:deg|°)?\s*azimuth", text, re.IGNORECASE)
        el_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:deg|°)?\s*elevation", text, re.IGNORECASE)
        bridge_m = re.search(r"(bridge-\d+)", text, re.IGNORECASE)
        return {
            "intent_type": "beamforming",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "antenna_array_profile": "massive2",
                "frequency_ghz": freq,
                "steer_azimuth_deg": float(az_m.group(1)) if az_m else 15.0,
                "steer_elevation_deg": float(el_m.group(1)) if el_m else 2.0,
                "beam_tracking_mode": "adaptive-closed-loop",
                "ignite_candidate_bridge": bridge_m.group(1) if bridge_m else None,
            },
            "priority": 8, "ttl_seconds": None, "tags": ["beamforming", "60ghz", "massive2"],
        }

    def _parse_multiband(self, text: str, ttype: str, ident: str) -> Dict:
        gbps = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*gbps"]) or 12.5
        return {
            "intent_type": "multiband",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "eband_carrier_ghz": 80.0,
                "microwave_carrier_ghz": 18.0,
                "aggregated_throughput_gbps": gbps,
                "bonding_mode": "L1-hitless-aggregation",
                "urllc_pinning": "microwave-anchor",
            },
            "priority": 8, "ttl_seconds": None, "tags": ["multiband", "eband", "l1-bonding"],
        }

    def _parse_oran_xhaul(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        comp = "BFP12" if "bfp12" in text_l else "BFP9"
        us_m = re.search(r"(\d+)\s*(?:us|µs)", text_l)
        t12_us = int(us_m.group(1)) if us_m else 100
        dscp_m = re.search(r"dscp\s*(\d+)", text_l)
        dscp = int(dscp_m.group(1)) if dscp_m else 46
        return {
            "intent_type": "oran_xhaul",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "functional_split": "7.2x",
                "iq_compression_format": comp,
                "max_fronthaul_oneway_us": t12_us,
                "cti_enabled": True,
                "f1u_dscp_mapping": dscp,
            },
            "priority": 8, "ttl_seconds": None, "tags": ["oran", "ecpri", "7.2x", comp],
        }

    def _parse_interference(self, text: str, ttype: str, ident: str) -> Dict:
        sinr_m = re.search(r"(\d+(?:\.\d+)?)\s*db", text, re.IGNORECASE)
        sinr = float(sinr_m.group(1)) if sinr_m else 28.0
        return {
            "intent_type": "interference",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "xpic_enabled": True,
                "atpc_coordinated": True,
                "dynamic_channel_switch": True,
                "target_sinr_db": sinr,
            },
            "priority": 7, "ttl_seconds": None, "tags": ["xpic", "interference", "atpc"],
        }

    def _parse_telemetry(self, text: str, ttype: str, ident: str) -> Dict:
        ms_m = re.search(r"(\d+)\s*ms", text, re.IGNORECASE)
        cadence = int(ms_m.group(1)) if ms_m else 1000
        scenario = "traffic_surge"
        if "rain" in text.lower() or "channel" in text.lower():
            scenario = "channel_degradation"
        elif "fail" in text.lower() or "cut" in text.lower():
            scenario = "link_failure"
        return {
            "intent_type": "telemetry",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {
                "yang_push_cadence_ms": cadence,
                "twamp_probe_enabled": True,
                "digital_twin_preflight": True,
                "what_if_scenario": scenario,
            },
            "priority": 6, "ttl_seconds": None, "tags": ["telemetry", "yang-push", "twamp"],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Intent Parser (public API)
# ──────────────────────────────────────────────────────────────────────────────

class IntentParser:
    """
    Top-level parser. Tries LLM first (if API key available), falls back to rules.
    Also accepts pre-formatted JSON dict directly (structured path).
    """

    def __init__(self):
        self._llm: Optional[LLMParser] = None
        self._rule = RuleParser()
        try:
            self._llm = LLMParser()
            logger.info("LLM parser initialised (Gemini)")
        except Exception as e:
            logger.info(f"LLM parser not available ({e}), using rule-based fallback")

    def parse(self, raw_input: str | Dict, source: str = "operator") -> Intent:
        """
        Parse a freetext string or a pre-structured dict into an Intent object.
        """
        if isinstance(raw_input, dict):
            return self._build_intent(raw_input, raw_input=str(raw_input), source=source)

        raw_str = str(raw_input).strip()

        if raw_str.startswith("{"):
            try:
                data = json.loads(raw_str)
                return self._build_intent(data, raw_input=raw_str, source=source)
            except json.JSONDecodeError:
                pass

        if self._llm:
            try:
                data = self._llm.parse_text(raw_str)
                logger.info(f"LLM parsed intent: {data.get('intent_type')}")
                return self._build_intent(data, raw_input=raw_str, source=source)
            except Exception as e:
                logger.warning(f"LLM parsing failed ({e}), falling back to rule parser")

        data = self._rule.parse_text(raw_str)
        logger.info(f"Rule parser result: {data.get('intent_type')}")
        return self._build_intent(data, raw_input=raw_str, source=source)

    def _build_intent(self, data: Dict, raw_input: str, source: str) -> Intent:
        target_data = data.get("target", {})
        target = IntentTarget(
            target_type=target_data.get("target_type", "all"),
            identifier=target_data.get("identifier", "all"),
            direction=target_data.get("direction"),
        )
        itype = data.get("intent_type") or data.get("type")
        if not itype:
            raise KeyError("Missing 'intent_type' or 'type' in intent data")

        return Intent(
            intent_type=itype,
            target=target,
            parameters=data.get("parameters", {}),
            priority=data.get("priority", 5),
            ttl_seconds=data.get("ttl_seconds"),
            raw_input=raw_input,
            source=source,
            tags=data.get("tags", []),
        )
