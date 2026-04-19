"""
High Capacity Skill
===================
Domain expertise for maximizing throughput on Ceragon 6G transport links.

Options understood by this skill:
  1. MRMC Script Upgrade     — Select higher-capacity MRMC profile (wider BW, higher mod)
  2. Channel BW Expansion    — Increase channel bandwidth (28→56→112 MHz)
  3. TX Power Increase       — Boost SNR to support higher modulation
  4. Spatial Multiplexing    — Enable XPIC / dual-polarization if hardware supports it
  5. Traffic Load Balancing  — Distribute capacity across parallel links
  6. ACM Ceiling Raise       — Enable 2048QAM to maximise spectral efficiency
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# MRMC profile table: (min_gbps, script_id, bw_mhz, min_mod, max_mod)
MRMC_PROFILES = [
    (0.5,  10, 28,  "QPSK",   "256QAM"),
    (1.0,  20, 28,  "16QAM",  "512QAM"),
    (2.5,  30, 56,  "16QAM",  "1024QAM"),
    (5.0,  40, 56,  "64QAM",  "2048QAM"),
    (7.5,  50, 112, "64QAM",  "2048QAM"),
    (10.0, 60, 112, "256QAM", "2048QAM"),
]


class HighCapacitySkill(BaseSkill):

    @property
    def name(self) -> str:
        return "high_capacity"

    @property
    def description(self) -> str:
        return (
            "Knows how to maximize link throughput via MRMC script selection, "
            "channel bandwidth expansion, TX power optimization, XPIC/dual-pol, "
            "load balancing across parallel links, and ACM ceiling raise."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["capacity", "modulation"]

    @property
    def applicable_goals(self) -> List[str]:
        return ["capacity", "throughput", "gbps", "bandwidth", "speed", "backhaul", "high capacity"]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        target_gbps = intent.parameters.get("min_throughput_gbps", 1.0)
        avg_util    = self._avg_metric(context, links, "utilization")
        avg_snr     = self._avg_metric(context, links, "snr_db")
        current_mod = context.telemetry.get(
            links[0]["id"] if links else "", {}
        ).get("current_modulation", "256QAM")

        # Select appropriate MRMC profile
        profile = next((p for p in MRMC_PROFILES if p[0] >= target_gbps), MRMC_PROFILES[-1])

        # ── STRATEGY 1: MRMC Script Upgrade ───────────────────────────────────
        strategies.append(Strategy(
            name="MRMC_Script_Upgrade",
            description=f"Select MRMC script #{profile[1]} ({profile[2]} MHz, {profile[3]}–{profile[4]}) for ≥{target_gbps} Gbps",
            skill_source=self.name,
            confidence=0.90,
            rationale=(
                f"Target: {target_gbps} Gbps. MRMC script #{profile[1]} with {profile[2]} MHz "
                f"channel and {profile[3]}–{profile[4]} ACM range is the standard approach for "
                f"this capacity tier on Ceragon IP-50FX/IP-20N hardware."
            ),
            tradeoffs="Wider channel BW requires spectrum coordination. Higher SNR needed for top modulation.",
            actions=[
                ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="capacity",
                    parameter_overrides={
                        "min_throughput_gbps": target_gbps,
                        "channel_bandwidth_mhz": profile[2],
                        "mrmc_script_id": profile[1],
                    },
                    rationale=f"MRMC script #{profile[1]} is the optimal profile for {target_gbps} Gbps",
                    execution_order=1,
                    estimated_impact=f"Enables up to {target_gbps * 1.2:.1f} Gbps peak throughput",
                ),
            ],
        ))

        # ── STRATEGY 2: TX Power + ACM Ceiling Raise ──────────────────────────
        if avg_snr < 28.0:  # SNR-limited; power boost helps
            pwr_conf = 0.75
        else:
            pwr_conf = 0.50  # SNR is fine; MRMC upgrade is better

        strategies.append(Strategy(
            name="TX_Power_And_ACM_Raise",
            description="Boost TX power to support 2048QAM and maximize spectral efficiency",
            skill_source=self.name,
            confidence=pwr_conf,
            rationale=(
                f"Current SNR: {avg_snr:.1f} dB. Current modulation: {current_mod}. "
                + (f"SNR headroom is insufficient for 2048QAM (needs ~32 dB). "
                   f"TX power boost could add 3–6 dB SNR margin, enabling 2048QAM."
                   if avg_snr < 28.0
                   else f"SNR is adequate. ACM ceiling raise to 2048QAM directly.")
            ),
            tradeoffs="TX power increase subject to EIRP regulatory limits. May cause interference.",
            actions=[
                ConfigAction(
                    action_type=ActionType.POWER_ADJUST,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "min_modulation": profile[3],
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale="2048QAM delivers maximum spectral efficiency (~11 bits/s/Hz)",
                    execution_order=1,
                    estimated_impact="Up to 30% throughput improvement over 1024QAM",
                ),
                ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="capacity",
                    parameter_overrides={
                        "channel_bandwidth_mhz": profile[2],
                        "min_throughput_gbps": target_gbps,
                    },
                    rationale="Set channel BW to match the MRMC script",
                    execution_order=2,
                    estimated_impact="Full channel utilization",
                ),
            ],
            score_details={"snr": avg_snr, "current_mod": current_mod},
        ))

        # ── STRATEGY 3: Load Balancing Across Parallel Links ──────────────────
        parallel = [l for l in context.topology.get("links", [])
                    if l["id"] != (links[0]["id"] if links else "")
                    and l.get("status") == "active"
                    and (l["src"] in {lk["src"] for lk in links} or
                         l["dst"] in {lk["dst"] for lk in links})]

        if parallel:
            strategies.append(Strategy(
                name="Inter_Link_Load_Balancing",
                description="Distribute traffic across parallel links to aggregate effective capacity",
                skill_source=self.name,
                confidence=0.65,
                rationale=(
                    f"{len(parallel)} parallel link(s) found sharing common endpoints. "
                    "Distributing traffic via ECMP or weighted load balancing effectively "
                    f"aggregates capacity without requiring radio reconfiguration."
                ),
                tradeoffs="Requires LAG or traffic engineering support. May cause out-of-order packets.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.PATH_CHANGE,
                        intent_type_override="capacity",
                        parameter_overrides={
                            "load_balance_mode": "ECMP",
                            "parallel_links": [l["id"] for l in parallel[:2]],
                        },
                        rationale="ECMP distributes load and aggregates effective capacity",
                        execution_order=1,
                        estimated_impact=f"Effective capacity: {len(parallel)+1}x single link capacity",
                        required=False,
                    ),
                ],
                score_details={"parallel_links": len(parallel)},
            ))

        return strategies
