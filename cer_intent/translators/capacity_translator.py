"""Capacity / Throughput Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator

# MRMC script selection table: (min_gbps, max_gbps) → (script_id, bw_mhz, min_mod, max_mod)
MRMC_TABLE = [
    (0,    0.5,  {"script_id": 10, "bw_mhz":  28, "min_mod": "QPSK",    "max_mod": "256QAM"}),
    (0.5,  1.0,  {"script_id": 20, "bw_mhz":  28, "min_mod": "16QAM",   "max_mod": "512QAM"}),
    (1.0,  2.5,  {"script_id": 30, "bw_mhz":  56, "min_mod": "16QAM",   "max_mod": "1024QAM"}),
    (2.5,  5.0,  {"script_id": 40, "bw_mhz":  56, "min_mod": "64QAM",   "max_mod": "2048QAM"}),
    (5.0,  7.5,  {"script_id": 50, "bw_mhz": 112, "min_mod": "64QAM",   "max_mod": "2048QAM"}),
    (7.5,  10.0, {"script_id": 60, "bw_mhz": 112, "min_mod": "256QAM",  "max_mod": "2048QAM"}),
]


def _select_mrmc(gbps: float, preferred_bw: int = None) -> dict:
    for lo, hi, profile in MRMC_TABLE:
        if lo <= gbps < hi:
            if preferred_bw:
                profile = dict(profile, bw_mhz=preferred_bw)
            return profile
    return MRMC_TABLE[-1][2]  # Default to highest profile


class CapacityTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        min_gbps = params.get("min_throughput_gbps", 1.0)
        preferred_bw = params.get("channel_bandwidth_mhz")
        mrmc = _select_mrmc(min_gbps, preferred_bw)

        configs = []
        warnings = []
        for device in target_devices:
            cfg_params = {
                "channel_bandwidth_mhz": mrmc["bw_mhz"],
                "mrmc_script_id": mrmc["script_id"],
                "min_modulation": mrmc["min_mod"],
                "max_modulation": mrmc["max_mod"],
                "acm_enabled": True,
                "slice_type": params.get("slice_type"),
                "target_throughput_gbps": min_gbps,
            }
            # Direct hardware configuration overrides from intent parameters
            for override_key in ["tx_frequency", "rx_frequency", "tx_power_dbm", "mrmc_script_id"]:
                if override_key in params:
                    cfg_params[override_key] = params[override_key]
            # Cap to device hardware limit
            max_cap = device.get("max_throughput_gbps", 10.0)
            if min_gbps > max_cap:
                warnings.append(
                    f"Device {device['id']} max capacity {max_cap} Gbps < requested {min_gbps} Gbps"
                )

            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="radio",
                yang_module="ceragon-radio-link",
                parameters=cfg_params,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Selected MRMC script #{mrmc['script_id']} ({mrmc['bw_mhz']} MHz channel, "
            f"{mrmc['min_mod']}–{mrmc['max_mod']} ACM) to support ≥{min_gbps} Gbps "
            f"across {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation, warnings)
