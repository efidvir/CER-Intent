"""
Energy Optimization Skill
==========================
Domain expertise for reducing power consumption in 6G transport networks.

As 6G operators face significant opex pressure from energy costs, and as
sustainability mandates grow, this skill autonomously identifies and applies
power-reduction configurations without compromising service quality.

Triggered by requests like:
  - "reduce power consumption overnight"
  - "enable sleep mode on low-traffic links"
  - "optimize energy usage on the backhaul"
  - "reduce opex by saving power"
  - "green network mode during off-peak"

Options understood by this skill:
  1. Deep Sleep Scheduling      -- Disable transmit on idle links during off-peak windows
  2. ATPC Power Backoff         -- Reduce TX power when SNR margin is comfortable
  3. ACM Floor Relaxation       -- Allow modulation to dip lower during low-traffic periods
  4. Carrier Shutdown (MIMO)    -- Disable one polarization on dual-pol links during off-peak
  5. Traffic-Aware Scaling      -- Dynamically correlate power levels with utilization
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# Thresholds
LOW_UTIL_THRESHOLD  = 0.30   # Below 30% -> eligible for energy reduction
SNR_SURPLUS_NEEDED  = 8.0    # dB of SNR headroom needed before power can be reduced
IDLE_UTIL_THRESHOLD = 0.05   # Below 5% -> eligible for deep sleep


class EnergyOptimizationSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "energy_optimization"

    @property
    def description(self) -> str:
        return (
            "Reduces 6G transport network energy consumption by scheduling deep sleep "
            "on idle links, applying ATPC power backoff on SNR-surplus links, and "
            "enabling adaptive carrier shutdown on underutilized dual-pol equipment. "
            "Designed to lower opex without compromising SLA commitments."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["energy", "capacity", "qos"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "energy", "power", "sleep", "opex", "green", "efficiency",
            "carbon", "sustainability", "idle", "off-peak", "overnight",
            "low traffic", "save power", "reduce consumption",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        # Categorize links by utilization and SNR headroom
        idle_links        = []
        low_util_links    = []
        snr_surplus_links = []

        for link in links:
            lid   = link["id"]
            telem = context.telemetry.get(lid, {})
            util  = telem.get("utilization", 0.5)
            snr   = telem.get("snr_db", 25.0)
            # Assume a "target SNR" based on current modulation
            current_mod = telem.get("current_modulation", "256QAM")
            snr_thresholds = {
                "2048QAM": 32, "1024QAM": 29, "512QAM": 26, "256QAM": 23,
                "128QAM": 20, "64QAM": 17, "QPSK": 0
            }
            target_snr = snr_thresholds.get(current_mod, 23)
            snr_surplus = snr - target_snr

            if util < IDLE_UTIL_THRESHOLD:
                idle_links.append((lid, util, snr_surplus))
            elif util < LOW_UTIL_THRESHOLD:
                low_util_links.append((lid, util, snr_surplus))
            if snr_surplus > SNR_SURPLUS_NEEDED:
                snr_surplus_links.append((lid, snr_surplus, util))

        # STRATEGY 1: Deep Sleep Scheduling on Idle Links
        if idle_links:
            idle_ids = [l[0] for l in idle_links]
            strategies.append(Strategy(
                name="Deep_Sleep_Idle_Links",
                description=(
                    f"Schedule deep sleep (TX shutdown) on {len(idle_links)} idle links "
                    f"({', '.join(idle_ids[:3])}{'...' if len(idle_ids) > 3 else ''})"
                ),
                skill_source=self.name,
                confidence=0.85,
                rationale=(
                    f"{len(idle_links)} links are below {IDLE_UTIL_THRESHOLD*100:.0f}% utilization. "
                    "Shutting down the TX chain on idle links (while keeping control plane active) "
                    "is the single highest-impact energy saving measure. "
                    "Links remain on standby and can be reactivated within seconds on traffic demand. "
                    "This is standard practice for Ceragon IP-20N/IP-20C in low-traffic overnight windows."
                ),
                tradeoffs=(
                    "Sleep mode increases reactivation latency by 2-5 seconds. "
                    "Not suitable for links carrying active traffic or protection paths."
                ),
                actions=[
                    ConfigAction(
                        action_type=ActionType.TRANSLATE,
                        intent_type_override="energy",
                        parameter_overrides={
                            "sleep_mode": "deep_sleep",
                            "target_links": idle_ids,
                            "activation_threshold_mbps": 10,  # Wake on 10Mbps demand
                            "schedule": intent.parameters.get("schedule", "22:00-06:00"),
                        },
                        rationale=f"Deep sleep on {len(idle_ids)} idle links saves ~80% TX power",
                        execution_order=1,
                        estimated_impact=f"~80% power saving on {len(idle_ids)} links during sleep window",
                    ),
                ],
                score_details={"idle_link_count": len(idle_links)},
            ))

        # STRATEGY 2: ATPC Power Backoff on SNR-Surplus Links
        if snr_surplus_links:
            top_surplus = sorted(snr_surplus_links, key=lambda x: x[1], reverse=True)[:5]
            actions = []
            for i, (lid, surplus, util) in enumerate(top_surplus):
                backoff_db = min(surplus - 5.0, 10.0)  # Leave 5dB safety margin
                actions.append(ConfigAction(
                    action_type=ActionType.POWER_ADJUST,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "target_link": lid,
                        "atpc_enabled": True,
                        "atpc_power_reduction_db": backoff_db,
                        "atpc_target_snr_db": 25.0,
                    },
                    rationale=(
                        f"Link {lid} has {surplus:.1f}dB SNR surplus. "
                        f"TX power can be reduced by {backoff_db:.1f}dB while maintaining quality."
                    ),
                    execution_order=i + 1,
                    estimated_impact=f"{backoff_db:.0f}dB TX power reduction on {lid}",
                ))

            avg_surplus = sum(l[1] for l in top_surplus) / len(top_surplus)
            strategies.append(Strategy(
                name="ATPC_Power_Backoff",
                description=(
                    f"Reduce TX power on {len(top_surplus)} links with surplus SNR "
                    f"(avg {avg_surplus:.1f}dB headroom)"
                ),
                skill_source=self.name,
                confidence=0.80,
                rationale=(
                    f"{len(snr_surplus_links)} links have more than {SNR_SURPLUS_NEEDED}dB SNR headroom. "
                    "ATPC (Automatic TX Power Control) allows dynamic power reduction while "
                    "maintaining link quality within the acceptable SNR margin. "
                    "Each 3dB of TX power reduction typically halves amplifier power consumption."
                ),
                tradeoffs=(
                    "Reduced TX power decreases fade margin. Must maintain minimum 5dB safety margin. "
                    "ATPC should be set to automatically restore power if SNR degrades."
                ),
                actions=actions,
                score_details={"avg_snr_surplus_db": avg_surplus, "links": len(snr_surplus_links)},
            ))

        # STRATEGY 3: Carrier Shutdown on Dual-Pol Links During Off-Peak
        dual_pol_low = [(lid, util, surplus) for lid, surplus, util in snr_surplus_links
                        if util < LOW_UTIL_THRESHOLD]
        if dual_pol_low:
            strategies.append(Strategy(
                name="MIMO_Carrier_Shutdown",
                description=(
                    f"Disable one polarization carrier on {len(dual_pol_low)} low-utilization "
                    "dual-pol links during off-peak windows"
                ),
                skill_source=self.name,
                confidence=0.65,
                rationale=(
                    f"{len(dual_pol_low)} links have both low utilization (<{LOW_UTIL_THRESHOLD*100:.0f}%) "
                    "and SNR surplus. On dual-polarization (XPIC) capable hardware (IP-50FX), "
                    "one carrier can be shut down during off-peak, halving the radio power consumption "
                    "while maintaining the minimum required throughput on the remaining carrier."
                ),
                tradeoffs=(
                    "Requires hardware support for hitless carrier shutdown (IP-50FX feature). "
                    "Peak capacity is halved during carrier-off period. "
                    "Not applicable if link is in active protection mode."
                ),
                actions=[
                    ConfigAction(
                        action_type=ActionType.TRANSLATE,
                        intent_type_override="energy",
                        parameter_overrides={
                            "mimo_mode": "single_carrier",
                            "target_links": [l[0] for l in dual_pol_low[:3]],
                            "schedule": intent.parameters.get("schedule", "22:00-06:00"),
                        },
                        rationale="Single-carrier mode saves ~50% radio power on dual-pol links",
                        execution_order=1,
                        required=False,
                        estimated_impact="~50% power saving per radio during off-peak window",
                    ),
                ],
            ))

        # Fallback if no links qualify for energy saving
        if not strategies:
            strategies.append(Strategy(
                name="Network_Already_Efficient",
                description="Network energy profile appears already optimized",
                skill_source=self.name,
                confidence=0.50,
                rationale=(
                    "No idle links or significant SNR surplus detected. "
                    "The network is running near its operational optimum. "
                    "Consider scheduling this optimization during off-peak hours "
                    "when traffic drops and SNR surplus links emerge."
                ),
                tradeoffs="",
                actions=[
                    ConfigAction(
                        action_type=ActionType.MONITOR,
                        intent_type_override="energy",
                        parameter_overrides={
                            "alert_on_threshold": {"utilization": IDLE_UTIL_THRESHOLD},
                            "monitoring_cadence_sec": 300,
                        },
                        rationale="Monitor for low-utilization windows to enable sleep mode automatically",
                        execution_order=1,
                        estimated_impact="Enables automatic energy saving when traffic drops",
                    ),
                ],
            ))

        return strategies
