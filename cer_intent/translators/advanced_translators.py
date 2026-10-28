"""
Advanced 6G / O-RAN / Millimeter-Wave / TSN Intent Translators
==============================================================
Implements standards-compliant intent-to-configuration translators for:
  1. SyncTranslator         (ITU-T G.8275.1 / G.8275.2 PTP + G.8262 SyncE)
  2. SecurityTranslator     (IEEE 802.1AE MACsec AES-GCM-256 + MKA + PQC KEX)
  3. TSNTranslator          (IEEE 802.1Qbv TAS + 802.1Qbu Preemption + PfifoFast Band-0)
  4. BeamformingTranslator  (60 GHz V-Band massive2 Phased-Array Steering + MARL Mesh)
  5. MultiBandTranslator    (80 GHz E-Band + Microwave L1 Hitless Carrier Bonding)
  6. OranXhaulTranslator    (O-RAN WG4 Split 7.2x eCPRI BFP9 + WG5 F1-U DSCP + CTI)
  7. InterferenceTranslator (XPIC Dual-Pol Cancellation + Coordinated ATPC + DFC)
  8. TelemetryTranslator    (RFC 8641 YANG Push + RFC 5357 TWAMP + NS-3 Digital Twin)
"""
from __future__ import annotations

from typing import List, Dict, Any
from cer_intent.intent_schema import Intent, DeviceConfig, TranslationResult
from cer_intent.translators.base_translator import BaseTranslator


