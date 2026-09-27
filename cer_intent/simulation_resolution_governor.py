"""
TFS-to-NS-3 Simulation Resolution & Fidelity Governor
=====================================================
Enforces goal-driven multi-resolution scoping for Telecom Network Digital Twins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ResolutionGovernor")


class ResolutionTier(str, Enum):
    TIER_1_MACRO_TOPOLOGY = "macro_topology"
    TIER_2_QUEUE_DYNAMICS = "queue_dynamics"
    TIER_3_PHYSICAL_RF = "physical_rf"
    TIER_4_URLLC_MICRO = "urllc_micro"
    TIER_5_ENERGY_MACRO = "energy_macro"


GOAL_TO_TIER_MAP: Dict[str, ResolutionTier] = {
    "link_failure": ResolutionTier.TIER_1_MACRO_TOPOLOGY,
    "fiber_cut": ResolutionTier.TIER_1_MACRO_TOPOLOGY,
    "fast_reroute": ResolutionTier.TIER_1_MACRO_TOPOLOGY,
    "routing_failover": ResolutionTier.TIER_1_MACRO_TOPOLOGY,
    "cspf_optimization": ResolutionTier.TIER_1_MACRO_TOPOLOGY,

    "traffic_surge": ResolutionTier.TIER_2_QUEUE_DYNAMICS,
    "congestion": ResolutionTier.TIER_2_QUEUE_DYNAMICS,
    "microburst": ResolutionTier.TIER_2_QUEUE_DYNAMICS,
    "bufferbloat": ResolutionTier.TIER_2_QUEUE_DYNAMICS,

    "channel_degradation": ResolutionTier.TIER_3_PHYSICAL_RF,
    "rain_fade": ResolutionTier.TIER_3_PHYSICAL_RF,
    "acm_modulation": ResolutionTier.TIER_3_PHYSICAL_RF,
    "rf_interference": ResolutionTier.TIER_3_PHYSICAL_RF,
    "atmospheric_attenuation": ResolutionTier.TIER_3_PHYSICAL_RF,

    "slice_admission": ResolutionTier.TIER_4_URLLC_MICRO,
    "urllc_critical": ResolutionTier.TIER_4_URLLC_MICRO,
    "jitter_budget": ResolutionTier.TIER_4_URLLC_MICRO,
    "p99_latency_guarantee": ResolutionTier.TIER_4_URLLC_MICRO,

    "energy_saving_sleep": ResolutionTier.TIER_5_ENERGY_MACRO,
    "carrier_shutdown": ResolutionTier.TIER_5_ENERGY_MACRO,
    "green_telco": ResolutionTier.TIER_5_ENERGY_MACRO,
}


@dataclass
class TierSpecification:
    tier: ResolutionTier
    tier_number: int
    name: str
    target_domains: List[str]
    retained_kpis: List[str]
    pruned_kpis: List[str]
    ns3_modules: List[str]
    fidelity_factor_pct: int
    graph_scope_factor_pct: int
    typical_sim_latency_ms: float
    description: str


TIER_SPECIFICATIONS: Dict[ResolutionTier, TierSpecification] = {
    ResolutionTier.TIER_1_MACRO_TOPOLOGY: TierSpecification(
        tier=ResolutionTier.TIER_1_MACRO_TOPOLOGY,
        tier_number=1,
        name="Tier 1: Macro-Topology & Resilience",
        target_domains=["Link Outages", "Fiber Cuts", "TI-LFA Fast Reroute", "CSPF Convergence"],
        retained_kpis=[
            "link_status (UP/DOWN)",
            "link_propagation_delay_ms",
            "total_capacity_gbps",
            "device_adjacency_matrix",
            "interface_ip_addresses"
        ],
        pruned_kpis=[
            "rf_carrier_frequency_ghz",
            "rssi_snr_decibels",
            "hitless_acm_modulation",
            "queue_drop_byte_counters",
            "packet_payload_bytes",
            "antenna_azimuth_elevation"
        ],
        ns3_modules=[
            "ns3::PointToPointHelper",
            "ns3::Ipv4GlobalRoutingHelper",
            "ns3::DropTailQueue<Packet>"
        ],
        fidelity_factor_pct=25,
        graph_scope_factor_pct=100,
        typical_sim_latency_ms=75.0,
        description="Preserves full global network graph for path recalculation, but abstracts all physical RF and packet queues into idealized delay/bandwidth pipes."
    ),

    ResolutionTier.TIER_2_QUEUE_DYNAMICS: TierSpecification(
        tier=ResolutionTier.TIER_2_QUEUE_DYNAMICS,
        tier_number=2,
        name="Tier 2: Queue & Congestion Dynamics",
        target_domains=["Traffic Surges", "Stadium Flash Crowds", "Bufferbloat", "Active Queue Management"],
        retained_kpis=[
            "ingress_traffic_rate_mbps",
            "port_mtu_bytes",
            "queue_max_packets",
            "queue_discipline_type (CoDel/RED/DropTail)",
            "burst_duration_ms",
            "traffic_interarrival_distribution"
        ],
        pruned_kpis=[
            "atmospheric_rain_rate_mm_hr",
            "rf_carrier_tuning_ghz",
            "atpc_power_boost_dbm",
            "remote_core_router_fib_tables"
        ],
        ns3_modules=[
            "ns3::DropTailQueueDisc",
            "ns3::CoDelQueueDisc",
            "ns3::OnOffApplication",
            "ns3::PacketSink"
        ],
        fidelity_factor_pct=55,
        graph_scope_factor_pct=50,
        typical_sim_latency_ms=350.0,
        description="Prunes outer edge networks to isolate congested transport bottlenecks; accurately models microsecond packet queues and drop probabilities."
    ),

    ResolutionTier.TIER_3_PHYSICAL_RF: TierSpecification(
        tier=ResolutionTier.TIER_3_PHYSICAL_RF,
        tier_number=3,
        name="Tier 3: Physical mmWave/Microwave Channel",
        target_domains=["ITU-R P.838 Rain Fading", "Hitless ACM Modulation", "ATPC Power", "V/E-Band Blockage"],
        retained_kpis=[
            "carrier_frequency_ghz",
            "channel_bandwidth_mhz",
            "rain_intensity_mm_hr",
            "hop_distance_km",
            "active_mcs_constellation",
            "rssi_dbm",
            "snr_db",
            "tx_power_dbm",
            "itu_r_p838_constants (k, alpha)"
        ],
        pruned_kpis=[
            "multi_hop_core_ip_routing",
            "unrelated_switch_ports",
            "unrelated_traffic_slices",
            "optical_transponder_wavelengths"
        ],
        ns3_modules=[
            "ns3::PointToPointChannel",
            "ns3::DynamicRateErrorModel",
            "ns3::PropagationLossModel",
            "ns3::AcmModulationController"
        ],
        fidelity_factor_pct=75,
        graph_scope_factor_pct=25,
        typical_sim_latency_ms=650.0,
        description="Isolates the targeted wireless hop; computes exact ITU-R atmospheric absorption and SNR boundaries to evaluate hitless modulation drops."
    ),

    ResolutionTier.TIER_4_URLLC_MICRO: TierSpecification(
        tier=ResolutionTier.TIER_4_URLLC_MICRO,
        tier_number=4,
        name="Tier 4: 5G/6G Slice SLA & Jitter Micro-Packet",
        target_domains=["URLLC Delay Budgets (<1.5ms)", "Mission-Critical Teleprotection", "Packet Delay Variation"],
        retained_kpis=[
            "5qi_qos_identifier",
            "packet_delay_budget_ms",
            "per_packet_arrival_timestamps_us",
            "priority_queue_weights",
            "jitter_window_ms",
            "packet_error_rate_threshold"
        ],
        pruned_kpis=[
            "non_critical_best_effort_payloads",
            "long_term_hourly_weather_trends",
            "device_internal_cpu_temperatures"
        ],
        ns3_modules=[
            "ns3::FlowMonitorHelper",
            "ns3::PriorityQueueDisc",
            "ns3::UdpEchoClientHelper",
            "ns3::HighResolutionTimer"
        ],
        fidelity_factor_pct=95,
        graph_scope_factor_pct=70,
        typical_sim_latency_ms=1150.0,
        description="Full packet-by-packet microsecond discrete event simulation; tracks individual flow delay sums, p99 jitter, and packet delay budget compliance."
    ),

    ResolutionTier.TIER_5_ENERGY_MACRO: TierSpecification(
        tier=ResolutionTier.TIER_5_ENERGY_MACRO,
        tier_number=5,
        name="Tier 5: Green Telco & Energy Optimization",
        target_domains=["Off-Peak Carrier Sleep", "Sector Shutdown", "Power Consumption Reduction (Watts)"],
        retained_kpis=[
            "transponder_power_draw_watts",
            "sleep_mode_power_watts",
            "hourly_aggregate_demand_mbps",
            "active_carrier_count",
            "residual_headroom_capacity_mbps"
        ],
        pruned_kpis=[
            "microsecond_packet_timestamps",
            "individual_packet_drops",
            "ber_curves",
            "rf_phase_noise"
        ],
        ns3_modules=[
            "ns3::SteadyStateCapacityChecker",
            "ns3::EnergyModelHelper"
        ],
        fidelity_factor_pct=20,
        graph_scope_factor_pct=30,
        typical_sim_latency_ms=35.0,
        description="Abstracts packet mechanics entirely into continuous capacity pipes; evaluates power consumption vs aggregate traffic load in real time."
    ),
}


@dataclass
class ScopedSimulationProfile:
    tier: ResolutionTier
    tier_number: int
    tier_name: str
    scenario_goal: str
    fidelity_factor_pct: int
    estimated_sim_latency_ms: float
    retained_kpis: List[str]
    pruned_kpis: List[str]
    activated_ns3_modules: List[str]
    total_nodes_available: int
    scoped_nodes_count: int
    total_links_available: int
    scoped_links_count: int
    target_device_scoped: Dict[str, Any]
    governor_digest: str


class SimulationResolutionGovernor:
    """
    Governor responsible for pruning and scoping TFS network state
    into an optimal fidelity tier for NS-3 simulation.
    """

    def __init__(self, default_tier: Optional[ResolutionTier] = None):
        self.default_tier = default_tier

    def resolve_tier(self, goal_or_scenario: str, requested_tier: Optional[str] = None) -> ResolutionTier:
        if requested_tier:
            req_clean = requested_tier.strip().lower()
            for t in ResolutionTier:
                if t.value == req_clean or t.name.lower() == req_clean:
                    return t

        goal_clean = goal_or_scenario.strip().lower().replace("-", "_")
        if goal_clean in GOAL_TO_TIER_MAP:
            return GOAL_TO_TIER_MAP[goal_clean]

        for k, v in GOAL_TO_TIER_MAP.items():
            if k in goal_clean:
                return v

        return self.default_tier or ResolutionTier.TIER_3_PHYSICAL_RF

    def scope_simulation(
        self,
        tfs_topology: Dict[str, Any],
        scenario_goal: str,
        requested_tier: Optional[str] = None,
        target_device_uuid: str = "f676623c-1a65-54bd-b1e8-279c8a6d8a1c"
    ) -> ScopedSimulationProfile:
        tier = self.resolve_tier(scenario_goal, requested_tier)
        spec = TIER_SPECIFICATIONS[tier]

        raw_nodes = tfs_topology.get("nodes", []) if isinstance(tfs_topology, dict) else []
        raw_links = tfs_topology.get("links", []) if isinstance(tfs_topology, dict) else []
        total_nodes = len(raw_nodes) or 34
        total_links = len(raw_links) or 34

        scope_factor = spec.graph_scope_factor_pct / 100.0
        scoped_nodes_cnt = max(2, int(total_nodes * scope_factor))
        scoped_links_cnt = max(1, int(total_links * scope_factor))

        scoped_dev = {
            "uuid": target_device_uuid,
            "device_model": "Ceragon MultiHaul TG (MH-T261 / ctu-96)",
            "tier_active": tier.value,
            "included_kpis": spec.retained_kpis,
            "discarded_kpis": spec.pruned_kpis
        }

        digest = (
            f"🎯 Resolution Governor: Selected [{spec.name}] ({spec.fidelity_factor_pct}% fidelity). "
            f"Retained {len(spec.retained_kpis)} critical KPIs for goal '{scenario_goal}', "
            f"pruning {len(spec.pruned_kpis)} non-essential metrics. "
            f"Graph scoped to {scoped_nodes_cnt}/{total_nodes} nodes ({spec.graph_scope_factor_pct}% scope). "
            f"Estimated NS-3 execution compute latency: {spec.typical_sim_latency_ms} ms."
        )

        logger.info(digest)

        return ScopedSimulationProfile(
            tier=tier,
            tier_number=spec.tier_number,
            tier_name=spec.name,
            scenario_goal=scenario_goal,
            fidelity_factor_pct=spec.fidelity_factor_pct,
            estimated_sim_latency_ms=spec.typical_sim_latency_ms,
            retained_kpis=spec.retained_kpis,
            pruned_kpis=spec.pruned_kpis,
            activated_ns3_modules=spec.ns3_modules,
            total_nodes_available=total_nodes,
            scoped_nodes_count=scoped_nodes_cnt,
            total_links_available=total_links,
            scoped_links_count=scoped_links_cnt,
            target_device_scoped=scoped_dev,
            governor_digest=digest
        )
