"""
Base Translator
===============
Abstract base class for all intent-to-configuration translators.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.yang_builder import YANGBuilder


class BaseTranslator(ABC):
    """Each subclass handles one IntentType and produces DeviceConfig objects."""

    def __init__(self):
        self._yang_builder = YANGBuilder()

    @abstractmethod
    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        """
        Translate an intent into device-specific configurations.

        Args:
            intent: The validated Intent object.
            target_devices: List of device dicts from the registry
                            that should be configured.
        Returns:
            TranslationResult containing one DeviceConfig per affected device.
        """

    def _finalize(
        self,
        intent: Intent,
        configs: List[DeviceConfig],
        explanation: str,
        warnings: List[str] = None,
    ) -> TranslationResult:
        """Attach YANG XML to each config and wrap in TranslationResult."""
        for cfg in configs:
            if cfg.yang_xml is None:
                try:
                    cfg.yang_xml = self._yang_builder.build(cfg)
                except Exception as e:
                    cfg.yang_xml = f"<!-- YANG build error: {e} -->"
        return TranslationResult(
            intent_id=intent.intent_id,
            success=True,
            device_configs=configs,
            explanation=explanation,
            warnings=warnings or [],
        )
