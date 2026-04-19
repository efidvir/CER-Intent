"""
Traffic Engineering Skill
=========================
Domain expertise for traffic path optimization and VPN management
in 6G transport networks.

Options understood by this skill:
  1. Traffic Path Steering     — Route flows via optimal transport path
  2. VPN Tunnel Reroute        — Move VPN tunnels to lower-latency segments
  3. Load Splitting            — Multi-path load balancing (ECMP, weighted ECMP)
  4. Failover Pre-positioning  — Pre-configure standby paths for instant failover
  5. Congestion-Aware Reroute  — React to utilization thresholds automatically
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill


class TrafficEngineeringSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "traffic_engineering"

    @property
    def description(self) -> str:
        return (
            "Knows how to optimize traffic flows through path steering, "
            "VPN rerouting, ECMP load balancing, and congestion-aware "
            "dynamic rerouting in Ceragon 6G transport networks."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["qos", "capacity", "slice"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "path", "route", "vpn", "traffic", "congestion", "reroute",
            "load balance", "failover", "steering", "engineering",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)
        all_links = context.topology.get("links", [])

        avg_util  = self._avg_metric(context, links, "utilization")
        avg_snr   = self._avg_metric(context, links, "snr_db")
        avg_lat   = self._avg_metric(context, links, "latency_ms")
        target_id = context.target_identifier

        # Find alternative paths not overlapping with current target
        target_link_ids = {l["id"] for l in links}
        alt_links = [l for l in all_links
                     if l["id"] not in target_link_ids and l.get("status") == "active"]
        low_util_alts = [l for l in alt_links
                         if context.telemetry.get(l["id"], {}).get("utilization", 1.0) < 0.60]

        # ── STRATEGY 1: Congestion-Aware Traffic Steering ─────────────────────
        steer_conf = min(0.85, 0.5 + avg_util * 0.5) if avg_util > 0.65 else 0.40
        strategies.append(Strategy(
            name="Congestion_Aware_Traffic_Steering",
            description="Dynamically steer high-priority traffic away from congested paths",
            skill_source=self.name,
            confidence=steer_conf,
            rationale=(
                f"Target path utilization: {avg_util:.0%}. "
                + (f"{len(low_util_alts)} lower-utilization alternative link(s) available. "
                   if low_util_alts else "Limited alternative paths detected. ")
                + "Policy-based traffic steering redistributes load to balance utilization."
            ),
            tradeoffs="Requires policy routing support. May introduce asymmetric paths.",
            actions=[
                ConfigAction(
                    action_type=ActionType.PATH_CHANGE,
                    intent_type_override="qos",
                    parameter_overrides={
                        "traffic_class": intent.parameters.get("traffic_class", "AF3"),
                        "preferred_path": [l["id"] for l in low_util_alts[:2]],
                        "steering_mode": "policy-based",
                    },
                    rationale=f"Redirect to {len(low_util_alts)} lower-load path(s)",
                    execution_order=1,
                    estimated_impact=f"Utilization target: < 70% after steering",
                ),
            ],
            score_details={"util": avg_util, "alt_paths": len(low_util_alts)},
        ))

        # ── STRATEGY 2: VPN Tunnel Reroute ────────────────────────────────────
        # Select the lowest-latency alternative link for VPN tunnel re-anchoring
        rated_alts = sorted(
            alt_links,
            key=lambda l: context.telemetry.get(l["id"], {}).get("latency_ms", 999),
        )
        if rated_alts:
            best_alt = rated_alts[0]
            best_lat = context.telemetry.get(best_alt["id"], {}).get("latency_ms", avg_lat)
            vpn_conf = 0.75 if best_lat < avg_lat else 0.45

            strategies.append(Strategy(
                name="VPN_Tunnel_Reroute",
                description=f"Reroute VPN tunnels via {best_alt['src']}→{best_alt['dst']} ({best_lat:.1f} ms)",
                skill_source=self.name,
                confidence=vpn_conf,
                rationale=(
                    f"Current path latency: {avg_lat:.1f} ms. "
                    f"Best alternative path ({best_alt['id']}): {best_lat:.1f} ms. "
                    + (f"Rerouting saves {avg_lat - best_lat:.1f} ms end-to-end."
                       if best_lat < avg_lat
                       else "Alternative path latency is similar to current.")
                ),
                tradeoffs="VPN tunnel reroute requires control-plane convergence time (~seconds). Temporary packet loss during switchover.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.VPN_REROUTE,
                        intent_type_override="qos",
                        parameter_overrides={
                            "vpn_tunnel_target": best_alt["id"],
                            "vpn_steering": "latency-optimized",
                            "switchover_mode": "graceful",
                        },
                        rationale=f"VPN re-anchored to {best_alt['id']} with {best_lat:.1f} ms latency",
                        execution_order=1,
                        estimated_impact=f"Latency improvement: {max(0, avg_lat - best_lat):.1f} ms",
                    ),
                ],
                score_details={"current_lat": avg_lat, "best_alt_lat": best_lat},
            ))

        # ── STRATEGY 3: ECMP Load Splitting ───────────────────────────────────
        ecmp_links = [l for l in all_links if l.get("status") == "active"
                      and (l["src"] in {lk["src"] for lk in links} or
                           l["dst"] in {lk["dst"] for lk in links})]
        if len(ecmp_links) >= 2:
            strategies.append(Strategy(
                name="ECMP_Load_Splitting",
                description=f"Equal-cost multi-path load balancing across {len(ecmp_links)} links",
                skill_source=self.name,
                confidence=0.60,
                rationale=(
                    f"{len(ecmp_links)} links share common endpoints. "
                    "ECMP distributes traffic flows across all links, effectively "
                    "aggregating bandwidth and reducing per-link utilization."
                ),
                tradeoffs="ECMP may cause out-of-order packets for non-flow-hashed implementations.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.PATH_CHANGE,
                        intent_type_override="capacity",
                        parameter_overrides={
                            "load_balance_mode": "ECMP",
                            "ecmp_links": [l["id"] for l in ecmp_links],
                            "hash_mode": "per-flow",
                        },
                        rationale="Per-flow hashing prevents reordering while distributing load",
                        execution_order=1,
                        estimated_impact=f"Effective capacity: {len(ecmp_links)}x single-link bandwidth",
                    ),
                ],
                score_details={"ecmp_links": len(ecmp_links)},
            ))

        return strategies


class ResilienceSkill(BaseSkill):
    """
    Domain expertise for link protection and redundancy in Ceragon transport.

    Options:
      1. 1+1 HSB Protection      — Immediate hitless switchover on failure
      2. Space Diversity (SD)    — Dual antenna, same frequency, combines signals
      3. Frequency Diversity (FD)— Two frequencies, provides frequency protection
      4. Ring Protection         — Leverage topology ring for path redundancy
      5. Pre-configured Failover — Provision backup paths ahead of time
    """

    @property
    def name(self) -> str:
        return "resilience"

    @property
    def description(self) -> str:
        return (
            "Knows how to improve transport link resilience via hardware "
            "protection schemes (HSB, SD, FD) and topology-level path redundancy."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["resilience", "qos"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "protection", "resilience", "redundancy", "hsb", "failover",
            "standby", "diversity", "availability", "sla",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        avg_snr  = self._avg_metric(context, links, "snr_db")
        avg_loss = self._avg_metric(context, links, "packet_loss_pct")

        # ── STRATEGY 1: 1+1 HSB (default recommended) ────────────────────────
        strategies.append(Strategy(
            name="1+1_HSB_Protection",
            description="1+1 Hot Standby — hitless switchover on radio or equipment failure",
            skill_source=self.name,
            confidence=0.90,
            rationale=(
                "HSB provides immediate (< 50ms) hitless protection switching. "
                "The working path carries all traffic; standby is pre-synchronized. "
                "On failure, automatic reversion after WTR timer. "
                "Best suited for mission-critical transport links."
            ),
            tradeoffs="Requires a second radio unit (2x hardware cost). Does not help against common-mode failures (same tower/path).",
            actions=[
                ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="resilience",
                    parameter_overrides={
                        "protection_mode": "1+1-hsb",
                        "revert_mode": "revertive",
                        "wtr_seconds": intent.parameters.get("wtr_seconds", 300),
                        "holdoff_ms": 0,
                    },
                    rationale="HSB is the gold standard for Ceragon link protection",
                    execution_order=1,
                    estimated_impact="Link availability: > 99.999% (5 nines)",
                ),
            ],
        ))

        # ── STRATEGY 2: Space Diversity ────────────────────────────────────────
        if avg_snr < 24.0:  # SD is most beneficial on SNR-marginal links
            sd_conf = 0.75
        else:
            sd_conf = 0.55

        strategies.append(Strategy(
            name="Space_Diversity",
            description="Dual receive antennas with MRC combining to mitigate multipath fading",
            skill_source=self.name,
            confidence=sd_conf,
            rationale=(
                f"Current SNR: {avg_snr:.1f} dB. "
                + ("SNR is marginal — space diversity provides significant fading protection. "
                   if avg_snr < 24.0 else
                   "SNR is sufficient but SD adds protection against multipath fading events. ")
                + "SD combines signals from two spatially-separated receive antennas using MRC."
            ),
            tradeoffs="Requires second antenna mount at receiver. No protection against equipment failure.",
            actions=[
                ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="resilience",
                    parameter_overrides={
                        "protection_mode": "space-diversity",
                        "revert_mode": "non-revertive",
                        "wtr_seconds": 0,
                        "holdoff_ms": 0,
                    },
                    rationale="SD improves fade margin without requiring full radio redundancy",
                    execution_order=1,
                    estimated_impact="Fade margin improvement: 6–12 dB effective gain",
                ),
            ],
            score_details={"snr": avg_snr},
        ))

        # ── STRATEGY 3: Topology Ring Redundancy ──────────────────────────────
        all_links = context.topology.get("links", [])
        ring_eligible = len([l for l in all_links if l.get("status") == "active"]) >= 4
        if ring_eligible:
            strategies.append(Strategy(
                name="Topology_Ring_Protection",
                description="Leverage existing ring topology for path-level redundancy (no extra HW)",
                skill_source=self.name,
                confidence=0.65,
                rationale=(
                    f"{len(all_links)} active links detected in topology. "
                    "Ring topology allows protection via alternate path rerouting "
                    "without requiring additional radio hardware — cost-efficient resilience."
                ),
                tradeoffs="Longer protection path (multiple hops) may increase latency during failure. Convergence time: ~1s.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.PATH_CHANGE,
                        intent_type_override="resilience",
                        parameter_overrides={
                            "protection_mode": "ring",
                            "protection_path": "auto-detect",
                        },
                        rationale="Ring path provides path-level redundancy without additional hardware",
                        execution_order=1,
                        required=False,
                        estimated_impact="Link availability: > 99.99% via path switching",
                    ),
                ],
                score_details={"active_links": len(all_links)},
            ))

        return strategies
