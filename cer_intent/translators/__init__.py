"""Translator package — Maps all 14 IntentTypes to standards-compliant YANG/RESTCONF translators."""
from cer_intent.translators.capacity_translator import CapacityTranslator
from cer_intent.translators.qos_translator import QoSTranslator
from cer_intent.translators.modulation_translator import ModulationTranslator
from cer_intent.translators.resilience_translator import ResilienceTranslator
from cer_intent.translators.slice_translator import SliceTranslator
from cer_intent.translators.energy_translator import EnergyTranslator
from cer_intent.translators.advanced_translators import (
    SyncTranslator,
    SecurityTranslator,
    TSNTranslator,
    BeamformingTranslator,
    MultiBandTranslator,
    OranXhaulTranslator,
    InterferenceTranslator,
    TelemetryTranslator,
)
from cer_intent.intent_schema import IntentType

TRANSLATOR_MAP = {
    IntentType.CAPACITY:     CapacityTranslator,
    IntentType.QOS:          QoSTranslator,
    IntentType.MODULATION:   ModulationTranslator,
    IntentType.RESILIENCE:   ResilienceTranslator,
    IntentType.SLICE:        SliceTranslator,
    IntentType.ENERGY:       EnergyTranslator,
    IntentType.SYNC:         SyncTranslator,
    IntentType.SECURITY:     SecurityTranslator,
    IntentType.TSN:          TSNTranslator,
    IntentType.BEAMFORMING:  BeamformingTranslator,
    IntentType.MULTIBAND:    MultiBandTranslator,
    IntentType.ORAN_XHAUL:   OranXhaulTranslator,
    IntentType.INTERFERENCE: InterferenceTranslator,
    IntentType.TELEMETRY:    TelemetryTranslator,
}

