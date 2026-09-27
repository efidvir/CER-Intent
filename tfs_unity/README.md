# TFS-Unity: ETSI TeraFlowSDN Northbound Adapter & Telecom Digital Twin Framework

TFS-Unity provides a carrier-grade Northbound Interface (NBI) adapter, Telecom Network Digital Twin (NDT) engine, and co-simulation bridge connecting **ETSI TeraFlowSDN (TFS)** with discrete-event network simulators (notably **NS-3**), telecom digital twin orchestrators, and AI/ML optimization agents.

It anchors on international telecom standards:
- **3GPP TS 28.561** (Release 19 SA5: Management aspects of Network Digital Twins)
- **3GPP TR 28.915** (Study on management aspects of Network Digital Twin)
- **ITU-T Y.3090** (Digital Twin Network: Requirements and Architecture)
- **IETF/IRTF NMRG** (`draft-irtf-nmrg-network-digital-twin-arch`, `draft-paillisse-nmrg-performance-digital-twin-02`)
- **TM Forum Open APIs / ODA** (TMF921 Intent Management, TMF639 Resource Inventory)
- **3GPP TS 29.222 / ETSI OpenCAPIF** (Common API Framework for API discovery, governance, and invocation)

---

## 5-Layer Telecom Digital Twin Architecture

```
 +-------------------------------------------------------------------------------+
 |  Layer 5: API Governance & Exposure (3GPP CAPIF / ETSI OpenCAPIF)             |
 |  OAuth2 / mTLS Authentication, Service API Discovery & Policy Enforcement     |
 +-------------------------------------------------------------------------------+
          |
          v
 +-------------------------------------------------------------------------------+
 |  Layer 4: Northbound Intent & Inventory Abstraction (TM Forum ODA)           |
 |  - TMF921 Intent Management (Autonomous SLA & Closed-Loop Declarations)       |
 |  - TMF639 Resource Inventory (Ceragon & Transport Resource Projections)      |
 +-------------------------------------------------------------------------------+
          |
          v
 +-------------------------------------------------------------------------------+
 |  Layer 2: Digital Twin Interface (DTI - IETF NMRG & 3GPP TS 28.561)          |
 |  - NDTI Lifecycle State Machine (Create, Init, Sync, Experiment, Terminate)  |
 |  - What-If Scenario Evaluation (Perturbations, Rain Fade, Traffic Surges)     |
 |  - Multi-fidelity Simulation Hooks (NS-3 C++ Discrete-Event & Analytical)    |
 +-------------------------------------------------------------------------------+
     |                                                                   ^
     | Layer 3: Actuation (Pre-commit Safety)                            | Layer 1: Sync
     v                                                                   |
 +-------------------------------------------------------------------------------+
 |  ETSI TeraFlowSDN Controller (Context & Device Service 2PC Engine)            |
 +-------------------------------------------------------------------------------+
     |                                                                   ^
     | Southbound 2PC Candidate Commit                                   | RESTCONF / Telemetry
     v                                                                   |
 +-------------------------------------------------------------------------------+
 |  Layer 1: Physical Network Transport (Ceragon Networks)                      |
 |  - MultiHaul TG MH-T261 / MH-N366 Terragraph mmWave (60 GHz)                 |
 |  - EtherHaul EH-8010FX / EH-2500FX E-Band (70/80 GHz)                        |
 |  - CeraOS IP-50 / IP-20 Microwave (XPIC, 4096-QAM, Hitless ACM)              |
 +-------------------------------------------------------------------------------+
```

---

## Key Modules

### 1. `tfs_digital_twin_api.py` (Digital Twin Interface & Lifecycle)
A carrier-grade HTTP/REST service implementing the complete **Digital Twin Interface (DTI)**:
- **3GPP TS 28.561 NDTI Lifecycle**: Manages `NetworkDigitalTwinInstance` state machines (`NULL` $\rightarrow$ `INITIALIZING` $\rightarrow$ `SYNCHRONIZED` $\rightarrow$ `EXECUTING_EXPERIMENT` $\rightarrow$ `TERMINATED`).
- **Layer 1 State Reconciliation**: Reconciles live physical radio parameters (carrier frequencies, ACM MCS, RSSI, SNR, TX power, modem temperatures) from Ceragon hardware via TFS.
- **Layer 2 What-If Scenario Engine**: Simulates adverse perturbations (e.g. ITU-R P.838 rain fade, interference, bursty traffic) and predicts SLA breaches, throughput degradation, latency spikes, and packet loss.
- **Layer 3 Closed-Loop Actuation**: Performs pre-commit safety boundary validation before dispatching configuration rules into TFS's 2-Phase Commit (2PC) candidate datastore.
- **Layer 4 TM Forum Projection**:
  - `POST /api/v1/tmf/tmf921/intent`: Ingests declarative high-level SLA intents.
  - `GET /api/v1/tmf/tmf639/resource`: Exposes synchronized physical transport inventory.
