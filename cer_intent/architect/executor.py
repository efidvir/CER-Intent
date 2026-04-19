"""
Architect Executor
==================
Orchestrator that executes the multi-domain strategies selected by the
Intent Architect Agent. It distills complex plans into concrete device configs.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any

from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.architect.strategy import ArchitectPlan, Strategy, ConfigAction, ActionType
from cer_intent.translators import get_translator

logger = logging.getLogger(__name__)


class ArchitectExecutor:
    """
    Takes an ArchitectPlan and executes its selected strategy.
    Maps high-level ConfigActions to specific Translator calls.
    """

    def __init__(self, registry):
        self._registry = registry

    def execute_plan(self, plan: ArchitectPlan, original_intent: Intent) -> TranslationResult:
        """
        Translates the selected strategy into a unified TranslationResult.
        """
        if not plan.selected_strategy:
            logger.warning(f"Plan {plan.plan_id} has no selected strategy. Falling back.")
            return TranslationResult(intent_id=original_intent.intent_id, success=False, error="No strategy selected")

        strategy = plan.selected_strategy
        logger.info(f"Executing strategy: {strategy.name} ({len(strategy.actions)} actions)")

        all_configs: List[DeviceConfig] = []
        explanation_parts: List[str] = [f"Architect Strategy: {strategy.name}"]
        warnings: List[str] = []

        # Sort actions by execution order
        sorted_actions = sorted(strategy.actions, key=lambda a: a.execution_order)

        for action in sorted_actions:
            try:
                configs, explanation = self._execute_action(action, original_intent)
                all_configs.extend(configs)
                if explanation:
                    explanation_parts.append(explanation)
            except Exception as e:
                logger.error(f"Failed to execute action {action.action_id} ({action.action_type}): {e}")
                if action.required:
                    return TranslationResult(
                        intent_id=original_intent.intent_id,
                        success=False,
                        error=f"Action {action.action_type} failed: {e}"
                    )
                warnings.append(f"Optional action {action.action_type} failed: {e}")

        # Finalize the combined result
        # We use a dummy "MegaTranslator" logic to finalize (build YANG etc.)
        from cer_intent.translators.base_translator import BaseTranslator
        class MegaTranslator(BaseTranslator):
            def translate(self, i, t): return None # Not used
        
        final_explanation = " | ".join(explanation_parts)
        return MegaTranslator()._finalize(original_intent, all_configs, final_explanation, warnings)

    def _execute_action(self, action: ConfigAction, original_intent: Intent) -> (List[DeviceConfig], str):
        """Maps a single ConfigAction to a translator call."""
        
        # Determine target devices for this action
        target_spec = action.target_override or original_intent.target.model_dump(mode='json')
        target_devices = self._registry.get_devices_for_target(
            target_spec.get("target_type", "all"),
            target_spec.get("identifier", "all")
        )
        # Enrich with state-store data for 'already applied' detection
        # We need a reference to state_store here. 
        # For PoC, the state_store is usually available on the app object or passed in.
        from flask import current_app
        state_store = current_app.config.get("state_store")
        if state_store:
            device_states = state_store.get_all_device_states()
            for dev in target_devices:
                dev["applied_configs"] = device_states.get(dev["id"], {}).get("configs", {})

        # Map ActionType to IntentType for translator lookup
        intent_type_map = {
            ActionType.TRANSLATE:    action.intent_type_override or original_intent.intent_type.value,
            ActionType.QOS_MARK:     "qos",
            ActionType.PATH_CHANGE:  "qos",   # Steering is often handled by QoS/PBR
            ActionType.VPN_REROUTE:  "qos",
            ActionType.RADIO_TUNE:   "modulation",
            ActionType.POWER_ADJUST: "modulation",
            ActionType.SLICE_ADJUST: "slice",
        }

        intent_type_str = intent_type_map.get(action.action_type, "qos")
        
        # If action is ALERT or MONITOR, no config change
        if action.action_type in [ActionType.ALERT, ActionType.MONITOR]:
            return [], f"[{action.action_type.value.upper()}] {action.rationale}"

        # Create a "Synthetic Intent" for the translator with overridden parameters
        from cer_intent.intent_schema import IntentType
        try:
            itype = IntentType(intent_type_str)
        except ValueError:
            itype = original_intent.intent_type

        synthetic_intent = original_intent.model_copy(deep=True)
        synthetic_intent.intent_type = itype
        # Merge overrides
        synthetic_intent.parameters.update(action.parameter_overrides)
        
        # Invoke Translator
        from cer_intent.translators import get_translator
        translator = get_translator(itype)
        
        # Execute translation
        result = translator.translate(synthetic_intent, target_devices)
        
        if not result.success:
            raise Exception(result.error)

        return result.device_configs, f"{action.action_type.value}: {result.explanation}"
