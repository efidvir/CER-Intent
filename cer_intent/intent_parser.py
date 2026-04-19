"""
Intent Parser
=============
Converts raw input (natural language or structured JSON) into a validated Intent object.

Two parsing paths:
  1. LLM Path  — uses Google Gemini to parse free-text into the canonical intent schema
  2. Rule Path — keyword-based fallback (works without any API key)
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

SYSTEM_PROMPT = """You are an expert network engineer specialising in 6G transport networks and Ceragon microwave equipment.
Your task is to parse a natural-language or semi-structured network management intent and return a single JSON object.

The JSON must conform to this schema:
{
  "intent_type": one of ["capacity", "qos", "modulation", "resilience", "slice", "energy", "sync", "security"],
  "target": {
    "target_type": one of ["link", "node", "sector", "all"],
    "identifier": "the link ID, node ID, sector name, or 'all'",
    "direction": null or "tx" or "rx" or "both"
  },
  "parameters": {
    // For capacity: min_throughput_gbps (float), max_throughput_gbps (float|null), channel_bandwidth_mhz (int|null), slice_type (null|"eMBB"|"URLLC"|"mMTC")
    // For qos: max_latency_ms (float|null), max_jitter_ms (float|null), max_packet_loss_pct (float|null), traffic_class ("EF"|"AF4"|"AF3"|"AF2"|"AF1"|"BE"), dscp_marking (int|null), bandwidth_guaranteed_mbps (float|null)
    // For modulation: min_modulation (str), max_modulation (str), acm_enabled (bool), tx_power_dbm (float|null)
    // For resilience: protection_mode ("1+1-hsb"|"1+1-cold"|"space-diversity"|"frequency-diversity"|"none"), revert_mode ("revertive"|"non-revertive"), wtr_seconds (int), holdoff_ms (int)
    // For slice: slice_name (str), slice_type ("eMBB"|"URLLC"|"mMTC"|"custom"), bandwidth_pct (float|null), bandwidth_mbps (float|null), priority_level (int 1-8), vlan_id (int|null)
    // For energy: sleep_mode_enabled (bool), tx_power_reduction_db (float|null), schedule (str|null)
    // For sync: ptp_profile (str|null), synce_enabled (bool)
    // For security: macsec_enabled (bool), encryption_algorithm (str|null)
  },
  "priority": integer 1-10 (default 5),
  "ttl_seconds": null or integer,
  "tags": []
}

