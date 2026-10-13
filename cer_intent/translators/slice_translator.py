"""Slice / Resource Allocation Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator

# Slice type → default VLAN range start
VLAN_BASE = {"eMBB": 100, "URLLC": 200, "mMTC": 300, "custom": 400}
# Slice type → default priority level
PRIORITY_MAP = {"eMBB": 5, "URLLC": 7, "mMTC": 3, "custom": 5}
# Slice type → 3GPP SST (Slice/Service Type)
SST_MAP = {"eMBB": 1, "URLLC": 2, "mMTC": 3, "custom": 4}
# D3.1 Table 2-1: DSCP midhaul socket mapping for per-slice F1u traffic separation
DSCP_MIDHAUL_MAP = {1: 6, 2: 7, 3: 8, 4: 9}


class SliceTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        slice_name = params.get("slice_name", "default-slice")
        slice_type = params.get("slice_type", "eMBB")
        bw_pct = params.get("bandwidth_pct")
        bw_mbps = params.get("bandwidth_mbps")
        priority = params.get("priority_level", PRIORITY_MAP.get(slice_type, 5))
        vlan = params.get("vlan_id") or (VLAN_BASE.get(slice_type, 400) + len(slice_name) % 94)

        sst = params.get("sst", SST_MAP.get(slice_type, 1))
        # D3.1 Table 2-1: Midhaul DSCP code assignment
        dscp = params.get("dscp", DSCP_MIDHAUL_MAP.get(sst, 6))
        five_qi = params.get("five_qi", 9 if sst == 1 else 82)
        min_prb = params.get("min_prb_ratio", 0)
        max_prb = params.get("max_prb_ratio", 30 if sst == 1 else 70)

        configs = []
        for device in target_devices:
            cfg = {
                "slice_name": slice_name,
                "slice_type": slice_type,
                "bandwidth_pct": bw_pct,
                "bandwidth_mbps": bw_mbps,
                "priority_level": priority,
                "vlan_id": vlan,
                "sst": str(sst),
                "dscp_midhaul": dscp,
                "five_qi": five_qi,
                "sched_cfg": {
                    "min_prb_policy_ratio": min_prb,
                    "max_prb_policy_ratio": max_prb,
                },
                "ietf_rfc9543_ref": f"slice-{slice_name}",
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
            f"(SST {sst}, Midhaul DSCP {dscp} [D3.1 Table 2-1], VLAN {vlan}, PRB {min_prb}-{max_prb}%) "
            f"on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)