class SyncTranslator(BaseTranslator):
    """Translates ITU-T G.8275.1 / G.8275.2 PTP & SyncE timing synchronization intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        ptp_profile = params.get("ptp_profile") or "G.8275.1"
        synce_enabled = params.get("synce_enabled", True)
        clock_mode = params.get("clock_mode", "T-BC")
        max_phase_error_ns = params.get("max_phase_error_ns", 1500)
        ssm_ql = params.get("ssm_quality_level", "QL-PRC")
        domain_number = 24 if ptp_profile == "G.8275.1" else 44

        configs = []
        for device in target_devices:
            cfg = {
                "ptp_profile": ptp_profile,
                "ptp_domain": domain_number,
                "clock_mode": clock_mode,
                "synce_enabled": synce_enabled,
                "esmc_ssm_ql": ssm_ql,
                "max_phase_error_ns": max_phase_error_ns,
                "announce_interval_log2": -3,
                "sync_interval_log2": -4,
                "holdover_spec": "ITU-T G.8273.2 Class-B",
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="sync",
                yang_module="ceragon-sync-ptp",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Provisioned ITU-T {ptp_profile} ({clock_mode}, Domain {domain_number}) + "
            f"{'SyncE (' + ssm_ql + ')' if synce_enabled else 'PTP-only'} with phase accuracy "
            f"≤ ±{max_phase_error_ns} ns across {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class SecurityTranslator(BaseTranslator):
    """Translates IEEE 802.1AE MACsec & quantum-safe key exchange security intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        macsec = params.get("macsec_enabled", True)
        cipher = params.get("encryption_algorithm") or "AES-GCM-256"
        if cipher == "AES-256":
            cipher = "AES-GCM-256"
        elif cipher == "AES-128":
            cipher = "AES-GCM-128"
        key_rotation_s = params.get("key_rotation_seconds", 3600)
        pqc_kex = params.get("quantum_safe_kex", True)
        replay_window = params.get("replay_protection_window", 64)

        configs = []
        for device in target_devices:
            cfg = {
                "macsec_enabled": macsec,
                "cipher_suite": cipher,
                "mka_sak_rekey_seconds": key_rotation_s,
                "quantum_safe_kex": "ML-KEM-768-Hybrid" if pqc_kex else "ECDH-P384",
                "replay_protection_window": replay_window,
                "confidentiality_offset": params.get("confidentiality_offset", 0),
                "line_rate_zero_jitter": True,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="security",
                yang_module="ieee802-dot1ae-macsec",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Enabled IEEE 802.1AE MACsec ({cipher}, MKA SAK rotation={key_rotation_s}s, "
            f"KEX={'ML-KEM-768 PQC' if pqc_kex else 'Standard'}) on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class TSNTranslator(BaseTranslator):
    """Translates IEEE 802.1Qbv Time-Aware Shaper, 802.1Qbu Preemption & PfifoFast Band-0 URLLC intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        tas_enabled = params.get("tas_8021qbv_enabled", True)
        preemption = params.get("frame_preemption_8021qbu", True)
        cycle_us = params.get("cycle_time_us", 1000)
        urllc_slot_us = params.get("urllc_slot_us", 250)
        guard_us = params.get("guard_band_us", 15)
        max_lat_ms = params.get("max_e2e_latency_ms", 0.5)
        frer_enabled = params.get("frer_8021cb_enabled", False)
        be_slot_us = max(100, cycle_us - urllc_slot_us - guard_us)

        configs = []
        for device in target_devices:
            cfg = {
                "tas_8021qbv_enabled": tas_enabled,
                "frame_preemption_8021qbu": preemption,
                "pfifofast_band0_strict_urllc": True,
                "tos_band0_match": "0xc0 (AC_VO / DSCP 46 EF)",
                "cycle_time_us": cycle_us,
                "gate_control_list": [
                    {"slot": "GCL-0-URLLC-Express", "gate_mask": "10000000", "duration_us": urllc_slot_us},
                    {"slot": "GCL-1-Shared-eMBB-BE", "gate_mask": "01111111", "duration_us": be_slot_us},
                    {"slot": "GCL-2-Guard-Band", "gate_mask": "00000000", "duration_us": guard_us},
                ],
                "max_e2e_latency_ms": max_lat_ms,
                "frer_8021cb_enabled": frer_enabled,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="tsn",
                yang_module="ieee802-dot1q-sched",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Configured IEEE 802.1Qbv TAS (cycle={cycle_us}µs, URLLC Express={urllc_slot_us}µs, "
            f"guard={guard_us}µs) + {'802.1Qbu Frame Preemption + ' if preemption else ''}"
            f"PfifoFast Band-0 strict priority (target ≤{max_lat_ms} ms) on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class BeamformingTranslator(BaseTranslator):
    """Translates 60 GHz V-Band phased-array beam steering & Siklu Terragraph mesh bridge intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        array_profile = params.get("antenna_array_profile", "massive2")
        freq_ghz = params.get("frequency_ghz", 60.48)
        azimuth = params.get("steer_azimuth_deg", 0.0)
        elevation = params.get("steer_elevation_deg", 0.0)
        tracking = params.get("beam_tracking_mode", "adaptive-closed-loop")
        bridge_id = params.get("ignite_candidate_bridge")

        # Map frequency GHz to IEEE 802.11ad/ay V-Band channel index
        vband_channels = {58.32: 1, 60.48: 2, 62.64: 3, 64.80: 4}
        channel_num = vband_channels.get(round(float(freq_ghz), 2), 2)

        configs = []
        for device in target_devices:
            cfg = {
                "antenna_array_profile": array_profile,
                "frequency_ghz": freq_ghz,
                "frequency_mhz": int(freq_ghz * 1000),
                "vband_channel": channel_num,
                "steer_azimuth_deg": azimuth,
                "steer_elevation_deg": elevation,
                "beam_tracking_mode": tracking,
                "tx_power_control": "auto",
                "ignite_candidate_bridge": bridge_id,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="beamforming",
                yang_module="radio-bridge-tg-radio-dn",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Steered {array_profile} 60GHz V-Band phased array (Ch {channel_num}: {freq_ghz} GHz, "
            f"Azimuth {azimuth:+.1f}°, Elevation {elevation:+.1f}°, mode={tracking})"
            + (f" + Ignited MARL Bridge '{bridge_id}'" if bridge_id else "")
            + f" on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class MultiBandTranslator(BaseTranslator):
    """Translates Multi-Band Carrier Aggregation (80 GHz E-Band + Microwave) L1 bonding intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        eband_ghz = params.get("eband_carrier_ghz", 80.0)
        mw_ghz = params.get("microwave_carrier_ghz", 18.0)
        agg_gbps = params.get("aggregated_throughput_gbps", 12.5)
        bonding_mode = params.get("bonding_mode", "L1-hitless-aggregation")
        urllc_pinning = params.get("urllc_pinning", "microwave-anchor")

        configs = []
        for device in target_devices:
            cfg = {
                "bonding_group_id": f"mb-group-{device['id']}",
                "bonding_mode": bonding_mode,
                "eband_carrier": {"frequency_ghz": eband_ghz, "bw_mhz": 2000, "capacity_gbps": 10.0, "role": "high-capacity-booster"},
                "microwave_carrier": {"frequency_ghz": mw_ghz, "bw_mhz": 112, "capacity_gbps": 2.5, "role": "high-availability-anchor"},
                "aggregated_throughput_gbps": agg_gbps,
                "urllc_pinning": urllc_pinning,
                "hitless_rain_failover": True,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="multiband",
                yang_module="ceragon-multiband-booster",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Configured {bonding_mode} Multi-Band Carrier Aggregation bonding {eband_ghz} GHz E-Band (2000 MHz) "
            f"+ {mw_ghz} GHz Microwave (112 MHz) for {agg_gbps} Gbps combined capacity "
            f"(URLLC pinned to {urllc_pinning}) on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class OranXhaulTranslator(BaseTranslator):
    """Translates O-RAN WG4 Open Fronthaul (Split 7.2x eCPRI) & WG5 F1-U Midhaul intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        split = params.get("functional_split", "7.2x")
        iq_comp = params.get("iq_compression_format", "BFP9")
        t12_us = params.get("max_fronthaul_oneway_us", 100)
        cti = params.get("cti_enabled", True)
        f1u_dscp = params.get("f1u_dscp_mapping", 46)

        compression_ratio = {"BFP9": "2.9:1", "BFP12": "2.2:1", "BFP14": "1.9:1", "uncompressed": "1:1"}.get(iq_comp, "2.9:1")

        configs = []
        for device in target_devices:
            cfg = {
                "functional_split": split,
                "ecpri_iq_compression": iq_comp,
                "compression_ratio": compression_ratio,
                "delay_management_profile": {
                    "T12_max_oneway_us": t12_us,
                    "T2a_max_dl_uplane_us": int(t12_us * 2.2),
                    "Ta3_max_ul_uplane_us": int(t12_us * 1.8),
                },
                "f1u_midhaul_dscp_socket": f1u_dscp,
                "oran_cti_enabled": cti,
                "cti_report_interval_ms": 5 if cti else 0,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="oran_xhaul",
                yang_module="oran-wg4-ecpri-xhaul",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Configured O-RAN Split {split} xHaul (eCPRI {iq_comp} [{compression_ratio} compression], "
            f"T12 ≤ {t12_us}µs, F1-U DSCP {f1u_dscp}, CTI={'Active (5ms)' if cti else 'Disabled'}) "
            f"on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class InterferenceTranslator(BaseTranslator):
    """Translates XPIC dual-pol interference cancellation, ATPC & Dynamic Channel Switch intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        xpic = params.get("xpic_enabled", True)
        atpc = params.get("atpc_coordinated", True)
        dfc = params.get("dynamic_channel_switch", True)
        target_sinr = params.get("target_sinr_db", 28.0)

        configs = []
        for device in target_devices:
            cfg = {
                "xpic_enabled": xpic,
                "xpic_cross_pol_isolation_db": 30.0 if xpic else 0.0,
                "atpc_coordinated": atpc,
                "atpc_target_rx_level_dbm": -42.0,
                "dynamic_channel_switch_dfc": dfc,
                "target_sinr_db": target_sinr,
                "adaptive_dfe_equalizer": True,
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="interference",
                yang_module="ceragon-xpic-interference",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Activated {'XPIC (30 dB cross-pol cancellation)' if xpic else 'Single-Pol'}"
            + (", Coordinated ATPC (-42 dBm target RX)" if atpc else "")
            + (", Hitless DFC channel avoidance" if dfc else "")
            + f" for target SINR ≥ {target_sinr} dB on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)


class TelemetryTranslator(BaseTranslator):
    """Translates RFC 8641 YANG Push streaming telemetry, TWAMP probes & NS-3 Digital Twin pre-flight intents."""

    def translate(self, intent: Intent, target_devices: List[dict]) -> TranslationResult:
        params = intent.parameters
        cadence_ms = params.get("yang_push_cadence_ms", 1000)
        twamp = params.get("twamp_probe_enabled", True)
        dt_preflight = params.get("digital_twin_preflight", True)
        scenario = params.get("what_if_scenario", "traffic_surge")

        configs = []
        for device in target_devices:
            cfg = {
                "yang_push_rfc8641": {
                    "periodic_cadence_ms": cadence_ms,
                    "on_change_dampening_ms": 200,
                    "xpath_subscriptions": [
                        "/radio-link-cfg/carrier/acm",
                        "/interfaces-state/interface/statistics",
                        "/qos-config/queue-statistics",
                    ],
                },
                "twamp_rfc5357_probe": {
                    "enabled": twamp,
                    "probe_interval_ms": 100,
                    "dscp": 46,
                },
                "digital_twin_ns3_preflight": {
                    "enabled": dt_preflight,
                    "what_if_scenario": scenario,
                    "itu_y3090_sync": True,
                },
            }
            configs.append(DeviceConfig(
                device_id=device["id"],
                config_type="telemetry",
                yang_module="ietf-yang-push-twamp",
                parameters=cfg,
                intent_id=intent.intent_id,
            ))

        explanation = (
            f"Configured RFC 8641 YANG Push ({cadence_ms}ms cadence + on-change)"
            + (", RFC 5357 TWAMP microsecond delay probes" if twamp else "")
            + (f", and ITU-T Y.3090 NS-3 Digital Twin pre-flight ('{scenario}')" if dt_preflight else "")
            + f" on {len(configs)} device(s)."
        )
        return self._finalize(intent, configs, explanation)
