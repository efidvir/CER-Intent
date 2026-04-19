"""Modulation / ACM Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator
from cer_intent.intent_validator import MODULATION_ORDER, DEVICE_CAPABILITIES


class ModulationTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        min_mod = params.get("min_modulation", "QPSK")
        max_mod = params.get("max_modulation", "2048QAM")
        acm = params.get("acm_enabled", True)
        tx_pwr = params.get("tx_power_dbm")

        configs = []
        warnings = []
        for device in target_devices:
            model = device.get("model", "IP-50FX")
            caps = DEVICE_CAPABILITIES.get(model, DEVICE_CAPABILITIES["IP-50FX"])
            hw_max = caps["max_modulation"]

            # Cap max_mod to hardware capability
            effective_max = max_mod
            if MODULATION_ORDER.get(max_mod, 0) > MODULATION_ORDER.get(hw_max, 0):
                effective_max = hw_max
                warnings.append(f"Device {device['id']} ({model}): max modulation capped to {hw_max}")

            cfg = {
                "min_modulation": min_mod,
                "max_modulation": effective_max,
                "acm_enabled": acm,
                "tx_power_dbm": tx_pwr,
                "mrmc_script_id": params.get("mrmc_script_id"),
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="radio",
                yang_module="ceragon-radio-link",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Set ACM range {min_mod}–{max_mod} (ACM {'enabled' if acm else 'disabled'}) "
            f"on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation, warnings)