TRANSLATION_MAPPING_CATALOG = [
    {
        "intent_type": "capacity",
        "translator": "CapacityTranslator",
        "yang_module": "ceragon-radio-link",
        "standards": ["ETSI EN 302 217", "IETF RFC 8561 (MW Radio Link)", "TM Forum TMF921"],
        "mapped_parameters": ["min_throughput_gbps", "channel_bandwidth_mhz (28/56/112/2000 MHz)", "mrmc_script_id", "acm_enabled"],
        "description": "Maps throughput SLAs to Ceragon MRMC script profiles, channel bandwidths, and ACM constellation bounds.",
    },
    {
        "intent_type": "qos",
        "translator": "QoSTranslator",
        "yang_module": "ceragon-qos",
        "standards": ["IETF RFC 4594 (DiffServ)", "3GPP TS 23.501 (5QI)", "ITU-T Y.1541"],
        "mapped_parameters": ["traffic_class (EF/AF4/AF3/AF2/BE)", "dscp_marking (46/34/26/18/0)", "max_latency_ms", "preferred_path"],
        "description": "Maps latency, jitter, and loss SLAs to DiffServ traffic classes, DSCP codepoints, WRED queues, and path steering.",
    },
    {
        "intent_type": "modulation",
        "translator": "ModulationTranslator",
        "yang_module": "ceragon-radio-link",
        "standards": ["ITU-R P.838 (Rain Attenuation)", "ETSI TR 102 311 (Adaptive Coding & Modulation)"],
        "mapped_parameters": ["min_modulation (QPSK..2048QAM)", "max_modulation", "acm_enabled", "tx_power_dbm"],
        "description": "Maps spectral efficiency and weather-hardening intents to ACM floor/ceiling bounds and ATPC TX power.",
    },
    {
        "intent_type": "resilience",
        "translator": "ResilienceTranslator",
        "yang_module": "ceragon-protection",
        "standards": ["ITU-T G.8031 / G.8032", "IETF RFC 7490 (TI-LFA)", "UNITY-6G D2.4 MARL Recovery"],
        "mapped_parameters": ["protection_mode (1+1-hsb / space-diversity / frequency-diversity / marl-autonomic-mesh)", "wtr_seconds", "holdoff_ms"],
        "description": "Maps availability SLAs to 1+1 Hot Standby, Space/Frequency Diversity, TI-LFA fast reroute, and MARL mesh healing.",
    },
    {
        "intent_type": "slice",
        "translator": "SliceTranslator",
        "yang_module": "ceragon-slice",
        "standards": ["IETF RFC 9543 (Network Slices)", "3GPP TS 28.541 (NRM)", "UNITY-6G D3.1 Table 2-1 (F1-U DSCP)"],
        "mapped_parameters": ["slice_name", "slice_type (eMBB/URLLC/mMTC)", "sst", "dscp_midhaul", "vlan_id", "sched_cfg (PRB ratio)"],
        "description": "Maps 6G slice requests to IEEE 802.1Q VLAN bridges, 3GPP SST/5QI profiles, and O-RAN F1-U midhaul DSCP sockets.",
    },
    {
        "intent_type": "energy",
        "translator": "EnergyTranslator",
        "yang_module": "instantaneous-device-energy-tid",
        "standards": ["ETSI ES 203 228 (EE)", "UNITY-6G D3.1 Section 4.2.5 (TID Energy YANG)", "ServiceDLC Pause"],
        "mapped_parameters": ["energy_mode (saving/eco-sleep)", "sleep_sectors", "off_peak_window", "target_power_w"],
        "description": "Maps Green-6G sustainability intents to sector TX sleep schedules, ATPC backoff, and ServiceDLC PAUSED state.",
    },
    {
        "intent_type": "sync",
        "translator": "SyncTranslator",
        "yang_module": "ceragon-sync-ptp",
        "standards": ["ITU-T G.8275.1 / G.8275.2 (PTP Telecom Profile)", "ITU-T G.8262 (SyncE)", "IEEE 1588v2"],
        "mapped_parameters": ["ptp_profile (G.8275.1)", "clock_mode (T-BC/T-TC/T-GM)", "synce_enabled", "esmc_ssm_ql (QL-PRC)", "max_phase_error_ns (<=1500ns)"],
        "description": "Maps 6G TDD & O-RAN phase/frequency timing intents to IEEE 1588v2 Telecom Boundary Clocks and SyncE ESMC.",
    },
    {
        "intent_type": "security",
        "translator": "SecurityTranslator",
        "yang_module": "ieee802-dot1ae-macsec",
        "standards": ["IEEE 802.1AE (MACsec)", "IEEE 802.1X-2020 (MKA)", "NIST FIPS 203 (ML-KEM-768 PQC)"],
        "mapped_parameters": ["macsec_enabled", "cipher_suite (AES-GCM-256)", "mka_sak_rekey_seconds", "quantum_safe_kex (ML-KEM-768-Hybrid)"],
        "description": "Maps zero-trust transport security intents to line-rate AES-GCM-256 MACsec payload encryption and PQC key exchange.",
    },
    {
        "intent_type": "tsn",
        "translator": "TSNTranslator",
        "yang_module": "ieee802-dot1q-sched",
        "standards": ["IEEE 802.1Qbv (Time-Aware Shaper)", "IEEE 802.1Qbu (Frame Preemption)", "IEEE 802.1CB (FRER)"],
        "mapped_parameters": ["tas_8021qbv_enabled", "frame_preemption_8021qbu", "cycle_time_us", "urllc_slot_us", "pfifofast_band0_strict_urllc"],
        "description": "Maps deterministic sub-ms URLLC intents to 802.1Qbv Gate Control Lists, 802.1Qbu Express MAC preemption, and PfifoFast Band-0 priority.",
    },
    {
        "intent_type": "beamforming",
        "translator": "BeamformingTranslator",
        "yang_module": "radio-bridge-tg-radio-dn",
        "standards": ["IEEE 802.11ad / 802.11ay (60 GHz V-Band)", "Siklu MultiHaul TG (Terragraph)", "Clixon RFC 8040"],
        "mapped_parameters": ["antenna_array_profile (massive2)", "frequency_ghz (58.32..64.80 GHz)", "steer_azimuth_deg", "steer_elevation_deg", "ignite_candidate_bridge"],
        "description": "Maps 60 GHz V-Band phased-array beam steering, NLOS obstacle bypass, and Terragraph/MARL candidate bridge ignition.",
    },
    {
        "intent_type": "multiband",
        "translator": "MultiBandTranslator",
        "yang_module": "ceragon-multiband-booster",
        "standards": ["IETF RFC 8561 (Multi-Carrier MW)", "Ceragon Multi-Band Booster L1 Bonding", "ITU-R P.530"],
        "mapped_parameters": ["eband_carrier (80 GHz, 2000 MHz)", "microwave_carrier (18 GHz, 112 MHz)", "aggregated_throughput_gbps", "urllc_pinning"],
        "description": "Maps ultra-high-capacity + high-availability intents to 80 GHz E-Band + 18 GHz Microwave L1 carrier bonding with URLLC pinning.",
    },
    {
        "intent_type": "oran_xhaul",
        "translator": "OranXhaulTranslator",
        "yang_module": "oran-wg4-ecpri-xhaul",
        "standards": ["O-RAN.WG4.CUS (Split 7.2x eCPRI)", "O-RAN.WG4.CTI (Cooperative Transport)", "UNITY-6G D3.1 F1-U"],
        "mapped_parameters": ["functional_split (7.2x)", "ecpri_iq_compression (BFP9/BFP12)", "T12_max_oneway_us", "f1u_midhaul_dscp_socket", "oran_cti_enabled"],
        "description": "Maps O-RAN fronthaul/midhaul intents to eCPRI BFP9 IQ compression, WG4 delay windows (T12/T2a), and CTI slot reporting.",
    },
    {
        "intent_type": "interference",
        "translator": "InterferenceTranslator",
        "yang_module": "ceragon-xpic-interference",
        "standards": ["ETSI EN 302 217-2 (XPIC & Co-Channel)", "ITU-R F.1108", "ATPC Closed-Loop"],
        "mapped_parameters": ["xpic_enabled (30 dB isolation)", "atpc_coordinated", "dynamic_channel_switch_dfc", "target_sinr_db"],
        "description": "Maps SINR and interference mitigation intents to XPIC dual-pol cancellation, coordinated ATPC, and hitless DFC channel switching.",
    },
    {
        "intent_type": "telemetry",
        "translator": "TelemetryTranslator",
        "yang_module": "ietf-yang-push-twamp",
        "standards": ["IETF RFC 8641 (YANG Push)", "IETF RFC 5357 (TWAMP)", "ITU-T Y.3090 / 3GPP TS 28.561 (Digital Twin)"],
        "mapped_parameters": ["yang_push_rfc8641 (periodic + on-change)", "twamp_rfc5357_probe", "digital_twin_ns3_preflight"],
        "description": "Maps observability and pre-flight validation intents to RFC 8641 YANG Push streams, TWAMP probes, and NS-3 Digital Twin simulations.",
    },
]


def get_translator(intent_type: IntentType):
    cls = TRANSLATOR_MAP.get(intent_type)
    if cls is None:
        raise ValueError(f"No translator registered for intent type: {intent_type}")
    return cls()
