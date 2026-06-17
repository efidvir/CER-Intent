"""
Network Health Optimization Skill
==================================
Holistic skill for diagnosing and optimizing the overall health of the
6G transport network. Triggered by broad operator requests like:
  - "optimize the network"
  - "fix congestion on the backhaul"
  - "reduce packet loss"
  - "improve overall network performance"

This skill differs from targeted skills: it surveys ALL links, identifies
the worst offenders by multiple health indicators, and generates a
prioritized remediation plan spanning multiple corrective actions.

Options understood by this skill:
  1. Congested Link Relief      -- Identify hot-spots (util > 85%) and propose relief
  2. Packet Loss Triage         -- Locate lossy links and recommend ACM floor raise
  3. Degraded Link Recovery     -- Handle links in 'degraded' status with fallback plans
  4. Cross-Link Rebalancing     -- Move load from saturated to underused parallel paths
  5. Proactive Efficiency Tune  -- When network is healthy, optimize for cost/power
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# Thresholds
HIGH_UTIL_THRESHOLD  = 0.85   # 85% utilization = congested
LOW_SNR_THRESHOLD    = 18.0   # dB -- below this = link health risk
HIGH_LOSS_THRESHOLD  = 0.5    # % packet loss -- above this = critical
DEGRADED_STATUS      = "degraded"


class NetworkHealthSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "network_health"

    @property
    def description(self) -> str:
        return (
            "Holistically diagnoses and optimizes the entire transport network. "
            "Identifies congested, lossy, and degraded links across all layers "
            "(aggregation ring, midhaul hubs, fronthaul tails) and generates a "
            "prioritized multi-action remediation plan."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["capacity", "qos", "resilience"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "optimize", "health", "network performance", "overall", "fix", "improve",
            "congestion", "packet loss", "degraded", "bottleneck", "network-wide",
            "global", "all links", "diagnose",
        ]

    def is_applicable(self, intent, context) -> bool:
        """Triggered by holistic optimization requests, not single pin-point ones."""
        raw = (intent.raw_input or "").lower()
        broad_terms = ["optimize", "fix", "improve", "overall", "network", "global", "all", "health"]
        if sum(1 for t in broad_terms if t in raw) >= 2:
            return True
        return super().is_applicable(intent, context)

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        all_links = context.topology.get("links", [])

        # Health Survey
        congested_links = []
        lossy_links     = []
        degraded_links  = []
        low_snr_links   = []

        for link in all_links:
            lid   = link["id"]
            telem = context.telemetry.get(lid, {})
            util   = telem.get("utilization", 0.0)
            loss   = telem.get("packet_loss_pct", 0.0)
            snr    = telem.get("snr_db", 30.0)
            status = link.get("status", "active")

            if util > HIGH_UTIL_THRESHOLD:
                congested_links.append((lid, util))
            if loss > HIGH_LOSS_THRESHOLD:
                lossy_links.append((lid, loss))
            if status == DEGRADED_STATUS:
                degraded_links.append(lid)
            if snr < LOW_SNR_THRESHOLD:
                low_snr_links.append((lid, snr))

        congested_links.sort(key=lambda x: x[1], reverse=True)
        lossy_links.sort(key=lambda x: x[1], reverse=True)
        low_snr_links.sort(key=lambda x: x[1])

        # STRATEGY 1: Congestion Relief
        if congested_links:
            top_n   = congested_links[:3]
            top_ids = [l[0] for l in top_n]
            avg_util = sum(l[1] for l in top_n) / len(top_n)
            actions = []
            for i, (lid, util) in enumerate(top_n):
                actions.append(ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="capacity",
                    parameter_overrides={
                        "target_link": lid,
                        "min_throughput_gbps": 5.0,
                        "channel_bandwidth_mhz": 112,
                        "mrmc_script_id": 50,
                    },
                    rationale=f"Link {lid} is {util*100:.0f}% utilized -- expand MRMC profile",
                    execution_order=i + 1,
                    estimated_impact=f"Expand capacity headroom on {lid}",
                ))
            strategies.append(Strategy(
                name="Congestion_Relief_Multi_Link",
                description=f"Expand capacity on {len(top_n)} congested links ({', '.join(top_ids)})",
                skill_source=self.name,
                confidence=0.88,
                rationale=(
                    f"Network survey found {len(congested_links)} congested links. "
                    f"Top offenders: {[f'{l}@{u*100:.0f}%' for l, u in top_n]}. "
                    "Expanding MRMC profiles on the worst links provides the fastest relief."
                ),
                tradeoffs="Wider channels require spectrum coordination. SNR must support 2048QAM.",
                actions=actions,
                score_details={"congested_count": len(congested_links), "avg_util": avg_util},
            ))

        # STRATEGY 2: Packet Loss Triage
        if lossy_links:
            top_lossy = lossy_links[:3]
            actions = []
            for i, (lid, loss) in enumerate(top_lossy):
                snr = context.telemetry.get(lid, {}).get("snr_db", 20.0)
                safe_floor = "64QAM" if snr > 20 else "16QAM" if snr > 14 else "QPSK"
                actions.append(ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "target_link": lid,
                        "min_modulation": safe_floor,
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale=f"Link {lid} has {loss:.2f}% packet loss -- raise ACM floor to {safe_floor}",
                    execution_order=i + 1,
                    estimated_impact=f"Stabilize link by anchoring ACM floor at {safe_floor}",
                ))
            strategies.append(Strategy(
                name="Packet_Loss_Triage",
                description=f"Raise ACM floors on {len(top_lossy)} lossy links to stabilize throughput",
                skill_source=self.name,
                confidence=0.82,
                rationale=(
                    f"{len(lossy_links)} links exceed {HIGH_LOSS_THRESHOLD}% packet loss. "
                    "Raising ACM floor prevents the radio from attempting modulations it cannot sustain, "
                    "eliminating burst packet loss during fade events."
                ),
                tradeoffs="Higher ACM floor reduces peak throughput headroom during good propagation.",
                actions=actions,
                score_details={"lossy_count": len(lossy_links)},
            ))

        # STRATEGY 3: Degraded Link Recovery
        if degraded_links:
            strategies.append(Strategy(
                name="Degraded_Link_Recovery",
                description=f"Escalate monitoring and NOC alert for {len(degraded_links)} degraded links",
                skill_source=self.name,
                confidence=0.75,
                rationale=(
                    f"{len(degraded_links)} links are in 'degraded' state: {degraded_links[:5]}. "
                    "Increasing telemetry cadence and alerting NOC enables faster corrective action."
                ),
                tradeoffs="Monitoring escalation increases control-plane overhead slightly.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.MONITOR,
                        intent_type_override="resilience",
                        parameter_overrides={
                            "target_links": degraded_links[:5],
                            "monitoring_cadence_sec": 15,
                        },
                        rationale="Escalate polling on degraded links",
                        execution_order=1,
                        estimated_impact="Fault detection latency reduced to 15s",
                    ),
                    ConfigAction(
                        action_type=ActionType.ALERT,
                        intent_type_override="resilience",
                        parameter_overrides={
                            "alert_type": "degraded_links_detected",
                            "links": degraded_links,
                            "recommendation": "Activate 1+1 HSB where supported. Review antenna alignment.",
                        },
                        rationale="Degraded links require field investigation",
                        execution_order=2,
                        required=False,
                        estimated_impact="Advisory -- requires NOC/field team coordination",
                    ),
                ],
                score_details={"degraded_count": len(degraded_links)},
            ))

        # STRATEGY 4: Proactive Tune (healthy network)
        if not congested_links and not lossy_links and not degraded_links:
            strategies.append(Strategy(
                name="Proactive_Efficiency_Tune",
                description="Network is healthy -- apply proactive efficiency tuning across all links",
                skill_source=self.name,
                confidence=0.60,
                rationale=(
                    "No congestion, packet loss, or degraded links detected. "
                    "Proactive tuning can improve spectral efficiency and reduce operating costs "
                    "without impacting service quality."
                ),
                tradeoffs="Efficiency optimizations may slightly reduce peak burst capacity.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.RADIO_TUNE,
                        intent_type_override="modulation",
                        parameter_overrides={
                            "acm_enabled": True,
                            "atpc_enabled": True,
                            "min_modulation": "64QAM",
                            "max_modulation": "2048QAM",
                        },
                        rationale="Enable ATPC and ACM on all links for dynamic efficiency",
                        execution_order=1,
                        estimated_impact="5-15% operating power reduction across the network",
                    ),
                ],
            ))

        return strategies
