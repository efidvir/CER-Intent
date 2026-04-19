"""
Intent Architect Agent — Strategy Data Models
=============================================
Data structures for strategies, actions, and reasoning traces
produced by the Intent Architect Agent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyStatus(str, Enum):
    CANDIDATE   = "candidate"    # Generated, not yet selected
    SELECTED    = "selected"     # Chosen by the agent
    EXECUTING   = "executing"
    COMPLETED   = "completed"
    FAILED      = "failed"
    SKIPPED     = "skipped"      # Valid but not chosen
    CONFLICT    = "conflict"     # Blocked by conflict resolver


class ConflictLevel(str, Enum):
    NONE     = "none"
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class ActionType(str, Enum):
    TRANSLATE      = "translate"        # Invoke a translator → push config
    PATH_CHANGE    = "path_change"      # Steer traffic to alternate path
    VPN_REROUTE    = "vpn_reroute"      # Change VPN tunnel routing
    POWER_ADJUST   = "power_adjust"     # Increase/decrease TX power
    RADIO_TUNE     = "radio_tune"       # ACM / modulation adjustment
    QOS_MARK       = "qos_mark"         # Traffic class / DSCP marking
    SLICE_ADJUST   = "slice_adjust"     # Bandwidth slice reallocation
    MONITOR        = "monitor"          # Increase monitoring cadence
    ALERT          = "alert"            # Emit recommendation without config change


from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cer_intent.device.knowledge_base import HardwareKnowledgeBase
    from cer_intent.device.profiles.schema import DeviceProfile

@dataclass
class NetworkContext:
    """Snapshot of the current network state passed to skills."""
    topology: Dict[str, Any]
    telemetry: Dict[str, Any]           # link_id → metrics
    active_intents: List[Dict]          # Current applied intents
    device_states: Dict[str, Any]       # device_id → applied configs
    target_identifier: str
    target_type: str
    # Knowledge interface
    knowledge_base: Optional[HardwareKnowledgeBase] = None

    def get_device_profile(self, node_id: str) -> Optional[DeviceProfile]:
        """Lookup hardware profile for a specific node in this context."""
        if not self.knowledge_base:
            return None
        # Find node in topology
        nodes = self.topology.get("nodes", [])
        node = next((n for n in nodes if n["id"] == node_id), None)
        if not node:
            return None
        return self.knowledge_base.get_profile(node.get("model", "Generic"))


@dataclass
class ConfigAction:
    """
    A single configuration action within a strategy.
    Each action maps to an invocation of a specific translator
    or a direct network operation.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: ActionType = ActionType.TRANSLATE
    # Translator parameters (for TRANSLATE actions)
    intent_type_override: Optional[str] = None   # e.g. "qos", "modulation" — overrides original intent type
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    target_override: Optional[Dict] = None       # Override target (for multi-hop strategies)
    # Metadata
    rationale: str = ""
    execution_order: int = 0
    required: bool = True                        # If False, action is advisory
    estimated_impact: str = ""                   # Human description of expected effect


@dataclass
class Strategy:
    """
    A candidate approach for fulfilling an intent.
    Contains an ordered list of ConfigActions to execute.
    """
    strategy_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    description: str = ""
    skill_source: str = ""          # Which skill generated this strategy
    confidence: float = 0.5         # 0.0–1.0 confidence score
    actions: List[ConfigAction] = field(default_factory=list)
    rationale: str = ""             # Reasoning for choosing this approach
    tradeoffs: str = ""             # Known trade-offs or caveats
    status: StrategyStatus = StrategyStatus.CANDIDATE
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Scoring components
    score_details: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "skill_source": self.skill_source,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "tradeoffs": self.tradeoffs,
            "status": self.status.value,
            "score_details": self.score_details,
            "actions": [
                {
                    "action_id": a.action_id,
                    "action_type": a.action_type.value,
                    "intent_type_override": a.intent_type_override,
                    "parameter_overrides": a.parameter_overrides,
                    "target_override": a.target_override,
                    "rationale": a.rationale,
                    "execution_order": a.execution_order,
                    "estimated_impact": a.estimated_impact,
                }
                for a in sorted(self.actions, key=lambda x: x.execution_order)
            ],
        }


@dataclass
class ArchitectPlan:
    """
    The final output of the Intent Architect Agent.
    Contains the selected strategy and all candidates considered.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    intent_id: str = ""
    intent_summary: str = ""
    selected_strategy: Optional[Strategy] = None
    candidate_strategies: List[Strategy] = field(default_factory=list)
    reasoning_trace: List[str] = field(default_factory=list)  # Step-by-step reasoning log
    network_observations: List[str] = field(default_factory=list)  # What the agent noticed
    conflict_report: Dict[str, Any] = field(default_factory=dict) # Output from simulate API
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "intent_summary": self.intent_summary,
            "selected_strategy": self.selected_strategy.to_dict() if self.selected_strategy else None,
            "candidate_strategies": [s.to_dict() for s in self.candidate_strategies],
            "reasoning_trace": self.reasoning_trace,
            "network_observations": self.network_observations,
            "conflict_report": self.conflict_report,
            "generated_at": self.generated_at.isoformat(),
        }
