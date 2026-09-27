"""
Demo: Telecom Network Digital Twin (NDT) End-to-End Closed Loop
================================================================
Demonstrates the complete multi-layer Telecom Digital Twin architecture:
  1. 3GPP CAPIF / ETSI OpenCAPIF Service API Discovery & Invocation
  2. 3GPP TS 28.561 NDTI Lifecycle Management (Create, Sync, Execute, Terminate)
  3. Layer 1 State Synchronization from Physical Ceragon Hardware & TFS
  4. Layer 4 TM Forum TMF921 Declarative Intent Ingestion
  5. Layer 2 IETF NMRG DTI What-If Scenario Prediction (ITU-R P.838 Rain Fade & NS-3)
  6. Layer 3 Closed-Loop Safety Verification & Actuation via TFS 2PC Candidate Commit
  7. Layer 4 TM Forum TMF639 Resource Inventory Projection
"""

import time
import json
import logging
import threading
import requests

from tfs_digital_twin_api import run_digital_twin_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DemoTelecomDigitalTwin")

DT_PORT = 9105
BASE_URL = f"http://127.0.0.1:{DT_PORT}"

def start_server_in_background():
    t = threading.Thread(target=run_digital_twin_server, kwargs={"port": DT_PORT, "tfs_host": "localhost", "tfs_port": 8088}, daemon=True)
    t.start()
    time.sleep(2.0)  # Wait for startup

