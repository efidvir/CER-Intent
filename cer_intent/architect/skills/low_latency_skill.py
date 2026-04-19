"""
Low Latency Skill
=================
Domain expertise for achieving low-latency goals in Ceragon 6G transport networks.

This skill knows that low latency can be achieved through MULTIPLE approaches,
each with different trade-offs:

  1. QoS Prioritization      — Elevate traffic class to EF, set DSCP 46
  2. Traffic Path Change      — Steer traffic through lower-hop or shorter paths
  3. VPN Reroute              — Change VPN tunnel routing to bypass congested nodes
  4. Radio Conditions Tune    — Increase TX power / raise min modulation (fewer retransmits)
  5. ACM Stability            — Raise ACM floor to reduce link adaptation latency jitter
  6. Slice Isolation          — Dedicate a low-latency slice to isolate URLLC traffic

The agent selects among these based on:
  - Current link utilization (high util → path change preferred)
  - Current SNR (low SNR → radio tuning preferred)
  - Latency target (< 1ms → QoS + slice; 1-5ms → QoS; 5-10ms → path/radio)
  - Existing intents (avoid conflicting configs)
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType, StrategyStatus
)
from cer_intent.architect.skills.base_skill import BaseSkill


class LowLatencySkill(BaseSkill):

    @property
    def name(self) -> str:
        return "low_latency"

    @property
    def description(self) -> str:
        return (
            "Knows how to achieve low-latency objectives through QoS prioritization, "
            "traffic path optimization, VPN rerouting, radio condition tuning, "
            "ACM stability adjustments, and slice isolation."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["qos"]

    @property
    def applicable_goals(self) -> List[str]:
        return ["low latency", "latency", "delay", "urllc", "real-time", "jitter", "ms"]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        target_latency = intent.parameters.get("max_latency_ms") or 10.0
        avg_util       = self._avg_metric(context, links, "utilization")
        avg_snr        = self._avg_metric(context, links, "snr_db")
        avg_latency    = self._avg_metric(context, links, "latency_ms")
        avg_loss       = self._avg_metric(context, links, "packet_loss_pct")

        # ── STRATEGY 1: QoS Prioritization ────────────────────────────────────
        # Always a valid first step. Elevate to EF class and set DSCP 46.
        qos_conf = 0.85
        # More confidence when utilization is not saturated (QoS helps when there's headroom)
        if avg_util > 0.90:
            qos_conf = 0.50
        if target_latency < 1.0:
            qos_conf = 0.90  # Almost always needed for sub-ms

        strategies.append(Strategy(
            name="QoS_Prioritization",
            description="Elevate traffic class to EF (Expedited Forwarding) with DSCP 46",
            skill_source=self.name,
            confidence=qos_conf,
            rationale=(
                f"Marking traffic as EF ensures it gets absolute priority in the scheduler. "
                f"Current link utilization is {avg_util:.0%} — "
                + ("sufficient headroom for QoS to be effective." if avg_util < 0.85
                   else "links are near-saturated; QoS alone may not be sufficient.")
            ),
            tradeoffs="Other traffic classes may experience higher latency. No bandwidth guarantee without pairing with slice isolation.",
            actions=[
                ConfigAction(
                    action_type=ActionType.QOS_MARK,
                    intent_type_override="qos",
                    parameter_overrides={
                        "traffic_class": "EF",
                        "dscp_marking": 46,
                        "max_latency_ms": target_latency,
                        "max_jitter_ms": intent.parameters.get("max_jitter_ms", 1.0),
                    },
                    rationale="EF class gives strict priority in the Ceragon QoS scheduler",
                    execution_order=1,
                    estimated_impact=f"Expected latency reduction: 20–40% on congested links",
                ),
            ],
            score_details={"util_penalty": max(0, avg_util - 0.85), "base": qos_conf},
        ))

        # ── STRATEGY 2: Traffic Path Change ───────────────────────────────────
        # If there are alternative paths through the topology, route latency-sensitive
        # traffic via a lower-hop or less-utilized path.
        alt_paths = self._find_alternative_paths(context, links)
        if alt_paths:
            path_conf = 0.75 if avg_util > 0.70 else 0.55
            strategies.append(Strategy(
                name="Traffic_Path_Optimization",
                description="Steer latency-sensitive traffic through lower-utilization alternate paths",
                skill_source=self.name,
                confidence=path_conf,
                rationale=(
                    f"Current path utilization is {avg_util:.0%}. "
                    f"Identified {len(alt_paths)} alternative path(s): "
                    + ", ".join(p["label"] for p in alt_paths[:2]) + ". "
                    "Routing URLLC/latency-sensitive traffic via a less-loaded path reduces queuing delay."
                ),
                tradeoffs="Requires traffic steering / policy routing. May increase path length (hops).",
                actions=[
                    ConfigAction(
                        action_type=ActionType.PATH_CHANGE,
                        intent_type_override="qos",
                        parameter_overrides={
                            "traffic_class": "EF",
                            "dscp_marking": 46,
                            "preferred_path": alt_paths[0]["links"],
                        },
                        rationale=f"Route via {alt_paths[0]['label']} — utilization {alt_paths[0]['util']:.0%}",
                        execution_order=1,
                        estimated_impact="Queuing delay reduction: 30–60% if path is less loaded",
                    ),
                    ConfigAction(
                        action_type=ActionType.QOS_MARK,
                        intent_type_override="qos",
                        parameter_overrides={"traffic_class": "EF", "dscp_marking": 46},
                        rationale="Ensure EF marking is consistent on alternate path",
                        execution_order=2,
                        estimated_impact="Prevents re-queuing on alternate path nodes",
                    ),
                ],
                score_details={"util_benefit": avg_util, "alt_path_count": len(alt_paths)},
            ))

        # ── STRATEGY 3: VPN Tunnel Reroute ────────────────────────────────────
        # For service-layer latency, changing VPN routing can bypass congested or
        # high-latency transport segments.
        vpn_conf = 0.65 if avg_util > 0.75 else 0.40
        strategies.append(Strategy(
            name="VPN_Tunnel_Reroute",
            description="Reroute VPN tunnels to bypass high-latency transport segments",
            skill_source=self.name,
            confidence=vpn_conf,
            rationale=(
                f"Transport-layer latency is {avg_latency:.1f} ms (target: {target_latency} ms). "
                "Changing VPN tunnel endpoints or MPLS paths can route around congested segments "
                "without requiring radio reconfiguration."
            ),
            tradeoffs="Requires VPN/MPLS control-plane changes. May not be applicable if single-path topology.",
            actions=[
                ConfigAction(
                    action_type=ActionType.VPN_REROUTE,
                    intent_type_override="qos",
                    parameter_overrides={
                        "traffic_class": "EF",
                        "vpn_steering": "latency-optimized",
                        "max_latency_ms": target_latency,
                    },
                    rationale="Steer VPN tunnel via shortest-latency transport path",
                    execution_order=1,
                    estimated_impact="End-to-end service latency reduction: 15–45%",
                ),
            ],
            score_details={"transport_latency": avg_latency, "target": target_latency},
        ))

        # ── STRATEGY 4: Radio Condition Tuning ────────────────────────────────
        # Poor radio conditions (low SNR) cause link retransmissions, which add
        # variable latency. Increasing TX power or fixing min modulation reduces jitter.
        if avg_snr < 22.0 or avg_loss > 0.1:
            radio_conf = 0.80  # High confidence when radio is the issue
        else:
            radio_conf = 0.45  # Radio is fine, unlikely to be the latency source

        strategies.append(Strategy(
            name="Radio_Condition_Tuning",
            description="Improve radio link quality to reduce retransmission-induced latency",
            skill_source=self.name,
            confidence=radio_conf,
            rationale=(
                f"Current avg SNR: {avg_snr:.1f} dB, packet loss: {avg_loss:.2f}%. "
                + ("Radio conditions are degraded — retransmissions are likely adding latency jitter. "
                   if avg_snr < 22.0 or avg_loss > 0.1
                   else "Radio conditions are good; this is unlikely the primary latency source. ")
                + "Increasing TX power raises SNR, enabling higher modulation with fewer errors."
            ),
            tradeoffs="TX power increase may cause interference to adjacent links. Subject to regulatory EIRP limits.",
            actions=[
                ConfigAction(
                    action_type=ActionType.POWER_ADJUST,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "tx_power_dbm": None,  # Adapter will determine max allowed
                        "min_modulation": "64QAM",  # Raise floor to reduce adaptation jitter
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale="Higher TX power → higher SNR → stable high modulation → fewer retransmits",
                    execution_order=1,
                    estimated_impact="Latency jitter reduction: 40–70% on SNR-limited links",
                ),
                ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "min_modulation": "64QAM",
                        "acm_enabled": True,
                    },
                    rationale="Raising ACM floor prevents drops to low modulations that increase latency",
                    execution_order=2,
                    required=False,
                    estimated_impact="Stabilizes link at higher throughput efficiency",
                ),
            ],
            score_details={"snr": avg_snr, "loss": avg_loss, "radio_needed": avg_snr < 22.0},
        ))

        # ── STRATEGY 5: ACM Stability (Raise Modulation Floor) ────────────────
        # When ACM frequently drops to low modulations, queuing time increases.
        # Raising the minimum ACM level (accepting occasional link drops) reduces jitter.
        acm_conf = 0.60 if avg_snr > 20.0 else 0.35  # Only works if SNR supports it
        strategies.append(Strategy(
            name="ACM_Stabilization",
            description="Raise minimum ACM modulation floor to reduce link-adaptation latency jitter",
            skill_source=self.name,
            confidence=acm_conf,
            rationale=(
                f"Average SNR {avg_snr:.1f} dB. "
                "Frequent ACM drops to low modulations (QPSK/16QAM) introduce bursts of "
                "increased serialization delay. Raising the ACM floor to 64QAM–256QAM "
                "trades marginal link availability for consistent latency."
            ),
            tradeoffs="Marginally increases link unavailability in adverse conditions. Not suitable for low SNR links.",
            actions=[
                ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "min_modulation": "64QAM" if avg_snr > 20 else "16QAM",
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale="Stable modulation = stable serialization delay = lower latency jitter",
                    execution_order=1,
                    estimated_impact="Jitter reduction: 20–50%",
                ),
            ],
            score_details={"snr_support": avg_snr, "acm_viable": avg_snr > 20},
        ))

        # ── STRATEGY 6: Slice Isolation ────────────────────────────────────────
        # Dedicate a guaranteed bandwidth slice for latency-sensitive traffic,
        # preventing it from competing with bulk traffic.
        if target_latency <= 5.0:  # Only relevant for strict latency targets
            slice_conf = 0.70
            strategies.append(Strategy(
                name="URLLC_Slice_Isolation",
                description="Dedicate a guaranteed-bandwidth URLLC slice to isolate latency-sensitive traffic",
                skill_source=self.name,
                confidence=slice_conf,
                rationale=(
                    f"Target latency {target_latency} ms is strict. Slice isolation prevents "
                    "latency-sensitive traffic from competing with eMBB/best-effort flows in queue. "
                    "Combined with EF marking, provides predictable end-to-end latency bounds."
                ),
                tradeoffs="Reduces available capacity for other traffic. Requires slice-aware transport.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.SLICE_ADJUST,
                        intent_type_override="slice",
                        parameter_overrides={
                            "slice_name": "urllc-latency",
                            "slice_type": "URLLC",
                            "bandwidth_pct": 15,  # Reserve 15% for URLLC
                            "priority_level": 7,
                            "vlan_id": 200,
                        },
                        rationale="Guaranteed URLLC slice prevents queuing behind bulk traffic",
                        execution_order=1,
                        estimated_impact="Latency variance reduction: up to 80% for URLLC flows",
                    ),
                    ConfigAction(
                        action_type=ActionType.QOS_MARK,
                        intent_type_override="qos",
                        parameter_overrides={"traffic_class": "EF", "dscp_marking": 46},
                        rationale="EF marking ensures URLLC traffic uses the reserved slice",
                        execution_order=2,
                        estimated_impact="Strict priority within the slice",
                    ),
                ],
                score_details={"target_strict": target_latency <= 5, "util": avg_util},
            ))

        return strategies

    def _find_alternative_paths(self, context: NetworkContext, target_links: List[dict]) -> List[dict]:
        """
        Heuristic: find topology paths that bypass the target links.
        Returns list of {"label": str, "links": [str], "util": float}.
        """
        all_links = context.topology.get("links", [])
        target_ids = {l["id"] for l in target_links}
        alt_links   = [l for l in all_links if l["id"] not in target_ids and l.get("status") == "active"]

        if not alt_links:
            return []

        # Group into simple alternative path suggestions
        paths = []
        for link in alt_links[:3]:  # Suggest up to 3 alternatives
            tel = context.telemetry.get(link["id"], {})
            util = tel.get("utilization", 0.5)
            paths.append({
                "label": f"{link['src']}→{link['dst']}",
                "links": [link["id"]],
                "util": util,
            })

        # Sort by utilization (prefer less loaded paths)
        return sorted(paths, key=lambda p: p["util"])
