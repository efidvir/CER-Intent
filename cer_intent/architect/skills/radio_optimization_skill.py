"""
Radio Optimization Skill
========================
Domain expertise for optimizing radio performance on Ceragon microwave links.

Options understood by this skill:
  1. Adaptive TX Power Control  — Dynamic power adjustment based on SNR margin
  2. ACM Profile Optimization   — Tune min/max modulation for target SNR
  3. Interference Mitigation    — Cross-polarization discrimination (XPIC), freq planning
  4. Antenna Pointing (advisory)— Flag potential antenna misalignment from SNR trend
  5. ATPC (Automatic TX Power Control) — Enable/tune ATPC for power efficiency
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# SNR thresholds for modulation levels
SNR_THRESHOLDS = {
    "2048QAM": 32, "1024QAM": 29, "512QAM": 26, "256QAM": 23,
    "128QAM": 20,  "64QAM": 17,   "32QAM": 14,  "16QAM": 11, "QPSK": 0,
}


class RadioOptimizationSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "radio_optimization"

    @property
    def description(self) -> str:
        return (
            "Knows how to optimize Ceragon microwave radio performance through "
            "adaptive TX power control, ACM profile tuning, XPIC/interference "
            "mitigation, and proactive antenna fault detection."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["modulation", "capacity", "qos"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "modulation", "acm", "mrmc", "radio", "snr", "power", "interference",
            "tx power", "signal", "qam", "optimize radio",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        min_mod = intent.parameters.get("min_modulation", "64QAM")
        max_mod = intent.parameters.get("max_modulation", "2048QAM")
        avg_snr = self._avg_metric(context, links, "snr_db")
        avg_loss = self._avg_metric(context, links, "packet_loss_pct")
        avg_util = self._avg_metric(context, links, "utilization")

        min_snr_needed = SNR_THRESHOLDS.get(min_mod, 17)
        max_snr_needed = SNR_THRESHOLDS.get(max_mod, 32)

        # ── STRATEGY 1: Adaptive TX Power Adjustment ──────────────────────────
        snr_deficit = max_snr_needed - avg_snr
        if snr_deficit > 0:
            pwr_conf = min(0.90, 0.6 + snr_deficit * 0.05)
            action = "increase"
            impact = f"Estimated SNR gain: {min(snr_deficit, 6):.0f} dB (hardware-limited)"
        else:
            pwr_conf = 0.70  # Power can be reduced for energy saving
            action = "optimize (reduce for efficiency)"
            impact = "Energy saving: 5–15% power reduction while maintaining link quality"

        strategies.append(Strategy(
            name="TX_Power_Adjustment",
            description=f"Adaptively {action} TX power to achieve required SNR for target modulation",
            skill_source=self.name,
            confidence=pwr_conf,
            rationale=(
                f"Current SNR: {avg_snr:.1f} dB. Required SNR for {max_mod}: {max_snr_needed} dB. "
                + (f"SNR deficit of {snr_deficit:.1f} dB — TX power increase needed."
                   if snr_deficit > 0 else
                   f"SNR surplus of {-snr_deficit:.1f} dB — power can be reduced for efficiency.")
            ),
            tradeoffs="TX power changes subject to regulatory EIRP limits. Always verify with Ceragon RF planning tool.",
            actions=[
                ConfigAction(
                    action_type=ActionType.POWER_ADJUST,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "min_modulation": min_mod,
                        "max_modulation": max_mod,
                        "acm_enabled": True,
                        "tx_power_dbm": intent.parameters.get("tx_power_dbm"),  # Use user request or None for auto
                    },
                    rationale=f"TX power {action} to support {max_mod} at current link distance",
                    execution_order=1,
                    estimated_impact=impact,
                ),
            ],
            score_details={"snr_deficit": snr_deficit, "avg_snr": avg_snr},
        ))

        # ── STRATEGY 2: ACM Profile Optimization ──────────────────────────────
        # Choose ACM floor that maximizes availability while meeting capacity target
        # Rule: ACM floor should be set to the modulation achievable at SNR - 3dB margin
        safe_snr = avg_snr - 3.0
        safe_mod = "QPSK"
        for mod, thresh in sorted(SNR_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            if safe_snr >= thresh:
                safe_mod = mod
                break

        strategies.append(Strategy(
            name="ACM_Profile_Optimization",
            description=f"Tune ACM: floor={safe_mod} (SNR-3dB margin), ceiling={max_mod}",
            skill_source=self.name,
            confidence=0.80,
            rationale=(
                f"With SNR {avg_snr:.1f} dB and a 3 dB fade margin, safe minimum modulation is "
                f"{safe_mod}. Setting ACM range {safe_mod}–{max_mod} balances capacity "
                f"with link availability. Packet loss is currently {avg_loss:.2f}%."
                + (" High loss suggests ACM floor too aggressive." if avg_loss > 0.5 else "")
            ),
            tradeoffs="Tighter ACM floor increases link outage duration during deep fades.",
            actions=[
                ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "min_modulation": safe_mod,
                        "max_modulation": max_mod,
                        "acm_enabled": True,
                    },
                    rationale=f"ACM floor {safe_mod} provides 3 dB fade margin at current SNR",
                    execution_order=1,
                    estimated_impact=f"Link availability >99.99% while supporting up to {max_mod}",
                ),
            ],
            score_details={"safe_mod": safe_mod, "avg_snr": avg_snr, "loss": avg_loss},
        ))

        # ── STRATEGY 3: Interference Mitigation (XPIC Advisory) ───────────────
        # If SNR is low despite presumably sufficient distance/power,
        # co-channel interference or antenna issues may be at play.
        if avg_snr < 18.0 and avg_loss > 0.2:
            strategies.append(Strategy(
                name="Interference_Mitigation_Advisory",
                description="Investigate cross-polarization interference and enable XPIC if available",
                skill_source=self.name,
                confidence=0.55,
                rationale=(
                    f"Low SNR ({avg_snr:.1f} dB) combined with packet loss ({avg_loss:.2f}%) "
                    "may indicate co-channel or cross-polarization interference rather than "
                    "path loss alone. XPIC (Cross Polarization Interference Cancellation) "
                    "can recover 10–20 dB of effective SNR on dual-pol links."
                ),
                tradeoffs="XPIC requires hardware support (IP-50FX dual-pol capable). Field verification needed.",
                actions=[
                    ConfigAction(
                        action_type=ActionType.RADIO_TUNE,
                        intent_type_override="modulation",
                        parameter_overrides={
                            "xpic_enabled": True,
                            "min_modulation": "16QAM",
                            "acm_enabled": True,
                        },
                        rationale="XPIC cancels cross-polar interference, recovering SNR margin",
                        execution_order=1,
                        required=False,
                        estimated_impact="SNR recovery: 10–20 dB on dual-pol links",
                    ),
                    ConfigAction(
                        action_type=ActionType.ALERT,
                        intent_type_override="qos",
                        parameter_overrides={
                            "alert_type": "interference_suspected",
                            "recommendation": "Inspect antenna alignment and check for co-channel transmitters",
                        },
                        rationale="Field verification recommended before radio changes",
                        execution_order=2,
                        required=False,
                        estimated_impact="Advisory — requires field team action",
                    ),
                ],
                score_details={"snr": avg_snr, "loss": avg_loss},
            ))

        return strategies
