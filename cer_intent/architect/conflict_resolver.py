"""
Conflict Resolver Service (Simulated API)
=========================================
Checks Architect Plans against active intents and hardware boundaries.
Acts as a mock representation of an external carrier-grade resource manager.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Any, Optional

from cer_intent.architect.strategy import ArchitectPlan, NetworkContext, ConflictLevel

logger = logging.getLogger(__name__)

class ConflictResolver:
    """
    Evaluates proposed architectural strategies for potential resource
    contention or boundary violations.
    """

    def resolve_conflicts(self, plan: ArchitectPlan, context: NetworkContext) -> Dict[str, Any]:
        """
        Simulates an external API call to check the plan.
        Returns a ConflictReport dictionary.
        """
        logger.info(f"Invoking Conflict Resolution API for plan {plan.plan_id}...")
        
        # Simulate API latency
        time.sleep(0.1) 
        
        selected = plan.selected_strategy
        if not selected:
            return {"level": ConflictLevel.NONE, "conflicts": [], "message": "No strategy selected; skipping check."}

        conflicts = []
        overall_level = ConflictLevel.NONE

        # ── 1. Check against Active Intents ───────────────────────────────────
        # In a real system, we'd query a database of live configurations.
        # Here we check context.active_intents.
        for existing in context.active_intents:
            if existing.get("intent_id") == plan.intent_id:
                continue # Ignore self
            
            # Simple overlap check: same target + same action types
            for action in selected.actions:
                if self._is_resource_overlap(action, existing):
                    conflicts.append({
                        "id": existing.get("intent_id"),
                        "type": "RESOURCE_CONTENTION",
                        "description": f"Target {context.target_identifier} is already managed by Intent {existing.get('intent_id')[:8]}",
                        "severity": "WARNING"
                    })
                    overall_level = ConflictLevel.WARNING

        # ── 2. Check Decision Boundaries (Safety Gate) ───────────────────────
        for action in selected.actions:
            # Check TX Power bounds
            if "tx_power_dbm" in action.parameter_overrides:
                pwr = action.parameter_overrides["tx_power_dbm"]
                node_id = action.target_override.get("identifier") if action.target_override else context.target_identifier
                
                # Mock boundary check: Node A cannot handle > 25dBm in current weather
                if node_id == "node-A" and pwr > 25:
                    conflicts.append({
                        "type": "BOUNDARY_VIOLATION",
                        "description": f"TX Power {pwr}dBm exceeds safe operating limit (25dBm) for {node_id} under current conditions.",
                        "severity": "CRITICAL"
                    })
                    overall_level = ConflictLevel.CRITICAL

        # ── 3. Resolve / Finalize ─────────────────────────────────────────────
        report = {
            "level": overall_level,
            "conflicts": conflicts,
            "api_endpoint": "http://internal-nrm/api/v1/verify",
            "timestamp": time.time(),
            "passed": overall_level != ConflictLevel.CRITICAL,
            "message": "Plan verified with warnings" if conflicts else "No conflicts detected."
        }
        
        if overall_level == ConflictLevel.CRITICAL:
            report["message"] = "Plan blocked by Conflict Resolution API due to safety violation."

        return report

    def _is_resource_overlap(self, action: Any, existing_intent: Dict) -> bool:
        """Heuristic check for resource overlap."""
        # This is a simplification for the PoC
        itype = existing_intent.get("intent_type")
        if not itype: return False
        
        # If both are modulation-related on the same target
        if action.action_type.value in ("radio_tune", "power_adjust") and itype == "modulation":
            return True
        # If both are QoS-related
        if action.action_type.value == "qos_mark" and itype == "qos":
            return True
            
        return False
