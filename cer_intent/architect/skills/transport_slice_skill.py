"""
Transport slice skill
=====================
An intent that names its two endpoints ("connect region-a and edge, 500 Mbps,
10 ms") is an end-to-end transport slice. It is fulfilled by one RFC 9543
request to the transport slice controller, which maps it, chooses L2VPN or
L3VPN and realizes it on TeraFlowSDN (L2SM / L3SM, radio decisions as service
settings), the same stages as the TeraFlowSDN slice controller.

This skill wins over per-device strategies for such intents, so the slice is
handled by the slice controller rather than by device-level tuning.
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import NetworkContext, Strategy, ConfigAction, ActionType
from cer_intent.architect.skills.base_skill import BaseSkill


def is_transport_slice(intent: Intent) -> bool:
    return intent.intent_type.value == "slice" and len(intent.parameters.get("sdps") or []) >= 2


class TransportSliceSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "transport_slice_controller"

    @property
    def description(self) -> str:
        return ("End-to-end transport slice through the slice controller: RFC 9543 in, "
                "L2SM (RFC 8466) or L3SM (RFC 8299) to TeraFlowSDN out.")

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["slice"]

    @property
    def applicable_goals(self) -> List[str]:
        return []

    def is_applicable(self, intent: Intent, context: NetworkContext) -> bool:
        return is_transport_slice(intent)

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        p = intent.parameters
        ends = " and ".join(f"{s.get('node_id')}:{s.get('tp_id')}" for s in p.get("sdps", [])[:2])
        slos = ", ".join(x for x in (
            f"{p['bandwidth_mbps']:g} Mbps" if p.get("bandwidth_mbps") else "",
            f"≤ {p['max_latency_ms']:g} ms" if p.get("max_latency_ms") else "") if x)
        extra = f"; ACM floor {p['acm']['min_modulation']}" if (p.get("acm") or {}).get("min_modulation") else ""
        return [Strategy(
            name="Transport slice through the slice controller",
            description=f"RFC 9543 slice between {ends}" + (f" ({slos})" if slos else "") + extra,
            skill_source=self.name,
            confidence=0.995,
            rationale=("The intent names both endpoints, so it is one end-to-end slice: the slice controller "
                       "maps it, selects L2VPN or L3VPN and realizes it on TeraFlowSDN through its standard "
                       "VPN interfaces; radio settings travel as service settings to the Ceragon handler."),
            tradeoffs="Device-level tuning outside the slice (e.g. fronthaul compression) is left to other intents.",
            actions=[ConfigAction(
                action_type=ActionType.SLICE_ADJUST,
                intent_type_override="slice",
                parameter_overrides={},
                rationale="Hand the RFC 9543 request to the transport slice controller",
                execution_order=1,
                estimated_impact="One TeraFlowSDN service along the path, verified by reading it back",
            )],
        )]
