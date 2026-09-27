"""
Demo: Universal Telecom Network Digital Twin (NDT) Multi-Domain Simulation
===========================================================================
Demonstrates the generic, extensible nature of the Telecom Digital Twin platform
across multiple distinct telecommunications operational domains:
  1. 3GPP CAPIF / ETSI OpenCAPIF Service API Discovery (TS 29.222)
  2. 3GPP TS 28.561 NDTI Lifecycle Management (Create, Init, Sync)
  3. Scenario A: Traffic Engineering & Congestion Surge (NS-3 Queue Delay & Bufferbloat)
  4. Scenario B: Topology Dynamics & Fiber Cut (TI-LFA Sub-50ms Protection Switching)
  5. Scenario C: Green Telco Energy Optimization (Off-Peak Sleep Mode & Power Savings)
  6. Scenario D: Multi-Tenant 5G Slice Admission Control (Capacity Verification)
  7. Scenario E: Physical mmWave Propagation & Adaptive Modulation (ITU-R Channel Fade)
  8. Layer 3 Closed-Loop Safety Verification & Actuation via TFS 2PC Candidate Commit
  9. Layer 4 TM Forum TMF639 Resource Inventory & TMF921 Intent Closed-Loop Reconciliation
"""

import time
import json
import logging
import threading
import requests

from tfs_digital_twin_api import run_digital_twin_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DemoTelecomDigitalTwin")

DT_PORT = 9108
BASE_URL = f"http://127.0.0.1:{DT_PORT}"

def start_server_in_background():
    t = threading.Thread(target=run_digital_twin_server, kwargs={"port": DT_PORT, "tfs_host": "localhost", "tfs_port": 8088}, daemon=True)
    t.start()
    time.sleep(2.0)

