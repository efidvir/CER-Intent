"""Resilience / Protection Intent Translator"""
from __future__ import annotations
from typing import List
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator
from cer_intent.intent_validator import DEVICE_CAPABILITIES


class ResilienceTranslator(BaseTranslator):

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        mode = params.get("protection_mode", "1+1-hsb")
        revert = params.get("revert_mode", "revertive")
        wtr = params.get("wtr_seconds", 300)
        holdoff = params.get("holdoff_ms", 0)

        configs = []
        warnings = []
        applied_count = 0
        fallback_count = 0

        for device in target_devices:
            model = device.get("model", "IP-50FX")
            caps = DEVICE_CAPABILITIES.get(model, DEVICE_CAPABILITIES["IP-50FX"])
            
            # Smart Fallback logic
            effective_mode = mode
            if mode == "space-diversity" and not caps.get("supports_sd"):
                if caps.get("supports_hsb"):
                    effective_mode = "1+1-hsb"
                    fallback_count += 1
                    warnings.append(f"Device {device['id']} ({model}): Fallback SD → HSB")
                else:
                    warnings.append(f"Device {device['id']} ({model}): No resilience support — skipping")
                    continue

            # Check if current state already matches (No-Op Detection)
            current_state = device.get("applied_configs", {}).get("protection", {})
            if current_state.get("protection_mode") == effective_mode:
                applied_count += 1
                continue

            cfg = {
                "protection_mode": effective_mode,
                "revert_mode": revert,
                "wtr_seconds": wtr,
                "holdoff_ms": holdoff,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="protection",
                yang_module="ceragon-protection",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        # Build Explanation
        if not configs and applied_count > 0:
            explanation = "Best resilience state already applied to all target devices; no action needed."
        elif not configs:
            explanation = "No configuration possible due to hardware limitations on target devices."
        else:
            explanation = f"Configured {mode} protection"
            if fallback_count > 0:
                explanation += f" (with {fallback_count} hardware fallbacks)"
            explanation += f" on {len(configs)} device(s)."
            if applied_count > 0:
                explanation += f" ({applied_count} devices already optimal)."

        return self._finalize(intent, configs, explanation, warnings)