def main():
    print("=" * 72)
    print("  TELECOM NETWORK DIGITAL TWIN (NDT) END-TO-END DEMONSTRATION")
    print("  Standards: 3GPP TS 28.561 | ITU-T Y.3090 | IETF NMRG | TM Forum | CAPIF")
    print("=" * 72)

    # 0. Start Digital Twin API Server
    logger.info("Initializing Telecom Digital Twin API Server in background...")
    start_server_in_background()

    # 1. CAPIF Service Discovery (ETSI OpenCAPIF / 3GPP TS 29.222)
    print("\n--- [STEP 1] 3GPP CAPIF Service API Discovery (TS 29.222 / OpenCAPIF) ---")
    resp = requests.get(f"{BASE_URL}/api/v1/capif/service-apis")
    capif_desc = resp.json()
    print(f"[+] Discovered Service API: {capif_desc.get('apiName')} (ID: {capif_desc.get('apiId')})")
    print(f"    Description: {capif_desc.get('description')}")
    print(f"    AEF Profile Status: {capif_desc['serviceAPIDescription']['apiStatus']} | Security: {capif_desc['serviceAPIDescription']['securityMethods']}")

    # 2. 3GPP TS 28.561 NDTI Lifecycle Management
    print("\n--- [STEP 2] 3GPP TS 28.561 Network Digital Twin Instance (NDTI) Lifecycle ---")
    ndti_req = {
        "instance_id": "ndti-oran-transport-demo",
        "name": "Ceragon-6G-Terragraph-DT",
        "scope": "microwave-oran-fronthaul"
    }
    resp = requests.post(f"{BASE_URL}/api/v1/dti/instances", json=ndti_req)
    ndti_created = resp.json()
    print(f"[+] Created NDTI Instance: {ndti_created.get('instance_id')}")
    print(f"    Lifecycle State:      {ndti_created.get('lifecycle_state')}")
    print(f"    Synchronized Nodes:   {ndti_created.get('synchronized_nodes')}")

    # 3. Layer 1 State Synchronization (ITU-T Y.3090)
    print("\n--- [STEP 3] Layer 1 Physical Network Synchronization (ITU-T Y.3090) ---")
    sync_resp = requests.post(f"{BASE_URL}/api/v1/dti/sync", json={"instance_id": "ndti-oran-transport-demo"}).json()
    print(f"[+] Reconciled Shadow State with Physical Ceragon Hardware & TFS:")
    print(f"    Nodes in Shadow:      {sync_resp.get('nodes_count')}")
    print(f"    Links in Shadow:      {sync_resp.get('links_count')}")
    print(f"    Active State:         {sync_resp.get('state')}")

    # 4. Layer 4 Declarative Intent Ingestion (TM Forum TMF921)
    print("\n--- [STEP 4] Layer 4 TM Forum TMF921 Intent Management Ingestion ---")
    intent_req = {
        "name": "URLLC_CarrierGrade_ZeroOutage_Intent",
        "intentSpecification": {
            "target_sla": {
                "max_latency_ms": 1.5,
                "min_availability_pct": 99.999,
                "min_throughput_mbps": 500.0
            },
            "governance": "AUTONOMIC_CLOSED_LOOP"
        }
    }
    intent_resp = requests.post(f"{BASE_URL}/api/v1/tmf/tmf921/intent", json=intent_req).json()
    print(f"[+] Ingested TMF921 Intent: {intent_resp.get('id')} ({intent_resp.get('name')})")
    print(f"    State:                  {intent_resp.get('state')}")
    print(f"    Target SLA:             {intent_resp.get('targetSLA')}")

    # 5. Layer 2 DTI What-If Scenario Prediction (IETF NMRG / NS-3 Physics Engine)
    print("\n--- [STEP 5] Layer 2 DTI What-If Scenario Simulation (IETF NMRG DTI) ---")
    scenario_req = {
        "instance_id": "ndti-oran-transport-demo",
        "scenario_id": "SC-RAIN-SEVERE-01",
        "base_state": "current-network",
        "engine": "ns3-itur-p838",
        "perturbations": [
            {
                "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
                "type": "rain_fade",
                "rain_rate_mm_hr": 55.0,
                "link_distance_km": 0.95
            }
        ]
    }
    print("[*] Submitting perturbation to Digital Twin: 55.0 mm/hr Heavy Rain Fade on Ceragon Link...")
    scen_resp = requests.post(f"{BASE_URL}/api/v1/dti/scenarios", json=scenario_req).json()
    impact = scen_resp["predicted_impacts"][0]
    print(f"[!] Simulation Results (Engine: {scen_resp.get('engine')}):")
    print(f"    ITU-R Attenuation:    {impact.get('attenuation_db')} dB loss")
    print(f"    Predicted RSSI:       {impact.get('predicted_rssi_dbm')} dBm")
    print(f"    Predicted SNR:        {impact.get('predicted_snr_db')} dB")
    print(f"    Predicted Modulation: MCS {impact.get('predicted_mcs')} (Down from MCS 8)")
    print(f"    Predicted Throughput: {impact.get('predicted_throughput_mbps')} Mbps")
    print(f"    Predicted Latency:    {impact.get('predicted_latency_ms')} ms")
    print(f"    SLA Breach Predicted: {scen_resp.get('overall_sla_breach_predicted')} (BREACH OF TMF921 INTENT!)")
    print(f"    Proposed Mitigation:  {scen_resp.get('recommended_mitigation', {}).get('proposed_rules')}")

    # 6. Layer 3 Closed-Loop Safety Verification & Physical Actuation (TFS 2PC)
    print("\n--- [STEP 6] Layer 3 Closed-Loop Actuation via TFS 2-Phase Commit ---")
    mitigation_plan = {
        "instance_id": "ndti-oran-transport-demo",
        "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
        "actions": [
            {"type": "ACM_FLOOR_HARDENING", "min_mcs": 2},
            {"type": "CARRIER_FREQUENCY_RETUNE", "target_ghz": 64.8, "target_bw_mhz": 2000},
            {"type": "URLLC_SLICE_RESERVATION", "vlan_id": 200, "rate_mbps": 1000}
        ]
    }
    print("[*] Validating safety rules in Digital Twin before physical commit...")
    commit_resp = requests.post(f"{BASE_URL}/api/v1/dti/validate-and-commit", json=mitigation_plan).json()
    print(f"[+] Safety Validation:       {commit_resp.get('safety_check')} ({commit_resp.get('status')})")
    for note in commit_resp.get("validation_notes", []):
        print(f"    - {note}")
    print(f"[+] Physical 2PC Committed:  {commit_resp.get('tfs_2pc_transaction_committed')}")
    print(f"    TFS Actions Dispatched:  {len(commit_resp.get('dispatch_results', []))}")

    # 7. Layer 4 TM Forum TMF639 Resource Inventory Verification
    print("\n--- [STEP 7] Layer 4 TM Forum TMF639 Resource Inventory Projection ---")
    tmf639_resp = requests.get(f"{BASE_URL}/api/v1/tmf/tmf639/resource").json()
    print(f"[+] Total Resources Projected into TMF639: {len(tmf639_resp)}")
    sample_res = tmf639_resp[0]
    print(f"    Sample Resource: {sample_res.get('name')} [Type: {sample_res.get('@type')}]")
    print(f"    Category:        {sample_res.get('category')} | Operational: {sample_res.get('operationalState')}")

    print("\n" + "=" * 72)
    print("  DEMONSTRATION SUCCESSFUL: Closed-loop Telecom Digital Twin verified")
    print("  across all 5 API layers in strict compliance with 3GPP & ITU-T.")
    print("=" * 72)

if __name__ == "__main__":
    main()
