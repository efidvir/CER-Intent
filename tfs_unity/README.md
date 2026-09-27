# TFS-Unity: ETSI TeraFlowSDN Northbound Adapter & NS-3 Co-Simulation Framework

TFS-Unity provides a carrier-grade Northbound Interface (NBI) adapter and co-simulation bridge connecting **ETSI TeraFlowSDN (TFS)** with discrete-event network simulators (notably **NS-3**) and external algorithmic orchestrators (AI/ML controllers, Intent-Based engines, digital twins).

It enables bi-directional closed-loop control:
1. **Northbound Ingestion & Telemetry**: Interrogate ETSI TeraFlowSDN contexts, topologies, devices, and operational telemetry (e.g. Ceragon wireless radio links, RSSI, SNR, ACM modulations, modem temperatures).
2. **Topology Synthesis**: Automatically translate complex multi-technology SDN topologies into production-ready C++ NS-3 simulation scenarios.
3. **Runtime Co-Simulation**: Dynamically synchronize live physical/simulated link degradation and ACM fluctuations between TFS and NS-3.
4. **Northbound Control Dispatch**: Dispatch configuration rules (RF frequency tuning, ACM floor hardening, 5G URLLC/eMBB slicing) from external applications through TFS's 2-Phase Commit (2PC) engine down to transport hardware.

---

## Architecture Overview

```
 +-------------------------------------------------------+
 |   External Applications / AI-ML / Intent Engine       |
 +-------------------------------------------------------+
          |                                  ^
          | Northbound REST Control (:9099)  | Telemetry & State
          v                                  |
 +-------------------------------------------------------+
 |                 TFS-Unity Framework                   |
 |  - ns3_tfs_runtime_bridge.py (Co-Simulation Daemon)   |
 |  - tfs_api_client.py         (Northbound REST Client) |
 |  - tfs_topology_to_ns3.py    (C++ Scenario Generator) |
 +-------------------------------------------------------+
      |                          |                  ^
      | C++ Scenario             | REST NBI (:8088) | Telemetry Polling
      v                          v                  |
+-------------+          +-------------------------------+
|    NS-3     |          |       ETSI TeraFlowSDN        |
|  Simulator  |          | - Context Service (Cockroach) |
| (C++ Nodes) |          | - Device Service (2PC Engine) |
+-------------+          +-------------------------------+
                                         |
                                         v Southbound (REST / NETCONF)
                                 +-------------------------------+
                                 | Ceragon Transport Elements    |
                                 | IP-50 / IP-20 / Point-to-Point|
                                 +-------------------------------+
```

---

## Key Modules

### 1. `tfs_api_client.py`
A robust, universal client for the ETSI TeraFlowSDN Northbound REST API:
- **Topology Discovery**: Discovers all active Contexts and Topologies via `/tfs-api/context/{context_uuid}/topology/{topology_uuid}`.
- **Normalized Topology Model**: Parses devices, endpoints, and bidirectional links into structured dictionaries ready for simulation or graph analysis.
- **Ceragon Radio Telemetry Extraction**: Decodes device configuration rules and operational state:
  - Carrier Frequency (e.g. 64.8 GHz / Channel 4)
  - Adaptive Coding & Modulation (ACM) state (e.g. MCS 0 to MCS 12)
  - Received Signal Strength Indication (RSSI in dBm)
  - Signal-to-Noise Ratio (SNR in dB)
  - Transmit Power (dBm) and Modem Temperature (°C)
- **Northbound Configuration Dispatch**:
  - `set_radio_tuning(device_uuid, frequency_ghz, bandwidth_mhz)`: Re-tunes radio frequency channels.
  - `set_acm_floor(device_uuid, min_mcs)`: Hardens the ACM modulation floor against link degradation.
  - `set_slice_qos(device_uuid, slice_name, vlan_id, bandwidth_mbps)`: Configures end-to-end transport network slices.
- **Resilient Fallback**: Automatically falls back to offline descriptors (`6g_transport_tfs_descriptors.json`) when operating in isolated lab environments or air-gapped testbeds.

### 2. `tfs_topology_to_ns3.py`
Automated C++ code generator that translates TFS topologies into high-fidelity NS-3 simulation scripts:
- **Node & Interface Mapping**: Instantiates `ns3::NodeContainer` with exact TFS device names and UUIDs.
- **Wireless Link Modeling**: Auto-detects Ceragon microwave/millimeter-wave hops and applies:
  - High-bandwidth, low-latency propagation delay models (`ns3::ConstantSpeedPropagationDelayModel`).
  - Link rates mapped directly from operational ACM modulation (up to 10 Gbps for mmWave).
  - Configurable error models (`ns3::RateErrorModel`) simulating wireless packet loss.