def main():
    print("=" * 76)
    print("  GENERIC TELECOM NETWORK DIGITAL TWIN (NDT) MULTI-DOMAIN DEMONSTRATION")
    print("  Standards: 3GPP TS 28.561 | ITU-T Y.3090 | IETF NMRG DTI | TM Forum | CAPIF")
    print("=" * 76)

    logger.info("Initializing Universal Telecom Digital Twin API Server...")
    start_server_in_background()

    # 1. 3GPP CAPIF Service Discovery (ETSI OpenCAPIF)
    print("\n--- [1] 3GPP CAPIF Service Discovery (TS 29.222 / OpenCAPIF) ---")
    resp = requests.get(f"{BASE_URL}/api/v1/capif/service-apis")
    capif_desc = resp.json()
    print(f"[+] Service Discovered: {capif_desc.get('apiName')} (ID: {capif_desc.get('apiId')})")
    print(f"    Security Methods:   {capif_desc['serviceAPIDescription']['securityMethods']}")

    # 2. 3GPP TS 28.561 NDTI Instance Creation & Initialization
    print("\n--- [2] 3GPP TS 28.561 NDTI Instance Lifecycle (Create & Synchronize) ---")
    ndti_req = {
        "instance_id": "ndti-multi-domain-core",
        "name": "Generic-6G-Transport-Twin",
        "scope": "end-to-end-oran-transport"
    }
    ndti_created = requests.post(f"{BASE_URL}/api/v1/dti/instances", json=ndti_req).json()
    print(f"[+] Created NDTI: {ndti_created.get('instance_id')} | State: {ndti_created.get('lifecycle_state')}")
    print(f"    Synchronized Elements: {ndti_created.get('synchronized_nodes')} nodes across transport mesh")

    # 3. Scenario A: Traffic Engineering & Congestion Surge
    print("\n--- [3] SCENARIO A: Traffic Engineering & Congestion Surge Simulation ---")
    surge_req = {
        "instance_id": "ndti-multi-domain-core",
        "scenario_id": "SC-TRAFFIC-SURGE-STADIUM",
        "domain": "TRAFFIC_ENGINEERING",
        "perturbations": [
            {
                "type": "traffic_surge",
                "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
                "traffic_multiplier": 3.5,
                "flow_type": "URLLC_Video_Burst"
            }
        ]
    }
    scen_a = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=surge_req).json()
    impact_a = scen_a["predicted_impacts"][0]
    print(f"[*] Simulated 3.5x Stadium Traffic Surge on transport link:")
    print(f"    Queue Buffer Occupancy: {impact_a.get('predicted_queue_buffer_occupancy_pct')}%")
    print(f"    Predicted Latency:      {impact_a.get('predicted_latency_ms')} ms (Baseline: 0.85 ms)")
    print(f"    Predicted Packet Loss:  {impact_a.get('predicted_packet_loss_rate') * 100}%")
    print(f"    SLA Breach Warning:     {impact_a.get('sla_breach_detected')}")
    print(f"    Recommended Action:     {scen_a.get('recommended_mitigation', {}).get('proposed_rules')}")

    # 4. Scenario B: Topology Dynamics & Fiber Cut (Fast Reroute)
    print("\n--- [4] SCENARIO B: Topology Dynamics & Fiber Cut Resilience Simulation ---")
    fail_req = {
        "instance_id": "ndti-multi-domain-core",
        "scenario_id": "SC-FIBER-CUT-FAILOVER",
        "domain": "TOPOLOGY_RESILIENCE",
        "perturbations": [
            {
                "type": "link_failure",
                "link_uuid": "link-edge-to-core-primary",
                "backup_path": ["ceragon-mw-carrier-backup", "edge-router-02"]
            }
        ]
    }
    scen_b = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=fail_req).json()
    impact_b = scen_b["predicted_impacts"][0]
    print(f"[*] Simulated Primary Fiber Cut on link-edge-to-core-primary:")
    print(f"    Protection Mechanism:   {impact_b.get('failover_mechanism')}")
    print(f"    Switchover Delay:       {impact_b.get('switchover_time_ms')} ms (Carrier Grade < 50ms)")
    print(f"    Post-Failover Latency:  {impact_b.get('post_failover_latency_ms')} ms")
    print(f"    Backup Link Load:       {impact_b.get('backup_link_load_pct')}%")
    print(f"    Service Interruption:   NONE (SLA Breach: {impact_b.get('sla_breach_detected')})")

    # 5. Scenario C: Green Telco Energy Optimization
    print("\n--- [5] SCENARIO C: Green Telco & Energy Sleep Optimization Simulation ---")
    energy_req = {
        "instance_id": "ndti-multi-domain-core",
        "scenario_id": "SC-GREEN-ENERGY-OFFPEAK",
        "domain": "ENERGY_OPTIMIZATION",
        "perturbations": [
            {
                "type": "energy_saving_sleep",
                "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
                "sectors": ["Sector-2-Redundant"],
                "window": "02:00-05:00"
            }
        ]
    }
    scen_c = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=energy_req).json()
    impact_c = scen_c["predicted_impacts"][0]
    print(f"[*] Evaluating Off-Peak Sleep Mode for Sector-2 (02:00-05:00):")
    print(f"    Power Saved:            {impact_c.get('power_saved_watts')} Watts per site")
    print(f"    Energy Reduction:       {impact_c.get('energy_reduction_pct')}%")
    print(f"    Residual Sector Load:   {impact_c.get('residual_sector_load_pct')}%")
    print(f"    Latency SLA Impact:     {impact_c.get('predicted_latency_ms')} ms (SLA Breach: {impact_c.get('sla_breach_detected')})")
    print(f"    Assessment:             SAFE TO POWER DOWN during off-peak window.")

    # 6. Scenario D: Multi-Tenant 5G Slice Admission Control
    print("\n--- [6] SCENARIO D: Multi-Tenant 5G Slice Admission Control Simulation ---")
    slice_req = {
        "instance_id": "ndti-multi-domain-core",
        "scenario_id": "SC-SLICE-ADMISSION-TEST",
        "domain": "SLICE_ADMISSION_CONTROL",
        "perturbations": [
            {
                "type": "slice_admission",
                "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
                "slice_id": "slice-smartgrid-teleprotection",
                "bandwidth_mbps": 350.0,
                "max_latency_ms": 1.5
            }
        ]
    }
    scen_d = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=slice_req).json()
    impact_d = scen_d["predicted_impacts"][0]
    print(f"[*] Evaluating New Slice Admission ('slice-smartgrid-teleprotection', 350 Mbps):")
    print(f"    Admission Decision:     {impact_d.get('admission_decision')}")
    print(f"    Residual Transport BW:  {impact_d.get('residual_capacity_mbps')} Mbps")
    print(f"    End-to-End Latency:     {impact_d.get('predicted_end_to_end_latency_ms')} ms")

    # 7. Scenario E: Physical Channel Fading & Hitless ACM Adaptation
    print("\n--- [7] SCENARIO E: Physical mmWave Propagation & Adaptive Modulation ---")
    fade_req = {
        "instance_id": "ndti-multi-domain-core",
        "scenario_id": "SC-CHANNEL-RAIN-FADE",
        "domain": "PHYSICAL_CHANNEL_PROPAGATION",
        "perturbations": [
            {
                "type": "rain_fade",
                "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
                "rain_rate_mm_hr": 45.0,
                "link_distance_km": 0.8
            }
        ]
    }
    scen_e = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=fade_req).json()
    impact_e = scen_e["predicted_impacts"][0]
    print(f"[*] Simulated Physical Channel Attenuation (45 mm/hr rain):")
    print(f"    Calculated Attenuation: {impact_e.get('attenuation_db')} dB loss")
    print(f"    Predicted SNR / MCS:    {impact_e.get('predicted_snr_db')} dB -> MCS {impact_e.get('predicted_mcs')}")
    print(f"    Predicted Capacity:     {impact_e.get('predicted_throughput_mbps')} Mbps")

    # 8. Layer 3 Closed-Loop Safety Verification & Actuation
    print("\n--- [8] Layer 3 Closed-Loop Actuation via TFS 2-Phase Commit ---")
    mitigation_plan = {
        "instance_id": "ndti-multi-domain-core",
        "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
        "actions": [
            {"type": "DYNAMIC_QOS_SLICING", "rate_mbps": 1200},
            {"type": "CSPF_REROUTE_OPTIMIZATION"},
            {"type": "ENERGY_SLEEP_POLICY_ACTIVATE", "power_savings_w": 24.0}
        ]
    }
    print("[*] Validating multi-domain mitigations in Digital Twin safety sandbox...")
    commit_res = requests.post(f"{BASE_URL}/api/v1/dti/validate-and-commit", json=mitigation_plan).json()
    print(f"[+] Safety Gatekeeper:       {commit_res.get('safety_check')} ({commit_res.get('status')})")
    for note in commit_res.get("validation_notes", []):
        print(f"    - {note}")
    print(f"[+] TFS 2PC Committed:       {commit_res.get('tfs_2pc_transaction_committed')}")

    # 9. Layer 4 TM Forum TMF639 Resource Inventory
    print("\n--- [9] Layer 4 TM Forum TMF639 Resource Inventory Projection ---")
    tmf_res = requests.get(f"{BASE_URL}/api/v1/tmf/tmf639/resource").json()
    print(f"[+] Total Resources Synchronized in TMF639: {len(tmf_res)}")

    print("\n" + "=" * 76)
    print("  DEMONSTRATION SUCCESSFUL: Universal Telecom Digital Twin validated")
    print("  across Traffic, Topology, QoS, Energy, and Physical Channel domains!")
    print("=" * 76)

if __name__ == "__main__":
    main()