Rules:
- Extract identifiers from the text (e.g. "link A-B" → identifier="link-A-B", "sector-north" → identifier="sector-north")
- If multiple links/nodes are implied, use target_type="sector" or "all" appropriately
- For throughput values, always convert to Gbps (e.g. "1000 Mbps" → 1.0)
- For modulation, use standard names: QPSK, 16QAM, 32QAM, 64QAM, 128QAM, 256QAM, 512QAM, 1024QAM, 2048QAM
- Respond ONLY with the JSON object. No explanation, no markdown fences.
- CRITICAL: If the user provides text that is nonsensical, adversarial, or completely unrelated to microwave transport network management, you MUST return a JSON object with exactly one key: {"error": "Unrecognized or nonsensical intent"}. Do not attempt to guess or map it to a network intent.
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
        "parts": ["Enable 1+1 Hot Standby protection on all links in sector-north with revertive mode"]
    },
    {
        "role": "model",
        "parts": [json.dumps({
            "intent_type": "resilience",
            "target": {"target_type": "sector", "identifier": "sector-north", "direction": None},
            "parameters": {"protection_mode": "1+1-hsb", "revert_mode": "revertive", "wtr_seconds": 300, "holdoff_ms": 0},
            "priority": 8, "ttl_seconds": None, "tags": ["protection", "hsb"]
        })]
    },
    {
        "role": "user",
        "parts": ["Set minimum ACM modulation to 256QAM and maximum to 2048QAM on all active links"]
    },
    {
        "role": "model",
        "parts": [json.dumps({
            "intent_type": "modulation",
            "target": {"target_type": "all", "identifier": "all", "direction": None},
            "parameters": {"min_modulation": "256QAM", "max_modulation": "2048QAM", "acm_enabled": True, "tx_power_dbm": None},
            "priority": 5, "ttl_seconds": None, "tags": ["acm", "mrmc"]
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
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        
        if "error" in parsed:
            raise ValueError(parsed["error"])
            
        return parsed


# ──────────────────────────────────────────────────────────────────────────────
# Keyword-based Rule Parser (no API key required)
# ──────────────────────────────────────────────────────────────────────────────

_MODULATION_LEVELS = ["QPSK", "16QAM", "32QAM", "64QAM", "128QAM", "256QAM", "512QAM", "1024QAM", "2048QAM"]

def _extract_identifier(text: str) -> tuple[str, str]:
    """Return (target_type, identifier) from text heuristics."""
    text_l = text.lower()
    if "all" in text_l or "every" in text_l or "network" in text_l:
        return "all", "all"
    # Sector
    sector_m = re.search(r"sector[- _]?(\w+)", text_l)
    if sector_m:
        return "sector", f"sector-{sector_m.group(1)}"
    # Node
    node_m = re.search(r"(?:node|site|gnb)[- _]?(\w+)", text_l)
    if node_m:
        return "node", f"node-{node_m.group(1)}"
    # Link  e.g.  "link A-B", "A to B", "between A and B"
    link_m = re.search(r"link[- ](\w+)[- ](\w+)", text)
    if link_m:
        return "link", f"link-{link_m.group(1)}-{link_m.group(2)}"
    between_m = re.search(r"between\s+(\w+)\s+and\s+(\w+)", text, re.IGNORECASE)
    if between_m:
        return "link", f"link-{between_m.group(1)}-{between_m.group(2)}"
    return "all", "all"


def _extract_float(text: str, patterns: list[str]) -> Optional[float]:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            # Convert Mbps → Gbps
            if "mbps" in p.lower() or ("mbps" in text[m.start():m.end()+5].lower()):
                val /= 1000
            return val
    return None


class RuleParser:
    """Keyword-driven intent parser — works without any LLM API key."""

    def parse_text(self, text: str) -> Dict[str, Any]:
        text_l = text.lower()
        target_type, identifier = _extract_identifier(text)

        # ── Determine intent type ─────────────────────────────────────────────
        if any(k in text_l for k in ["hsb", "hot standby", "protection", "revert", "diversity", "redundan"]):
            return self._parse_resilience(text, target_type, identifier)

        if any(k in text_l for k in ["qam", "modulation", "acm", "mrmc", "constellation"]):
            return self._parse_modulation(text, target_type, identifier)

        if any(k in text_l for k in ["latency", "jitter", "packet loss", "qos", "delay", "dscp"]):
            return self._parse_qos(text, target_type, identifier)

        # Capacity takes priority over slice when explicit throughput values are given
        if any(k in text_l for k in ["gbps", "mbps", "throughput", "increase capacity", "channel bandwidth"]):
            return self._parse_capacity(text, target_type, identifier)

        if any(k in text_l for k in ["slice", "vlan", "embb", "urllc", "mmtc", "allocat"]):
            return self._parse_slice(text, target_type, identifier)

        if any(k in text_l for k in ["sleep", "green", "power saving", "power reduction", "energy"]):
            return self._parse_energy(text, target_type, identifier)

        if any(k in text_l for k in ["ptp", "synce", "1588", "timing", "clock", "sync"]):
            return self._parse_sync(text, target_type, identifier)

        if any(k in text_l for k in ["macsec", "encryption", "secure", "cipher", "security"]):
            return self._parse_security(text, target_type, identifier)

        if any(k in text_l for k in ["capacity", "bandwidth"]):
            return self._parse_capacity(text, target_type, identifier)

        # Explicit rejection for anything else
        raise ValueError("Could not map request to a known network intent type (resilience, modulation, qos, capacity, slice, energy, sync, security)")

    # ── Type parsers ───────────────────────────────────────────────────────────

    def _parse_capacity(self, text: str, ttype: str, ident: str) -> Dict:
        gbps = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*gbps", r"(\d+(?:\.\d+)?)\s*mbps"]) or 1.0
        if "mbps" in text.lower() and "gbps" not in text.lower():
            # Already converted by _extract_float pattern logic, but double-check
            pass
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
            "parameters": {"min_throughput_gbps": gbps, "max_throughput_gbps": None,
                           "channel_bandwidth_mhz": bw, "slice_type": slice_type},
            "priority": 6, "ttl_seconds": None, "tags": ["capacity"],
        }

    def _parse_qos(self, text: str, ttype: str, ident: str) -> Dict:
        latency = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*ms", r"(\d+(?:\.\d+)?)\s*millisecond"])
        jitter = _extract_float(text, [r"jitter[^\d]*(\d+(?:\.\d+)?)\s*ms"])
        loss = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*%\s*(?:packet\s+)?loss", r"loss[^\d]*(\d+(?:\.\d+)?)"])
        tc = "EF" if any(k in text.lower() for k in ["high priority", "urllc", "critical"]) else "AF2"
        return {
            "intent_type": "qos",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {"max_latency_ms": latency, "max_jitter_ms": jitter,
                           "max_packet_loss_pct": loss, "traffic_class": tc,
                           "dscp_marking": None, "bandwidth_guaranteed_mbps": None},
            "priority": 7, "ttl_seconds": None, "tags": ["qos"],
        }

    def _parse_modulation(self, text: str, ttype: str, ident: str) -> Dict:
        found = [m for m in _MODULATION_LEVELS if m.lower() in text.lower()]
        min_mod = found[0] if found else "QPSK"
        max_mod = found[-1] if len(found) > 1 else "2048QAM"
        pwr = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*dbm"])
        return {
            "intent_type": "modulation",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {"min_modulation": min_mod, "max_modulation": max_mod,
                           "acm_enabled": True, "tx_power_dbm": pwr},
            "priority": 5, "ttl_seconds": None, "tags": ["acm", "mrmc"],
        }

    def _parse_resilience(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        if "frequency diversity" in text_l or "fd " in text_l:
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
        return {
            "intent_type": "resilience",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {"protection_mode": mode, "revert_mode": revert,
                           "wtr_seconds": wtr, "holdoff_ms": 0},
            "priority": 8, "ttl_seconds": None, "tags": ["protection"],
        }

    def _parse_slice(self, text: str, ttype: str, ident: str) -> Dict:
        text_l = text.lower()
        stype = "eMBB"
        for s in ["urllc", "mmtc", "embb"]:
            if s in text_l:
                stype = s.upper() if s != "embb" else "eMBB"
                break
        pct = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*%"])
        mbps = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*mbps"])
        vlan_m = re.search(r"vlan[- ]?(\d+)", text_l)
        vlan = int(vlan_m.group(1)) if vlan_m else None
        name_m = re.search(r"slice[- ]?(\w+)", text_l)
        name = name_m.group(1) if name_m else stype
        return {
            "intent_type": "slice",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {"slice_name": name, "slice_type": stype,
                           "bandwidth_pct": pct, "bandwidth_mbps": mbps,
                           "priority_level": 5, "vlan_id": vlan},
            "priority": 6, "ttl_seconds": None, "tags": ["slice"],
        }

    def _parse_energy(self, text: str, ttype: str, ident: str) -> Dict:
        tx_db = _extract_float(text, [r"(\d+(?:\.\d+)?)\s*db"])
        return {
            "intent_type": "energy",
            "target": {"target_type": ttype, "identifier": ident, "direction": None},
            "parameters": {"sleep_mode_enabled": "sleep" in text.lower(),
                           "tx_power_reduction_db": tx_db,
                           "schedule": None},
            "priority": 4, "ttl_seconds": None, "tags": ["energy", "green"],
        }

    def _parse_sync(self, text: str, ttype: str, ident: str) -> Dict:
        return {
            "intent_type": "sync",
            "target": {"target_type": ttype, "identifier": ident, "direction": "tx"},
            "parameters": {"ptp_profile": "G.8275.1" if "ptp" in text.lower() else None,
                           "synce_enabled": True},
            "priority": 9, "ttl_seconds": None, "tags": ["timing", "sync"],
        }

    def _parse_security(self, text: str, ttype: str, ident: str) -> Dict:
        alg = "AES-256" if "256" in text else "AES-128"
        return {
            "intent_type": "security",
            "target": {"target_type": ttype, "identifier": ident, "direction": "both"},
            "parameters": {"macsec_enabled": True, "encryption_algorithm": alg},
            "priority": 10, "ttl_seconds": None, "tags": ["security", "macsec"],
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
        # ── Structured JSON path ──────────────────────────────────────────────
        if isinstance(raw_input, dict):
            return self._build_intent(raw_input, raw_input=str(raw_input), source=source)

        raw_str = str(raw_input).strip()

        # Check if it's JSON text
        if raw_str.startswith("{"):
            try:
                data = json.loads(raw_str)
                return self._build_intent(data, raw_input=raw_str, source=source)
            except json.JSONDecodeError:
                pass

        # ── NL path ───────────────────────────────────────────────────────────
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