- **Wired Ethernet Modeling**: Sets standard Point-to-Point links with CSMA or GbE attributes.
- **5G / URLLC Traffic Injection**: Adds `ns3::OnOffHelper` and `ns3::PacketSinkHelper` traffic generators to simulate synthetic user-plane flows across the transport topology.
- **Visualization & Export**: Generates NetAnim XML (`AnimationInterface`) and co-simulation state files (`ns3_link_state.json`).

### 3. `ns3_tfs_runtime_bridge.py`
Bi-directional runtime daemon for dynamic co-simulation:
- **Telemetry Polling Engine**: Continuously polls TFS device telemetry every 1 second and syncs link capacities and channel quality into a shared IPC state (`ns3_link_state.json`).
- **REST Control Server (`:9099`)**: Exposes northbound endpoints for NS-3 simulation hooks or external controllers:
  - `GET /status`: Query daemon status and active topology statistics.
  - `POST /control/rf_tune`: Dynamically trigger radio carrier retuning in TFS.
  - `POST /control/acm_floor`: Adjust ACM modulation floor in real time.
  - `POST /control/slice`: Deploy network slices with rate limits.
  - `POST /events/ns3_degrade`: Simulate rain fade or link degradation events.

### 4. `demo_ns3_tfs_control.py`
A comprehensive demonstration and validation harness:
- Validates TFS connectivity.
- Discovers contexts and topologies.
- Extracts live Ceragon telemetry.
- Dispatches radio tuning, ACM hardening, and URLLC slice provisioning rules.

---

## Quickstart & Usage

### Prerequisites
- Python 3.8+
- Python packages: `requests`, `urllib3`
- (Optional for running NS-3 simulations) NS-3.36+ installed with C++17 compiler (`g++` / `clang++`).

### 1. Run the Northbound Verification Demo
```bash
python demo_ns3_tfs_control.py
```

### 2. Generate an NS-3 Simulation Script from TFS
Connect to a live TFS cluster (or run against local descriptors):
```bash
# Connect to live TFS REST NBI
python tfs_topology_to_ns3.py --tfs-host localhost --tfs-port 8088 --context admin --topology admin --output scratch/tfs_sim.cc --traffic

# Or run with offline descriptors
python tfs_topology_to_ns3.py --descriptors c:\CER_Intent\data\6g_transport_tfs_descriptors.json --output scratch/tfs_sim.cc --traffic
```

### 3. Launch the Runtime Co-Simulation Bridge
Start the daemon to enable continuous telemetry sync and external REST control:
```bash
python ns3_tfs_runtime_bridge.py --tfs-host localhost --tfs-port 8088 --listen-port 9099 --poll-interval 1.0
```

### 4. Dispatch Dynamic Control via REST API
While the runtime bridge is active, external apps or NS-3 scripts can send HTTP requests:

**Tune Radio Frequency:**
```bash
curl -X POST http://localhost:9099/control/rf_tune \
     -H "Content-Type: application/json" \
     -d '{"device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c", "frequency_ghz": 64.8, "bandwidth_mhz": 2000}'
```

**Harden ACM Modulation Floor:**
```bash
curl -X POST http://localhost:9099/control/acm_floor \
     -H "Content-Type: application/json" \
     -d '{"device_uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c", "min_mcs": 2}'
```

**Trigger Simulated Rain Fade / Degradation:**
```bash
curl -X POST http://localhost:9099/events/ns3_degrade \
     -H "Content-Type: application/json" \
     -d '{"link_uuid": "link-ctu96-ctu97", "snr_drop_db": 10.5, "new_mcs": 1}'
```

---

## Integration with Ceragon Intent-Based SDN

TFS-Unity acts as the bridge connecting high-level intent policies from the **Ceragon Intent Engine** down to the network transport layer through ETSI TeraFlowSDN:

1. **Intent Declaration**: The Intent Engine specifies high-level transport requirements (e.g. *“Ensure latency < 1ms between Node A and Node B with 99.999% availability”*).
2. **Simulation Validation (NS-3)**: TFS-Unity exports the active topology to NS-3 to simulate packet arrival, queueing latency, and channel degradation under varying weather models.
3. **Automated Remediation**: If NS-3 detects imminent link failure or SLA breach, the external engine calls TFS-Unity's control endpoints (`/control/acm_floor` or `/control/rf_tune`) to reconfigure the physical Ceragon devices via TFS.

---

## Directory Structure

```
tfs-unity/
├── README.md                  # Project documentation and guide
├── .gitignore                 # Git ignore rules
├── tfs_api_client.py          # Northbound REST API client for TFS
├── tfs_topology_to_ns3.py     # C++ NS-3 scenario generator
├── ns3_tfs_runtime_bridge.py  # Runtime co-simulation daemon (:9099)
├── demo_ns3_tfs_control.py    # Demonstration & validation script
└── scratch/                   # Generated NS-3 simulation scripts (.cc)
```
