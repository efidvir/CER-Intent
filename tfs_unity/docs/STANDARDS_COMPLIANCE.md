# Standards Compliance & Telecommunications Traceability Matrix

This framework anchors on official telecommunications specifications to provide a standardized, carrier-grade Network Digital Twin (NDT) implementation.

---

## 1. 3GPP Standards Mapping

### 3GPP TS 28.561: Management aspects of Network Digital Twins (Release 19 SA5)
- **NDTI Lifecycle Management**: Implemented in `tfs_digital_twin_api.py` via class `NetworkDigitalTwinInstance`.
  - Operations supported: `CreateNDTI`, `InitializeNDTI`, `SyncNDTI`, `UpdateNDTI`, `ExecuteExperiment`, `RetrieveResults`, `TerminateNDTI`.
  - State machine transitions conform exactly to TS 28.561 Section 5.
- **NDT Data Exposure**: Exposes normalized operational state via standard JSON schemas conforming to 3GPP MnS stage 2/3 definitions.
- **Experimental Execution**: Sandboxed what-if scenario invocation mapped to 3GPP experiment execution procedures.

### 3GPP TR 28.915: Study on management aspects of Network Digital Twin
- Maps standardized telecommunications use cases:
  - *Use Case 1: Dynamic Traffic Surges, Buffer Congestion & QoS Bandwidth Resizing*
  - *Use Case 2: Topology Perturbations, Fiber Cuts & TI-LFA Fast Rerouting*
  - *Use Case 3: Green Telco Off-Peak Energy Optimization & Carrier Sleep Modes*
  - *Use Case 4: 5G/6G Multi-Tenant Network Slice Admission & PDB/PER Verification*
  - *Use Case 5: Channel Degradation & Predictive SLA Outage Prevention (e.g., Rain Fade)*
  - *Use Case 6: Closed-Loop Optimization with Automated Pre-Commit Safety Verification*

### 3GPP TS 29.222: Common API Framework for 3GPP Northbound APIs (CAPIF)
- **CAPIF Core Function (CCF)**: Registered service API `TelecomDigitalTwin_DTI_API` via endpoint `GET /api/v1/capif/service-apis`.
- **API Exposing Function (AEF)**: Profile with OAuth 2.0 / mTLS security methods and discrete resource paths.

---

## 2. ITU-T Standards Mapping

### ITU-T Recommendation Y.3090: Digital Twin Network - Requirements and Architecture
- **Physical Network Layer**: Physical Ceragon MultiHaul TG (60 GHz) and CeraOS Microwave nodes.
- **Twin Data Layer**: Telemetry ingestion via RFC 8040 RESTCONF, NETCONF RFC 6241, and TFS Context Service CockroachDB datastore.
- **Network Twin Model Layer**: NS-3 C++ Discrete-Event engine (QueueDisc, PointToPoint, CSMA) + analytical physics propagation models (ITU-R P.838 mmWave rain attenuation, free space path loss, oxygen absorption).
- **Network Application Layer**: TM Forum TMF921 Intent engine, AI optimization agents, and visual network dashboards.
- **SBI & NBI Compliance**: Open, standardized northbound and southbound interface decoupling.

---

## 3. IETF / IRTF NMRG Standards Mapping

### draft-paillisse-nmrg-performance-digital-twin-02
- **Digital Twin Interface (DTI)**: Formalized as `POST /api/v1/dti/scenarios`.
- **Input Specifications**: Topology baseline, perturbation vector, traffic matrix, simulation duration.
- **Output Specifications**: Performance metrics (throughput, delay, loss, jitter), SLA violation flags, and recommended remediation configurations.

### draft-zcz-nmrg-digitaltwin-data-collection
- Protocol bindings evaluated and implemented:
  - RESTCONF (RFC 8040)
  - NETCONF (RFC 6241 / RFC 6022)
  - gNMI / Streaming Telemetry
  - YANG Push (RFC 8641 / RFC 8639)

---

## 4. TM Forum Open Digital Architecture (ODA) Mapping

| TM Forum Open API | Framework Endpoint | Purpose & Mapping |
| :--- | :--- | :--- |
| **TMF921 Intent Management** | `POST /api/v1/tmf/tmf921/intent` | Ingests declarative SLA contracts and target QoS expressions. |
| **TMF639 Resource Inventory** | `GET /api/v1/tmf/tmf639/resource` | Projects the multi-vendor equipment graph as standardized `PhysicalResource` records. |
| **TMF640 Service Activation** | Managed via TFS 2PC | Translates service creation into candidate datastore mutations. |
| **TMF642 Alarm Management** | DTI Anomaly Alerts | Generates proactive degradation warnings prior to SLA breaches. |
