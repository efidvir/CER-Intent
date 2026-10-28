"""
Skill Registry
==============
Discovers and manages all 17 loaded AI Architect skills.
Provides rich catalog metadata (categories, governing standards, and clickable
natural-language prompts) for the API and Dashboard UI.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from cer_intent.intent_schema import Intent
from cer_intent.architect.strategy import NetworkContext
from cer_intent.architect.skills.base_skill import BaseSkill
from cer_intent.architect.skills.low_latency_skill import LowLatencySkill
from cer_intent.architect.skills.high_capacity_skill import HighCapacitySkill
from cer_intent.architect.skills.radio_optimization_skill import RadioOptimizationSkill
from cer_intent.architect.skills.traffic_engineering_skill import TrafficEngineeringSkill, ResilienceSkill
from cer_intent.architect.skills.network_health_skill import NetworkHealthSkill
from cer_intent.architect.skills.rain_fade_skill import RainFadeSkill
from cer_intent.architect.skills.energy_optimization_skill import EnergyOptimizationSkill
from cer_intent.architect.skills.spectral_efficiency_skill import SpectralEfficiencySkill
from cer_intent.architect.skills.advanced_telecom_skills import (
    TSNDeterministicSkill,
    MmWaveBeamSteeringSkill,
    MultiBandAggregationSkill,
    OranXhaulSkill,
    TimingSynchronizationSkill,
    ZeroTrustSecuritySkill,
    InterferenceMitigationSkill,
    MARLAutonomicHealingSkill,
)

logger = logging.getLogger(__name__)

# All 17 available AI Architect skills
_ALL_SKILLS: List[BaseSkill] = [
    LowLatencySkill(),
    HighCapacitySkill(),
    RadioOptimizationSkill(),
    TrafficEngineeringSkill(),
    ResilienceSkill(),
    NetworkHealthSkill(),
    RainFadeSkill(),
    EnergyOptimizationSkill(),
    SpectralEfficiencySkill(),
    TSNDeterministicSkill(),
    MmWaveBeamSteeringSkill(),
    MultiBandAggregationSkill(),
    OranXhaulSkill(),
    TimingSynchronizationSkill(),
    ZeroTrustSecuritySkill(),
    InterferenceMitigationSkill(),
    MARLAutonomicHealingSkill(),
]

# Enriched metadata for each skill so users know what they can ask the Intent Architect to achieve
_SKILL_ENRICHMENT: Dict[str, dict] = {
    "low_latency": {
        "title": "Ultra-Low Latency & Sub-ms QoS",
        "category": "Deterministic QoS & Slicing",
        "standards": ["IETF RFC 4594 (DiffServ EF)", "3GPP TS 23.501 (5QI 82)", "ITU-T Y.1541"],
        "what_it_achieves": "Achieves <1–5 ms latency via DSCP 46 EF prioritization, alternate low-hop path steering, ACM floor stabilization, and dedicated URLLC slice isolation.",
        "example_prompts": [
            "Ensure latency < 1.5ms and jitter < 0.1ms on ceragon-mh-t261-ctu-96 for URLLC traffic",
            "Minimize latency below 2ms on link-D-E with high priority EF scheduling",
        ],
    },
    "high_capacity": {
        "title": "High-Capacity MRMC & Bandwidth Scaling",
        "category": "RF & Spectrum Optimization",
        "standards": ["ETSI EN 302 217", "IETF RFC 8561 (MW Radio Link)"],
        "what_it_achieves": "Scales link throughput from 500 Mbps up to 10+ Gbps by upgrading MRMC script profiles, expanding channel bandwidth (28→56→112 MHz), and raising ACM ceilings.",
        "example_prompts": [
            "Increase capacity on link-A-B to 5 Gbps using 112 MHz channel bandwidth for eMBB",
            "Upgrade backhaul throughput on sector-north to at least 7.5 Gbps",
        ],
    },
    "radio_optimization": {
        "title": "Adaptive Radio & ACM/ATPC Tuning",
        "category": "RF & Spectrum Optimization",
        "standards": ["ETSI TR 102 311", "Ceragon CeraOS MRMC/ACM"],
        "what_it_achieves": "Optimizes SNR margins, tunes adaptive modulation (QPSK–2048QAM) profiles, adjusts ATPC transmit power, and detects antenna alignment drift.",
        "example_prompts": [
            "Set ACM modulation range from 64QAM to 2048QAM with ATPC enabled on sector-south",
            "Optimize radio SNR and set TX power to 18 dBm on link-A-C",
        ],
    },
    "traffic_engineering": {
        "title": "Congestion-Aware Traffic Engineering & VPN Steering",
        "category": "Routing, Resilience & Self-Healing",
        "standards": ["IETF RFC 9543", "Policy-Based Routing (PBR)", "Weighted ECMP"],
        "what_it_achieves": "Steers flows away from saturated links (>70% utilization), re-anchors VPN tunnels onto lowest-latency hops, and balances multi-path ECMP load.",
        "example_prompts": [
            "Reroute congested traffic on link-B-D via lower-utilization alternate path",
            "Steer VPN tunnels across sector-east to avoid bottleneck links",
        ],
    },
    "resilience_planning": {
        "title": "1+1 HSB & Space/Frequency Diversity Protection",
        "category": "Routing, Resilience & Self-Healing",
        "standards": ["ITU-T G.8031 / G.8032", "ETSI EN 302 217 Diversity"],
        "what_it_achieves": "Enforces 99.999% (5-nines) availability using 1+1 Hot Standby (<50ms hitless switchover), MRC Space Diversity, Frequency Diversity, or ring protection with automatic hardware fallback.",
        "example_prompts": [
            "Enable 1+1 Hot Standby protection on sector-north with revertive mode and 300s WTR",
            "Enable space diversity protection on link-A-C for multipath fading resilience",
        ],
    },
    "network_health": {
        "title": "Holistic Network-Wide Triage & Health Optimization",
        "category": "Observability, Security & Green 6G",
        "standards": ["TM Forum IG1253", "3GPP TS 28.535 MDA"],
        "what_it_achieves": "Scans all 35+ topology links simultaneously to triage congested hotspots, packet-loss links, and degraded nodes in a unified multi-action plan.",
        "example_prompts": [
            "Diagnose and optimize overall network performance and fix any congested or lossy links",
            "Improve global network health across all links in the topology",
        ],
    },
    "rain_fade_adaptation": {
        "title": "ITU-R P.838 Weather & Monsoon Rain-Fade Hardening",
        "category": "RF & Spectrum Optimization",
        "standards": ["ITU-R P.838-3 (Specific Attenuation Model for Rain)", "ITU-R P.530"],
        "what_it_achieves": "Computes per-link rain attenuation (dB/km) for 5–100 mm/hr storms and proactively hardens ACM modulation floors, boosts ATPC ceilings, and pre-arms 1+1 HSB.",
        "example_prompts": [
            "Harden all links in sector-north against heavy 50 mm/hr rain fade using ITU-R P.838",
            "Prepare ceragon-mh-t261-ctu-96 for severe storm weather by hardening ACM floor to 64QAM",
        ],
    },
    "energy_optimization": {
        "title": "Green-6G Energy Saving & ServiceDLC Sleep",
        "category": "Observability, Security & Green 6G",
        "standards": ["ETSI ES 203 228", "UNITY-6G D3.1 instantaneous-device-energy-tid"],
        "what_it_achieves": "Reduces network OPEX and carbon footprint via off-peak TX deep-sleep scheduling, ATPC power backoff on SNR-surplus links, and MIMO single-pol carrier shutdown.",
        "example_prompts": [
            "Enable green energy saving sleep mode during 02:00-05:00 off-peak window on sector-north",
            "Reduce TX power consumption by 6 dB on underutilized links overnight",
        ],
    },
    "spectral_efficiency": {
        "title": "Maximal Spectral Efficiency (11 bits/s/Hz & XPIC)",
        "category": "RF & Spectrum Optimization",
        "standards": ["ETSI EN 302 217-2", "2048QAM / Dual-Pol XPIC"],
        "what_it_achieves": "Pushes spectral efficiency to the physical Shannon limit (11 bits/s/Hz) by unlocking 2048QAM, activating dual-polarization XPIC (2x capacity in same channel), and channel bonding.",
        "example_prompts": [
            "Maximize spectral efficiency and bits per Hz across all backhaul links using 2048QAM",
            "Push modulation to maximum achievable spectral efficiency on link-A-B",
        ],
    },
    "tsn_deterministic_qos": {
        "title": "IEEE 802.1Qbv TSN Time-Aware Shaper & Preemption",
        "category": "Deterministic QoS & Slicing",
        "standards": ["IEEE 802.1Qbv (TAS)", "IEEE 802.1Qbu (Frame Preemption)", "IEEE 802.1CB (FRER)"],
        "what_it_achieves": "Programs microsecond Gate Control Lists (GCL), Express MAC frame preemption, and PfifoFast Band-0 URLLC queuing on Ceragon ctu-96 to maintain 0.475 ms latency under 3.5x traffic surges.",
        "example_prompts": [
            "Enable IEEE 802.1Qbv TSN time-aware shaper with 1000us cycle and 250us URLLC window on ceragon-mh-t261-ctu-96",
            "Protect deterministic TSN robotics traffic against 3.5x video bufferbloat surge with 802.1Qbu frame preemption",
        ],
    },
    "mmwave_beam_steering": {
        "title": "60 GHz V-Band Phased-Array Beam Steering (MH-T261)",
        "category": "60GHz/80GHz Millimeter-Wave & O-RAN",
        "standards": ["IEEE 802.11ad / 802.11ay", "Siklu MultiHaul TG (massive2 64-Element Array)"],
        "what_it_achieves": "Electronically steers the 64-element 'massive2' phased antenna array in azimuth/elevation on Ceragon MH-T261 (ctu-96) and shifts V-Band channels (58.32–64.80 GHz) to bypass obstacles and O2 absorption.",
        "example_prompts": [
            "Steer 60.48 GHz massive2 phased array beam to +15 deg azimuth and +2 deg elevation on ceragon-mh-t261-ctu-96",
            "Tune 60 GHz V-Band beamforming array on ctu-96 to channel 64.80 GHz to minimize oxygen absorption",
        ],
    },
    "multiband_carrier_aggregation": {
        "title": "Multi-Band Booster (80 GHz E-Band + Microwave Bonding)",
        "category": "60GHz/80GHz Millimeter-Wave & O-RAN",
        "standards": ["IETF RFC 8561 Multi-Carrier", "Ceragon L1 Multi-Band Booster"],
        "what_it_achieves": "Bonds 80 GHz E-Band (2000 MHz BW, 10 Gbps) with 18 GHz Microwave (112 MHz BW, 2.5 Gbps) into a 12.5 Gbps virtual pipe while pinning URLLC & sync flows to the weather-immune microwave anchor.",
        "example_prompts": [
            "Bond 80 GHz E-Band and 18 GHz Microwave into a 12.5 Gbps Multi-Band carrier aggregation group on link-A-B",
            "Enable Multi-Band L1 hitless bonding with URLLC pinned to microwave anchor on sector-north",
        ],
    },
    "oran_xhaul_optimization": {
        "title": "O-RAN Split 7.2x eCPRI Fronthaul & F1-U Midhaul",
        "category": "60GHz/80GHz Millimeter-Wave & O-RAN",
        "standards": ["O-RAN.WG4.CUS (Split 7.2x)", "O-RAN.WG4.CTI", "UNITY-6G D3.1 F1-U DSCP"],
        "what_it_achieves": "Configures eCPRI Split 7.2x Block Floating Point (BFP9/BFP12) IQ compression (2.9:1 bitrate reduction), T12/T2a delay windows (≤100 µs), F1-U midhaul DSCP sockets, and 5ms CTI rate reporting to O-DU.",
        "example_prompts": [
            "Optimize O-RAN Split 7.2x eCPRI fronthaul with BFP9 IQ compression and 100us T12 delay budget on oran-cu1",
            "Configure O-RAN F1-U midhaul DSCP 46 socket and enable CTI rate reporting on all O-DU links",
        ],
    },
    "timing_phase_sync": {
        "title": "ITU-T G.8275.1 PTP Phase & SyncE Frequency Lock",
        "category": "Deterministic QoS & Slicing",
        "standards": ["ITU-T G.8275.1 / G.8275.2", "ITU-T G.8262 (SyncE)", "IEEE 1588v2"],
        "what_it_achieves": "Deploys Telecom Boundary Clocks (T-BC) and physical-layer SyncE (ESMC QL-PRC) across wireless hops to guarantee ≤ ±1.5 µs phase synchronization for 6G TDD and Cooperative MIMO.",
        "example_prompts": [
            "Configure ITU-T G.8275.1 PTP Telecom Boundary Clock and SyncE QL-PRC with <1500ns phase error on node-A",
            "Enable IEEE 1588v2 PTP phase synchronization and SyncE timing across all fronthaul links",
        ],
    },
    "zero_trust_macsec": {
        "title": "IEEE 802.1AE Line-Rate MACsec & PQC Encryption",
        "category": "Observability, Security & Green 6G",
        "standards": ["IEEE 802.1AE (MACsec)", "IEEE 802.1X-2020 (MKA)", "NIST FIPS 203 ML-KEM-768"],
        "what_it_achieves": "Secures wireless xHaul links against RF eavesdropping with hardware-offloaded AES-GCM-256 MACsec L2 encryption (0.0 µs jitter) and post-quantum ML-KEM-768 MKA key rotation.",
        "example_prompts": [
            "Enable IEEE 802.1AE MACsec AES-GCM-256 line-rate encryption with quantum-safe key exchange on link-D-E",
            "Turn on zero-trust MACsec payload encryption with 3600s MKA key rotation across all links",
        ],
    },
    "interference_xpic_mitigation": {
        "title": "XPIC Dual-Pol Cancellation & Dynamic Channel Avoidance",
        "category": "RF & Spectrum Optimization",
        "standards": ["ETSI EN 302 217-2 (XPIC)", "ITU-R F.1108", "Coordinated ATPC"],
        "what_it_achieves": "Cancels up to 30 dB of V/H cross-polarization interference via baseband XPIC, coordinates ATPC power across dense hubs, and triggers hitless Dynamic Frequency/Channel Selection (DFC).",
        "example_prompts": [
            "Enable XPIC cross-polarization interference cancellation and coordinated ATPC for SINR >= 28 dB on sector-south",
            "Mitigate co-channel RF interference on link-B-E using XPIC and dynamic channel switching",
        ],
    },
    "marl_autonomic_healing": {
        "title": "DPIR + Decentralized MARL Disaster Recovery & Mesh Healing",
        "category": "Routing, Resilience & Self-Healing",
        "standards": ["UNITY-6G D2.4 MARL Recovery", "DPIR Spanning Tree", "3GPP TS 28.561 Pre-Flight"],
        "what_it_achieves": "Recovers partitioned topology islands after multi-node fiber/power cuts by steering 60 GHz phased arrays to ignite dormant MARL candidate bridges (e.g. bridge-1) and verifying via NS-3.",
        "example_prompts": [
            "Execute MARL autonomic disaster recovery and ignite emergency 60GHz bridge-1 to heal isolated topology islands",
            "Run DPIR spanning-tree re-rooting and MARL mesh self-healing with NS-3 Digital Twin pre-flight check",
        ],
    },
}


class SkillRegistry:
    """
    Central registry of all 17 AI Architect skills.
    Finds applicable skills for a given intent and network context.
    """

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {s.name: s for s in _ALL_SKILLS}
        logger.info(f"Skill registry loaded ({len(self._skills)} skills): {list(self._skills.keys())}")

    def get_all_skills(self) -> List[BaseSkill]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def find_applicable_skills(self, intent: Intent, context: NetworkContext) -> List[BaseSkill]:
        """Return all skills that are applicable to the given intent and context."""
        applicable = []
        for skill in self._skills.values():
            try:
                if skill.is_applicable(intent, context):
                    applicable.append(skill)
                    logger.debug(f"Skill '{skill.name}' is applicable")
            except Exception as e:
                logger.warning(f"Skill '{skill.name}' applicability check failed: {e}")
        return applicable

    def skill_catalog(self) -> List[dict]:
        """Return a rich, human-readable catalog of all 17 skills for the API and Dashboard."""
        catalog = []
        for s in self._skills.values():
            meta = _SKILL_ENRICHMENT.get(s.name, {})
            catalog.append({
                "name": s.name,
                "title": meta.get("title", s.name.replace("_", " ").title()),
                "category": meta.get("category", "Core Transport"),
                "description": s.description,
                "what_it_achieves": meta.get("what_it_achieves", s.description),
                "standards": meta.get("standards", []),
                "applicable_intent_types": s.applicable_intent_types,
                "applicable_goals": s.applicable_goals,
                "example_prompts": meta.get("example_prompts", []),
            })
        return catalog
