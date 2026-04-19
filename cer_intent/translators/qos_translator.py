"""QoS Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator

# Traffic class → DSCP mapping
DSCP_MAP = {"EF": 46, "AF4": 34, "AF3": 26, "AF2": 18, "AF1": 10, "BE": 0}

# Latency thresholds → recommended traffic class
def _recommend_tc(latency_ms: float) -> str:
    if latency_ms <= 1:   return "EF"
    if latency_ms <= 5:   return "AF4"
    if latency_ms <= 10:  return "AF3"
    if latency_ms <= 20:  return "AF2"
    return "BE"


class QoSTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        latency = params.get("max_latency_ms")
        tc = params.get("traffic_class", "AF2")
        if latency and tc == "AF2":
            tc = _recommend_tc(latency)

        dscp = params.get("dscp_marking") if params.get("dscp_marking") is not None else DSCP_MAP.get(tc, 18)

        configs = []
        for device in target_devices:
            cfg = {
                "traffic_class": tc,
                "dscp_marking": dscp,
                "max_latency_ms": latency,
                "max_jitter_ms": params.get("max_jitter_ms"),
                "max_packet_loss_pct": params.get("max_packet_loss_pct"),
                "bandwidth_guaranteed_mbps": params.get("bandwidth_guaranteed_mbps"),
                "preferred_path": params.get("preferred_path"),
                "vpn_steering": params.get("vpn_steering"),
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="qos",
                yang_module="ceragon-qos",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Configured QoS class {tc} (DSCP {dscp})"
            + (f" with max latency {latency} ms" if latency else "")
            + (f" | Steering via path: {params.get('preferred_path')}" if params.get("preferred_path") else "")
            + (f" | VPN Reroute: {params.get('vpn_steering')}" if params.get("vpn_steering") else "")
            + f" on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)
