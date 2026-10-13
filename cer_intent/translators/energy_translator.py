"""
Energy Management Intent Translator (D3.1 Section 2.4.2.2 & 4.2.5)
===================================================================
Translates high-level energy-saving intents into device-level power configurations
and aligns with the Telefónica instantaneous-device-energy-tid YANG model.
"""
from __future__ import annotations

from typing import List, Dict, Any
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator


class EnergyTranslator(BaseTranslator):
    """
    Translates energy management directives into actionable power configurations.
    """

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        mode = params.get("energy_mode", "saving")  # "basic", "saving", "eco-sleep"
        max_power = params.get("target_power_w") or params.get("max_power_w")
        sectors_to_sleep = params.get("sleep_sectors") or ["Sector-2-Redundant"]
        off_peak_window = params.get("window", "02:00-05:00")
        
        configs = []
        for device in target_devices:
            dev_id = device.get("id", "ctu-96")
            cfg = {
                "energy_mode": mode,
                "target_power_w": max_power,
                "sleep_sectors": sectors_to_sleep if mode in ["saving", "eco-sleep"] else [],
                "off_peak_window": off_peak_window,
                "yang_model": "instantaneous-device-energy-tid",
                "estimated_power_saving_w": 24.0 if mode in ["saving", "eco-sleep"] else 0.0,
            }
            configs.append(DeviceConfig(
                device_id=dev_id,
                config_type="energy",
                yang_module="instantaneous-device-energy-tid",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        saved = 24.0 * len(configs) if mode in ["saving", "eco-sleep"] else 0.0
        explanation = (
            f"Configured energy mode '{mode}' on {len(configs)} device(s). "
            f"Sectors transitioned to sleep: {sectors_to_sleep}. "
            f"Estimated power reduction: {saved} W (D3.1 Section 4.2.5 compliant)."
        )
        return self._finalize(intent, configs, explanation)
