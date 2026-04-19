"""
Intent Architect Agent
======================
The reasoning engine that coordinates multi-domain skills and hardware knowledge
to produce optimized network strategy plans.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ArchitectPlan, StrategyStatus
)
from cer_intent.architect.skill_registry import SkillRegistry
from cer_intent.architect.conflict_resolver import ConflictResolver
from cer_intent.device.knowledge_base import HardwareKnowledgeBase

logger = logging.getLogger(__name__)


class IntentArchitectAgent:
    """
    Reasoning layer that transforms a single Intent into a multi-step ArchitectPlan.
    Consults available skills and hardware capabilities to ensure configurations
    are optimized and appropriate for the specific device types in the network.
    """

    def __init__(self, registry, state_store, knowledge_base: Optional[HardwareKnowledgeBase] = None):
        self._registry = registry
        self._state_store = state_store
        self._skills = SkillRegistry()
        self._kb = knowledge_base or HardwareKnowledgeBase()
        self._resolver = ConflictResolver()

    def create_plan(self, intent: Intent, telemetry: Dict[str, Any]) -> ArchitectPlan:
        """
        Main entry point for architecture reasoning.
        1. Build context
        2. Find skills
        3. Generate candidate strategies
        4. Select & Score
        5. Conflict Resolution (Outside API)
        """
        logger.info(f"Architecting plan for intent {intent.intent_id[:8]}...")
        
        # Build Reasoning Context
        context = NetworkContext(
            topology=self._registry.get_topology(),
            telemetry=telemetry,
            active_intents=intent.context_intents or [],
            device_states=self._state_store.get_all_device_states(),
            target_identifier=intent.target.identifier,
            target_type=intent.target.target_type.value,
            knowledge_base=self._kb
        )

        plan = ArchitectPlan(
            intent_id=intent.intent_id,
            intent_summary=intent.summary()
        )
        plan.reasoning_trace.append(f"[THOUGHT] Analyzing incoming {intent.intent_type.value} intent request. Objective target is '{intent.target.identifier}'.")

        # 1. Hardware Awareness
        target_devs = self._registry.get_devices_for_target(
            intent.target.target_type.value, intent.target.identifier
        )
        from cer_intent.intent_validator import DEVICE_CAPABILITIES
        for dev in target_devs:
            profile = self._kb.get_profile(dev.get("model", "Generic"))
            model = dev.get("model", "IP-50FX")
            caps = DEVICE_CAPABILITIES.get(model, DEVICE_CAPABILITIES["IP-50FX"])
            
            plan.network_observations.append(
                f"Target device {dev['id']} has model {profile.model_name}. "
                f"Capabilites: HSB={caps.get('supports_hsb')}, SD={caps.get('supports_sd')}."
            )
            plan.reasoning_trace.append(
                f"[OBSERVATION] Interrogating hardware matrix for {dev['id']} ({profile.model_name}). Identified physical capabilities: HSB={caps.get('supports_hsb')}, SD={caps.get('supports_sd')}."
            )
            
            # Predictive reasoning about constraints
            if intent.intent_type.value == "resilience":
                mode = intent.parameters.get("protection_mode")
                if mode == "space-diversity" and not caps.get("supports_sd"):
                    plan.reasoning_trace.append(
                        f"[EVALUATION] Space Diversity requested, but validation shows {dev['id']} ({model}) lacks supporting RF components."
                    )
                    plan.reasoning_trace.append(
                        f"[DECISION] Formulating fallback strategy. I will pivot to 1+1 HSB to best satisfy the reliability requirement without creating a failure state."
                    )

        # 2. Skill Invocation
        applicable_skills = self._skills.find_applicable_skills(intent, context)
        plan.reasoning_trace.append(f"[THOUGHT] Scanning semantic skill registry... Found {len(applicable_skills)} matching abilities: {[s.name for s in applicable_skills]}. Initiating strategy generation.")

        all_candidates: List[Strategy] = []
        for skill in applicable_skills:
            try:
                strategies = skill.generate_strategies(intent, context)
                all_candidates.extend(strategies)
                plan.reasoning_trace.append(f"[EVALUATION] Consulted '{skill.name}'. Generated {len(strategies)} potential configuration paths.")
            except Exception as e:
                logger.error(f"Error in skill '{skill.name}': {e}")
                plan.reasoning_trace.append(f"ERROR: Skill '{skill.name}' failed to generate strategies: {e}")

        if not all_candidates:
            plan.reasoning_trace.append("[OBSERVATION] No viable complex strategies formulated. Proceeding with standard direct translation.")
            return plan

        # 3. Strategy Selection (Simplified scoring for PoC)
        # In a real system, this could be an LLM-based choice or a multi-objective utility function.
        all_candidates.sort(key=lambda s: s.confidence, reverse=True)
        plan.candidate_strategies = all_candidates
        
        selected = all_candidates[0]
        selected.status = StrategyStatus.SELECTED
        plan.selected_strategy = selected
        
        plan.reasoning_trace.append(f"[DECISION] Determining optimal path. Selected '{selected.name}' with computed confidence score {selected.confidence:.2f}.")
        plan.reasoning_trace.append(f"[THOUGHT] Rationale behind this choice: {selected.rationale}")

        # 4. Conflict Resolution Check (Simulated API)
        plan.reasoning_trace.append("[ACTION] Final check: running proposed strategy through the cross-domain conflict resolver api.")
        report = self._resolver.resolve_conflicts(plan, context)
        plan.conflict_report = report
        
        status_msg = f"[OBSERVATION] Verification complete. Impact level evaluated as: {report['level'].upper()} - {report['message']}."
        plan.reasoning_trace.append(status_msg)
        if report["conflicts"]:
            for c in report["conflicts"]:
                plan.reasoning_trace.append(f"  > [{c['severity']}] {c['description']}")

        return plan
