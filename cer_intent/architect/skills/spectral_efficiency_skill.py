"""
Spectral Efficiency Optimization Skill
=======================================
Domain expertise for maximizing bits-per-Hz on 6G transport microwave links.

Spectral efficiency (SE) is measured in bits/s/Hz and is the fundamental
limit of wireless transport capacity within a licensed spectrum allocation.
This skill pushes SE to its physical maximum through XPIC, ACM ceiling,
channel bonding, and interference-aware modulation selection.

Triggered by requests like:
  - "maximize spectral efficiency"
  - "improve bits per Hz"
  - "get maximum throughput from existing spectrum"
  - "optimize spectrum utilization"
  - "push modulation to maximum"

Options understood by this skill:
  1. ACM Ceiling Push          -- Enable 2048QAM where SNR permits (11 bits/s/Hz)
  2. XPIC Dual-Pol Activation  -- Double SE by using both polarizations independently
  3. Channel Bonding (MRMC)    -- Aggregate adjacent channels for wider effective BW
  4. Interference Floor Reduction -- XPIC + diversity to lower noise floor
  5. Adaptive Channel Width    -- Select widest available licensed BW (up to 112MHz)
"""
from __future__ import annotations

from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# Spectral efficiency (bits/s/Hz) by modulation
SPECTRAL_EFFICIENCY = {
    "QPSK":    2.0,
    "16QAM":   4.0,
    "32QAM":   5.0,
    "64QAM":   6.0,
    "128QAM":  7.0,
    "256QAM":  8.0,
    "512QAM":  9.0,
    "1024QAM": 10.0,
    "2048QAM": 11.0,   # Maximum for Ceragon IP-50FX
}

# SNR required for each modulation (with coding overhead)
SNR_REQUIRED = {
    "2048QAM": 32, "1024QAM": 29, "512QAM": 26, "256QAM": 23,
    "128QAM": 20,  "64QAM": 17,   "32QAM": 14,  "16QAM": 11, "QPSK": 0,
}


def max_achievable_modulation(snr_db: float, fade_margin_db: float = 3.0) -> str:
    """Return highest modulation achievable with given SNR and fade margin."""
    effective_snr = snr_db - fade_margin_db
    best_mod = "QPSK"
    for mod, req in sorted(SNR_REQUIRED.items(), key=lambda x: x[1], reverse=True):
        if effective_snr >= req:
            best_mod = mod
            break
    return best_mod