- **Layer 5 CAPIF Registration**:
  - `GET /api/v1/capif/service-apis`: Standardized 3GPP TS 29.222 / OpenCAPIF service API descriptor.

### 2. `tfs_api_client.py` (Northbound REST Client)
Connects directly to ETSI TeraFlowSDN Northbound REST API (`:8088`):
- Dynamic topology queries (`/tfs-api/context/{ctx}/topology/{topo}`).
- Device telemetry extraction for Ceragon wireless nodes.
- High-level configuration dispatchers: `set_radio_tuning()`, `set_acm_floor()`, `set_slice_qos()`.
- Resilient offline fallback using `6g_transport_tfs_descriptors.json`.

### 3. `tfs_topology_to_ns3.py` (NS-3 Scenario Generator)
Translates live TFS topologies into executable C++ NS-3 simulation scenarios:
- Classifies Point-to-Point wired Ethernet vs. Ceragon wireless mmWave links.
- Maps operational ACM modulation to physical data rates and error models.
- Generates 5G traffic flows using `ns3::OnOffHelper` and `ns3::PacketSinkHelper`.
- Exports NetAnim visualization XML.

### 4. `ns3_tfs_runtime_bridge.py` (Runtime Co-Simulation Daemon)
- Synchronizes live link capacities between TFS and NS-3 via IPC file `ns3_link_state.json`.
- Hosts a REST server on `:9099` for external runtime triggers.

### 5. `demo_telecom_digital_twin.py` (End-to-End Verification Harness)
Validates the complete 7-step digital twin workflow:
1. CAPIF Service API Discovery (TS 29.222)
2. 3GPP TS 28.561 NDTI Instance Creation
3. ITU-T Y.3090 State Synchronization
4. TM Forum TMF921 Intent Ingestion
5. IETF NMRG DTI What-If Scenario Prediction (Rain Fade Simulation)
6. Closed-Loop Safety Verification & Physical 2PC Actuation
7. TM Forum TMF639 Resource Inventory Verification

---

## Quickstart & Usage

### 1. Run the Telecom Digital Twin Demo
```bash
python demo_telecom_digital_twin.py
```

### 2. Start the Standalone Digital Twin API Server
```bash
python tfs_digital_twin_api.py 9100
```

### 3. Query Standards-Compliant Endpoints

**Discover CAPIF Services (ETSI OpenCAPIF):**
```bash
curl -X GET http://localhost:9100/api/v1/capif/service-apis
```

**Evaluate a What-If Scenario (IETF NMRG DTI):**
```bash
curl -X POST http://localhost:9100/api/v1/dti/scenarios \
     -H "Content-Type: application/json" \
     -d '{
       "instance_id": "ndti-ceragon-transport-01",
       "scenario_id": "SC-RAIN-01",
       "engine": "ns3-itur-p838",
       "perturbations": [
         {
           "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
           "type": "rain_fade",
           "rain_rate_mm_hr": 50.0,
           "link_distance_km": 0.8
         }
       ]
     }'
```

**Submit a Declarative Intent (TM Forum TMF921):**
```bash
curl -X POST http://localhost:9100/api/v1/tmf/tmf921/intent \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ZeroOutage_URLLC_Transport_Intent",
       "intentSpecification": {
         "target_sla": {"max_latency_ms": 1.5, "min_availability_pct": 99.999}
       }
     }'
```

**Validate and Actuate Closed-Loop Mitigation:**
```bash
curl -X POST http://localhost:9100/api/v1/dti/validate-and-commit \
     -H "Content-Type: application/json" \
     -d '{
       "instance_id": "ndti-ceragon-transport-01",
       "device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c",
       "actions": [
         {"type": "ACM_FLOOR_HARDENING", "min_mcs": 2},
         {"type": "CARRIER_FREQUENCY_RETUNE", "target_ghz": 64.8, "target_bw_mhz": 2000},
         {"type": "URLLC_SLICE_RESERVATION", "vlan_id": 200, "rate_mbps": 1000}
       ]
     }'
```

---

## Directory Structure

```
tfs-unity/
├── README.md                      # Architecture & standards guide
├── .gitignore                     # Git ignore rules
├── tfs_digital_twin_api.py        # Telecom Digital Twin Server (DTI, 3GPP, CAPIF, TMF)
├── demo_telecom_digital_twin.py   # End-to-end 7-step verification harness
├── tfs_api_client.py              # Northbound REST API client for TFS
├── tfs_topology_to_ns3.py         # C++ NS-3 scenario generator
├── ns3_tfs_runtime_bridge.py      # Runtime co-simulation daemon (:9099)
├── demo_ns3_tfs_control.py        # Hardware control & telemetry verification
└── scratch/                       # Generated NS-3 simulation scripts (.cc)
```
