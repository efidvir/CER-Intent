"""
Rain Fade Adaptation Skill
===========================
Domain expertise for hardening microwave links against adverse weather
propagation conditions (rain fade, atmospheric ducting, multipath fading).

In 6G O-RAN fronthaul over microwave, fronthaul tails (IP-20C, short hops)
are most vulnerable to rain fade above 18 GHz. This skill proactively
adjusts ACM floors, power margins, and protection schemes.

Triggered by requests like:
  - "prepare the network for rain"
  - "harden links against weather"
  - "reduce impact of rain fade tonight"
  - "increase fade margin on fronthaul"

Options understood by this skill:
  1. ACM Floor Hardening        -- Raise ACM floor to survive deep fades (ITU-R P.838)
  2. TX Power Pre-Boost         -- Increase ATPC ceiling to maximum for fade headroom
  3. Space Diversity Activation -- Enable SD to achieve frequency/space diversity gain
  4. Adaptive Monitoring        -- Increase telemetry polling during weather events
  5. Protection Pre-positioning -- Pre-activate 1+1 HSB on critical segments
"""
from __future__ import annotations

import math
from typing import List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import (
    NetworkContext, Strategy, ConfigAction, ActionType
)
from cer_intent.architect.skills.base_skill import BaseSkill

# ITU-R P.838 approximate rain attenuation: aR^b dB/km
# For ~23 GHz bands: a=0.0667, b=1.129 (vertical polarization)
RAIN_ATTENUATION_A = 0.0667
RAIN_ATTENUATION_B = 1.129

# Heavy rain rate (mm/hr) thresholds by climate zone
RAIN_RATES = {
    "light": 5,     # Drizzle
    "moderate": 20, # Steady rain
    "heavy": 50,    # Heavy storm
    "extreme": 100, # Tropical downpour
}

# SNR thresholds for modulation levels (same as RadioOptimizationSkill)
SNR_THRESHOLDS = {
    "2048QAM": 32, "1024QAM": 29, "512QAM": 26, "256QAM": 23,
    "128QAM": 20,  "64QAM": 17,   "32QAM": 14,  "16QAM": 11, "QPSK": 0,
}


def estimate_rain_attenuation(rate_mm_hr: float, distance_km: float) -> float:
    """Estimate rain fade margin loss using ITU-R P.838 model."""
    specific_atten = RAIN_ATTENUATION_A * (rate_mm_hr ** RAIN_ATTENUATION_B)
    return specific_atten * distance_km