class SpectralEfficiencySkill(BaseSkill):

    @property
    def name(self) -> str:
        return "spectral_efficiency"

    @property
    def description(self) -> str:
        return (
            "Maximizes bits-per-Hz on 6G microwave transport links by enabling "
            "2048QAM, XPIC dual-polarization, channel bonding, and adaptive BW selection. "
            "Pushes spectral efficiency to the physical maximum while maintaining "
            "a safe fade margin and link availability target."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["capacity", "modulation"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "spectral", "bits per hz", "spectrum", "efficiency", "2048qam",
            "maximum modulation", "qam", "maximize", "throughput per hz",
            "channel", "xpic", "dual pol", "polarization", "mrmc",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        fade_margin = intent.parameters.get("fade_margin_db", 3.0)

        # Analyze per-link SE potential
        link_se_analysis = []
        for link in links:
            lid   = link["id"]
            telem = context.telemetry.get(lid, {})
            snr   = telem.get("snr_db", 25.0)
            current_mod = telem.get("current_modulation", "256QAM")
            current_se  = SPECTRAL_EFFICIENCY.get(current_mod, 8.0)
            best_mod    = max_achievable_modulation(snr, fade_margin)
            best_se     = SPECTRAL_EFFICIENCY.get(best_mod, current_se)
            se_gain     = best_se - current_se

            link_se_analysis.append({
                "id": lid, "snr": snr,
                "current_mod": current_mod, "current_se": current_se,
                "best_mod": best_mod, "best_se": best_se, "se_gain": se_gain,
            })

        # Sort by highest SE gain potential
        link_se_analysis.sort(key=lambda x: x["se_gain"], reverse=True)
        improvable = [l for l in link_se_analysis if l["se_gain"] > 0]
        top_gains = improvable[:5]
        at_max    = [l for l in link_se_analysis if l["se_gain"] == 0]
        avg_se_gain = sum(l["se_gain"] for l in improvable) / len(improvable) if improvable else 0

        # STRATEGY 1: ACM Ceiling Push to Maximum Modulation
        if top_gains:
            actions = []
            for i, la in enumerate(top_gains):
                actions.append(ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "target_link": la["id"],
                        "min_modulation": la["current_mod"],     # Keep current floor
                        "max_modulation": la["best_mod"],        # Raise ceiling
                        "acm_enabled": True,
                    },
                    rationale=(
                        f"Link {la['id']}: SNR {la['snr']:.1f}dB supports {la['best_mod']} "
                        f"({la['best_se']:.0f} bits/s/Hz vs current {la['current_se']:.0f}). "
                        f"SE gain: +{la['se_gain']:.0f} bits/s/Hz."
                    ),
                    execution_order=i + 1,
                    estimated_impact=(
                        f"{la['se_gain']:.0f} bits/s/Hz SE gain = "
                        f"~{la['se_gain']/la['current_se']*100:.0f}% throughput improvement"
                    ),
                ))

            strategies.append(Strategy(
                name="ACM_Ceiling_Push_MaxSE",
                description=(
                    f"Push ACM ceiling to maximum on {len(top_gains)} links "
                    f"(avg +{avg_se_gain:.1f} bits/s/Hz gain)"
                ),
                skill_source=self.name,
                confidence=0.90,
                rationale=(
                    f"{len(improvable)} of {len(links)} links can improve spectral efficiency. "
                    f"Average potential gain: {avg_se_gain:.1f} bits/s/Hz. "
                    "Raising ACM ceiling allows the radio to use higher modulations during "
                    "good propagation windows, maximizing throughput within the licensed spectrum. "
                    f"Current ceiling prevents use of {', '.join(set(l['best_mod'] for l in top_gains))} "
                    "despite sufficient SNR."
                ),
                tradeoffs=(
                    f"Higher modulations require more stable SNR. A {fade_margin:.0f}dB fade margin "
                    "is maintained. ACM will automatically step down during propagation degradation."
                ),
                actions=actions,
                score_details={
                    "improvable_links": len(improvable),
                    "avg_se_gain_bps_hz": avg_se_gain,
                    "at_max_already": len(at_max),
                },
            ))

        # STRATEGY 2: XPIC Dual-Polarization (doubles SE on supported hardware)
        strategies.append(Strategy(
            name="XPIC_DualPol_SE_Doubling",
            description="Enable XPIC dual-polarization to effectively double spectral efficiency",
            skill_source=self.name,
            confidence=0.75,
            rationale=(
                "XPIC (Cross-Polarization Interference Cancellation) enables two independent "
                "data streams on the same frequency channel using orthogonal polarizations (H/V). "
                "This doubles the effective capacity within the same licensed spectrum allocation, "
                "achieving the equivalent of 2x the single-carrier spectral efficiency. "
                "Supported on Ceragon IP-50FX. Each carrier can independently run 2048QAM, "
                "yielding up to 22 bits/s/Hz combined (equivalent to 2x 11 bits/s/Hz)."
            ),
            tradeoffs=(
                "Requires dual-polarization antenna and IP-50FX or higher hardware. "
                "XPIC requires careful cross-pol discrimination (XPD) at the antenna. "
                "Performance degrades in heavy rain (XPD decreases at higher rain rates)."
            ),
            actions=[
                ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "xpic_enabled": True,
                        "min_modulation": "64QAM",
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale="XPIC enables two independent 2048QAM streams = 2x SE",
                    execution_order=1,
                    required=False,
                    estimated_impact="Up to 2x capacity within existing spectrum (22 bits/s/Hz combined)",
                ),
            ],
        ))

        # STRATEGY 3: Channel Width Maximization (widest licensed BW)
        current_bw = intent.parameters.get("channel_bandwidth_mhz", 28)
        if current_bw < 112:
            strategies.append(Strategy(
                name="Channel_BW_Maximization",
                description=f"Expand channel bandwidth from {current_bw}MHz to 112MHz for maximum raw throughput",
                skill_source=self.name,
                confidence=0.70,
                rationale=(
                    f"Current channel width: {current_bw}MHz. Maximum supported: 112MHz (IP-50FX). "
                    f"Expanding from {current_bw}MHz to 112MHz directly scales raw throughput by "
                    f"{112/current_bw:.1f}x while maintaining the same spectral efficiency (bits/s/Hz). "
                    "Combined with 2048QAM, this delivers the maximum possible throughput "
                    "from a single radio carrier."
                ),
                tradeoffs=(
                    "Requires licensed spectrum for 112MHz channel. "
                    "Wider channels are more susceptible to adjacent channel interference. "
                    "Verify spectrum coordination with local regulator."
                ),
                actions=[
                    ConfigAction(
                        action_type=ActionType.TRANSLATE,
                        intent_type_override="capacity",
                        parameter_overrides={
                            "channel_bandwidth_mhz": 112,
                            "mrmc_script_id": 60,
                            "min_throughput_gbps": 10.0,
                        },
                        rationale=f"112MHz channel + 2048QAM = maximum raw throughput",
                        execution_order=1,
                        estimated_impact=f"{112/current_bw:.1f}x raw throughput increase from BW alone",
                    ),
                ],
            ))

        return strategies
