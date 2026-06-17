"""
Skill Registry
==============
Discovers and manages all loaded skills.
Skills are auto-discovered — just add a new class in the skills/ package.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import NetworkContext
from cer_intent.architect.skills.base_skill import BaseSkill
from cer_intent.architect.skills.low_latency_skill import LowLatencySkill
from cer_intent.architect.skills.high_capacity_skill import HighCapacitySkill
from cer_intent.architect.skills.radio_optimization_skill import RadioOptimizationSkill
from cer_intent.architect.skills.traffic_engineering_skill import TrafficEngineeringSkill, ResilienceSkill
from cer_intent.architect.skills.network_health_skill import NetworkHealthSkill
from cer_intent.architect.skills.rain_fade_skill import RainFadeSkill
from cer_intent.architect.skills.energy_optimization_skill import EnergyOptimizationSkill
from cer_intent.architect.skills.spectral_efficiency_skill import SpectralEfficiencySkill

logger = logging.getLogger(__name__)

# All available skills (extend this list to add new skills)
_ALL_SKILLS: List[BaseSkill] = [
    LowLatencySkill(),
    HighCapacitySkill(),
    RadioOptimizationSkill(),
    TrafficEngineeringSkill(),
    ResilienceSkill(),
    NetworkHealthSkill(),
    RainFadeSkill(),
    EnergyOptimizationSkill(),
    SpectralEfficiencySkill(),
]


class SkillRegistry:
    """
    Central registry of all architect skills.
    Finds applicable skills for a given intent and network context.
    """

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {s.name: s for s in _ALL_SKILLS}
        logger.info(f"Skill registry loaded: {list(self._skills.keys())}")

    def get_all_skills(self) -> List[BaseSkill]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def find_applicable_skills(self, intent: Intent, context: NetworkContext) -> List[BaseSkill]:
        """Return all skills that are applicable to the given intent and context."""
        applicable = []
        for skill in self._skills.values():
            try:
                if skill.is_applicable(intent, context):
                    applicable.append(skill)
                    logger.debug(f"Skill '{skill.name}' is applicable")
            except Exception as e:
                logger.warning(f"Skill '{skill.name}' applicability check failed: {e}")
        return applicable

    def skill_catalog(self) -> List[dict]:
        """Return a human-readable catalog of all skills for the dashboard."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "applicable_intent_types": s.applicable_intent_types,
                "applicable_goals": s.applicable_goals,
            }
            for s in self._skills.values()
        ]
