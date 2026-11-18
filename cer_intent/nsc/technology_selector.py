"""
Slice controller, stage 2: Technology Selector
==============================================
Chooses how the slice is realized on the transport network: as an L2VPN or as
an L3VPN, the same two options as the TeraFlowSDN slice controller.

The rules are fixed and each choice carries its reason:
  1. a technology named in the request wins;
  2. a selector skill, when one is plugged in, may choose (CER-Intent's
     AI-native step); its answer is used only if it names L2VPN or L3VPN;
  3. endpoints with IP addresses or IP match criteria -> L3VPN;
  4. endpoints matched by VLAN only -> L2VPN;
  5. otherwise the configured default (NSC_DEFAULT_TECHNOLOGY, L3VPN unless set).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from cer_intent.nsc.mapper import MappedSlice

L2VPN = "L2VPN"
L3VPN = "L3VPN"
_ALIASES = {"L2VPN": L2VPN, "L2SM": L2VPN, "L2": L2VPN, "L3VPN": L3VPN, "L3SM": L3VPN, "L3": L3VPN, "IP": L3VPN}

SelectorSkill = Callable[[MappedSlice], Optional[Tuple[str, str]]]


@dataclass
class TechnologyChoice:
    technology: str
    reason: str
    decided_by: str  # "request", "skill", "rule", "default"

    def to_dict(self):
        return {"technology": self.technology, "reason": self.reason, "decided_by": self.decided_by}


def normalize(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return _ALIASES.get(str(name).strip().upper())


def default_technology() -> str:
    return normalize(os.getenv("NSC_DEFAULT_TECHNOLOGY")) or L3VPN


def select_technology(mapped: MappedSlice, skill: Optional[SelectorSkill] = None) -> TechnologyChoice:
    requested = normalize(mapped.requested_technology)
    if requested:
        return TechnologyChoice(requested, f"requested as {mapped.requested_technology}", "request")

    if skill is not None:
        try:
            answer = skill(mapped)
        except Exception:  # pylint: disable=broad-except  # a failing skill leaves the choice to the rules
            answer = None
        if answer and normalize(answer[0]):
            return TechnologyChoice(normalize(answer[0]), answer[1] or "chosen by the selector skill", "skill")

    has_ip = all(ep.ip_address or ep.source_prefixes or ep.destination_prefixes for ep in mapped.endpoints)
    if has_ip:
        return TechnologyChoice(L3VPN, "every endpoint has an IP address or IP match criteria", "rule")
    if all(ep.vlan_id is not None for ep in mapped.endpoints):
        return TechnologyChoice(L2VPN, "endpoints are matched by VLAN only", "rule")
    tech = default_technology()
    return TechnologyChoice(tech, "no IP or VLAN match on every endpoint; using the default", "default")
