"""
Base Skill
==========
Abstract base class for all Intent Architect skills.
Each skill encapsulates domain knowledge about HOW to achieve
a particular network objective through multiple possible approaches.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import NetworkContext, Strategy


class BaseSkill(ABC):
    """
    A skill represents domain expertise the architect agent can apply.

    Skills answer the question:
      "Given this intent and the current network state, what are my options?"

    Each skill may generate multiple candidate strategies with confidence scores,
    allowing the agent to reason about trade-offs before selecting the best approach.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill identifier."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short human-readable description of what this skill knows."""

    @property
    @abstractmethod
    def applicable_intent_types(self) -> List[str]:
        """List of intent types this skill can handle (e.g. ['qos', 'capacity'])."""

    @property
    @abstractmethod
    def applicable_goals(self) -> List[str]:
        """
        Semantic goal keywords this skill responds to.
        Used for cross-type skill matching (e.g. 'low_latency' can be achieved
        by both QoS and radio tuning skills).
        """

    def is_applicable(self, intent: Intent, context: NetworkContext) -> bool:
        """
        Return True if this skill is relevant for the given intent and network context.
        Default: check intent type or goal keywords in raw_input.
        Subclasses may override with richer logic.
        """
        if intent.intent_type.value in self.applicable_intent_types:
            return True
        raw = (intent.raw_input or "").lower()
        return any(g in raw for g in self.applicable_goals)

    @abstractmethod
    def generate_strategies(
        self,
        intent: Intent,
        context: NetworkContext,
    ) -> List[Strategy]:
        """
        Generate one or more candidate strategies for fulfilling this intent.

        Each strategy represents a different approach with a different set of
        configuration actions. The agent will score and select among them.

        Args:
            intent:  The validated intent to fulfill.
            context: Current network state (topology + telemetry + device states).

        Returns:
            List of Strategy objects, each with confidence score and action list.
        """

    def _get_link_telemetry(self, context: NetworkContext, link_id: str) -> dict:
        """Convenience: fetch telemetry for a specific link."""
        return context.telemetry.get(link_id, {})

    def _get_links_for_target(self, context: NetworkContext) -> List[dict]:
        """Return relevant links from topology for the current target."""
        links = context.topology.get("links", [])
        t_type = context.target_type
        t_id   = context.target_identifier

        if t_type == "all":
            return links
        if t_type == "link":
            return [l for l in links if l["id"] == t_id]
        if t_type == "node":
            return [l for l in links if l["src"] == t_id or l["dst"] == t_id]
        if t_type == "sector":
            nodes = context.topology.get("nodes", [])
            sector_nodes = {n["id"] for n in nodes if n.get("sector") == t_id}
            return [l for l in links if l["src"] in sector_nodes or l["dst"] in sector_nodes]
        return links

    def _avg_metric(self, context: NetworkContext, links: List[dict], metric: str) -> float:
        """Average a telemetry metric across a set of links."""
        vals = [context.telemetry.get(l["id"], {}).get(metric, 0) for l in links]
        return sum(vals) / len(vals) if vals else 0
