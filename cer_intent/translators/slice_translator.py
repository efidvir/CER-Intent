"""Slice / Resource Allocation Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator

# Slice type → default VLAN range start
VLAN_BASE = {"eMBB": 100, "URLLC": 200, "mMTC": 300, "custom": 400}
# Slice type → default priority level
PRIORITY_MAP = {"eMBB": 5, "URLLC": 7, "mMTC": 3, "custom": 5}


class SliceTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        slice_name = params.get("slice_name", "default-slice")
        slice_type = params.get("slice_type", "eMBB")
        bw_pct = params.get("bandwidth_pct")
        bw_mbps = params.get("bandwidth_mbps")
        priority = params.get("priority_level", PRIORITY_MAP.get(slice_type, 5))
        vlan = params.get("vlan_id") or (VLAN_BASE.get(slice_type, 400) + len(slice_name) % 94)

        configs = []
        for device in target_devices:
            cfg = {
                "slice_name": slice_name,
                "slice_type": slice_type,
                "bandwidth_pct": bw_pct,
                "bandwidth_mbps": bw_mbps,
                "priority_level": priority,
                "vlan_id": vlan,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="slice",
                yang_module="ceragon-slice",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        bw_str = f"{bw_pct}%" if bw_pct else (f"{bw_mbps} Mbps" if bw_mbps else "best-effort")
        explanation = (
            f"Allocated {bw_str} capacity to {slice_type} slice '{slice_name}' "
            f"(VLAN {vlan}, priority {priority}) on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)