def hardened_acm_floor(current_snr: float, rain_loss_db: float) -> str:
    """Return the safe ACM floor given SNR headroom after rain attenuation."""
    effective_snr = current_snr - rain_loss_db - 3.0  # 3 dB extra safety margin
    safe_mod = "QPSK"
    for mod, thresh in sorted(SNR_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if effective_snr >= thresh:
            safe_mod = mod
            break
    return safe_mod


class RainFadeSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "rain_fade_adaptation"

    @property
    def description(self) -> str:
        return (
            "Hardens 6G microwave transport links against rain fade and adverse "
            "weather propagation. Uses ITU-R P.838 rain attenuation modelling to "
            "calculate required fade margins and applies ACM floor hardening, "
            "TX power boost, space diversity, and HSB pre-positioning."
        )

    @property
    def applicable_intent_types(self) -> List[str]:
        return ["resilience", "modulation", "capacity"]

    @property
    def applicable_goals(self) -> List[str]:
        return [
            "rain", "weather", "fade", "rain fade", "storm", "harden",
            "fade margin", "attenuation", "adverse", "precipitation",
            "tropical", "outage", "availability", "outdoor",
        ]

    def generate_strategies(self, intent: Intent, context: NetworkContext) -> List[Strategy]:
        strategies: List[Strategy] = []
        links = self._get_links_for_target(context)

        # Determine rain intensity from intent parameters or default to heavy
        rain_rate = intent.parameters.get("rain_rate_mm_hr",
                    RAIN_RATES["heavy"])  # Conservative default
        rain_label = next(
            (k for k, v in sorted(RAIN_RATES.items(), key=lambda x: x[1])
             if rain_rate <= v), "extreme"
        )

        # Calculate per-link rain fade impact
        link_analyses = []
        for link in links:
            lid  = link["id"]
            dist = link.get("distance_km", 3.0)
            telem = context.telemetry.get(lid, {})
            snr   = telem.get("snr_db", 25.0)

            rain_loss = estimate_rain_attenuation(rain_rate, dist)
            snr_after = snr - rain_loss
            safe_floor = hardened_acm_floor(snr, rain_loss)
            link_analyses.append({
                "id": lid, "dist": dist, "snr": snr,
                "rain_loss_db": rain_loss, "snr_after_rain": snr_after,
                "safe_floor": safe_floor,
            })

        # Sort by worst rain impact (most attenuation)
        link_analyses.sort(key=lambda x: x["rain_loss_db"], reverse=True)
        most_affected = link_analyses[:5]

        avg_rain_loss = (
            sum(l["rain_loss_db"] for l in link_analyses) / len(link_analyses)
            if link_analyses else 0
        )

        # STRATEGY 1: ACM Floor Hardening
        if most_affected:
            actions = []
            for i, la in enumerate(most_affected):
                actions.append(ConfigAction(
                    action_type=ActionType.RADIO_TUNE,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "target_link": la["id"],
                        "min_modulation": la["safe_floor"],
                        "max_modulation": "2048QAM",
                        "acm_enabled": True,
                    },
                    rationale=(
                        f"Link {la['id']}: {la['dist']:.1f}km hop. "
                        f"Rain loss at {rain_rate}mm/hr: {la['rain_loss_db']:.1f}dB. "
                        f"Safe ACM floor: {la['safe_floor']} (SNR after fade: {la['snr_after_rain']:.1f}dB)."
                    ),
                    execution_order=i + 1,
                    estimated_impact=f"Maintains link connectivity during {rain_label} rain events",
                ))

            strategies.append(Strategy(
                name="ACM_Floor_Hardening_Rain",
                description=(
                    f"Raise ACM floors on {len(most_affected)} most-affected links "
                    f"for {rain_label} rain ({rain_rate}mm/hr, ~{avg_rain_loss:.1f}dB avg loss)"
                ),
                skill_source=self.name,
                confidence=0.91,
                rationale=(
                    f"ITU-R P.838 model predicts {avg_rain_loss:.1f}dB average rain attenuation "
                    f"at {rain_rate}mm/hr across the transport links. "
                    "Raising ACM floors preemptively prevents modulation instability and "
                    "burst packet loss that typically accompanies rain fade onset. "
                    "Fronthaul tails (short, high-frequency hops) are most vulnerable."
                ),
                tradeoffs=(
                    "Higher ACM floors reduce peak throughput headroom during clear conditions. "
                    "Floors should be reverted after the weather event passes."
                ),
                actions=actions,
                score_details={
                    "rain_rate_mm_hr": rain_rate,
                    "avg_rain_loss_db": avg_rain_loss,
                    "links_affected": len(most_affected),
                },
            ))

        # STRATEGY 2: TX Power Pre-Boost (ATPC Ceiling Raise)
        strategies.append(Strategy(
            name="ATPC_Power_Boost_PreFade",
            description=f"Pre-raise ATPC power ceiling to maximise fade margin before {rain_label} rain",
            skill_source=self.name,
            confidence=0.78,
            rationale=(
                f"Expected rain attenuation: {avg_rain_loss:.1f}dB average, "
                f"up to {max((l['rain_loss_db'] for l in link_analyses), default=0):.1f}dB on longest hops. "
                "Pre-raising ATPC ceiling allows radios to autonomously boost TX power "
                "as SNR degrades, maximising available fade margin within EIRP limits."
            ),
            tradeoffs=(
                "TX power increase subject to regulatory EIRP limits. "
                "Verify with Ceragon link budget calculator before applying."
            ),
            actions=[
                ConfigAction(
                    action_type=ActionType.POWER_ADJUST,
                    intent_type_override="modulation",
                    parameter_overrides={
                        "atpc_enabled": True,
                        "atpc_max_power_dbm": intent.parameters.get("max_tx_power_dbm", 23),
                        "atpc_target_snr_db": 30.0,
                        "min_modulation": "16QAM",
                    },
                    rationale="ATPC at maximum ceiling provides dynamic fade compensation",
                    execution_order=1,
                    estimated_impact=f"Up to 6dB additional fade margin via ATPC headroom",
                ),
            ],
        ))

        # STRATEGY 3: Space Diversity Pre-activation (advisory for supported hardware)
        strategies.append(Strategy(
            name="Space_Diversity_PreActivation",
            description="Pre-activate space diversity on links with SD-capable hardware to gain diversity gain",
            skill_source=self.name,
            confidence=0.65,
            rationale=(
                "Space Diversity (SD) provides 3-10dB effective diversity gain against "
                "multipath and rain-induced amplitude fading. Pre-activating SD before "
                "the weather event ensures the protection path is ready without hitless "
                "switchover delays. Applicable on IP-50FX and IP-20N with dual antenna."
            ),
            tradeoffs="Requires SD-capable hardware and pre-configured secondary antenna. Field verification needed.",
            actions=[
                ConfigAction(
                    action_type=ActionType.TRANSLATE,
                    intent_type_override="resilience",
                    parameter_overrides={
                        "protection_mode": "space_diversity",
                        "diversity_gain_db": 6,
                    },
                    rationale="SD provides 3-10dB diversity gain against rain-induced fading",
                    execution_order=1,
                    required=False,
                    estimated_impact="3-10dB effective SNR improvement under fading conditions",
                ),
                ConfigAction(
                    action_type=ActionType.MONITOR,
                    intent_type_override="resilience",
                    parameter_overrides={
                        "monitoring_cadence_sec": 10,
                        "alert_on_threshold": {"snr_db": 15.0, "utilization": 0.95},
                    },
                    rationale="Increase telemetry cadence to detect rapid fade onset",
                    execution_order=2,
                    estimated_impact="Early warning system for fade events",
                ),
            ],
        ))

        return strategies
