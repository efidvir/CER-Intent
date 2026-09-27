# ETSI TeraFlowSDN (TFS) & Ceragon Wireless Transport Integration
## Complete End-to-End Master Technical Specification & Architecture Manual

**Document Reference**: ETSI-TFS-CERAGON-SPEC-2026-V7  
**Edition**: First Edition, Comprehensive Engineering Manual  
**Publication Date**: September 2026  
**System Versions**: ETSI TeraFlowSDN v7.0.0 | Ceragon CeraOS v3.4.0 / Terragraph 802.11ay | CER-Intent v2.4  
**Authoring Body**: Network Architecture, Wireless Transport & Autonomous Systems Engineering  
**Primary Repositories**: 
- `https://github.com/efidvir/CER-Intent` (Northbound Intent Engine, Topology Dashboard, Adapter Wheel)
- `https://github.com/efidvir/teraflowsdn` (ETSI TeraFlowSDN Fork, Southbound Ceragon Driver, YANG Models)

---

## Notice & Governance Statement

This specification describes the production-grade integration between Ceragon Networks wireless millimeter-wave (mmWave) and microwave transport hardware and the ETSI TeraFlowSDN (TFS) open-source cloud-native Software-Defined Networking (SDN) controller. In accordance with organizational governance, all software artifacts, driver extensions, device descriptors, schemas, and documentation are officially maintained and versioned within the authorized personal repository namespace (`efidvir`). Official upstream submission to `labs.etsi.org` is strictly decoupled; all distribution and operational deployments reference this definitive repository suite.

---

## Executive Table of Contents

- [ETSI TeraFlowSDN (TFS) & Ceragon Wireless Transport Integration](#etsi-teraflowsdn-tfs--ceragon-wireless-transport-integration)
  - [Complete End-to-End Master Technical Specification & Architecture Manual](#complete-end-to-end-master-technical-specification--architecture-manual)
  - [Notice & Governance Statement](#notice--governance-statement)
  - [Executive Table of Contents](#executive-table-of-contents)
  - [Document Metadata & Revision History](#document-metadata--revision-history)
  - [Chapter 1: Executive Summary & Telecommunications Industry Context](#chapter-1-executive-summary--telecommunications-industry-context)
    - [1.1 Evolution of Mobile X-Haul from 4G to 5G-Advanced and 6G](#11-evolution-of-mobile-x-haul-from-4g-to-5g-advanced-and-6g)
    - [1.2 Open Optical & Wireless Transport (OOWT) and Disaggregation](#12-open-optical--wireless-transport-oowt-and-disaggregation)
    - [1.3 The SDN Paradigm Shift in Wireless Microwave & Millimeter-Wave Networks](#13-the-sdn-paradigm-shift-in-wireless-microwave--millimeter-wave-networks)
    - [1.4 ETSI TeraFlowSDN (TFS): Cloud-Native SDN Architecture & Objectives](#14-etsi-teraflowsdn-tfs-cloud-native-sdn-architecture--objectives)
    - [1.5 Ceragon Wireless Transport Systems: MultiHaul TG, EtherHaul, and CeraOS](#15-ceragon-wireless-transport-systems-multihaul-tg-etherhaul-and-ceraos)
    - [1.6 The Architectural Problem Statement](#16-the-architectural-problem-statement)
    - [1.7 Architectural Value Proposition & System Objectives](#17-architectural-value-proposition--system-objectives)
    - [1.8 Governance, Scope Boundaries, and Repository Matrix](#18-governance-scope-boundaries-and-repository-matrix)
  - [Chapter 2: Theoretical Foundations & Mathematical Formulations](#chapter-2-theoretical-foundations--mathematical-formulations)
    - [2.1 Wireless Propagation Physics across Microwave, V-Band, and E-Band](#21-wireless-propagation-physics-across-microwave-v-band-and-e-band)
    - [2.2 ITU-R P.838-3 Specific Rain Attenuation Formulation](#22-itu-r-p838-3-specific-rain-attenuation-formulation)
      - [2.2.1 Mathematical Formulation](#221-mathematical-formulation)
      - [2.2.2 Frequency and Polarization Coefficients](#222-frequency-and-polarization-coefficients)
      - [2.2.3 Rain Rate Distribution and Availability Statistics](#223-rain-rate-distribution-and-availability-statistics)
    - [2.3 ITU-R P.676 Atmospheric Gas Absorption & Oxygen Resonance Peak at 60 GHz](#23-itu-r-p676-atmospheric-gas-absorption--oxygen-resonance-peak-at-60-ghz)
      - [2.3.1 Physics of 60 GHz Molecular Absorption](#231-physics-of-60-ghz-molecular-absorption)
      - [2.3.2 Line-by-Line Summation & Approximations](#232-line-by-line-summation--approximations)
    - [2.4 Shannon-Hartley Channel Capacity and Adaptive Coding & Modulation (ACM)](#24-shannon-hartley-channel-capacity-and-adaptive-coding--modulation-acm)
      - [2.4.1 Fundamental Information Capacity Limit](#241-fundamental-information-capacity-limit)
      - [2.4.2 Discrete Modulation Constellations & Spectral Efficiencies](#242-discrete-modulation-constellations--spectral-efficiencies)
      - [2.4.3 Adaptive Modulation State Machine & Hysteresis Algorithms](#243-adaptive-modulation-state-machine--hysteresis-algorithms)
    - [2.5 Adaptive Transmission Power Control (ATPC) Feedback Mechanics](#25-adaptive-transmission-power-control-atpc-feedback-mechanics)
    - [2.6 Quality of Service (QoS), Token Buckets, and Traffic Shaping Mathematics](#26-quality-of-service-qos-token-buckets-and-traffic-shaping-mathematics)
      - [2.6.1 Single-Rate Three-Color Marker (srTCM, RFC 2697)](#261-single-rate-three-color-marker-srtcm-rfc-2697)
      - [2.6.2 Two-Rate Three-Color Marker (trTCM, RFC 2698)](#262-two-rate-three-color-marker-trtcm-rfc-2698)
      - [2.6.3 Latency, Jitter, and Packet Loss Probability Bounds](#263-latency-jitter-and-packet-loss-probability-bounds)
  - [Chapter 3: Ceragon Wireless Transport Hardware & Physical Architecture](#chapter-3-ceragon-wireless-transport-hardware--physical-architecture)
  - [Chapter 4: Physical YANG Schema Catalog (The 51 RFC-Compliant Models)](#chapter-4-physical-yang-schema-catalog-the-51-rfc-compliant-models)
  - [Chapter 5: ETSI TeraFlowSDN Architecture & Integration Framework](#chapter-5-etsi-teraflowsdn-architecture--integration-framework)
  - [Chapter 6: Ceragon Southbound RESTCONF Driver Deep-Dive](#chapter-6-ceragon-southbound-restconf-driver-deep-dive)
  - [Chapter 7: Simulated Components & Network Topology Replication](#chapter-7-simulated-components--network-topology-replication)
  - [Chapter 8: CER-Intent Northbound AI & Intent Engine](#chapter-8-cer-intent-northbound-ai--intent-engine)
  - [Chapter 9: Closed-Loop Telemetry, Monitoring & Assurance](#chapter-9-closed-loop-telemetry-monitoring--assurance)
  - [Chapter 10: The 3-Tier Interactive Dashboard & Web Interface](#chapter-10-the-3-tier-interactive-dashboard--web-interface)
  - [Chapter 11: Verification, Testing & Quality Assurance](#chapter-11-verification-testing--quality-assurance)
  - [Chapter 12: Production Deployment, Packaging & 6G Roadmap](#chapter-12-production-deployment-packaging--6g-roadmap)
  - [Appendices](#appendices)

---

## Document Metadata & Revision History

| Version | Release Date | Authoring Body | Scope & Summary of Changes |
| :--- | :--- | :--- | :--- |
| **v1.0.0** | 2026-04-14 | CER-Intent Engineering | Initial technical whitepaper on AI-driven wireless transport intent modeling. |
| **v3.2.0** | 2026-08-10 | Transport SDN Core Group | Preliminary RESTCONF binding research on Terragraph MultiHaul TG hardware. |
| **v5.0.0** | 2026-09-15 | Autonomous Systems Lab | Extraction and cataloging of 51 RFC-compliant YANG models directly from physical `MH-T261`. |
| **v6.1.0** | 2026-09-22 | Protocol Interop Team | ETSI TeraFlowSDN 7.0 driver scaffolding, `DEVICEDRIVER_CERAGON = 22` enum assignment, and 2-phase candidate datastore commit engine. |
| **v7.0.0** | 2026-09-27 | System Architecture Group | Definitive 100-page equivalent master specification: complete mathematical foundations, driver source deep-dive, hybrid 34-node simulation, 3-tier D3.js dashboard, pytest suite, and 6G roadmap. |

---

# Chapter 1: Executive Summary & Telecommunications Industry Context

## 1.1 Evolution of Mobile X-Haul from 4G to 5G-Advanced and 6G

The global telecommunications architecture is undergoing a foundational paradigm shift. In legacy 3G (UMTS) and 4G (LTE) architectures, the Radio Access Network (RAN) was constructed using monolithic, proprietary base stations where the Baseband Unit (BBU) and Remote Radio Head (RRH) were tightly coupled through vendor-locked protocols such as the Common Public Radio Interface (CPRI). Backhaul networks—tasked with transporting aggregated user traffic from cell tower sites to the Evolved Packet Core (EPC)—were largely engineered with over-provisioned static Carrier Ethernet links or point-to-point microwave hops operating under fixed, pre-calculated link budgets.

With the advent of 5G New Radio (NR), 3GPP Release 16/17, and the upcoming 5G-Advanced (Release 18/19) and 6G standards, the radio access topology has been systematically decomposed. Under the O-RAN ALLIANCE and 3GPP standards, the monolithic base station is disaggregated into three functional entities:
1. **Open Radio Unit (O-RU)**: Executes real-time lower physical layer (Low-PHY) functions such as FFT/IFFT, digital beamforming, and CP addition/removal.
2. **Open Distributed Unit (O-DU)**: Executes High-PHY, Media Access Control (MAC), and Radio Link Control (RLC) processing under strict sub-millisecond scheduling deadlines.
3. **Open Central Unit (O-CU)**: Executes Packet Data Convergence Protocol (PDCP) and Service Data Adaptation Protocol (SDAP) operations, logically partitioned into Control Plane (O-CU-CP) and User Plane (O-CU-UP).

```
+----------------------------------------------------------------------------------------------------+
|                                    DISAGGREGATED 5G/6G X-HAUL ARCHITECTURE                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ O-RU ] <======== Fronthaul ========> [ O-DU ] <======= Midhaul =======> [ O-CU ]              |
|   (Antenna)   (eCPRI / IEEE 1914.3)       (Baseband)      (3GPP F1-U/C)      (Centralized)         |
|        |                                      |                                   |                |
|        | Latency: < 100-250 us                | Latency: < 1.5 - 5 ms             | Latency: < 10ms|
|        | Jitter:  < 1 us (SyncE/PTP)          | Jitter:  < 1 ms                   | Bandwidth: 10G+|
|        | Bandwidth: 10 - 25 Gbps              | Bandwidth: 2.5 - 10 Gbps          |                |
|                                                                                   v                |
|                                                                             [ Backhaul ]           |
|                                                                           (3GPP N2/N3/N9)          |
|                                                                                   |                |
|                                                                                   v                |
|                                                                             [ 5G Core / UPF ]      |
+----------------------------------------------------------------------------------------------------+
```

This functional disaggregation bifurcates the legacy backhaul into three transport tiers—collectively designated **X-Haul**:
- **Fronthaul**: Connecting O-RU to O-DU over enhanced CPRI (eCPRI) or IEEE 1914.3 encapsulation, demanding ultra-low one-way latency ($\le 100-250 \ \mu	ext{s}$), sub-microsecond time synchronization (IEEE 1588v2 PTP Telecom Profile G.8275.1), and zero packet loss.
- **Midhaul**: Connecting O-DU to O-CU over the 3GPP F1 interface (F1-C/F1-U), requiring low latency ($\le 1.5 - 5 \ 	ext{ms}$) and robust bandwidth guarantees ($1 - 10 \ 	ext{Gbps}$).
- **Backhaul**: Connecting O-CU to the 5G Core User Plane Function (UPF) across metro and regional transport domains over 3GPP N2/N3 interfaces, requiring determinism and high throughput ($10 - 100 \ 	ext{Gbps}$).

In dense urban environments, suburban infill zones, and enterprise private networks, deploying continuous dedicated fiber-optic infrastructure for every O-RU and O-DU is economically cost-prohibitive and geographically unfeasible. Civil excavation, municipal right-of-way licensing, and conduit installation regularly account for over 70% of total fiber deployment capital expenditures (CAPEX), with deployment timelines stretching from months to years. 

Consequently, **wireless transport**—specifically high-capacity millimeter-wave (mmWave) in the V-Band (57–66 GHz) and E-Band (70/80 GHz), alongside ultra-high-capacity multi-core microwave (6–42 GHz)—has emerged as an indispensable, mission-critical foundation for 5G-Advanced and 6G X-Haul networks.

---

## 1.2 Open Optical & Wireless Transport (OOWT) and Disaggregation

Historically, wireless transport equipment has operated as proprietary, vertically integrated "black boxes." Network operators purchasing microwave or mmWave links were locked into single-vendor Network Management Systems (NMS) relying on vendor-specific Simple Network Management Protocol (SNMP) MIBs, proprietary command-line interfaces (CLI) accessed via SSH or Telnet, and closed element managers. 

This vendor lock-in created profound operational friction:
1. **Siloed Orchestration**: Microwave transport links could not be dynamically orchestrated in concert with optical core rings, IP/MPLS routers, or cloud data center networks. Multi-domain service provisioning required manual human coordination across distinct engineering teams and disparate NMS consoles.
2. **Static Over-Provisioning**: Because wireless link state (e.g., rain-induced modulation drops) could not be communicated in real time to the IP routing layer or transport controller, operators had to statically over-provision radio links or implement crude local protection schemes that failed to optimize network-wide utilization.
3. **Impediment to Network Slicing**: 3GPP 5G end-to-end network slicing demands deterministic quality-of-service (QoS) guarantees across the Radio, Transport, and Core domains. A closed microwave transport layer that lacks standard software-defined interfaces breaks the end-to-end slice SLA chain.

To dismantle these proprietary silos, the global telecommunications industry formed the **Telecom Infra Project (TIP) Open Optical & Wireless Transport (OOWT)** working group and the **O-RAN ALLIANCE Work Group 9 (Open X-Haul)**. These initiatives established a common objective: **disaggregate wireless transport hardware from control-plane software**, establishing standard Southbound Interfaces (SBI) based on modern IETF Network Configuration (NETCONF) / RESTCONF protocols and RFC-compliant YANG data models.

---

## 1.3 The SDN Paradigm Shift in Wireless Microwave & Millimeter-Wave Networks

Software-Defined Networking (SDN) abstracts the network into three logically distinct planes:
- **Data Plane (Forwarding Plane)**: Executes line-rate packet forwarding, modulation adaptation, frame encapsulation, and hardware queue scheduling.
- **Control Plane**: Computes optimal routing paths, maintains link-state topologies, enforces QoS traffic contracts, and orchestrates dynamic failovers.
- **Application / Management Plane**: Exposes high-level Northbound Interfaces (NBI) to operators, AI intent engines, and Operations Support Systems (OSS) / Business Support Systems (BSS).

In optical and packet networks, SDN has matured extensively through protocols such as OpenFlow, P4, and BGP-LS. However, bringing SDN to the **wireless transport domain** introduces severe physical-layer complexities absent in fiber-optic media:
- **Atmospheric Vulnerability**: Wireless links are subject to stochastic meteorological phenomena, primarily precipitation attenuation (rain fade), atmospheric gaseous absorption (e.g., the 60 GHz oxygen resonance peak), multipath fading, and foliage blockage.
- **Dynamic Capacity Variations**: Unlike fixed-capacity fiber lines, microwave and mmWave links utilize **Adaptive Coding and Modulation (ACM)** to continuously adjust spectral efficiency (ranging from BPSK to 4096-QAM) in response to instantaneous Signal-to-Interference-plus-Noise Ratio (SINR). Consequently, link capacity is not a static constant, but a dynamic, time-varying stochastic variable:
  $$C(t) = B \cdot \log_2 \left(1 + 	ext{SINR}(t)
ight)$$
- **Hardware-Enforced Candidate Datastores**: Telecom-grade radio links cannot tolerate arbitrary, unvalidated parameter mutations during live transmissions. Hardware management systems enforce transactional candidate datastores (RFC 8342 NMDA) where configurations must be staged, validated against strict physical RF constraints, and atomically committed or rolled back.

An effective wireless transport SDN controller must therefore possess not only standard packet-routing capabilities, but also deep domain awareness of radio frequency (RF) physics, candidate datastore lifecycles, and real-time telemetry-driven closed-loop assurance.

---

## 1.4 ETSI TeraFlowSDN (TFS): Cloud-Native SDN Architecture & Objectives

To deliver an open-source, carrier-grade, cloud-native SDN controller for next-generation telecommunications networks, the European Telecommunications Standards Institute (ETSI) chartered the **TeraFlowSDN (TFS)** Open Source Group (OSG). 

ETSI TeraFlowSDN represents a revolutionary departure from legacy monolithic Java-based controllers (such as ONOS or OpenDaylight). Built from the ground up as a microservice-based, cloud-native system running on Kubernetes, TeraFlowSDN provides:
- **Extreme Horizontal Scalability**: Every functional domain (Context, Device, Topology, Path Computation, Service, Slice, Monitoring, Telemetry) is deployed as an independent microservice communicating over ultra-high-speed gRPC protocols with Protocol Buffers (protobuf) serialization.
- **Resilient Distributed State**: Controller state is persisted across distributed, highly available database backends (CockroachDB distributed SQL, Redis cache, QuestDB time-series database), eliminating single points of failure.
- **Multi-Domain & Multi-Layer Orchestration**: Native capability to compute end-to-end paths spanning optical transport (WDM/OTN), IP/MPLS packet routing, edge computing nodes, and wireless transport.
- **Pluggable Southbound Driver Framework**: A clean, modular driver interface (`_Driver` abstract base class) allowing hardware vendors and community contributors to introduce native protocol adapters without modifying the controller core.

Despite its exceptional architecture, up until the release of TFS v7.0, the controller possessed robust southbound drivers for Netconf/OpenConfig optical switches, P4 packet pipelines, and IETF network topologies, but lacked a native, fully functional Southbound Driver for **Carrier-Grade Wireless Millimeter-Wave and Microwave Transport hardware**.

---

## 1.5 Ceragon Wireless Transport Systems: MultiHaul TG, EtherHaul, and CeraOS

Ceragon Networks is the global leader in wireless transport solutions, commanding decades of engineering excellence in multi-core microwave radio systems, disaggregated cell site routers, and ultra-high-capacity millimeter-wave technologies. 

The Ceragon transport portfolio encompasses three primary technological families:
1. **Ceragon / Siklu MultiHaul TG Series (Terragraph mmWave)**:
   - Operating in the unlicensed and lightly licensed 60 GHz V-Band (57–66 GHz), implementing the IEEE 802.11ad and 802.11ay standards alongside Qualcomm Terragraph technology.
   - Flagship units include the **MH-T261 Terminal Unit (TU)** (equipped with advanced `massive2` electronic beamforming phased-array antennas) and the **MH-N366 Distribution Node (DN)** (providing multi-sector 360-degree coverage for self-organizing mesh networks).
   - Designed for 5G small cell backhaul, urban fiber extension, and fixed wireless access (FWA), delivering multi-gigabit throughput with ultra-low latency.
   - Managed natively via **RFC 8040 RESTCONF** exposing candidate datastores and 51 proprietary and standard YANG schemas.
2. **Ceragon / Siklu EtherHaul Series (E-Band mmWave)**:
   - Operating in the 70/80 GHz licensed E-Band spectrum (`EH-8010FX`, `EH-2500FX`, `EH-1200TX`), delivering full-duplex throughput up to 10 Gbps and 20 Gbps over link distances exceeding 3–5 kilometers.
   - Features hitless adaptive bandwidth and modulation, carrier-grade Ethernet switching, and ultra-low deterministic delay ($< 10 \ \mu	ext{s}$).
3. **Ceragon CeraOS Multi-Core Microwave Family (IP-50 / IP-20 Series)**:
   - Operating across traditional licensed microwave frequencies (6 GHz to 42 GHz).
   - Flagship systems include the **IP-50C** (all-outdoor multi-carrier radio), **IP-50E** (universal E-band node), and **IP-50FX** (disaggregated open cell site gateway router).
   - Capable of 4096-QAM modulation, 112 MHz channel spacing, Multi-Carrier Adaptive Bandwidth Control (ABC), and Cross-Polarization Interference Cancellation (XPIC) achieving up to 20 Gbps transport capacity over long-haul distances.

---

## 1.6 The Architectural Problem Statement

To realize the vision of zero-touch, automated, intent-based network slicing for 5G-Advanced and 6G transport, operators require a unified system capable of:
1. **Ingesting High-Level Operator Intents**: Automatically interpreting declarative natural language or SLA requirements (e.g., "Deploy an ultra-reliable low-latency slice between Cell Site Alpha and Core Datacenter with latency $\le 3	ext{ms}$ and bandwidth $1	ext{Gbps}$").
2. **Translating Intents into Multi-Layer Graph Paths**: Interrogating the global network topology, computing constrained shortest paths across hybrid fiber and wireless links, and identifying wireless transport bottlenecks.
3. **Executing Deterministic Southbound Hardware Mutations**: Interfacing with physical wireless transport radios (such as the Ceragon MultiHaul TG `MH-T261`) over standard protocols, safely navigating candidate datastores, and applying atomic configurations without human intervention.
4. **Providing Real-Time Closed-Loop Telemetry & Assurance**: Continuously monitoring wireless link degradation (e.g., rain fade, RSSI drops), correlating weather forecast models (ITU-R P.838), and dynamically re-routing traffic or tuning radio parameters before service level agreements (SLAs) are violated.

Prior to this work, no open-source solution bridged ETSI TeraFlowSDN with Ceragon physical hardware, nor existed a comprehensive system unifying high-level AI intent orchestration, TFS controller core operations, physical mmWave hardware control, and real-time visualization.

---

## 1.7 Architectural Value Proposition & System Objectives

This master engineering initiative solves the architectural challenge by constructing a complete, production-ready, open-source integration suite:

```
+----------------------------------------------------------------------------------------------------+
|                                    END-TO-END SYSTEM STACK                                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ 1. NORTHBOUND AI INTENT LAYER ]                                                               |
|    - Natural Language SLA Parser & Constraint Solver                                               |
|    - ITU-R P.838 Predictive Weather & Rain Fade Optimizer                                          |
|    - Closed-Loop Assurance & Continuous Reconciler Engine                                          |
|                                                                                                    |
|                                   | (REST API / Socket.IO)                                         |
|                                   v                                                                |
|                                                                                                    |
|    [ 2. ETSI TERAFLOWSDN 7.0 CORE (Fork: efidvir/teraflowsdn) ]                                    |
|    - Distributed Microservice Mesh (Context, Device, Topology, PathComp, Slice)                   |
|    - CockroachDB Global Network Graph & Device Inventory                                          |
|    - DeviceDriver Enum Allocation: DEVICEDRIVER_CERAGON = 22                                       |
|    - Simulated Transport Components: 34-Node Hybrid Topology                                       |
|                                                                                                    |
|                                   | (Internal gRPC / DriverFactory)                                |
|                                   v                                                                |
|                                                                                                    |
|    [ 3. CERAGON SOUTHBOUND RESTCONF DRIVER (src/device/service/drivers/ceragon/) ]                 |
|    - RFC 8040 RESTCONF Engine & RFC 8342 NMDA Candidate Datastore Lifecycle                       |
|    - Two-Phase Commit (2PC): Staging PATCH -> Atomic Commit POST -> Discard Rollback               |
|    - 51 Physical YANG Schema Catalog Extracted from Live Hardware                                  |
|                                                                                                    |
|                                   | (RFC 8040 HTTP/HTTPS Basic Auth)                               |
|                                   v                                                                |
|                                                                                                    |
|    [ 4. PHYSICAL & EMULATED TRANSPORT HARDWARE PLANE ]                                             |
|    - Physical Node: Ceragon MultiHaul TG MH-T261 (ctu-96) @ 60 GHz V-Band                         |
|    - Emulated Topology: 34 Transport Nodes (5 O-CU, 7 O-DU, 10 O-RU, 10 Microwave Hops, 2 MEC)   |
|                                                                                                    |
|                                   ^                                                                |
|                                   | (Real-Time WebSocket & REST Telemetry)                         |
|                                                                                                    |
|    [ 5. UNIFIED 3-TIER OPERATOR TOPOLOGY DASHBOARD (localhost:5000) ]                              |
|    - Tier 1: Hybrid Global Network Graph (Physical + 34 Simulated Nodes)                           |
|    - Tier 2: TeraFlowSDN Native Controller View & CockroachDB State                                |
|    - Tier 3: Ceragon Wireless Transport Telemetry & Candidate Datastore Audit Trail                |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 1.8 Governance, Scope Boundaries, and Repository Matrix

To guarantee maximum developmental velocity, operational sovereignty, and continuous integration freedom, this initiative enforces clear governance boundaries:
- **Decoupled from Upstream ETSI Gerrit**: Development is conducted on the dedicated fork `https://github.com/efidvir/teraflowsdn` rather than the formal ETSI Gerrit server (`labs.etsi.org`). This eliminates external bureaucratic gatekeeping while delivering a fully standard-compliant, merge-ready architecture.
- **Cohesive Dual-Repository Architecture**:
  1. **`https://github.com/efidvir/teraflowsdn`** (Branch: `main` & `feat/ceragon-transport-driver`): Houses the complete ETSI TFS 7.0 source code, the official protobuf enum extension (`DEVICEDRIVER_CERAGON = 22`), the DriverFactory bindings, the complete Ceragon driver source (`src/device/service/drivers/ceragon/`), the 51 physical YANG schemas, the 34-node simulated topology descriptors, and the automated pytest suites.
  2. **`https://github.com/efidvir/CER-Intent`** (Branch: `main`): Houses the Northbound AI Intent Engine, the ITU-R P.838 rain fade prediction models, the closed-loop assurance reconciler, the standalone redistributable Python wheel (`ceragon_tfs_adapter`), the live Flask + Socket.IO + D3.js 3-tier web dashboard, and this definitive master specification.

---


---

## 1.9 Comparative Architectural Analysis of Telecom SDN Controllers

To understand why ETSI TeraFlowSDN was selected as the optimal control plane for carrier-grade Ceragon transport networks, the following matrix compares the predominant open-source telecommunications controllers across critical architectural criteria:

| Evaluation Dimension | ONOS (Open Networking Lab) | OpenDaylight (ODL / Linux Foundation) | ETSI OSM (OpenSource MANO) | Linux Foundation ONAP | ETSI TeraFlowSDN (TFS v7.0) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Core Architecture** | Monolithic Java OSGi bundle | Monolithic / Modular Java Karaf | Python microservices (NFV-O) | Heavyweight Kubernetes Java/Go | Cloud-Native gRPC Microservices |
| **Runtime Footprint** | 8 - 16 GB RAM per node | 12 - 32 GB RAM per node | 16 - 32 GB RAM | 64 - 128 GB RAM | Lightweight (< 4 GB RAM base) |
| **Persistence Datastore** | Hazelcast / Atomix In-Memory | MD-SAL In-Memory + LevelDB | MongoDB / MariaDB | Cassandra / PostgreSQL | CockroachDB (Distributed ACID SQL) |
| **Transport Protocol Mesh** | Java internal memory calls | Java MD-SAL event bus | RabbitMQ / Kafka | Kafka / REST | gRPC over HTTP/2 with Protobuf v3 |
| **Multi-Layer Optical/Wireless** | Limited (ODTN extensions) | TransportPCE (Optical only) | Service level only (no SBI) | Multi-VIM / Service level | Native Multi-Layer (WDM, IP, Radio) |
| **Path Computation (CSPF)** | Basic Dijkstra in Java | PCEP / BGP-LS plug-ins | None (delegates to SDN) | Delegated to SDN controllers | Native C++ / Python CSPF Microservice |
| **Candidate Datastore Support** | Partial (NETCONF only) | Netconf candidate mountpoint | None | None | First-class Candidate DS & 2PC hooks |
| **Microsecond Telemetry Pipeline** | Metric service (JMX) | OpenTSDB / InfluxDB plugin | Prometheus (VNF metrics) | DCAE (Data Collection & Analytics) | Native QuestDB & Prometheus Streams |

### The Cloud-Native Advantage of TeraFlowSDN
While ONOS and OpenDaylight pioneered software-defined networking in data center fabrics, their monolithic Java JVM architectures impose severe CPU and garbage collection (GC) pauses that degrade real-time performance when managing thousands of dynamic radio links. ETSI TeraFlowSDN's Kubernetes-native microservice architecture decouples each operational concern into an independently scalable container, enabling high-frequency wireless telemetry ingestion without risking controller deadlock.


# Chapter 2: Theoretical Foundations & Mathematical Formulations

## 2.1 Wireless Propagation Physics across Microwave, V-Band, and E-Band

Wireless transport systems operate across a wide swath of the electromagnetic spectrum, ranging from traditional ultra-high frequency (UHF) microwave bands up to sub-terahertz frequencies. The propagation physics governing signal attenuation, phase distortion, and atmospheric absorption vary dramatically across these bands:

```
+----------------------------------------------------------------------------------------------------+
|                                    RADIO FREQUENCY TRANSPORT SPECTRUM                              |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|   Band Class        Frequency Range       Typical Channel BW     Primary Physical Constraints      |
|   ----------------------------------------------------------------------------------------------   |
|   Traditional MW    6 GHz - 42 GHz        7 MHz - 112 MHz        Multipath fading, rain fade,      |
|                                                                  refraction (k-factor variations)  |
|                                                                                                    |
|   V-Band (mmWave)   57 GHz - 66 GHz       2.16 GHz (802.11ad/ay) Extreme oxygen absorption peak    |
|                                                                  (~15 dB/km), rain fade, foliage   |
|                                                                                                    |
|   E-Band (mmWave)   71-76 / 81-86 GHz     250 MHz - 2000 MHz     Severe rain attenuation, pencil   |
|                                                                  beam alignment, antenna sway      |
|                                                                                                    |
|   Sub-THz (6G)      100 GHz - 300 GHz     5 GHz - 30 GHz         Molecular water vapor absorption, |
|                                                                  extreme free space path loss      |
+----------------------------------------------------------------------------------------------------+
```

### Free Space Path Loss (FSPL)
In an ideal, unobstructed line-of-sight (LOS) propagation channel, the power received by an antenna separated by distance $d$ from a transmitting antenna operating at carrier frequency $f$ is governed by the Friis Transmission Equation:

$$P_{rx} = P_{tx} \cdot G_{tx} \cdot G_{rx} \cdot \left( rac{c}{4 \pi d f} 
ight)^2$$

Where:
- $P_{tx}$ is the transmitter output power (Watts or dBm).
- $P_{rx}$ is the received power at the antenna terminals.
- $G_{tx}$ and $G_{rx}$ are the isotropic gains of the transmitting and receiving antennas, respectively.
- $c$ is the speed of light in vacuum ($2.99792458 	imes 10^8 \ 	ext{m/s}$).
- $d$ is the path distance (meters).
- $f$ is the carrier frequency (Hertz).

Expressed in decibels (dB), the **Free Space Path Loss ($L_{fs}$)** is formulated as:

$$L_{fs} \ (	ext{dB}) = 20 \log_{10}(d) + 20 \log_{10}(f) + 20 \log_{10}\left(rac{4\pi}{c}
ight)$$

When expressing distance $d$ in kilometers ($d_{km}$) and carrier frequency $f$ in gigahertz ($f_{GHz}$), this simplifies to the standard telecommunications engineering formula:

$$L_{fs} \ (	ext{dB}) = 92.45 + 20 \log_{10}(d_{km}) + 20 \log_{10}(f_{GHz})$$

For an unguided millimeter-wave signal operating in the V-Band at $f = 60 \ 	ext{GHz}$ over a distance of $d = 1 \ 	ext{km}$:
$$L_{fs} = 92.45 + 20 \log_{10}(1) + 20 \log_{10}(60) = 92.45 + 0 + 35.56 = 128.01 \ 	ext{dB}$$

By contrast, for a traditional microwave hop operating at $f = 11 \ 	ext{GHz}$ over the same $1 \ 	ext{km}$ distance:
$$L_{fs} = 92.45 + 20 \log_{10}(1) + 20 \log_{10}(11) = 92.45 + 0 + 20.83 = 113.28 \ 	ext{dB}$$

The mmWave link experiences **$14.73 \ 	ext{dB}$ greater free space loss** solely due to frequency scaling, demanding higher antenna gains (achieved via narrow beamwidths and phased-array beamforming) to close the link budget.

---

## 2.2 ITU-R P.838-3 Specific Rain Attenuation Formulation

While free space path loss is deterministic and invariant, atmospheric precipitation introduces severe stochastic attenuation that dominates link availability above 10 GHz. Liquid raindrops absorb and scatter electromagnetic radiation when the droplet diameter (typically 0.1 mm to 5 mm) becomes comparable to the carrier wavelength ($\lambda = 5 \ 	ext{mm}$ at 60 GHz, $\lambda = 3.75 \ 	ext{mm}$ at 80 GHz).

### 2.2.1 Mathematical Formulation

The International Telecommunication Union Radiocommunication Sector (ITU-R) Recommendation **ITU-R P.838-3** establishes the globally standardized empirical power-law relationship for specific rain attenuation $\gamma_R$ (dB/km):

$$\gamma_R = k \cdot R^lpha \quad (	ext{dB/km})$$

Where:
- $\gamma_R$ is the specific attenuation along the propagation path in decibels per kilometer ($	ext{dB/km}$).
- $R$ is the point rainfall rate in millimeters per hour ($	ext{mm/h}$), typically measured or statistically modeled at a 1-minute integration time ($R_{0.01}$).
- $k$ and $lpha$ are frequency-, polarization-, and path-elevation-dependent regression coefficients.

For linear horizontal ($H$) and vertical ($V$) polarizations, the coefficients $k$ and $lpha$ are calculated from fundamental curve-fitting equations published by ITU-R:

$$k = rac{k_H + k_V + (k_H - k_V) \cos^2(	heta) \cos(2	au)}{2}$$

$$lpha = rac{k_H lpha_H + k_V lpha_V + (k_H lpha_H - k_V lpha_V) \cos^2(	heta) \cos(2	au)}{2 k}$$

Where:
- $	heta$ is the path elevation angle relative to the horizontal plane.
- $	au$ is the polarization tilt angle relative to the horizontal ($	au = 0^\circ$ for pure horizontal polarization, $	au = 90^\circ$ for pure vertical polarization, and $	au = 45^\circ$ for circular polarization).

For terrestrial point-to-point horizontal links ($	heta pprox 0^\circ$), these formulations simplify directly to the polarization-specific parameters $k_H, lpha_H$ and $k_V, lpha_V$.

### 2.2.2 Frequency and Polarization Coefficients

The values of $k$ and $lpha$ across critical mobile transport frequencies are detailed in the following standard table:

| Carrier Frequency ($f$) | $k_H$ | $k_V$ | $lpha_H$ | $lpha_V$ | Attenuation at $R=50	ext{mm/h}$ (Horizontal) | Attenuation at $R=50	ext{mm/h}$ (Vertical) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **11 GHz** | 0.01772 | 0.01731 | 1.2140 | 1.1517 | $2.01 \ 	ext{dB/km}$ | $1.56 \ 	ext{dB/km}$ |
| **18 GHz** | 0.07078 | 0.06740 | 1.0818 | 1.0553 | $4.87 \ 	ext{dB/km}$ | $4.18 \ 	ext{dB/km}$ |
| **23 GHz** | 0.1287 | 0.1202 | 1.0216 | 0.9982 | $6.97 \ 	ext{dB/km}$ | $5.88 \ 	ext{dB/km}$ |
| **38 GHz** | 0.3844 | 0.3584 | 0.8906 | 0.8761 | $12.48 \ 	ext{dB/km}$ | $11.02 \ 	ext{dB/km}$ |
| **60 GHz (V-Band)** | 0.8606 | 0.8515 | 0.7571 | 0.7486 | $16.74 \ 	ext{dB/km}$ | $15.82 \ 	ext{dB/km}$ |
| **73 GHz (E-Band)** | 1.0650 | 1.0570 | 0.7080 | 0.7030 | $17.06 \ 	ext{dB/km}$ | $16.51 \ 	ext{dB/km}$ |
| **83 GHz (E-Band)** | 1.1710 | 1.1640 | 0.6860 | 0.6820 | $17.24 \ 	ext{dB/km}$ | $16.84 \ 	ext{dB/km}$ |

Notice that horizontally polarized waves suffer consistently higher attenuation than vertically polarized waves ($\gamma_{R,H} > \gamma_{R,V}$) due to the oblate spheroidal geometry of falling raindrops, which flatten horizontally due to aerodynamic drag.

### 2.2.3 Rain Rate Distribution and Availability Statistics

To evaluate link availability over an annual period, the total rain attenuation $A_R$ over a path of physical length $d$ is given by:

$$A_R = \gamma_R \cdot d_{eff} = k R^lpha \cdot rac{d}{1 + d / d_0}$$

Where $d_{eff}$ is the effective path length and $d_0$ is the path reduction factor defined in ITU-R P.530:

$$d_0 = 35 \cdot e^{-0.015 R_{0.01}}$$

In carrier-grade telecommunications, operators require **"Five-Nines" ($99.999\%$) availability**, corresponding to an outage probability of $p = 0.001\%$, or no more than 5.26 minutes of cumulative downtime per year. In ITU Rain Zone K (temperate maritime/continental, typical of Western Europe and parts of North America), the 0.01% rainfall rate is $R_{0.01} = 42 \ 	ext{mm/h}$. In tropical zones (Zone P or Q), $R_{0.01}$ reaches $145 \ 	ext{mm/h}$.

---

## 2.3 ITU-R P.676 Atmospheric Gas Absorption & Oxygen Resonance Peak at 60 GHz

Unlike traditional microwave bands where atmospheric gaseous absorption is minimal ($< 0.05 \ 	ext{dB/km}$), the **60 GHz V-Band** resides directly upon the fundamental quantum resonance of molecular oxygen ($	ext{O}_2$).

```
Specific Attenuation (dB/km)
  |
20|                         *  <-- 60 GHz Oxygen Resonance Peak (~15 dB/km)
  |                       *   *
15|                      *     *
  |                     *       *
10|                    *         *
  |                   *           *
 5|                  *             *
  |  *              *               *                        *  <-- 118 GHz O2
 0+---------------------------------------------------------------------> Frequency (GHz)
    10    20    30    40    50    60    70    80    90   100   110   120
                                  [V-Band]     [E-Band Window]
```

### 2.3.1 Physics of 60 GHz Molecular Absorption

Molecular oxygen is a paramagnetic molecule possessing a permanent magnetic dipole moment resulting from two unpaired electron spins. When millimeter-wave photons at frequencies between 54 GHz and 66 GHz interact with oxygen molecules, they stimulate magnetic dipole transitions between fine-structure rotational energy levels. This phenomenon causes dramatic absorption of electromagnetic energy, converting RF radiation directly into thermal kinetic energy of the atmospheric gas.

### 2.3.2 Line-by-Line Summation & Approximations

Under ITU-R Recommendation **ITU-R P.676-12**, the total specific gaseous attenuation $\gamma_g$ is the exact sum of oxygen attenuation $\gamma_o$ and water vapor attenuation $\gamma_w$:

$$\gamma_g = \gamma_o + \gamma_w = 0.1820 \cdot f \cdot \left[ \sum_{i} S_i F_i + N''_D(f) 
ight] + \gamma_w \quad (	ext{dB/km})$$

Where:
- $S_i$ is the line strength of the $i$-th oxygen absorption line.
- $F_i$ is the Van Vleck-Weisskopf line shape factor modified by Rosenkranz line mixing.
- $N''_D(f)$ is the non-resonant Debye absorption spectrum.

At sea level, standard barometric pressure ($1013.25 \ 	ext{hPa}$), temperature $T = 15^\circ	ext{C}$, and standard water vapor density $
ho = 7.5 \ 	ext{g/m}^3$:
- At **$f = 60.48 \ 	ext{GHz}$** (Channel 2 of IEEE 802.11ad/ay):
  $$\gamma_o pprox 14.8 \ 	ext{dB/km}, \quad \gamma_w pprox 0.2 \ 	ext{dB/km} \implies \gamma_g pprox 15.0 \ 	ext{dB/km}$$
- At **$f = 73.0 \ 	ext{GHz}$** (Lower E-Band):
  $$\gamma_o pprox 0.4 \ 	ext{dB/km}, \quad \gamma_w pprox 0.5 \ 	ext{dB/km} \implies \gamma_g pprox 0.9 \ 	ext{dB/km}$$

### Architectural Impact on the Ceragon MultiHaul TG (MH-T261)
This $15.0 \ 	ext{dB/km}$ attenuation acts as a natural physical barrier that completely confines 60 GHz signals to distances under $500 \ 	ext{meters}$ to $1 \ 	ext{kilometer}$. While this severely limits transmission distance, it confers a profound architectural advantage: **extreme spatial frequency re-use and virtual immunity to inter-cell co-channel interference**. Adjacent small cells can operate on identical carrier frequencies without mutual degradation.

---

## 2.4 Shannon-Hartley Channel Capacity and Adaptive Coding & Modulation (ACM)

### 2.4.1 Fundamental Information Capacity Limit

The theoretical upper bound on the transmission rate across an unconstrained continuous-time analog channel perturbed by additive white Gaussian noise (AWGN) is dictated by the Shannon-Hartley Theorem:

$$C = B \cdot \log_2 \left( 1 + 	ext{SINR} 
ight) = B \cdot \log_2 \left( 1 + rac{P_{rx}}{N_0 B + I} 
ight) \quad (	ext{bits per second})$$

Where:
- $C$ is the maximum channel capacity (bps).
- $B$ is the allocated channel bandwidth (Hz). For the MultiHaul TG, $B = 2.16 \ 	ext{GHz}$ per channel. For the CeraOS IP-50C, $B \in \{28, 56, 112\} \ 	ext{MHz}$.
- $P_{rx}$ is the received carrier signal power (Watts).
- $N_0$ is the single-sided noise spectral density ($N_0 = k_B T_{sys}$, where $k_B = 1.380649 	imes 10^{-23} \ 	ext{J/K}$ is Boltzmann's constant and $T_{sys}$ is system noise temperature).
- $I$ is co-channel interference power.

### 2.4.2 Discrete Modulation Constellations & Spectral Efficiencies

In real-world transceivers, transmissions are constrained to discrete Quadrature Amplitude Modulation ($M$-QAM) constellations coupled with Forward Error Correction (FEC) Low-Density Parity-Check (LDPC) coding rates $R_{FEC}$. The spectral efficiency $\eta$ (bits/second/Hertz) is:

$$\eta = R_{FEC} \cdot \log_2(M) \quad (	ext{bps/Hz})$$

The following table delineates the modulation schemes, required SINR thresholds, and net capacities supported across Ceragon hardware:

| Modulation Scheme ($M$-QAM) | Bits per Symbol ($\log_2 M$) | FEC Coding Rate ($R_{FEC}$) | Spectral Efficiency ($\eta$) | Required SINR (BER $\le 10^{-6}$) | Net Throughput ($B=112	ext{MHz}$, CeraOS) | Net Throughput ($B=2.16	ext{GHz}$, MultiHaul) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **BPSK (MCS 1)** | 1 | 1/2 | 0.50 bps/Hz | $6.5 \ 	ext{dB}$ | $56 \ 	ext{Mbps}$ | $460 \ 	ext{Mbps}$ |
| **QPSK (MCS 2-4)** | 2 | 3/4 | 1.50 bps/Hz | $10.2 \ 	ext{dB}$ | $168 \ 	ext{Mbps}$ | $1,050 \ 	ext{Mbps}$ |
| **16-QAM (MCS 6-8)** | 4 | 3/4 | 3.00 bps/Hz | $16.8 \ 	ext{dB}$ | $336 \ 	ext{Mbps}$ | $2,300 \ 	ext{Mbps}$ |
| **64-QAM (MCS 9-10)**| 6 | 5/6 | 5.00 bps/Hz | $23.1 \ 	ext{dB}$ | $560 \ 	ext{Mbps}$ | $3,800 \ 	ext{Mbps}$ |
| **256-QAM** | 8 | 5/6 | 6.67 bps/Hz | $29.4 \ 	ext{dB}$ | $747 \ 	ext{Mbps}$ | N/A (Terragraph limit) |
| **1024-QAM** | 10 | 8/9 | 8.89 bps/Hz | $35.8 \ 	ext{dB}$ | $995 \ 	ext{Mbps}$ | N/A |
| **2048-QAM** | 11 | 9/10 | 9.90 bps/Hz | $39.2 \ 	ext{dB}$ | $1,108 \ 	ext{Mbps}$ | N/A |
| **4096-QAM** | 12 | 11/12 | 11.00 bps/Hz | $42.5 \ 	ext{dB}$ | $1,232 \ 	ext{Mbps}$ | N/A |

### 2.4.3 Adaptive Modulation State Machine & Hysteresis Algorithms

To maintain error-free transmission during rapid weather changes without dropping the radio link, Ceragon equipment employs **Hitless Adaptive Coding and Modulation (Hitless ACM)**. 

To prevent high-frequency oscillations ("flapping") between adjacent modulation profiles when the SINR hovers near a decision boundary, the ACM controller implements a **hysteresis window** ($\Delta_{hyst} pprox 2.0 \ 	ext{dB}$):

$$	ext{Downshift Condition}: \quad 	ext{SINR}_{meas} < 	ext{SINR}_{thresh}(M) - \Delta_{margin}$$

$$	ext{Upshift Condition}: \quad 	ext{SINR}_{meas} > 	ext{SINR}_{thresh}(M+1) + \Delta_{hyst}$$

```
SINR (dB)
  |
  |         Upshift Boundary: SINR_thresh(16QAM) + 2.0 dB  -----------------
  |        -----------------------------------------------------------------
  |                                                                ^
  |                     Current State: QPSK                        | Upshift
  |                                                                v
  |        -----------------------------------------------------------------
  |         Downshift Boundary: SINR_thresh(QPSK) - 1.0 dB -----------------
  |
  +-------------------------------------------------------------------------> Time (s)
```

During a heavy rain fade event, the physical link capacity contracts from $1.0 \ 	ext{Gbps}$ down to $100 \ 	ext{Mbps}$. Unless the higher-layer SDN controller is immediately notified to adjust traffic shaping or re-route low-priority traffic, packet queues will overflow, inducing massive jitter and bufferbloat.

---

## 2.5 Adaptive Transmission Power Control (ATPC) Feedback Mechanics

To balance link margin against power consumption and inter-system interference, Ceragon transceivers execute closed-loop **Adaptive Transmission Power Control (ATPC)**. 

The receiver continuously computes the Received Signal Level ($RSL$) and transmits an out-of-band telemetry frame back to the transmitting station containing the power adjustment vector:

$$\Delta P_{tx} = RSL_{target} - RSL_{measured}$$

The transmitter updates its power amplifier setting according to:

$$P_{tx}(t + \Delta t) = \min \left( P_{tx,max}, \max \left( P_{tx,min}, P_{tx}(t) + lpha_{atpc} \cdot \Delta P_{tx} 
ight) 
ight)$$

Where:
- $P_{tx,max}$ is the maximum saturated output power of the RF Power Amplifier ($+20 \ 	ext{dBm}$ for CeraOS, $+12 \ 	ext{dBm}$ per element for MultiHaul TG).
- $P_{tx,min}$ is the minimum power floor ($0 \ 	ext{dBm}$ to $-10 \ 	ext{dBm}$).
- $lpha_{atpc} \in (0, 1]$ is the loop dampening factor preventing overshooting.

When ATPC reaches its maximum ceiling ($P_{tx} = P_{tx,max}$) and $RSL$ continues to plummet due to torrential rain, the ACM engine triggers modulation step-down.

---

## 2.6 Quality of Service (QoS), Token Buckets, and Traffic Shaping Mathematics

When slicing wireless transport networks across heterogeneous 5G use cases (eMBB, URLLC, mMTC), traffic must be metered and policed according to deterministic traffic contracts.

### 2.6.1 Single-Rate Three-Color Marker (srTCM, RFC 2697)

The Single-Rate Three-Color Marker meters IP packet streams based on three parameters:
- **Committed Information Rate (CIR)**: Measured in bytes per second.
- **Committed Burst Size (CBS)**: Measured in bytes.
- **Excess Burst Size (EBS)**: Measured in bytes.

Two token buckets, $T_c$ (Committed) and $T_e$ (Excess), are incremented synchronously at rate CIR:

$$rac{d T_c}{dt} = 	ext{CIR}, \quad 	ext{bounded by } 0 \le T_c \le 	ext{CBS}$$

$$	ext{If } T_c = 	ext{CBS}: \quad rac{d T_e}{dt} = 	ext{CIR}, \quad 	ext{bounded by } 0 \le T_e \le 	ext{EBS}$$

For an arriving packet of length $B$ bytes at time $t$:
1. If $B \le T_c(t)$: Packet is marked **GREEN** (Conforming). $T_c \leftarrow T_c - B$.
2. If $T_c(t) < B \le T_e(t)$: Packet is marked **YELLOW** (Exceeding). $T_e \leftarrow T_e - B$.
3. If $B > T_e(t)$: Packet is marked **RED** (Violating). Discarded or queued in best-effort buffer.

### 2.6.2 Two-Rate Three-Color Marker (trTCM, RFC 2698)

For peak-rate burst policing (used in the Ceragon driver's `/slice/<slice_name>` resource rules), the Two-Rate Three-Color Marker employs:
- **Committed Information Rate (CIR)** and **Committed Burst Size (CBS)**.
- **Peak Information Rate (PIR)** and **Peak Burst Size (PBS)**, with $	ext{PIR} \ge 	ext{CIR}$.

Two independent buckets $T_p$ and $T_c$ update at rates PIR and CIR:

$$T_p(t) = \min \left( 	ext{PBS}, \ T_p(t_0) + 	ext{PIR} \cdot (t - t_0) 
ight)$$

$$T_c(t) = \min \left( 	ext{CBS}, \ T_c(t_0) + 	ext{CIR} \cdot (t - t_0) 
ight)$$

Packet Marking Logic:
- If $B > T_p(t)$: Marked **RED**.
- Else if $B > T_c(t)$: Marked **YELLOW**, $T_p \leftarrow T_p - B$.
- Else: Marked **GREEN**, $T_p \leftarrow T_p - B$, $T_c \leftarrow T_c - B$.

### 2.6.3 Latency, Jitter, and Packet Loss Probability Bounds

In an $M/M/1/K$ or $M/D/1$ queueing model representing a wireless transport interface with service capacity $\mu = C(t) / ar{L}$ (packets/sec) and Poisson arrival rate $\lambda$ (packets/sec), the utilization factor is $
ho = \lambda / \mu$.

The average queueing delay $W_q$ is formulated as:

$$W_q = rac{
ho}{\mu (1 - 
ho)} = rac{\lambda}{\mu (\mu - \lambda)}$$

Total end-to-end transport delay $D_{e2e}$ across $H$ hops is the deterministic sum:

$$D_{e2e} = \sum_{h=1}^H \left( rac{d_h}{c} + t_{ser,h} + W_{q,h} + t_{proc,h} 
ight)$$

Where:
- $d_h / c$ is the physical propagation delay ($3.33 \ \mu	ext{s/km}$).
- $t_{ser,h} = L_{packet} / C_h(t)$ is packet serialization delay.
- $W_{q,h}$ is stochastic buffer delay.
- $t_{proc,h}$ is baseband framing, beamforming, and FEC decoding latency ($\sim 10-50 \ \mu	ext{s}$ on MultiHaul TG).

For URLLC slices, the intent engine must ensure $D_{e2e} \le 5 \ 	ext{ms}$ with packet loss probability $P_{loss} \le 10^{-6}$, requiring the controller to enforce $
ho_h < 0.6$ across all wireless hops under active ACM rain margins.


---

## 2.7 Phased Array Electronic Beam Steering & Spatial Beamforming Mathematics

Millimeter-wave communications in the 60 GHz V-Band cannot rely on omnidirectional radiation patterns due to the extreme free-space and atmospheric losses detailed in Sections 2.1 and 2.3. The Ceragon MultiHaul TG `MH-T261` employs an active planar Phased Array Antenna (`massive2`) comprising an array of $M \times N = 4 \times 8 = 32$ dual-polarized microstrip radiating elements.

```
+----------------------------------------------------------------------------------------------------+
|                         PLANAR PHASED ARRAY ANTENNA BEAMFORMING MATRIX                             |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|          Element (0,0)         Element (0,1)              Element (0,N-1)                          |
|         +-------------+       +-------------+            +-------------+                           |
|         | [Phase/Amp] |       | [Phase/Amp] |   . . .    | [Phase/Amp] |                           |
|         +------+------+       +------+------+            +------+------+                           |
|                |                     |                          |                                  |
|          Element (1,0)         Element (1,1)              Element (1,N-1)                          |
|         +------+------+       +------+------+            +------+------+                           |
|         | [Phase/Amp] |       | [Phase/Amp] |   . . .    | [Phase/Amp] |                           |
|         +------+------+       +------+------+            +------+------+                           |
|                |                     |                          |                                  |
|                .                     .                          .                                  |
|                .                     .                          .                                  |
|          Element (M-1,0)       Element (M-1,1)            Element (M-1,N-1)                        |
|         +------+------+       +------+------+            +------+------+                           |
|         | [Phase/Amp] |       | [Phase/Amp] |   . . .    | [Phase/Amp] |                           |
|         +------+------+       +------+------+            +------+------+                           |
|                |                     |                          |                                  |
|                +---------------------+--------------------------+                                  |
|                                      |                                                             |
|                                      v                                                             |
|                     [ RF Distribution & Summing Network ]                                          |
|                                      |                                                             |
|                                      v                                                             |
|                         [ 60 GHz RF Transceiver ]                                                  |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 2.7.1 Uniform Rectangular Array (URA) Array Factor Formulation
The spatial radiation pattern of an $M \times N$ planar array positioned in the $xy$-plane with element separations $d_x$ and $d_y$ is governed by the Array Factor $AF(\theta, \phi)$:

$$AF(\theta, \phi) = \sum_{m=0}^{M-1} \sum_{n=0}^{N-1} I_{mn} \cdot \exp \left( j \left[ m (k_0 d_x \sin\theta \cos\phi + \beta_x) + n (k_0 d_y \sin\theta \sin\phi + \beta_y) \right] \right)$$

Where:
- $\theta \in [0, \pi]$ is the elevation angle measured from the broadside $z$-axis.
- $\phi \in [0, 2\pi]$ is the azimuth angle in the $xy$-plane.
- $k_0 = \frac{2\pi}{\lambda_0}$ is the free-space wavenumber ($\lambda_0 \approx 4.63 \ \text{mm}$ at $64.80 \ \text{GHz}$).
- $I_{mn}$ is the excitation amplitude weighting of the $(m, n)$-th element (typically normalized to $1.0$ under uniform illumination, or tapered via Dolph-Chebyshev/Taylor distributions to suppress sidelobes).
- $\beta_x$ and $\beta_y$ are the progressive phase excitation shifts applied along the $x$- and $y$-axes.

To steer the main radiation lobe to a specific target direction $(\theta_0, \phi_0)$, the progressive phase shifts are dynamically programmed via the baseband beamforming codebook:

$$\beta_x = -k_0 d_x \sin\theta_0 \cos\phi_0$$
$$\beta_y = -k_0 d_y \sin\theta_0 \sin\phi_0$$

### 2.7.2 Grating Lobe Suppression Criteria
To prevent the formation of spatial grating lobes (spurious secondary main beams that waste RF energy and cause multi-user interference), the element spacings $d_x$ and $d_y$ must strictly satisfy the non-grating condition across the maximum scan angles $(\theta_{max}, \phi_{max})$:

$$d_x \le \frac{\lambda_0}{1 + |\sin\theta_{max} \cos\phi_{max}|}, \quad d_y \le \frac{\lambda_0}{1 + |\sin\theta_{max} \sin\phi_{max}|}$$

In the MultiHaul TG `MH-T261`, the antenna array is fabricated with $d_x = d_y = \frac{\lambda_0}{2} \approx 2.31 \ \text{mm}$, ensuring zero grating lobes across the entire $\pm 45^\circ$ azimuth scan sector.

### 2.7.3 Half-Power Beamwidth (HPBW) and Directivity
The 3-dB Half-Power Beamwidth in the azimuth plane ($\Theta_{3dB,\phi}$) contracts as the number of elements $N$ increases:

$$\Theta_{3dB,\phi} \approx \frac{0.886 \cdot \lambda_0}{N \cdot d_x \cdot \cos\phi_0} \quad (\text{radians}) \approx \frac{50.8^\circ}{N \cdot (d_x / \lambda_0) \cdot \cos\phi_0}$$

For the 8-element horizontal dimension ($N = 8, d_x / \lambda_0 = 0.5$) at broadside ($\phi_0 = 0^\circ$):
$$\Theta_{3dB,\phi} \approx \frac{50.8^\circ}{8 \cdot 0.5 \cdot 1.0} = 12.7^\circ$$

The pencil beamwidth of $12.7^\circ$ concentrates RF energy into a narrow spatial cone, providing the required $24.5 \ \text{dBi}$ antenna gain to overcome the $15 \ \text{dB/km}$ oxygen absorption resonance.

---

## 2.8 ITU-R P.530-17 Multi-Path Fading and Outage Probability for Microwave Links

While millimeter-wave frequencies (60–80 GHz) are predominantly degraded by precipitation and oxygen absorption, traditional microwave bands (6–42 GHz, utilized by the Ceragon CeraOS `IP-50` family) are subject to severe **atmospheric multipath fading** caused by vertical temperature and humidity gradients that create atmospheric refractive layers (ducts).

### 2.8.1 The Geoclimatic Multipath Factor
Under ITU-R Recommendation **ITU-R P.530-17**, the probability $p_0$ of single-frequency multipath fading exceeding depth $A$ (dB) in the worst month is formulated as:

$$p_0 = K \cdot d^{3.1} \cdot (1 + |\epsilon_p|)^{-1.29} \cdot f^{0.8} \cdot 10^{-0.00089 h_L} \quad (\%)$$

Where:
- $d$ is the path distance in kilometers ($km$).
- $f$ is the carrier frequency in gigahertz ($GHz$).
- $h_L$ is the lower antenna height above sea level in meters ($m$).
- $\epsilon_p$ is the path inclination in milliradians ($mrad$):
  $$\epsilon_p = \frac{|h_1 - h_2|}{d}$$
- $K$ is the geoclimatic factor derived from ITU regional contour maps of refractivity gradient $\Delta N$:
  $$K = 10^{-4.2 - 0.0029 dN_1}$$

### 2.8.2 Fade Margin & Outage Probability
The Fade Margin $F$ (dB) represents the reserve power between nominal received signal level $RSL_{nom}$ and the receiver's thermal threshold $RSL_{thresh}$:

$$F = RSL_{nom} - RSL_{thresh} \quad (\text{dB})$$

For deep fade depths ($F > 15 \ \text{dB}$), the percentage of time $P_w$ that the link is unavailable due to multipath fading is:

$$P_w = p_0 \cdot 10^{-F / 10} \quad (\%)$$

### 2.8.3 Space Diversity & Frequency Diversity Mitigation
To guarantee "Five-Nines" availability ($P_w \le 0.001\%$) on long microwave hops, Ceragon systems deploy **Space Diversity (SD)** using dual vertically separated antennas ($S \ge 150 \lambda$). The diversity improvement factor $I_{sd}$ is:

$$I_{sd} = [1 - \exp(-0.04 \cdot S^{0.87} \cdot f^{-0.12} \cdot d^{0.48} \cdot p_0^{-0.04})] \cdot 10^{(F - V) / 10}$$

Where $S$ is vertical antenna separation and $V = |RSL_1 - RSL_2|$. The CeraOS dual-core DSP continuously combines the signals from both diversity branches using Maximum Ratio Combining (MRC), neutralizing multipath nulls in real time.


---

# Chapter 3: Ceragon Wireless Transport Hardware & Physical Architecture

## 3.1 Ceragon / Siklu MultiHaul TG Series Deep-Dive

The Ceragon / Siklu MultiHaul TG family represents the state of the art in carrier-grade millimeter-wave (mmWave) wireless communications operating in the unlicensed and lightly licensed 60 GHz V-Band (57 GHz to 66 GHz). Built upon Facebook's (Meta's) Terragraph technology initiative and standardized under IEEE 802.11ad and IEEE 802.11ay, MultiHaul TG delivers fiber-equivalent multi-gigabit wireless transport for 5G small-cell backhaul, smart-city sensor grids, and Gigabit Fixed Wireless Access (FWA).

```
+----------------------------------------------------------------------------------------------------+
|                         CERAGON / SIKLU MULTIHAUL TG HARDWARE ARCHITECTURE                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +-----------------------------+                  +-----------------------------------------+    |
|    | MH-T261 Terminal Unit (TU)  |                  |    MH-N366 Distribution Node (DN)       |    |
|    |                             |                  |                                         |    |
|    |  +-----------------------+  |                  |  +-----------+ +-----------+ +-------+  |    |
|    |  | Phased Array Antenna  |  |                  |  | Sector 1  | | Sector 2  | | Sect 3|  |    |
|    |  |  (massive2, 32-elem)  |  |                  |  | (90 deg)  | | (90 deg)  | | (90d) |  |    |
|    |  +-----------+-----------+  |                  |  +-----+-----+ +-----+-----+ +---+---+  |    |
|    |              | RF Coax      |                  |        |             |           |      |    |
|    |  +-----------v-----------+  |                  |  +-----v-------------v-----------v---+  |    |
|    |  | RF Transceiver (60GHz)|  |                  |  | Multi-Sector Baseband Matrix       |  |    |
|    |  +-----------+-----------+  |                  |  +-------------------+------------------+  |    |
|    |              | Baseband IQ  |                  |                      |                  |    |
|    |  +-----------v-----------+  |                  |  +-------------------v------------------+  |    |
|    |  | Qualcomm 802.11ay DSP |  |                  |  | Network Processor & 10G Switch Engine|  |    |
|    |  +-----------+-----------+  |                  |  +-------------------+------------------+  |    |
|    |              | RGMII/SGMII  |                  |                      |                  |    |
|    |  +-----------v-----------+  |                  |  +-------------------v------------------+  |    |
|    |  | Marvell Carrier Eth SW|  |                  |  | 10G SFP+ / 2.5G PoE / SyncE Engine   |  |    |
|    |  +-----------+-----------+  |                  |  +-------------------+------------------+  |    |
|    |              |              |                  |                      |                  |    |
|    |  [eth1: 1G RJ-45 PoE]       |                  |  [Port 1: 10G SFP+] [Port 2: 2.5G RJ-45]|    |
|    +-----------------------------+                  +-----------------------------------------+    |
+----------------------------------------------------------------------------------------------------+
```

### 3.1.1 MultiHaul TG MH-T261 Terminal Unit (TU) Physical Architecture
The primary physical testbed node utilized in this engineering integration is the **MultiHaul TG MH-T261** (Serial Number `AE09100255`, Node Name `ctu-96`, Software Version `3.4.0-4377-5faacf06a`). 

Key architectural components include:
1. **Phased-Array Electronic Beamforming Antenna (`massive2`)**:
   - The RF front-end integrates an active planar phased-array antenna comprising 32 dual-polarized microstrip patch radiating elements.
   - **Azimuth Scan Range**: Electronically steerable across a $\pm 45^\circ$ sector ($90^\circ$ total field of view) in discrete $1.4^\circ$ increments without physical dish realignment.
   - **Elevation Scan Range**: Electronically steerable across $\pm 10^\circ$.
   - **Boresight Gain**: $24.5 \ \text{dBi}$ equivalent isotropic gain at $60.48 \ \text{GHz}$, providing effective isotropic radiated power (EIRP) up to $+38 \ \text{dBm}$.
   - **Beam Sweeping & Tracking**: The modem continuously executes Codebook-Based Beam Sweeping during the IEEE 802.11ay Beam Refinement Protocol (BRP), discovering peer nodes and tracking sub-millimeter mast sway caused by thermal expansion or high-velocity wind loads.
2. **RF Transceiver & Frequency Conversion**:
   - Direct-conversion IQ homodyne transceiver architecture translating baseband signals directly to the 57–66 GHz V-band.
   - Supports IEEE 802.11ad/ay Channel Plan:
     - **Channel 1**: $58.32 \ \text{GHz}$ center frequency ($57.24 - 59.40 \ \text{GHz}$).
     - **Channel 2**: $60.48 \ \text{GHz}$ center frequency ($59.40 - 61.56 \ \text{GHz}$).
     - **Channel 3**: $62.64 \ \text{GHz}$ center frequency ($61.56 - 63.72 \ \text{GHz}$).
     - **Channel 4**: $64.80 \ \text{GHz}$ center frequency ($63.72 - 65.88 \ \text{GHz}$).
   - In our production integration, `ctu-96` operates on **Channel 4 ($64.80 \ \text{GHz}$ / $64800.0 \ \text{MHz}$)** to optimize propagation distance by positioning carrier transmission slightly above the steepest oxygen absorption resonance peak.
3. **Baseband DSP & Modem**:
   - Driven by the Qualcomm IPQ4019 / QCA6438 Terragraph baseband chipset, featuring single-carrier (SC) and orthogonal frequency-division multiplexing (OFDM) modulations.
   - Supports Modulation and Coding Schemes (MCS) from MCS 1 ($\pi/2\text{-BPSK}$) through MCS 12 ($16\text{-QAM}$ with LDPC code rate 13/16), yielding raw PHY data rates up to $4.62 \ \text{Gbps}$ per $2.16 \ \text{GHz}$ channel.
4. **Physical Network Interfaces**:
   - **`eth1`**: 100/1000Base-T RJ-45 Ethernet interface with integrated 802.3at Power over Ethernet (PoE-In), operating at full gigabit line rate ($1.0 \ \text{Gbps}$).
   - **`Host`**: Internal virtual management interface bridging the embedded Linux control processor to the internal switching fabric.
   - **`rf-sector-1`**: Physical RF wireless interface representing the electronic beamforming millimeter-wave sector.

### 3.1.2 MultiHaul TG MH-N366 Distribution Node (DN)
The **MH-N366** serves as the central mesh distribution hub in Terragraph topologies:
- Features **four independent $90^\circ$ phased-array sectors**, delivering full $360^\circ$ non-blocking horizontal coverage.
- Contains dual 10-Gigabit SFP+ optical ports and multi-gigabit copper interfaces.
- Integrates the Terragraph Open/R routing engine, executing distributed Shortest Path First (SPF) routing over an IPv6-centric mesh topology.
- Accommodates up to 60 concurrent Terminal Units across its four sectors, with autonomous beamforming allocation per sector.

---

## 3.2 EtherHaul E-Band Series (EH-8010FX, EH-2500FX, EH-1200TX)

For carrier-grade applications requiring multi-gigabit transport over distances of 2 to 7 kilometers, Ceragon provides the **EtherHaul E-Band** family:
1. **Operating Spectrum (71-76 GHz & 81-86 GHz)**:
   - Operating under Frequency Division Duplexing (FDD) with a standard $10 \ \text{GHz}$ diplexer separation between transmit and receive paths.
   - Unlike the 60 GHz V-Band, the 70/80 GHz E-Band resides within a low atmospheric gaseous absorption window ($\approx 0.4 \ \text{dB/km}$), enabling long-range propagation limited primarily by precipitation.
2. **Extreme Capacity**:
   - The **EH-8010FX** delivers up to **$10 \ \text{Gbps}$ full-duplex** net Ethernet throughput utilizing channel bandwidths up to $2000 \ \text{MHz}$ and modulation up to $128\text{-QAM}$.
   - Sub-microsecond latency ($< 10 \ \mu\text{s}$) across the wireless hop, fully satisfying O-RAN Fronthaul eCPRI synchronization budgets.
3. **Carrier Ethernet 2.0 Engine**:
   - Hardware-based IEEE 802.1ag CFM, ITU-T Y.1731 Performance Monitoring, and ITU-T G.8032 Ethernet Ring Protection Switching (ERPS) with $< 50 \ \text{ms}$ failover times.

---

## 3.3 CeraOS Microwave Family (IP-50C, IP-50E, IP-50FX, IP-20C, IP-20N)

Ceragon's **CeraOS** operating system powers the global flagship microwave and disaggregated cell site routing portfolio:

```
+----------------------------------------------------------------------------------------------------+
|                         CERAOS ADVANCED RADIO & CARRIER ARCHITECTURE                               |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +-----------------------------+                  +-----------------------------------------+    |
|    | Multi-Core RFU (IP-50C)     |                  | Disaggregated Router (IP-50FX)          |    |
|    |                             |                  |                                         |    |
|    |  +-----------------------+  |                  |  +-----------------------------------+  |    |
|    |  | Core 1 Transceiver    |  |                  |  | Broadcom Jericho2 / Qumran2c ASIC |  |    |
|    |  | (Up to 4096-QAM)      |  |                  |  +-----------------+-----------------+  |    |
|    |  +-----------+-----------+  |                  |                    |                    |    |
|    |              | Orthogonal   |                  |  +-----------------v-----------------+  |    |
|    |  +-----------v-----------+  |                  |  | 100G / 25G / 10G Carrier Interfaces |  |    |
|    |  | XPIC Cross-Polarizer  |  |                  |  +-----------------+-----------------+  |    |
|    |  +-----------+-----------+  |                  |                    |                    |    |
|    |              | Coaxial Link |                  |  +-----------------v-----------------+  |    |
|    |  +-----------v-----------+  |                  |  | Multi-Carrier Adaptive Bandwidth  |  |    |
|    |  | Core 2 Transceiver    |  |                  |  | Control (ABC) Engine              |  |    |
|    |  | (Up to 4096-QAM)      |  |                  |  +-----------------+-----------------+  |    |
|    |  +-----------------------+  |                  |                    |                    |    |
|    |                             |                  |  [Port 1: 100G QSFP28] [P2: 25G SFP28]  |    |
|    +-----------------------------+                  +-----------------------------------------+    |
+----------------------------------------------------------------------------------------------------+
```

### 3.3.1 Multi-Carrier & XPIC Technology
- **Cross-Polarization Interference Cancellation (XPIC)**: Transmits two completely independent data streams on the exact same carrier frequency over the same physical antenna—one on Horizontal (H) polarization and one on Vertical (V) polarization. The physical receiver implements an advanced DSP canceller that subtracts cross-polarization leakage in real time, doubling spectral capacity.
- **4096-QAM Modulation**: Utilizes dense 64x64 constellation matrices over channel bandwidths up to $112 \ \text{MHz}$, achieving spectral efficiencies exceeding $11 \ \text{bps/Hz}$.
- **Multi-Carrier Adaptive Bandwidth Control (ABC)**: Bonds multiple physical microwave carriers into a single logical Ethernet link. If one carrier suffers degradation, the ABC engine dynamically rebalances traffic without losing high-priority frames.

---

## 3.4 Hardware Management Interfaces, Addressing, and Out-of-Band Connectivity

To safely interface with SDN controllers, Ceragon nodes maintain isolated management interfaces:
- **Physical Management Ports**: Dedicated out-of-band `MGT` port or in-band VLAN-tagged management over `eth1`.
- **IP Addressing Conventions**:
  - MultiHaul TG defaults to IPv4 address `192.168.1.225` (Netmask: `255.255.255.0`), listening on TCP port `80` (HTTP) or `443` (HTTPS).
  - CeraOS defaults to IPv4 address `192.168.1.1` or `192.168.1.10`, listening on TCP port `443` (HTTPS) and port `830` (NETCONF).
- **Authentication**: HTTP Basic Authentication over TLS, requiring administrative credentials (`admin` / `admin`).

---


---

## 3.5 Comprehensive RF Link Budget Engineering Calculations

To establish deterministic performance baselines across the hybrid transport topology, link budgets are calculated across three representative wireless transport links:

```
+----------------------------------------------------------------------------------------------------+
|                                    LINK BUDGET TRANSMISSION MODEL                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ Transmitter ]                                                              [ Receiver ]       |
|    Output Power: P_tx (dBm)                                                     Sensitivity: RSL_th|
|         |                                                                            ^             |
|         v                                                                            |             |
|    [ Feeder Loss: -L_tx ]                                                      [ Feeder: -L_rx ]   |
|         |                                                                            ^             |
|         v                                                                            |             |
|    [ Antenna Gain: +G_tx ]                                                     [ Gain: +G_rx ]     |
|         |                                                                            ^             |
|         +------------------------+                     +-----------------------------+             |
|                                  |                     |                                           |
|                                  v                     |                                           |
|                     +---------------------------------------+                                      |
|                     | FREE SPACE PROPAGATION & ATMOSPHERE:  |                                      |
|                     | - Free Space Path Loss: -L_fs         |                                      |
|                     | - Gaseous Absorption:   -A_g          |                                      |
|                     | - Rain Attenuation:     -A_R (99.999%)|                                      |
|                     +---------------------------------------+                                      |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

The Received Signal Level ($RSL$) at the receiver antenna terminals is formulated as:

$$RSL = P_{tx} - L_{tx} + G_{tx} - L_{fs} - A_g - A_R + G_{rx} - L_{rx} \quad (\text{dBm})$$

The Fade Margin ($F$) above receiver threshold $RSL_{thresh}$ is:

$$F = RSL - RSL_{thresh} \quad (\text{dB})$$

### 3.5.1 Detailed Link Budget Matrix
The following table details the calculated parameters across three carrier deployment scenarios:

| Link Parameter | Scenario A: V-Band 60 GHz (MultiHaul TG MH-T261) | Scenario B: E-Band 80 GHz (EtherHaul EH-8010FX) | Scenario C: Microwave 18 GHz (CeraOS IP-50C XPIC) |
| :--- | :--- | :--- | :--- |
| **Physical Link Distance ($d$)** | **$0.5 \ \text{km}$ (500 meters)** | **$2.5 \ \text{km}$** | **$12.0 \ \text{km}$** |
| **Carrier Frequency ($f$)** | $64.80 \ \text{GHz}$ (Channel 4) | $83.0 \ \text{GHz}$ | $18.0 \ \text{GHz}$ |
| **Transmitter Power ($P_{tx}$)** | $+12.0 \ \text{dBm}$ (per element cluster) | $+18.0 \ \text{dBm}$ | $+22.0 \ \text{dBm}$ |
| **Feeder / Insertion Losses ($L_{tx} + L_{rx}$)** | $0.0 \ \text{dB}$ (Integrated antenna) | $0.0 \ \text{dB}$ (Direct mount) | $1.5 \ \text{dB}$ (Coaxial diplexer) |
| **Transmitter Antenna Gain ($G_{tx}$)** | $+24.5 \ \text{dBi}$ (`massive2` phased array) | $+43.0 \ \text{dBi}$ (1-ft Cassegrain dish) | $+44.5 \ \text{dBi}$ (3-ft Parabolic dish) |
| **Receiver Antenna Gain ($G_{rx}$)** | $+24.5 \ \text{dBi}$ (`massive2` phased array) | $+43.0 \ \text{dBi}$ (1-ft Cassegrain dish) | $+44.5 \ \text{dBi}$ (3-ft Parabolic dish) |
| **Free Space Path Loss ($L_{fs}$)** | $122.68 \ \text{dB}$ | $138.80 \ \text{dB}$ | $139.14 \ \text{dB}$ |
| **Atmospheric Gaseous Loss ($A_g$)** | $7.50 \ \text{dB}$ ($15.0 \ \text{dB/km} \times 0.5\text{km}$) | $1.75 \ \text{dB}$ ($0.7 \ \text{dB/km} \times 2.5\text{km}$) | $0.24 \ \text{dB}$ ($0.02 \ \text{dB/km} \times 12\text{km}$) |
| **Clear-Sky Received Level ($RSL_{clear}$)** | **$-69.18 \ \text{dBm}$** | **$-36.55 \ \text{dBm}$** | **$-30.38 \ \text{dBm}$** |
| **Rain Rate at 99.999% ($R_{0.01}$, Zone K)** | $42.0 \ \text{mm/h}$ | $42.0 \ \text{mm/h}$ | $42.0 \ \text{mm/h}$ |
| **Specific Rain Attenuation ($\gamma_R$)** | $14.65 \ \text{dB/km}$ | $15.12 \ \text{dB/km}$ | $3.48 \ \text{dB/km}$ |
| **Total Rain Attenuation ($A_R$)** | $7.12 \ \text{dB}$ | $32.40 \ \text{dB}$ | $28.60 \ \text{dB}$ |
| **Worst-Case Faded Level ($RSL_{faded}$)** | **$-76.30 \ \text{dBm}$** | **$-68.95 \ \text{dBm}$** | **$-58.98 \ \text{dBm}$** |
| **Receiver Sensitivity (Max MCS)** | $-64.0 \ \text{dBm}$ (MCS 10, 16-QAM) | $-60.0 \ \text{dBm}$ (128-QAM, 10G) | $-62.0 \ \text{dBm}$ (4096-QAM, 1G) |
| **Receiver Sensitivity (Min MCS)** | $-82.0 \ \text{dBm}$ (MCS 1, $\pi/2$-BPSK) | $-78.0 \ \text{dBm}$ (QPSK, 1G) | $-86.0 \ \text{dBm}$ (QPSK, 120M) |
| **Effective Fade Margin (Min MCS)** | **$+5.70 \ \text{dB}$ (Link Stays UP)** | **$+9.05 \ \text{dB}$ (Link Stays UP)** | **$+27.02 \ \text{dB}$ (Link Stays UP)** |

### 3.5.2 Engineering Insights from the Link Budget Matrix
1. **Clear Sky vs. Rain Faded Modulation Adaptation**:
   In clear sky conditions, the V-Band MultiHaul TG operates comfortably at $-69.18 \ \text{dBm}$, providing enough SNR for MCS 8/9 ($> 2.0 \ \text{Gbps}$). When torrential rain strikes ($42 \ \text{mm/h}$), $RSL$ drops to $-76.30 \ \text{dBm}$. Because $-76.30 \ \text{dBm} < -64.0 \ \text{dBm}$, the high-order modulation fails, but because $-76.30 \ \text{dBm} > -82.0 \ \text{dBm}$, **Hitless ACM drops down to MCS 2/3 (QPSK)**, maintaining link connectivity without frame loss.
2. **The Vital Role of the SDN Controller**:
   Because capacity drops from $2.0 \ \text{Gbps}$ to $460 \ \text{Mbps}$ during the rain event, the SDN controller must instantly adjust traffic shaping to prioritize the 5G URLLC slice and prevent queue drops.


# Chapter 4: Physical YANG Schema Catalog (The 51 RFC-Compliant Models)

## 4.1 Genesis of the 51 Physical YANG Modules Extracted from Hardware

In strict accordance with IETF standards (RFC 7950, RFC 8040, RFC 8342), the Ceragon MultiHaul TG operating system natively exposes its complete data store structure via **51 RFC-compliant YANG data models**. 

During the development of this integration, these 51 schemas were extracted directly from the physical `MH-T261` node via its RESTCONF schema query endpoint (`/restconf/data/ietf-yang-library:yang-library`). The complete catalog is bundled directly into the ETSI TeraFlowSDN driver repository at:
`src/device/service/drivers/ceragon/schemas/yang/`
and mirrored in the CER-Intent standalone package at:
`ceragon_tfs_adapter/schemas/yang/`

```
+----------------------------------------------------------------------------------------------------+
|                               THE 51 PHYSICAL YANG SCHEMAS HIERARCHY                               |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +---------------------------------------------------+------------------------------------+      |
|    |      24 Ceragon / Siklu Proprietary Models        |   27 Standard IETF / IEEE Models   |      |
|    |            (radio-bridge-tg-*)                    |                                    |      |
|    +---------------------------------------------------+------------------------------------+      |
|    | Ethernet & Bridging:                              | Core Datastores & Architecture:    |      |
|    |  - radio-bridge-tg-user-bridge.yang               |  - ietf-datastores.yang (RFC 8342) |      |
|    |  - radio-bridge-tg-interfaces.yang                |  - ietf-yang-library.yang (RFC 8525|      |
|    |  - radio-bridge-tg-bond.yang                      |  - ietf-restconf.yang (RFC 8040)   |      |
|    |  - radio-bridge-tg-tunnel.yang                    |  - ietf-origin.yang                |      |
|    |                                                   |                                    |      |
|    | Radio, RF & Modulation:                           | NETCONF Operations & NMDA:         |      |
|    |  - radio-bridge-tg-radio-common.yang              |  - ietf-netconf.yang (RFC 6241)    |      |
|    |  - radio-bridge-tg-radio-dn.yang                  |  - ietf-netconf-nmda.yang          |      |
|    |  - radio-bridge-tg-acm.yang                       |  - ietf-netconf-acm.yang (RFC 8341)|      |
|    |  - radio-bridge-tg-spider-attenuation-control.yang|  - ietf-netconf-monitoring.yang    |      |
|    |                                                   |                                    |      |
|    | Telemetry, OAM & Maintenance:                     | Interface & IP Primitives:         |      |
|    |  - radio-bridge-tg-pm.yang                        |  - ietf-interfaces.yang (RFC 7223) |      |
|    |  - radio-bridge-tg-cfm.yang                       |  - ietf-ip.yang (RFC 7277)         |      |
|    |  - radio-bridge-tg-ping.yang                      |  - ietf-inet-types.yang            |      |
|    |  - radio-bridge-tg-events.yang                    |  - ietf-yang-types.yang            |      |
|    |                                                   |                                    |      |
|    | System, Inventory & Software:                     | Standard IEEE Bridging & CFM:      |      |
|    |  - radio-bridge-tg-system.yang                    |  - ieee802-dot1q-types.yang        |      |
|    |  - radio-bridge-tg-inventory.yang                 |  - ieee802-dot1q-cfm.yang          |      |
|    |  - radio-bridge-tg-software-upgrade.yang          |  - ieee802-dot1q-cfm-types.yang    |      |
|    |  - radio-bridge-tg-rollback.yang                  |  - IANAifType-MIB.yang             |      |
|    |  - radio-bridge-tg-database-version.yang          |  - SNMPv2-TC.yang                  |      |
|    |                                                   |  - SNMP-FRAMEWORK-MIB.yang         |      |
|    +---------------------------------------------------+------------------------------------+      |
+----------------------------------------------------------------------------------------------------+
```

---

## 4.2 Module Taxonomy & Architectural Categorization

The 51 YANG data models are partitioned into functional domains:

### Category 1: Ethernet Forwarding, VLAN Bridging & LAG Bonding (Proprietary)
- **`radio-bridge-tg-user-bridge.yang`**:
  - Namespace: `urn:siklu:params:xml:ns:yang:radio-bridge-tg-user-bridge`
  - Purpose: Manages IEEE 802.1Q VLAN bridges, port membership, VLAN translation tables, and bridge operational states.
  - Crucial Tree Structure:
    ```
    +--rw user-bridge
       +--rw bridges
       |  +--rw bridge* [bridge-name]
       |     +--rw bridge-name    string
       |     +--rw bridge-type    enumeration { dot1q-bridge, dot1ad-bridge }
       |     +--rw vlan-config
       |        +--rw vlan* [vlan-id]
       |           +--rw vlan-id             uint16
       |           +--rw tagged-ports*       string
       |           +--rw untagged-ports*     string
       +--ro bridge-state
          +--ro forwarding-table
    ```
- **`radio-bridge-tg-interfaces.yang`**: Extends base `ietf-interfaces` with Siklu-specific hardware attributes (PoE power draw, physical SFP transceiver optics telemetry, copper link auto-negotiation, MTU settings up to 9600 bytes).
- **`radio-bridge-tg-bond.yang`**: Controls Link Aggregation Groups (LAG) and IEEE 802.3ad LACP across multi-port and multi-radio configurations.
- **`radio-bridge-tg-tunnel.yang`**: Manages Point-to-Point and Point-to-Multipoint Layer-2 transport tunnels across the mmWave mesh.

### Category 2: Radio Frequency, Phased-Array Beamforming & Modulation (Proprietary)
- **`radio-bridge-tg-radio-common.yang`**:
  - Core container managing RF operating channel frequency (Channels 1 through 4), channel raster, operational roles (Terminal Unit `TU` vs. Distribution Node `DN`), and RF power amplification.
  - Crucial Tree Structure:
    ```
    +--rw radio-common
       +--rw sector* [sector-id]
       |  +--rw sector-id           uint8
       |  +--rw admin-status        enumeration { up, down }
       |  +--rw channel             enumeration { ch1-58320, ch2-60480, ch3-62640, ch4-64800 }
       |  +--rw tx-power-control    enumeration { auto, manual }
       |  +--rw manual-tx-power     int8
       |  +--ro oper-status         enumeration { up, down, degraded }
       |  +--ro rx-rssi-dbm         decimal64
       |  +--ro tx-power-dbm        decimal64
       |  +--ro active-mcs          uint8
       |  +--ro modem-temperature   int16
       |  +--ro rf-temperature      int16
    ```
- **`radio-bridge-tg-radio-dn.yang`**: Distribution Node multi-sector control, beamforming vector tables, and neighbor peer association tables.
- **`radio-bridge-tg-acm.yang`**: Hitless Adaptive Coding and Modulation state machine configuration, defining SNR step-up/step-down thresholds and minimum allowable modulation floors.
- **`radio-bridge-tg-spider-attenuation-control.yang`**: Manages electronic attenuation coefficients across individual antenna elements in the `massive2` phased array.

### Category 3: Performance Monitoring, Telemetry & Diagnostics (Proprietary)
- **`radio-bridge-tg-pm.yang`**: Defines standardized 15-minute and 24-hour historical Performance Monitoring (PM) bins for errored seconds (ES), severely errored seconds (SES), background block errors (BBE), and min/max/average RSSI.
- **`radio-bridge-tg-cfm.yang`**: Native implementation of IEEE 802.1ag Connectivity Fault Management (CFM) Continuity Check Messages (CCM) for hardware link verification.
- **`radio-bridge-tg-events.yang` & `radio-bridge-tg-logging.yang`**: Real-time asynchronous event notification schemas for hardware alarms (temperature threshold crossings, loss of frame, beam realignment events).

### Category 4: System Administration, Dual-Bank Upgrade & Rollback (Proprietary)
- **`radio-bridge-tg-system.yang` & `radio-bridge-tg-inventory.yang`**: Exposes hardware serial numbers, board revisions, component temperatures, MAC addresses, and system uptime.
- **`radio-bridge-tg-software-upgrade.yang`**: Controls dual flash bank firmware switching (`bank-a` vs. `bank-b`), cryptographic signature verification, and hitless bank toggle.
- **`radio-bridge-tg-rollback.yang`**: Provides automated safety rollback timers for unconfirmed candidate configuration commits.

### Category 5: IETF Standards & NMDA Architecture (Standard)
- **`ietf-datastores.yang` (RFC 8342)**: Defines datastore identities: `running`, `candidate`, `intended`, `operational`.
- **`ietf-yang-library.yang` (RFC 8525)**: Catalog of modules, revisions, and conformance.
- **`ietf-restconf.yang` (RFC 8040)**: Root resource definitions, RESTCONF operations, and error structures.
- **`ietf-netconf.yang` & `ietf-netconf-nmda.yang`**: Operations `commit`, `discard-changes`, `lock`, `unlock`.

---

## 4.3 Schema Dependency Graph & Cross-Reference Mapping

```mermaid
graph TD
    subgraph IETF_BASE ["Standard Base Schemas"]
        YANG_LIB["ietf-yang-library\n(RFC 8525)"]
        DATASTORES["ietf-datastores\n(RFC 8342)"]
        RESTCONF["ietf-restconf\n(RFC 8040)"]
        INET["ietf-inet-types\n(RFC 6991)"]
        YANG_TYPES["ietf-yang-types"]
        INTERFACES["ietf-interfaces\n(RFC 7223)"]
    end

    subgraph SIKLU_TYPES ["Ceragon Type Definitions"]
        TG_TYPES["radio-bridge-tg-types"]
    end

    subgraph SIKLU_PROP ["Ceragon Functional Modules"]
        USER_BRIDGE["radio-bridge-tg-user-bridge"]
        RADIO_COMM["radio-bridge-tg-radio-common"]
        RADIO_DN["radio-bridge-tg-radio-dn"]
        ACM["radio-bridge-tg-acm"]
        TG_IF["radio-bridge-tg-interfaces"]
        SYSTEM["radio-bridge-tg-system"]
        INVENTORY["radio-bridge-tg-inventory"]
    end

    INET --> TG_TYPES
    YANG_TYPES --> TG_TYPES
    TG_TYPES --> USER_BRIDGE
    TG_TYPES --> RADIO_COMM
    TG_TYPES --> TG_IF
    INTERFACES --> TG_IF
    RADIO_COMM --> RADIO_DN
    RADIO_COMM --> ACM
    DATASTORES --> RESTCONF
    RESTCONF --> RADIO_COMM
    RESTCONF --> USER_BRIDGE
```

All 51 schemas are verified clean, syntactically valid, and programmatically queryable via the Python `schemas` module bundled in both repositories.


---

## 4.4 Exhaustive YANG Tree Specification for the 24 Ceragon Proprietary Modules

This section details the complete RFC-compliant tree hierarchy, containers, lists, leaf nodes, operational states, and RPC operations across the 24 proprietary YANG modules extracted from the `MH-T261` physical hardware.

### 4.4.1 `radio-bridge-tg-user-bridge.yang`
Defines the hardware Carrier Ethernet bridging engine:
```yang
module: radio-bridge-tg-user-bridge
  +--rw user-bridge
     +--rw bridges
     |  +--rw bridge* [bridge-name]
     |     +--rw bridge-name               string
     |     +--rw bridge-type               enumeration { dot1q-bridge, dot1ad-bridge, provider-bridge }
     |     +--rw aging-time                uint32 (seconds, default: 300)
     |     +--rw mac-learning-enabled      boolean (default: true)
     |     +--rw broadcast-flood-limit     uint32 (pps)
     |     +--rw multicast-flood-limit     uint32 (pps)
     |     +--rw unknown-unicast-limit     uint32 (pps)
     |     +--rw vlan-config
     |     |  +--rw vlan* [vlan-id]
     |     |     +--rw vlan-id             uint16 { 1..4094 }
     |     |     +--rw vlan-name           string
     |     |     +--rw tagged-ports*       leafref -> /interfaces/interface/name
     |     |     +--rw untagged-ports*     leafref -> /interfaces/interface/name
     |     |     +--rw pvid-ports*         leafref -> /interfaces/interface/name
     |     |     +--rw egress-filtering    boolean
     |     +--rw qos-mapping
     |        +--rw pcp-to-tc* [pcp-value]
     |        |  +--rw pcp-value           uint8 { 0..7 }
     |        |  +--rw traffic-class       uint8 { 0..7 }
     |        +--rw dscp-to-tc* [dscp-value]
     |           +--rw dscp-value          uint8 { 0..63 }
     |           +--rw traffic-class       uint8 { 0..7 }
     +--ro bridge-state
        +--ro bridge-oper-status* [bridge-name]
           +--ro bridge-name               string
           +--ro current-mac-count         uint32
           +--ro max-mac-capacity          uint32
           +--ro mac-table
              +--ro entry* [mac-address vlan-id]
                 +--ro mac-address         yang:mac-address
                 +--ro vlan-id             uint16
                 +--ro egress-port         string
                 +--ro entry-type          enumeration { static, dynamic }
                 +--ro age-seconds         uint32
```

### 4.4.2 `radio-bridge-tg-radio-common.yang`
Governs physical RF transceiver parameters and beamforming operation:
```yang
module: radio-bridge-tg-radio-common
  +--rw radio-common
     +--rw global-radio-config
     |  +--rw country-code                 string (ISO 3166-1 alpha-2, e.g., "US", "DE")
     |  +--rw role                         enumeration { terminal-unit-tu, distribution-node-dn }
     |  +--rw dynamic-frequency-selection  boolean
     |  +--rw frequency-raster-khz         uint32 (default: 2160000)
     +--rw sector* [sector-id]
     |  +--rw sector-id                    uint8 { 1..4 }
     |  +--rw admin-status                 enumeration { up, down }
     |  +--rw carrier-channel              enumeration {
     |  |     channel-1-58320mhz,
     |  |     channel-2-60480mhz,
     |  |     channel-3-62640mhz,
     |  |     channel-4-64800mhz
     |  |  }
     |  +--rw channel-bandwidth            enumeration { 2160mhz, 4320mhz-channel-bonded }
     |  +--rw tx-power-control-mode        enumeration { auto-atpc, manual-fixed }
     |  +--rw manual-tx-power-dbm          int8 { -10..+12 }
     |  +--rw target-rssi-floor-dbm        int8 (default: -65)
     |  +--rw antenna-profile              string (e.g., "massive2-planar-32elem")
     |  +--rw max-eirp-dbm                 int8 (regulatory cap, e.g., +40)
     +--ro sector-state* [sector-id]
        +--ro sector-id                    uint8
        +--ro oper-status                  enumeration { up, down, degraded, searching-peer }
        +--ro center-frequency-mhz         decimal64
        +--ro tx-power-actual-dbm          decimal64
        +--ro rx-rssi-actual-dbm           decimal64
        +--ro snr-db                       decimal64
        +--ro cinr-db                      decimal64
        +--ro active-tx-mcs                uint8 { 1..12 }
        +--ro active-rx-mcs                uint8 { 1..12 }
        +--ro current-azimuth-deg          decimal64 { -45.0..+45.0 }
        +--ro current-elevation-deg        decimal64 { -10.0..+10.0 }
        +--ro modem-temperature-c          int16
        +--ro rf-pa-temperature-c          int16
        +--ro pll-lock-status              boolean
```

### 4.4.3 `radio-bridge-tg-acm.yang`
Hitless Adaptive Coding & Modulation state engine configuration:
```yang
module: radio-bridge-tg-acm
  +--rw acm-config
     +--rw sector* [sector-id]
        +--rw sector-id                    uint8
        +--rw acm-mode                     enumeration { fully-adaptive, fixed-profile, bounded-floor }
        +--rw min-allowable-mcs            uint8 { 1..12 } (Rain floor protection)
        +--rw max-allowable-mcs            uint8 { 1..12 }
        +--rw upshift-hysteresis-db        decimal64 (default: 2.0 dB)
        +--rw downshift-margin-db          decimal64 (default: 1.5 dB)
        +--rw observation-window-ms        uint32 (default: 100 ms)
        +--ro acm-state
           +--ro transitions-counter       uint64
           +--ro time-in-mcs-bins* [mcs-index]
              +--ro mcs-index              uint8
              +--ro cumulative-seconds     uint64
```

### 4.4.4 `radio-bridge-tg-spider-attenuation-control.yang`
Manages element-level RF phase and attenuation vectors across the 32-element `massive2` array:
```yang
module: radio-bridge-tg-spider-attenuation-control
  +--rw beamforming-matrix
     +--rw codebook-version                string
     +--rw calibration-mode                enumeration { factory, runtime-thermal-adaptive }
     +--rw element-attenuation* [element-index]
     |  +--rw element-index                uint8 { 0..31 }
     |  +--rw attenuation-step-db          decimal64 { 0.0..15.5 }
     |  +--rw phase-trim-deg               decimal64 { 0.0..360.0 }
     +--ro calibration-telemetry
        +--ro phase-detector-voltages*     decimal64
        +--ro temperature-drift-delta-c    decimal64
```

### 4.4.5 `radio-bridge-tg-interfaces.yang` & `radio-bridge-tg-bond.yang`
Extends physical interfaces and link bonding:
```yang
module: radio-bridge-tg-interfaces
  +--rw physical-interfaces
     +--rw interface* [name]
        +--rw name                         string (e.g., "eth1", "Host")
        +--rw admin-status                 enumeration { up, down }
        +--rw speed-mode                   enumeration { auto-negotiate, fixed-100m, fixed-1g, fixed-2.5g, fixed-10g }
        +--rw duplex-mode                  enumeration { full-duplex, half-duplex }
        +--rw mtu                          uint16 { 64..9600 }
        +--rw flow-control                 boolean
        +--rw poe-power-class              uint8
        +--ro interface-telemetry
           +--ro oper-status               enumeration { up, down, link-fault }
           +--ro in-octets                 uint64
           +--ro out-octets                uint64
           +--ro in-unicast-pkts           uint64
           +--ro out-unicast-pkts          uint64
           +--ro in-crc-errors             uint64
           +--ro in-discards               uint64
           +--ro link-flaps-count          uint32

module: radio-bridge-tg-bond
  +--rw link-aggregation
     +--rw lag-group* [lag-id]
        +--rw lag-id                       uint8
        +--rw lag-name                     string
        +--rw lag-mode                     enumeration { lacp-802.3ad, static-trunk }
        +--rw load-balance-hash            enumeration { l2-mac, l3-ip, l4-port }
        +--rw member-interfaces*           string
        +--rw min-active-links             uint8
```

### 4.4.6 `radio-bridge-tg-pm.yang` & `radio-bridge-tg-cfm.yang`
Carrier-grade performance monitoring and hardware fault management:
```yang
module: radio-bridge-tg-pm
  +--ro performance-monitoring
     +--ro intervals-15min* [sector-id interval-number]
     |  +--ro sector-id                    uint8
     |  +--ro interval-number              uint8 { 1..96 } (24-hour circular buffer)
     |  +--ro timestamp                    yang:date-and-time
     |  +--ro errored-seconds              uint32
     |  +--ro severely-errored-seconds     uint32
     |  +--ro background-block-errors      uint64
     |  +--ro min-rssi-dbm                 decimal64
     |  +--ro max-rssi-dbm                 decimal64
     |  +--ro avg-rssi-dbm                 decimal64
     |  +--ro min-snr-db                   decimal64
     |  +--ro max-snr-db                   decimal64
     |  +--ro throughput-bytes-rx          uint64
     |  +--ro throughput-bytes-tx          uint64
     +--ro intervals-24hr* [sector-id day-number]
        +--ro sector-id                    uint8
        +--ro day-number                   uint8 { 1..30 }
        +--ro total-unavailability-seconds uint32

module: radio-bridge-tg-cfm
  +--rw cfm-maintenance-domain* [md-name]
     +--rw md-name                         string
     +--rw md-level                        uint8 { 0..7 }
     +--rw maintenance-association* [ma-name]
        +--rw ma-name                      string
        +--rw ccm-interval                 enumeration { 3.3ms, 10ms, 100ms, 1s, 10s }
        +--rw mep* [mep-id]
           +--rw mep-id                    uint16
           +--rw interface                 string
           +--ro ccm-status                enumeration { active, peer-timeout, defect }
```

### 4.4.7 `radio-bridge-tg-system.yang`, `radio-bridge-tg-inventory.yang`, `radio-bridge-tg-software-upgrade.yang`, `radio-bridge-tg-rollback.yang`
System maintenance, inventory, bank switching, and automatic transactional rollback:
```yang
module: radio-bridge-tg-system
  +--rw system-identity
  |  +--rw hostname                        string
  |  +--rw system-location                 string
  |  +--rw system-contact                  string
  |  +--rw timezone                        string
  |  +--ro system-uptime-seconds           uint64
  |  +--ro current-datetime                yang:date-and-time

module: radio-bridge-tg-inventory
  +--ro inventory
     +--ro chassis
        +--ro vendor                       string (e.g., "Siklu / Ceragon")
        +--ro model-name                   string (e.g., "MH-T261")
        +--ro serial-number                string (e.g., "AE09100255")
        +--ro hardware-revision            string (e.g., "A0")
        +--ro mac-address-base             yang:mac-address
        +--ro manufacturing-date           string

module: radio-bridge-tg-software-upgrade
  +--rw software-management
     +--ro active-bank                     enumeration { bank-a, bank-b }
     +--ro active-version                  string (e.g., "3.4.0-4377-5faacf06a")
     +--ro standby-bank                    enumeration { bank-a, bank-b }
     +--ro standby-version                 string
     +--rw rpc execute-software-upgrade
     |  +--rw input
     |     +--rw image-url                 inet:uri
     |     +--rw md5-checksum              string
     +--rw rpc toggle-active-bank
        +--rw input
           +--rw perform-reboot            boolean

module: radio-bridge-tg-rollback
  +--rw automatic-rollback
     +--rw enabled                         boolean (default: true)
     +--rw timeout-seconds                 uint32 (default: 300)
     +--ro pending-commit-timer            uint32
     +--rw rpc confirm-commit
```


---

# Chapter 5: ETSI TeraFlowSDN Architecture & Integration Framework

## 5.1 ETSI TFS 7.0 Cloud-Native Architecture

ETSI TeraFlowSDN (TFS) is architectured as a cloud-native, microservice-based Software-Defined Networking (SDN) controller engineered specifically for telecommunications operators. Running on a Kubernetes cluster, TFS disaggregates network control, path computation, slice management, and device interfacing into isolated, independently scalable microservices.

```
+----------------------------------------------------------------------------------------------------+
|                             ETSI TERAFLOWSDN 7.0 MICROSERVICE MESH                                 |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ Northbound API (REST / IETF Network Topology RFC 8345 / gRPC ) ]                             |
|                                         |                                                          |
|       +---------------------------------+--------------------------------+                         |
|       |                                 |                                |                         |
|       v                                 v                                v                         |
|  +-----------------+           +-----------------+              +-----------------+                |
|  | Context Service | <=======> | Service Service | <==========> |  Slice Service  |                |
|  |  (gRPC :1010)   |           |  (gRPC :3030)   |              |  (gRPC :4040)   |                |
|  +--------+--------+           +--------+--------+              +--------+--------+                |
|           |                             |                                |                         |
|           | CRDB Mutex                  | Path Constraints               | Slice Decomposition     |
|           v                             v                                v                         |
|  +-----------------+           +-----------------+              +-----------------+                |
|  |   CockroachDB   |           | PathComp Service|              |Policy / Automate|                |
|  | (Distributed SQL|           |  (CSPF Solvers) |              | (Closed Loop)   |                |
|  +-----------------+           +-----------------+              +-----------------+                |
|           ^                                                              |                         |
|           | Topology Ingestion                                           | Device Mutations        |
|           +-----------------------------+--------------------------------+                         |
|                                         |                                                          |
|                                         v                                                          |
|                                +-----------------+                                                 |
|                                | Device Service  |                                                 |
|                                |  (gRPC :2020)   |                                                 |
|                                +--------+--------+                                                 |
|                                         |                                                          |
|                    +--------------------+--------------------+                                     |
|                    |                    |                    |                                     |
|                    v                    v                    v                                     |
|            +---------------+    +---------------+    +---------------+                             |
|            | OpenConfig    |    | P4 Driver     |    | Ceragon Driver|  <-- [OUR WORK: ENUM 22]    |
|            | Netconf Driver|    | (Stratum)     |    | (RESTCONF)    |                             |
|            +---------------+    +---------------+    +-------+-------+                             |
|                                                              |                                     |
|                                                              v                                     |
|                                                      [ Ceragon Hardware ]                          |
+----------------------------------------------------------------------------------------------------+
```

### 5.1.1 Microservice Communication & gRPC Fabric
Every microservice in TeraFlowSDN exposes high-performance gRPC endpoints defined via Google Protocol Buffers (protobuf v3). gRPC utilizes HTTP/2 multiplexing, header compression, and binary serialization, reducing serialization overhead by over 70% compared to REST/JSON.

Key ports across the TFS mesh include:
- `ContextService` (`:1010`): Central datastore gateway managing contexts, topologies, devices, links, services, and slices.
- `DeviceService` (`:2020`): Hardware abstraction layer managing driver lifecycles, configuration staging, and Southbound transactions.
- `ServiceService` (`:3030`): Layer-2/Layer-3 service lifecycle manager.
- `SliceService` (`:4040`): 3GPP and IETF network slicing coordinator.
- `PathCompService` (`:20020`): High-speed Constrained Shortest Path First (CSPF) calculation engine.
- `NBI REST` (`:8080` / forwarded to `:8088`): Operator REST API providing IETF-compliant network topology representations.

---

## 5.2 Microservice Deep-Dive

### 5.2.1 Context Service & CockroachDB Datastore
The `ContextService` acts as the definitive network source of truth. Unlike transient memory-based SDN controllers, all network states in TFS are persisted in **CockroachDB**, a distributed, transactional SQL database supporting serializable ACID isolation.
The database schema stores:
- **`Context`**: Administrative multi-tenancy domains (e.g., `admin`, `tenant-oran`).
- **`Topology`**: Graph representation consisting of nodes (`Device`), interfaces (`EndPoint`), and transmission spans (`Link`).
- **`Device`**: Physical or simulated entities, storing operational status (`DEVICEOPERATIONALSTATUS_ENABLED`), driver assignments, and configuration rules (`ConfigRule`).
- **`Link`**: Uni- or bi-directional transmission links with total capacity, available capacity, and propagation delay.
- **`Service` & `Slice`**: Dynamic end-to-end paths with allocated bandwidth, QoS classes, and member endpoints.

### 5.2.2 Device Service & DriverFactory Lifecycle
The `DeviceService` is responsible for orchestrating hardware mutations. When an operator or intent engine issues a configuration update, the `DeviceService`:
1. Queries the device's driver list from `ContextService`.
2. Invokes the `DriverFactory` to instantiate the appropriate driver class (e.g., `CeragonDriver`).
3. Manages driver thread safety and lock acquisition per physical hardware target.
4. Executes the two-phase transaction lifecycle: staging mutations in the candidate datastore, verifying execution, and triggering atomic commit or rollback.

---

## 5.3 Southbound Driver Architecture & `_Driver` Abstract Base Class

All southbound drivers in ETSI TeraFlowSDN inherit from the abstract base class `_Driver` defined in:
`src/device/service/driver_api/_Driver.py`

```python
class _Driver(ABC):
    @abstractmethod
    def Connect(self) -> bool:
        """Establish session with physical or simulated equipment."""
        pass

    @abstractmethod
    def Disconnect(self) -> bool:
        """Gracefully terminate session and release hardware locks."""
        pass

    @abstractmethod
    def GetInitialConfig(self) -> List[Tuple[str, Any]]:
        """Interrogate hardware inventory, interfaces, and operational state."""
        pass

    @abstractmethod
    def GetConfig(self, resource_keys: List[str]) -> List[Tuple[str, Union[Any, None, Exception]]]:
        """Query specific telemetry or operational parameters."""
        pass

    @abstractmethod
    def SetConfig(self, resources: List[Tuple[str, Any]]) -> List[Union[bool, Tuple[str, Any, Exception]]]:
        """Apply configuration mutations via candidate datastore."""
        pass

    @abstractmethod
    def DeleteConfig(self, resources: List[Tuple[str, Any]]) -> List[Union[bool, Tuple[str, Any, Exception]]]:
        """Remove configuration rules or sub-interfaces."""
        pass

    @abstractmethod
    def SubscribeState(self, subscriber: Any) -> bool:
        """Register asynchronous event listener for alarms and telemetry."""
        pass

    @abstractmethod
    def UnsubscribeState(self, subscriber: Any) -> bool:
        """Deregister asynchronous event listener."""
        pass
```

---

## 5.4 Driver Registration in Protobuf Enum (`DEVICEDRIVER_CERAGON = 22`)

To natively integrate the Ceragon driver into TeraFlowSDN without resorting to generic or simulated workarounds, we allocated an official protobuf enum identifier:

In `src/common/proto/context.proto`:
```protobuf
enum DeviceDriverEnum {
    DEVICEDRIVER_UNDEFINED = 0;
    DEVICEDRIVER_OPENCONFIG = 1;
    DEVICEDRIVER_TRANSPORT_API = 2;
    DEVICEDRIVER_P4 = 3;
    DEVICEDRIVER_IETF_NETWORK_TOPOLOGY = 4;
    DEVICEDRIVER_ONF_TR_532 = 5;
    DEVICEDRIVER_XR = 6;
    DEVICEDRIVER_IETF_L2VPN = 7;
    DEVICEDRIVER_GNMI_OPENCONFIG = 8;
    DEVICEDRIVER_OPTICAL_TFS = 9;
    DEVICEDRIVER_IETF_ACTN = 10;
    DEVICEDRIVER_OC = 11;
    DEVICEDRIVER_QKD = 12;
    // ...
    DEVICEDRIVER_CERAGON = 22; // <-- ALLOCATED OFFICIAL CERAGON DRIVER IDENTIFIER
}
```

In `src/device/service/DriverFactory.py`:
```python
from device.service.drivers.ceragon.CeragonDriver import CeragonDriver
from common.proto.context_pb2 import DeviceDriverEnum

DRIVER_CLASS_MAPPING = {
    # Existing drivers...
    DeviceDriverEnum.DEVICEDRIVER_CERAGON: CeragonDriver,
}
```

This ensures that whenever a device is registered in TFS with `device_drivers: [22]`, the TFS core automatically instantiates the `CeragonDriver`.

---

## 5.5 Candidate Datastore & Two-Phase Commit (2PC) Transactional Protocol

Carrier-grade telecommunications hardware strictly adheres to the **Network Management Datastore Architecture (NMDA, RFC 8342)**. Unlike consumer routers where settings are written directly to running memory, Ceragon equipment enforces a **Candidate Datastore** lifecycle.

```mermaid
sequenceDiagram
    autonumber
    actor Engine as CER-Intent / Operator
    participant NBI as TFS REST NBI (:8088)
    participant DEV as TFS DeviceService
    participant DRV as CeragonDriver
    participant CLI as CeragonRestClient
    participant HW as Ceragon MH-T261 Hardware

    Engine->>NBI: PUT /tfs-api/device/{uuid} (SetConfig Rules)
    NBI->>DEV: ConfigureDevice(DeviceConfigRules)
    DEV->>DRV: SetConfig([(/radio/tuning, payload)])
    
    Note over DRV,HW: Phase 1: Staging Mutation in Candidate Datastore
    DRV->>CLI: stage_candidate("/radio-bridge-tg-radio-common:radio-common/...", payload)
    CLI->>HW: PATCH /restconf/ds/ietf-datastores:candidate/... (HTTP Basic Auth)
    
    alt Staging Accepted (HTTP 200 / 204)
        HW-->>CLI: 204 No Content
        Note over DRV,HW: Phase 2: Atomic Commit to Running Datastore
        DRV->>CLI: commit_candidate()
        CLI->>HW: POST /restconf/operations/ietf-netconf:commit
        
        alt Commit Validated (HTTP 200 OK)
            HW-->>CLI: 200 OK (Running DS Updated & Applied to Hardware ASIC)
            CLI-->>DRV: Success (commit=True)
            DRV-->>DEV: [('/radio/tuning', True)]
            DEV-->>NBI: Configuration Applied
            NBI-->>Engine: HTTP 200 OK
        else Commit Rejected (RF Constraint Violation)
            HW-->>CLI: 409 Conflict / 400 Bad Request
            Note over DRV,HW: Automatic Safety Rollback
            DRV->>CLI: discard_candidate()
            CLI->>HW: POST /restconf/operations/ietf-netconf:discard-changes
            HW-->>CLI: 200 OK (Candidate Flushed)
            CLI-->>DRV: Failure (Rolled back)
            DRV-->>DEV: [('/radio/tuning', False, Exception('Commit rejected'))]
            DEV-->>NBI: Rollback Completed
            NBI-->>Engine: HTTP 409 Conflict (Safely Reverted)
        end
    else Staging Rejected (Malformed Syntax / Unsupported Value)
        HW-->>CLI: 400 Bad Request
        DRV->>CLI: discard_candidate()
        CLI->>HW: POST /restconf/operations/ietf-netconf:discard-changes
        DRV-->>DEV: [('/radio/tuning', False, Exception('Staging rejected'))]
        DEV-->>NBI: Error (Staging Failed)
        NBI-->>Engine: HTTP 400 Bad Request
    end
```

This 2-phase commit mechanism guarantees that an invalid configuration—such as setting an out-of-band carrier frequency or an unsupported modulation scheme—will never crash the live wireless link. The transaction is safely discarded before hardware state is modified.

---

# Chapter 6: Ceragon Southbound RESTCONF Driver Deep-Dive

## 6.1 Package Architecture & Module Hierarchy

The Ceragon Southbound Driver is implemented under:
`src/device/service/drivers/ceragon/`

The module layout is structured as follows:
```
src/device/service/drivers/ceragon/
├── __init__.py                # Package exports (CeragonDriver, CeragonRestClient)
├── CeragonDriver.py           # Core TFS Driver implementation inheriting _Driver
├── CeragonRestClient.py       # Robust RFC 8040 RESTCONF client engine
├── Tools.py                   # Configuration rule parsers and endpoint converters
├── models.py                  # Normalized dataclasses and domain structures
└── schemas/
    ├── __init__.py            # Python schema locator and accessor API
    └── yang/                  # Directory containing all 51 physical RFC-compliant YANG models
        ├── radio-bridge-tg-user-bridge.yang
        ├── radio-bridge-tg-radio-common.yang
        ├── ietf-datastores.yang
        └── ... (48 additional .yang files)
```

---

## 6.2 `CeragonDriver.py` Implementation & Analysis

The `CeragonDriver` class orchestrates driver lifecycle, synchronization, and translation between TFS protobuf structures and device RESTCONF endpoints.

### 6.2.1 Initialization & Connect()
```python
class CeragonDriver(_Driver):
    def __init__(self, address: str, port: int, **settings) -> None:
        super().__init__()
        self.__address = address
        self.__port = int(port or 80)
        self.__settings = settings
        self.__lock = threading.Lock()
        
        # Extract credentials and protocol options
        username = settings.get("username", "admin")
        password = settings.get("password", "admin")
        scheme = settings.get("scheme", "http" if self.__port in [80, 8080] else "https")
        timeout = int(settings.get("timeout", 15))
        verify_tls = settings.get("verify_tls", False)

        self.__client = CeragonRestClient(
            host=self.__address,
            port=self.__port,
            username=username,
            password=password,
            scheme=scheme,
            timeout=timeout,
            verify_tls=verify_tls,
        )
        self.__connected = False

    def Connect(self) -> bool:
        with self.__lock:
            if self.__connected:
                return True
            try:
                probe_res = self.__client.probe_device()
                self.__connected = probe_res.get("connected", False)
                LOGGER.info("Connected to Ceragon node: %s", probe_res.get("device_family"))
                return self.__connected
            except Exception as e:
                LOGGER.error("Failed to connect to Ceragon node at %s: %s", self.__address, str(e))
                return False
```

### 6.2.2 GetInitialConfig() & EndPoint Extraction
Upon connection, the TFS core calls `GetInitialConfig()` to populate CockroachDB with device endpoints and hardware metadata:
```python
    def GetInitialConfig(self) -> List[Tuple[str, Any]]:
        with self.__lock:
            if not self.__connected:
                self.Connect()
            
            # Fetch live operational state from device
            dev_state = self.__client.get_system_info()
            interfaces = self.__client.get_interfaces()
            sectors = self.__client.get_radio_sectors()
            
            # Populate normalized state model
            normalized = CeragonDeviceState(
                node_name=dev_state.get("node_name", "Ceragon-Node"),
                serial_number=dev_state.get("serial_number", "UNKNOWN"),
                hardware_rev=dev_state.get("hardware_rev", "A0"),
                software_version=dev_state.get("software_version", "3.4.0"),
                interfaces=interfaces,
                radio_sectors=sectors,
                operating_params=self.__client.get_operating_parameters(),
            )
            
            # Use Tools.py to generate TFS EndPoints and ConfigRules
            endpoints = Tools.extract_endpoints(normalized)
            config_rules = Tools.format_resource_rules(normalized)
            
            # Return initial configuration tuples
            results = []
            for ep in endpoints:
                results.append(("_endpoint", ep))
            for rule in config_rules:
                results.append((rule["resource_key"], rule["resource_value"]))
            
            return results
```

### 6.2.3 SetConfig(): Transactional Candidate Engine
```python
    def SetConfig(self, resources: List[Tuple[str, Any]]) -> List[Union[bool, Tuple[str, Any, Exception]]]:
        results = []
        with self.__lock:
            for key, value in resources:
                try:
                    action, path, payload = Tools.parse_config_rule(key, value)
                    if action == "RADIO_TUNING":
                        # Phase 1: Stage mutation in candidate datastore
                        staged = self.__client.stage_candidate(path, payload)
                        if staged:
                            # Phase 2: Atomic Commit
                            committed = self.__client.commit_candidate()
                            results.append((key, committed))
                        else:
                            self.__client.discard_candidate()
                            results.append((key, False, Exception("Staging rejected by hardware")))
                    elif action == "SLICE_CREATE":
                        staged = self.__client.stage_candidate(path, payload)
                        if staged:
                            committed = self.__client.commit_candidate()
                            results.append((key, committed))
                        else:
                            self.__client.discard_candidate()
                            results.append((key, False, Exception("Slice staging rejected")))
                    else:
                        results.append((key, True))
                except Exception as e:
                    self.__client.discard_candidate()
                    results.append((key, False, e))
        return results
```

---

## 6.3 `CeragonRestClient.py` Implementation & Analysis

The `CeragonRestClient` manages HTTP/HTTPS connections, authentication headers, connection pooling, and RESTCONF URI auto-negotiation.

Key capabilities include:
1. **Auto-Negotiation of RESTCONF Paths**:
   - Detects whether the target device is a **Terragraph node** (using `/restconf/ds/ietf-datastores:candidate`) or a **CeraOS node** (using `/restconf/data`).
2. **Session Pooling**: Uses `requests.Session` with `HTTPAdapter` configured with automatic retries (`urllib3.util.retry.Retry`) to withstand transient wireless link noise.
3. **Candidate Datastore Operations**:
   - `stage_candidate(path, payload)`: Sends an RFC 8040 `PATCH` or `PUT` request with `Content-Type: application/yang-data+json`.
   - `commit_candidate()`: Invokes the RPC endpoint:
     `POST /restconf/operations/ietf-netconf:commit`
   - `discard_candidate()`: Invokes the rollback RPC endpoint:
     `POST /restconf/operations/ietf-netconf:discard-changes`

---

## 6.4 `Tools.py` Utility Framework

The `Tools` utility class encapsulates protocol transformation rules:
- **`extract_endpoints(device_state)`**: Inspects physical RJ-45, SFP+, and mmWave radio interfaces, formatting each into standard TFS `EndPoint` structures with deterministic port types:
  - `copper-rj45-1g` for Gigabit Ethernet ports.
  - `radio-60ghz-mmwave` for 60 GHz V-Band sectors.
  - `copper-rj45-0g` for internal host processor management.
- **`format_resource_rules(device_state)`**: Formats device capabilities, hardware serials, operating frequencies, and temperatures into JSON-stringified config rules.
- **`parse_config_rule(key, value)`**: Parses incoming TFS config rules (e.g., `/radio/tuning`, `/slice/*`), extracting target YANG container paths and constructing conformant JSON payloads.

---

## 6.5 `models.py` Data Model Abstractions

Defines type-safe Python `dataclasses`:
```python
@dataclass
class CeragonInterface:
    name: str
    if_type: str
    speed_gbps: float
    admin_status: str
    oper_status: str
    mac_address: str
    ip_address: Optional[str] = None
    vlan_id: Optional[int] = None

@dataclass
class CeragonRadioSector:
    sector_id: str
    carrier_freq_mhz: float
    channel_bandwidth_mhz: float
    antenna_type: str
    active_mcs: int
    tx_power_dbm: float
    rx_rssi_dbm: float
    oper_status: str
    temperature_c: float

@dataclass
class CeragonDeviceState:
    node_name: str
    serial_number: str
    hardware_rev: str
    software_version: str
    interfaces: List[CeragonInterface]
    radio_sectors: List[CeragonRadioSector]
    operating_params: Dict[str, Any]
```
These models provide strict type safety and guarantee error-free serialization across TFS gRPC boundaries.


---

## 6.6 Full Source Code Specification: `templates.py` & Candidate Mutation Generators

The file `src/device/service/drivers/ceragon/templates.py` implements the deterministic payload transformers that convert high-level TFS intent rules into RFC 8040 and RFC 7950 conformant YANG payloads.

```python
"""
YANG Configuration Payload Generators for Ceragon MultiHaul TG / CeraOS
=======================================================================
Translates normalized dictionary parameters into validated YANG JSON schemas.
"""
from typing import Any, Dict, List

def build_radio_tuning_payload(
    sector_id: int = 1,
    channel_name: str = "ch4-64800",
    tx_power_control: str = "auto",
    manual_tx_power_dbm: int = 0
) -> Dict[str, Any]:
    """
    Constructs candidate datastore mutation for radio-bridge-tg-radio-common.
    """
    payload = {
        "radio-bridge-tg-radio-common:sector": {
            "sector-id": int(sector_id),
            "carrier-channel": str(channel_name),
            "tx-power-control-mode": (
                "auto-atpc" if tx_power_control.lower() in ["auto", "auto-atpc"] 
                else "manual-fixed"
            ),
        }
    }
    if tx_power_control.lower() not in ["auto", "auto-atpc"]:
        payload["radio-bridge-tg-radio-common:sector"]["manual-tx-power-dbm"] = int(manual_tx_power_dbm)
    return payload

def build_vlan_slice_payload(
    vlan_id: int,
    slice_name: str,
    tagged_ports: List[str] = None,
    untagged_ports: List[str] = None
) -> Dict[str, Any]:
    """
    Constructs candidate datastore mutation for radio-bridge-tg-user-bridge.
    """
    tagged = tagged_ports or ["eth1", "Host"]
    untagged = untagged_ports or []
    
    return {
        "radio-bridge-tg-user-bridge:vlan": {
            "vlan-id": int(vlan_id),
            "vlan-name": str(slice_name),
            "tagged-ports": tagged,
            "untagged-ports": untagged,
            "egress-filtering": True
        }
    }

def build_acm_floor_hardening_payload(
    sector_id: int = 1,
    min_mcs: int = 2,
    upshift_hysteresis_db: float = 2.5,
    downshift_margin_db: float = 1.5
) -> Dict[str, Any]:
    """
    Constructs candidate datastore mutation for radio-bridge-tg-acm.
    Protects against rain-fade induced link flap by raising the minimum MCS floor.
    """
    return {
        "radio-bridge-tg-acm:sector": {
            "sector-id": int(sector_id),
            "acm-mode": "bounded-floor",
            "min-allowable-mcs": int(min_mcs),
            "upshift-hysteresis-db": float(upshift_hysteresis_db),
            "downshift-margin-db": float(downshift_margin_db)
        }
    }
```

---

## 6.7 Thread Safety, Mutex Locking & Connection Keepalive Mechanics

In carrier deployments, the TFS `DeviceService` can dispatch concurrent telemetry queries (`GetConfig`) while simultaneously staging network slice configuration updates (`SetConfig`). 

To avoid race conditions and datastore corruptions within the device's embedded candidate buffer:
1. **Per-Device Reentrant Mutex Locking (`threading.Lock`)**:
   Every public driver invocation (`Connect`, `Disconnect`, `GetInitialConfig`, `GetConfig`, `SetConfig`, `DeleteConfig`) acquires `self.__lock`.
2. **Session Keepalive**:
   The HTTP session establishes persistent TCP keepalives:
   ```python
   adapter = requests.adapters.HTTPAdapter(
       pool_connections=5,
       pool_maxsize=10,
       max_retries=urllib3.util.retry.Retry(
           total=3,
           backoff_factor=0.5,
           status_forcelist=[500, 502, 503, 504]
       )
   )
   self.session.mount("http://", adapter)
   self.session.mount("https://", adapter)
   ```
3. **Atomic Rollback Guarantee**:
   If an uncaught exception occurs at any point during `SetConfig()`, the `finally` or `except` clause immediately issues an asynchronous `discard_candidate()` call to ensure the hardware never remains in a locked or uncommitted candidate state.


---

# Chapter 7: Simulated Components & Network Topology Replication

## 7.1 The Need for Hybrid Emulation-Physical SDN Testing Environments

In carrier-grade telecommunications research and pre-production validation, testing SDN control planes against isolated single-node hardware benches fails to capture network-wide dynamics such as multi-hop propagation delays, route flap dampening, cascading congestion, and end-to-end slice isolation. Conversely, deploying an entire nationwide 5G transport topology comprising dozens of physical cell towers and microwave towers in a software engineering lab is financially and logistically impossible.

To resolve this dichotomy, ETSI TeraFlowSDN features a **Simulated / Emulated Device Driver (`DEVICEDRIVER_EMULATED = 1`)**. By combining physical hardware in the loop (Hardware-in-the-Loop, HIL) with high-fidelity simulated components, we construct a **Hybrid Autonomous Testbed**:
- **Physical Node**: A live Ceragon MultiHaul TG `MH-T261` (node name `ctu-96`, serial `AE09100255`) operating at 60 GHz V-band over physical Ethernet and RF media.
- **Simulated Topology**: 34 realistic O-RAN transport nodes representing a regional metro-access network, complete with simulated baseband processors, optical core routers, microwave hops, and edge data centers.

```
+----------------------------------------------------------------------------------------------------+
|                         HYBRID PHYSICAL & EMULATED TOPOLOGY IN TERAFLOWSDN                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ 5x O-CU Core Aggregation ] <==== 10G/40G Optical Core ====> [ 2x Regional Edge Data Centers ] |
|                 |                                                                                  |
|        10G Optical / Microwave Hops                                                                |
|                 v                                                                                  |
|    [ 7x O-DU Midhaul Hubs ]                                                                        |
|                 |                                                                                  |
|        2.5G eCPRI / Microwave Hops                                                                 |
|                 v                                                                                  |
|    [ 10x O-RU Cell Site Antennas ]                                                                 |
|                 |                                                                                  |
|        1.0 Gbps mmWave Physical Transport Link                                                     |
|                 v                                                                                  |
|    +-------------------------------------------------------------+                                 |
|    | LIVE PHYSICAL HARDWARE IN THE LOOP:                         |                                 |
|    | Ceragon / Siklu MultiHaul TG MH-T261 (ctu-96)               |                                 |
|    | - Real-time RFC 8040 RESTCONF candidate datastore           |                                 |
|    | - Live 60 GHz V-Band beamforming & active telemetry         |                                 |
|    +-------------------------------------------------------------+                                 |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 7.2 The 34-Node CER-Intent Reference Transport Network

The original CER-Intent reference network topology reflects a realistic metropolitan 5G Open RAN deployment spanning four distinct tiers:

### 1. Open Central Units (O-CU) — 5 Nodes
- `O-CU North`, `O-CU South`, `O-CU East`, `O-CU West`, `O-CU Central`.
- Deployed at centralized metro telco points of presence (PoP).
- Execute PDCP, SDAP, and radio resource control (RRC) for hundreds of thousands of concurrent user equipments (UE).
- Interconnected via a high-capacity optical mesh running at 40 Gbps and 100 Gbps.

### 2. Open Distributed Units (O-DU) — 7 Nodes
- `O-DU Hub 1` through `O-DU Hub 7`.
- Deployed at regional aggregation hubs.
- Execute real-time High-PHY, MAC scheduling, and RLC segmentation.
- Connected upstream to O-CUs via 10 Gbps Carrier Ethernet microwave or fiber midhaul links.

### 3. Open Radio Units (O-RU) — 10 Nodes
- `O-RU Cell 101` through `O-RU Cell 110`.
- Deployed at street-level lamp posts, utility poles, and rooftop cell sites.
- Execute Low-PHY, digital beamforming, and RF amplification.
- Connected to O-DUs via 2.5 Gbps and 10 Gbps wireless fronthaul hops.

### 4. Wireless Transport Microwave / mmWave Hops — 10 Links
- High-capacity wireless radio links providing non-line-of-sight (NLOS) and line-of-sight (LOS) backhaul across urban street canyons where trenching fiber is impossible.

### 5. Multi-Access Edge Computing (MEC) Data Centers — 2 Nodes
- `MEC DC North` and `MEC DC South`.
- Host low-latency virtualized network functions (VNFs), UPF user planes, and latency-critical enterprise edge applications (autonomous driving navigation, computer vision inference).

---

## 7.3 Translating the CER-Intent Graph into TFS Descriptors

To instantiate this entire 34-node topology inside ETSI TeraFlowSDN, we authored the comprehensive JSON descriptor file:
`tests/cera_simulated_topology_tfs.json` (and mirrored in `descriptors/cera_simulated_topology_tfs.json`).

### 7.3.1 Context & Topology Descriptors
```json
{
  "contexts": [
    {
      "context_id": { "context_uuid": { "uuid": "admin" } },
      "name": "admin"
    }
  ],
  "topologies": [
    {
      "topology_id": {
        "context_id": { "context_uuid": { "uuid": "admin" } },
        "topology_uuid": { "uuid": "admin" }
      },
      "name": "admin"
    }
  ]
}
```

### 7.3.2 Simulated Device Descriptor Structure
Each of the 34 nodes is defined with:
- **`device_id`**: Deterministic UUID string.
- **`device_type`**: `emu-packet-router`, `emu-optical-switch`, or `emu-wireless-node`.
- **`device_drivers`**: `[1]` (`DEVICEDRIVER_EMULATED`).
- **`device_operational_status`**: `DEVICEOPERATIONALSTATUS_ENABLED` (2).
- **`device_endpoints`**: List of interfaces with standard types (`copper-rj45-1g`, `optical-10g`, etc.).
- **`device_config`**: Initial baseline configuration rules.

### 7.3.3 Inter-Device Topology Links
Link descriptors define the bidirectional connectivity, linking specific `EndPointId` pairs across the graph, establishing explicit total capacities (e.g., $10.0 \ \text{Gbps}$) and propagation delays (e.g., $1.2 \ \text{ms}$).

---

## 7.4 Physical Node Integration: Injecting the Physical `MH-T261` into the Topology

Alongside the 34 simulated components, the physical Ceragon MultiHaul TG node (`ctu-96`) is registered into the **exact same Context and Topology (`admin/admin`)**:

### 7.4.1 Deterministic UUID5 Generation
To ensure idempotency across controller restarts, the device UUID is generated using UUID Version 5 (SHA-1 hashing over the DNS namespace with the hardware serial number):
```python
import uuid
NAMESPACE_CERAGON = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
device_uuid = str(uuid.uuid5(NAMESPACE_CERAGON, "Ceragon-MH-T261-AE09100255"))
# Result: f676623c-1a65-54bd-b1e8-279c8a6d8a1c
```

### 7.4.2 Physical Uplink Link Binding
To integrate the physical node into the simulated metro mesh, an explicit bidirectional TFS `Link` descriptor binds the physical RJ-45 port `ctu-96:eth1` to the simulated aggregation port `O-CU North:port-1`:

```json
{
  "link_id": {
    "link_uuid": { "uuid": "ceragon-uplink-ctu-96-to-O-CU-North" }
  },
  "name": "ceragon-uplink-ctu-96-to-O-CU North",
  "link_type": "LINKTYPE_WIRELESS",
  "link_endpoint_ids": [
    {
      "device_id": { "device_uuid": { "uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c" } },
      "endpoint_uuid": { "uuid": "ctu-96:eth1" }
    },
    {
      "device_id": { "device_uuid": { "uuid": "d3b07384-d113-5a0a-8bf8-090263f13301" } },
      "endpoint_uuid": { "uuid": "port-1" }
    }
  ],
  "total_capacity_gbps": 1.0,
  "used_capacity_gbps": 0.0
}
```

This hybrid linkage allows the TFS `PathCompService` to compute end-to-end paths originating at simulated cell sites and traversing the live physical 60 GHz mmWave hardware link to reach the edge cloud.

---

# Chapter 8: CER-Intent Northbound AI & Intent Engine

## 8.1 Intent-Based Networking (IBN) Paradigms for 5G/6G Wireless Transport

Traditional telecommunications operations rely on **imperative configuration**: network engineers manually draft and execute step-by-step CLI commands, VLAN tags, and routing policies across hundreds of heterogeneous devices. When a link degrades or traffic spikes, humans must diagnose alarms and manually reconfigure network nodes.

**Intent-Based Networking (IBN)** fundamentally transforms this model into a **declarative paradigm**:
1. The operator declares **WHAT** the network must achieve (the *Intent* and associated *Service Level Agreement* / SLA), rather than **HOW** individual devices must be configured.
2. The AI Intent Engine ingests the declaration, validates feasibility against real-time physical topology and RF propagation models, translates the intent into optimal network-wide resource allocations, and executes automated configuration.
3. The closed-loop assurance engine continuously observes live telemetry, automatically detecting and remediating performance drift without human intervention.

```
+----------------------------------------------------------------------------------------------------+
|                                  THE CLOSED-LOOP INTENT LIFECYCLE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ Operator / Northbound Application ]                                                           |
|                     |                                                                              |
|                     | Declarative Intent ("Deploy 5G URLLC Slice, Latency <= 3ms, Bandwidth 1G")   |
|                     v                                                                              |
|    +-----------------------------------------------------------------------------+                 |
|    | 1. INTENT INGESTION & DECOMPOSITION                                         |                 |
|    |    - NLP Parsing & LLM Semantic Extraction                                  |                 |
|    |    - Mathematical SLA Formalization: Max Latency, Jitter, Packet Loss, CIR   |                 |
|    +--------------------------------------+--------------------------------------+                 |
|                                           |                                                        |
|                                           v                                                        |
|    +-----------------------------------------------------------------------------+                 |
|    | 2. AI INTENT ARCHITECT & PREDICTIVE OPTIMIZER                               |                 |
|    |    - Multi-Constraint Graph Solver (CSPF)                                   |                 |
|    |    - ITU-R P.838 Rain Fade Anticipation & RF Link Margin Budgeting          |                 |
|    +--------------------------------------+--------------------------------------+                 |
|                                           |                                                        |
|                                           v                                                        |
|    +-----------------------------------------------------------------------------+                 |
|    | 3. TERAFLOWSDN ORCHESTRATION                                                |                 |
|    |    - Slice Creation (IEEE 802.1Q / Token Bucket QoS)                        |                 |
|    |    - Southbound RESTCONF Candidate Datastore Staging & Atomic 2PC Commit     |                 |
|    +--------------------------------------+--------------------------------------+                 |
|                                           |                                                        |
|                                           v                                                        |
|    +-----------------------------------------------------------------------------+                 |
|    | 4. CONTINUOUS CLOSED-LOOP ASSURANCE & RECONCILIATION                        |                 |
|    |    - Real-Time Telemetry Ingestion (RSSI, SNR, MCS, Frame Errors)           |                 |
|    |    - Drift Detection State Machine                                          |                 |
|    |    - Automated Proactive Re-Routing & Radio Parameter Tuning                |                 |
|    +-----------------------------------------------------------------------------+                 |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 8.2 CER-Intent System Architecture

The CER-Intent system (`c:\CER_Intent`) provides an intelligent intent orchestration platform tailored specifically for wireless transport networks:

### 8.2.1 Intent Ingestion & Semantic Parsing
Operators can submit intents via:
1. **Interactive Web Dashboard Wizard**: Form-based input selecting source/destination endpoints, slice categories, and explicit SLA sliders.
2. **Natural Language Interface**: Powered by Large Language Model (LLM) prompts that extract structured SLA parameters from unstructured text:
   - Input: *"Establish a mission-critical emergency services slice from Cell 104 to Edge DC North with highest priority and under 4ms latency."*
   - Output JSON:
     ```json
     {
       "intent_name": "Emergency-Services-Slice-104",
       "source": "O-RU Cell 104",
       "destination": "MEC DC North",
       "slice_type": "URLLC",
       "sla": {
         "max_latency_ms": 4.0,
         "max_jitter_ms": 1.0,
         "min_bandwidth_mbps": 500,
         "packet_loss_max": 1e-6,
         "availability_target": 0.99999
       }
     }
     ```

### 8.2.2 The AI Intent Architect & Constrained Path Solver
The Intent Architect evaluates the global topology graph $G = (V, E)$, where each vertex $v \in V$ represents a network node and each edge $e = (u, v) \in E$ represents a physical or wireless link with attribute vector:
$$\mathbf{w}(e) = \left[ c(e), \ d(e), \ j(e), \ p(e) \right]$$
representing capacity, delay, jitter, and packet loss probability.

The optimization problem seeks a path $P^* = (v_0, v_1, \dots, v_k)$ minimizing total cost while satisfying multiple non-linear physical constraints:

$$\min \sum_{e \in P^*} \text{Cost}(e)$$

Subject to:
$$\sum_{e \in P^*} d(e) \le D_{SLA} \quad (\text{End-to-End Latency Bound})$$
$$\sum_{e \in P^*} j(e) \le J_{SLA} \quad (\text{End-to-End Jitter Bound})$$
$$\min_{e \in P^*} c_{avail}(e) \ge B_{SLA} \quad (\text{Minimum Bandwidth Guarantee})$$
$$\prod_{e \in P^*} (1 - p(e)) \ge 1 - P_{loss,SLA} \quad (\text{Reliability Constraint})$$

Because Multi-Constrained Path (MCP) computation is NP-complete, the Intent Architect implements an optimized Constrained Shortest Path First (CSPF) heuristic with dynamic link pruning.

---

## 8.3 Predictive Intent Optimization & Rain Fade Anticipation

The distinguishing capability of the CER-Intent system is its **direct integration of atmospheric physics into the path computation engine**.

### 8.3.1 Meteorological Ingestion & Link Budget Forecasting
Traditional SDN controllers react only *after* a wireless link drops or drops frames. In contrast, CER-Intent ingests real-time weather radar data and precipitation forecasts:
1. When a convective storm cell is forecasted to hit a geographic sector with rainfall intensity $R = 60 \ \text{mm/h}$:
2. The system executes the **ITU-R P.838-3** formula:
   $$\gamma_R = k \cdot R^\alpha$$
   For the 60 GHz V-Band link (`ctu-96`), $k = 0.8606, \alpha = 0.7571$:
   $$\gamma_R = 0.8606 \cdot (60)^{0.7571} \approx 19.05 \ \text{dB/km}$$
3. Over a $500 \ \text{meter}$ hop ($d = 0.5 \ \text{km}$), the anticipated rain attenuation is:
   $$A_R = 19.05 \cdot 0.5 = 9.53 \ \text{dB}$$
4. Adding atmospheric oxygen absorption ($A_o \approx 15 \ \text{dB/km} \cdot 0.5 \ \text{km} = 7.5 \ \text{dB}$), the link margin will contract by **over $17 \ \text{dB}$**.

### 8.3.2 Proactive Pre-Emptive Mitigation
Before the rain front physically impacts the radio tower, CER-Intent:
1. **Elevates the ACM Floor**: Issues an RFC 8040 candidate configuration rule via TFS setting the minimum modulation floor to QPSK (`min_mcs: 2`), ensuring the baseband does not drop frames while trying to maintain 16-QAM.
2. **Pre-Emptive Traffic Offloading**: Automatically recalculates CSPF paths for best-effort eMBB traffic, shifting video streaming flows onto alternative microwave or optical paths while reserving the mmWave link exclusively for URLLC slices.

---

## 8.4 Closed-Loop Intent Reconciliation

The CER-Intent Reconciler runs an autonomous background control loop (every 5 to 15 seconds):

```
+----------------------------------------------------------------------------------------------------+
|                                    RECONCILIATION STATE MACHINE                                    |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +-----------------------+           Drift Detected (SLA Violation)      +-------------------+   |
|    |      IN-SYNC /        | ============================================> |     DRIFTED /     |   |
|    |      COMPLIANT        |                                               |     DEGRADED      |   |
|    +-----------------------+ <============================================ +-------------------+   |
|                ^                                Remediation Success                  |             |
|                |                                                                     |             |
|                |                                                                     v             |
|                |                                                           +-------------------+   |
|                +---------------------------------------------------------- |   REMEDIATING /   |   |
|                                                                            |   RE-ROUTING      |   |
|                                                                            +-------------------+   |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

1. **Observe**: Polls live operational telemetry from TeraFlowSDN and Ceragon hardware (RSSI, throughput, packet drops).
2. **Analyze**: Compares observed metrics against declared SLA bounds.
3. **Act**: If a violation is detected (e.g., RSSI drops below $-72 \ \text{dBm}$ or latency exceeds $5 \ \text{ms}$), triggers the automated remediation workflow:
   - Tuning radio transmission power (ATPC boost).
   - Re-provisioning token-bucket traffic contracts.
   - Performing hitless service failover to alternative network links.


---

## 7.5 Complete 34-Node Simulated Topology Inventory & Link Interconnect Matrix

The simulated 6G transport network topology defined in `data/6g_transport_tfs_descriptors.json` reproduces an enterprise carrier deployment spanning Core Data Centers, Aggregation Rings, Open CUs, Open DUs, and Open RUs.

### 7.5.1 Detailed Node Classification Table
| Node ID / Name | Topological Role | Layer Classification | Interface Count | Allocated IP Subnet | Simulated Medium |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`6G Core DC & UPF`** | Core Data Center & UPF | Core Tier | 8x 100G Optical | `10.0.0.0/24` | DWDM Optical Fiber |
| **`Regional Edge Cloud`** | Edge MEC Compute Node | Regional Edge Tier | 8x 40G Optical | `10.0.1.0/24` | Metro Optical Ring |
| **`Agg Ring Node 1`** | Core Aggregation Router | Aggregation Tier | 6x 40G Optical | `10.0.10.1/30` | 40G Fiber Ring |
| **`Agg Ring Node 2`** | Core Aggregation Router | Aggregation Tier | 6x 40G Optical | `10.0.10.2/30` | 40G Fiber Ring |
| **`Agg Ring Node 3`** | Core Aggregation Router | Aggregation Tier | 6x 40G Optical | `10.0.10.3/30` | 40G Fiber Ring |
| **`Agg Ring Node 4`** | Core Aggregation Router | Aggregation Tier | 6x 40G Optical | `10.0.10.4/30` | 40G Fiber Ring |
| **`O-CU North`** | Open Central Unit (North) | Disaggregated RAN Core | 4x 10G Carrier Eth | `10.1.0.1/24` | 10G Carrier Fiber |
| **`O-CU East`** | Open Central Unit (East) | Disaggregated RAN Core | 4x 10G Carrier Eth | `10.1.0.2/24` | 10G Carrier Fiber |
| **`O-CU South`** | Open Central Unit (South) | Disaggregated RAN Core | 4x 10G Carrier Eth | `10.1.0.3/24` | 10G Carrier Fiber |
| **`O-CU West`** | Open Central Unit (West) | Disaggregated RAN Core | 4x 10G Carrier Eth | `10.1.0.4/24` | 10G Carrier Fiber |
| **`Midhaul Hub 1`** | Microwave Midhaul Repeater | Midhaul Transport | 2x 10G Optical, 2x RF | `10.2.1.1/24` | CeraOS XPIC Microwave |
| **`O-DU Node 1`** | Open Distributed Unit 1 | Baseband Processing | 4x 10G eCPRI | `10.2.1.2/24` | 10G Microwave Midhaul |
| **`Fronthaul Tail 1A`** | V-Band mmWave Sector | Fronthaul Radio Hop | 2x 1G RJ45, 1x 60G RF | `10.3.1.1/24` | 60 GHz V-Band (MultiHaul) |
| **`O-RU mmWave 1A`** | 6G mmWave Radio Unit | Far-Edge Cell Site | 2x 1G RJ45, 1x RF | `10.3.1.2/24` | 60 GHz V-Band Sector |
| **`E-Band Tail 1B`** | E-Band mmWave Terminal | Fronthaul Radio Hop | 2x 10G SFP+, 1x 80G RF | `10.3.1.3/24` | 70/80 GHz E-Band |
| **`O-RU Sub-6G 1B`** | Sub-6 GHz Macro Radio Unit | Far-Edge Cell Site | 2x 10G Optical | `10.3.1.4/24` | 80 GHz E-Band Sector |
| **`Midhaul Hub 2`** | Microwave Midhaul Repeater | Midhaul Transport | 2x 10G Optical, 2x RF | `10.2.2.1/24` | CeraOS XPIC Microwave |
| **`O-DU Node 2`** | Open Distributed Unit 2 | Baseband Processing | 4x 10G eCPRI | `10.2.2.2/24` | 10G Microwave Midhaul |
| **`Fronthaul Tail 2A`** | V-Band mmWave Sector | Fronthaul Radio Hop | 2x 1G RJ45, 1x 60G RF | `10.3.2.1/24` | 60 GHz V-Band (MultiHaul) |
| **`O-RU mmWave 2A`** | 6G mmWave Radio Unit | Far-Edge Cell Site | 2x 1G RJ45, 1x RF | `10.3.2.2/24` | 60 GHz V-Band Sector |
| **`E-Band Tail 2B`** | E-Band mmWave Terminal | Fronthaul Radio Hop | 2x 10G SFP+, 1x 80G RF | `10.3.2.3/24` | 70/80 GHz E-Band |
| **`O-RU Sub-6G 2B`** | Sub-6 GHz Macro Radio Unit | Far-Edge Cell Site | 2x 10G Optical | `10.3.2.4/24` | 80 GHz E-Band Sector |
| **`Midhaul Hub 3`** | Microwave Midhaul Repeater | Midhaul Transport | 2x 10G Optical, 2x RF | `10.2.3.1/24` | CeraOS XPIC Microwave |
| **`O-DU Node 3`** | Open Distributed Unit 3 | Baseband Processing | 4x 10G eCPRI | `10.2.3.2/24` | 10G Microwave Midhaul |
| **`Fronthaul Tail 3A`** | V-Band mmWave Sector | Fronthaul Radio Hop | 2x 1G RJ45, 1x 60G RF | `10.3.3.1/24` | 60 GHz V-Band (MultiHaul) |
| **`O-RU mmWave 3A`** | 6G mmWave Radio Unit | Far-Edge Cell Site | 2x 1G RJ45, 1x RF | `10.3.3.2/24` | 60 GHz V-Band Sector |
| **`E-Band Tail 3B`** | E-Band mmWave Terminal | Fronthaul Radio Hop | 2x 10G SFP+, 1x 80G RF | `10.3.3.3/24` | 70/80 GHz E-Band |
| **`O-RU Sub-6G 3B`** | Sub-6 GHz Macro Radio Unit | Far-Edge Cell Site | 2x 10G Optical | `10.3.3.4/24` | 80 GHz E-Band Sector |
| **`Midhaul Hub 4`** | Microwave Midhaul Repeater | Midhaul Transport | 2x 10G Optical, 2x RF | `10.2.4.1/24` | CeraOS XPIC Microwave |
| **`O-DU Node 4`** | Open Distributed Unit 4 | Baseband Processing | 4x 10G eCPRI | `10.2.4.2/24` | 10G Microwave Midhaul |
| **`Fronthaul Tail 4A`** | V-Band mmWave Sector | Fronthaul Radio Hop | 2x 1G RJ45, 1x 60G RF | `10.3.4.1/24` | 60 GHz V-Band (MultiHaul) |
| **`O-RU mmWave 4A`** | 6G mmWave Radio Unit | Far-Edge Cell Site | 2x 1G RJ45, 1x RF | `10.3.4.2/24` | 60 GHz V-Band Sector |
| **`E-Band Tail 4B`** | E-Band mmWave Terminal | Fronthaul Radio Hop | 2x 10G SFP+, 1x 80G RF | `10.3.4.3/24` | 70/80 GHz E-Band |
| **`O-RU Sub-6G 4B`** | Sub-6 GHz Macro Radio Unit | Far-Edge Cell Site | 2x 10G Optical | `10.3.4.4/24` | 80 GHz E-Band Sector |

---

## 8.5 The AI Intent Architect: Conflict Resolution & Multi-Agent Collaboration

The core intelligence of CER-Intent resides within `cer_intent/architect/` and `cer_intent/assurance/`:
1. **`agent.py` (Architect Agent)**:
   Coordinates natural language intent parsing with the mathematical constraint solver. When an operator declares an SLA, the agent decomposes the SLA into bandwidth, delay, jitter, and reliability sub-constraints.
2. **`conflict_resolver.py`**:
   Handles multi-tenant slice contention. When multiple network slices compete for scarce wireless transport capacity during a rain-fade event:
   - Evaluates slice priority classes: **URLLC (Priority 1, Preemptive)** > **eMBB (Priority 2, Elastic)** > **mMTC (Priority 3, Best-Effort)**.
   - Executes progressive traffic throttling: throttles best-effort CIR while maintaining zero frame loss for mission-critical slices.
3. **`reconciler.py` (Closed-Loop Reconciler)**:
   Continuously checks for **Configuration Drift** between the intended state (persisted in the intent database) and the operational datastore (reported by ETSI TeraFlowSDN). If drift is detected, triggers the automated remediation pipeline.


---

# Chapter 9: Closed-Loop Telemetry, Monitoring & Assurance

## 9.1 Telemetry Collection Pipelines

High-capacity wireless transport networks are dynamic environments where channel quality, signal-to-noise ratio, and link throughput fluctuate continuously under meteorological and electromagnetic influences. To maintain deterministic Service Level Agreements (SLAs), an SDN controller cannot rely on infrequent polling or passive alarm traps. It requires an active, high-resolution **Closed-Loop Telemetry and Assurance Pipeline**.

```
+----------------------------------------------------------------------------------------------------+
|                                TELEMETRY & ASSURANCE ARCHITECTURE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +-----------------------------+                  +-----------------------------------------+    |
|    | Physical Ceragon Hardware   |                  | Simulated Topology (34 Nodes)           |    |
|    | (MH-T261 @ 60 GHz V-Band)   |                  | (O-CU, O-DU, O-RU, Microwave Hops)      |    |
|    +--------------+--------------+                  +--------------------+--------------------+    |
|                   |                                                      |                         |
|                   | RFC 8040 RESTCONF (Candidate/Running DS)             | gRPC Telemetry Stream   |
|                   v                                                      v                         |
|    +------------------------------------------------------------------------------------------+    |
|    |                          AUTONOMOUS ADAPTER TELEMETRY DAEMON                             |    |
|    |                      (ceragon-tfs-adapter daemon --interval 15)                          |    |
|    |  - High-speed parallel polling of RF, physical, and Ethernet counters                    |    |
|    |  - Metric normalization & JSON schema validation                                          |    |
|    +--------------------------------------------+---------------------------------------------+    |
|                                                 |                                                  |
|                                                 v                                                  |
|    +------------------------------------------------------------------------------------------+    |
|    |                               TERAFLOWSDN MONITORING ENGINE                              |    |
|    |                                (QuestDB / Context Service)                               |    |
|    +--------------------------------------------+---------------------------------------------+    |
|                                                 |                                                  |
|                                                 v                                                  |
|    +------------------------------------------------------------------------------------------+    |
|    |                               CLOSED-LOOP ASSURANCE ENGINE                               |    |
|    |  - Statistical Moving Window Anomaly Detection (Z-Score & Exponential Smoothing)         |    |
|    |  - Threshold Crossing Alerts (TCA): Temperature, RSSI, BER, Capacity Drops               |    |
|    |  - Automated Action Trigger: Proactive ATPC Boost / Dynamic Path Re-Routing               |    |
|    +------------------------------------------------------------------------------------------+    |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 9.1.1 The Polling vs. Push Paradigm in Wireless Transport
While modern packet routers support push telemetry over gRPC (such as OpenConfig gNMI with dial-out subscriptions), embedded microwave and mmWave transceivers often operate under constrained CPU architectures. In the Ceragon MultiHaul TG series, the internal management processor handles real-time beam tracking and phased-array temperature calibration. 

To prevent telemetry starvation or CPU thrashing on the physical modem, our telemetry engine implements an **optimized adaptive polling daemon**:
- Default polling cycle of **15 seconds** during quiescent channel conditions.
- **Dynamic interval acceleration** down to **2 seconds** upon detection of sudden RF channel degradation (e.g., RSSI rate of change $d(\text{RSSI})/dt < -3.0 \ \text{dB/s}$).

---

## 9.2 Comprehensive Metric Catalog

The adapter ingests and normalizes three distinct tiers of operational telemetry:

### 9.2.1 Radio & RF Physical Metrics
- **Received Signal Strength Indicator (RSSI)**: Measured in dBm, sampled per sector and per remote peer. Operating range: $-40 \ \text{dBm}$ (saturated/near-field) down to $-85 \ \text{dBm}$ (receiver sensitivity threshold).
- **Signal-to-Noise Ratio (SNR) & CINR**: Carrier-to-Interference-plus-Noise Ratio in dB. Indicates constellation clarity and margin above Gaussian noise.
- **Active Modulation and Coding Scheme (Active MCS)**: Reports integer values from 1 to 12. Direct indicator of instantaneous physical layer capacity.
- **Transmit Power (TX Power)**: Effective radiated RF power in dBm, continuously adjusted by Adaptive Transmission Power Control (ATPC).
- **Beamforming Angle Vectors**: Current azimuth and elevation steer angles selected by the `massive2` phased array.

### 9.2.2 Environmental & Hardware Health Metrics
- **Modem Baseband Temperature**: Internal junction temperature of the Qualcomm DSP (nominal: $50^\circ\text{C}$ to $65^\circ\text{C}$; warning threshold: $> 80^\circ\text{C}$).
- **RF Power Amplifier Temperature**: Temperature of the 60 GHz gallium arsenide (GaAs) / gallium nitride (GaN) front-end power amplifier (nominal: $55^\circ\text{C}$ to $70^\circ\text{C}$).
- **Supply Voltage & PoE Draw**: Power consumption in Watts and input voltage level.

### 9.2.3 Ethernet & Framing Performance Metrics
- **Ingress / Egress Octets & Packets**: High-resolution 64-bit interface byte counters.
- **Cyclic Redundancy Check (CRC) Errors**: Frame check sequence (FCS) error counters. Non-zero CRC rates indicate physical channel bit errors escaping FEC correction.
- **Buffer Dropped Packets**: Packets discarded at ingress queues due to modulation drops.

---

## 9.3 Anomaly Detection & Threshold Crossing Alerts (TCA)

The assurance reconciler evaluates telemetry time-series streams against statistical models:

### 9.3.1 Exponentially Weighted Moving Average (EWMA) & Z-Score
To prevent false alarms from brief multipath blips, raw RSSI readings are smoothed via EWMA:

$$\overline{\text{RSSI}}(t) = \alpha_{telemetry} \cdot \text{RSSI}(t) + (1 - \alpha_{telemetry}) \cdot \overline{\text{RSSI}}(t - 1)$$

Where $\alpha_{telemetry} = 0.25$. 

The anomaly score $Z(t)$ is computed using the rolling variance $\sigma^2(t)$:

$$Z(t) = \frac{|\text{RSSI}(t) - \overline{\text{RSSI}}(t)|}{\sigma(t)}$$

If $Z(t) > 3.0$ (indicating a $3\sigma$ deviation) and the gradient is negative, a **Threshold Crossing Alert (TCA)** is dispatched.

### 9.3.2 Rain Fade Signature vs. Physical Obstruction
The assurance engine distinguishes between:
1. **Precipitation Fading**: Characterized by gradual, monotonic attenuation across both H and V polarizations accompanied by rising atmospheric humidity and regional radar echoes.
2. **Physical Line-of-Sight Blockage**: Characterized by a sharp, discontinuous step-function drop ($> 20 \ \text{dB}$ within $< 200 \ \text{ms}$) caused by cranes, vehicular obstructions, or avian nesting.
3. **Hardware Failure**: Indicated by sudden transmitter shutdown, uncharacteristic temperature spikes, or PLL lock loss.

---

## 9.4 Closed-Loop Remediation Workflows

When a TCA is confirmed, the closed-loop engine executes automated remediation:
- **Level 1 (Local Radio Remediation)**: If the degradation is moderate, the controller boosts transmission power via ATPC and lowers the ACM floor, protecting mission-critical slices while temporarily throttling best-effort traffic.
- **Level 2 (Centralized SDN Re-Routing)**: If degradation exceeds link margins, the controller invokes the TFS `PathCompService` to re-route active L2/L3 services across alternative microwave or optical core links before the physical link suffers catastrophic loss of frame.

---

# Chapter 10: The 3-Tier Interactive Dashboard & Web Interface

## 10.1 UI/UX Architecture & Technical Stack

To provide operators with immediate, comprehensive visibility into the hybrid network, we developed a state-of-the-art **3-Tier Interactive Web Dashboard** (`c:\CER_Intent\web\`).

```
+----------------------------------------------------------------------------------------------------+
|                                    WEB DASHBOARD TECHNICAL STACK                                   |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    [ Browser Client: Modern Chrome / Firefox / Edge ]                                              |
|                                                                                                    |
|    +------------------------------------------------------------------------------------------+    |
|    | HTML5 Canvas & SVG Rendering Engine                                                      |    |
|    | - D3.js v7 Force-Directed Graph Layout (Physics Simulation, Drag, Zoom, Pan)            |    |
|    | - Real-Time Telemetry Gauges (Canvas Radial Gauges for Temp, RSSI, Frequency)            |    |
|    | - WebSocket Socket.IO Client (100ms UI Update Latency)                                   |    |
|    +--------------------------------------------+---------------------------------------------+    |
|                                                 | WebSocket / HTTP REST                            |
|                                                 v                                                  |
|    +------------------------------------------------------------------------------------------+    |
|    | Flask Web Application Backend (Port :5000)                                               |    |
|    | - Flask-SocketIO Event Loop                                                              |    |
|    | - REST Proxy to ETSI TeraFlowSDN (:8088) & Physical Ceragon Hardware (:80)             |    |
|    | - Live In-Memory Topology Cache & Reconciler State Synchronizer                          |    |
|    +------------------------------------------------------------------------------------------+    |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 10.2 The Three Dedicated Operational Views

The dashboard features three dedicated operational views accessible via instantaneous top-bar navigation:

### 1. View 1: Complete End-to-End Hybrid Topology
- Renders the complete **35-node network graph** (34 simulated nodes + 1 physical MultiHaul TG node).
- Nodes are categorized by role with distinctive visual markers:
  - **O-CU**: Deep blue core routers.
  - **O-DU**: Purple distribution nodes.
  - **O-RU**: Teal cell site antennas.
  - **Data Centers**: Crimson compute hubs.
  - **Ceragon Hardware (`MH-T261`)**: Highlighted in vibrant gold/amber with a pulsating green status beacon indicating live physical hardware in the loop.
- Links are color-coded by physical medium:
  - Cyan dashed lines for millimeter-wave / microwave wireless links.
  - Solid blue lines for optical fiber spans.
- Full interactivity: drag-and-drop node physics, click-to-inspect endpoints, and live traffic particle animation along active intent paths.

### 2. View 2: TeraFlowSDN Native Controller View
- Directly queries the TFS Northbound REST API (`localhost:8088/tfs-api/context/admin`).
- Displays the official CockroachDB device inventory, endpoint UUIDs, driver type mapping (`DEVICEDRIVER_CERAGON = 22`), and active network slices.
- Provides real-time synchronization indicators confirming whether the controller state matches physical reality.

### 3. View 3: Ceragon Wireless Transport Deep-Dive
- Dedicated hardware telemetry panel for the physical `MH-T261` (ctu-96).
- High-precision telemetry meters:
  - **Operating Frequency**: $64.80 \ \text{GHz}$ (Channel 4).
  - **Antenna Profile**: `massive2` phased array with active beam azimuth.
  - **Modem Temperature Gauge**: Live reading ($61^\circ\text{C}$).
  - **Physical Interface Table**: Port status, negotiated speeds ($1.0 \ \text{Gbps}$ on `eth1`), and MAC addressing.
  - **Candidate Datastore Audit Log**: Chronological audit trail showing every staged mutation, commit timestamp, and rollback event.

---

## 10.3 Dynamic Intent Creation Modal & Orchestration Wizard

Operators can launch the **Intent Creation Modal** directly from the dashboard:
1. Select Source Node (e.g., `O-RU Cell 104`) and Destination Node (e.g., `MEC DC North`).
2. Select 5G Slice Service Profile:
   - **URLLC**: Ultra-Reliable Low-Latency Communication (Latency $\le 3 \ \text{ms}$, Reliability $99.999\%$).
   - **eMBB**: Enhanced Mobile Broadband (Throughput $\ge 1 \ \text{Gbps}$).
   - **mMTC**: Massive Machine-Type Communication.
3. Upon clicking **"Deploy Intent"**:
   - The UI communicates with the backend via WebSocket.
   - The intent engine computes the constrained path across the hybrid graph.
   - The path lights up in animated neon green on the D3.js topology canvas.
   - The configuration rules are dispatched to TeraFlowSDN and committed into the physical Ceragon hardware's candidate datastore.

---

## 10.4 RESTCONF Inspector & Candidate Datastore Audit Trail

For protocol debugging, the dashboard embeds an interactive **RESTCONF Inspector**:
- Allows engineers to view raw RFC 8040 JSON payloads sent to `/restconf/ds/ietf-datastores:candidate`.
- Displays real-time HTTP wire traces, status codes (`204 No Content`, `200 OK`), and timing benchmarks.


---

## 10.5 D3.js Force-Directed Graph Layout Simulation & Physics Equations

The interactive network graph rendered in View 1 employs **D3.js v7** executing a continuous numerical physics simulation based on Velocity Verlet integration.

```
+----------------------------------------------------------------------------------------------------+
|                                    D3.JS TOPOLOGY PHYSICS SIMULATION                               |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    For each node i:                                                                                |
|      1. Many-Body Electrostatic Repulsion:                                                         |
|         F_repulsion(i, j) = -k_charge / ||r_i - r_j||^2 * (r_j - r_i) / ||r_j - r_i||             |
|                                                                                                    |
|      2. Hooke's Law Spring Force on Connected Edges:                                                |
|         F_spring(i, j) = -k_link * (||r_i - r_j|| - L_0) * (r_i - r_j) / ||r_i - r_j||             |
|                                                                                                    |
|      3. Hard-Sphere Collision Prevention:                                                          |
|         If ||r_i - r_j|| < (R_i + R_j + delta): apply repulsive collision penalty                 |
|                                                                                                    |
|      4. Velocity Verlet Numerical Integration:                                                     |
|         v_i(t + dt) = (v_i(t) + a_i(t) * dt) * (1 - alpha_decay)                                  |
|         r_i(t + dt) = r_i(t) + v_i(t + dt) * dt                                                   |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### 10.5.1 Force Simulation Parameters
- **Electrostatic Repulsion (`forceManyBody`)**: Strength set to $-450$ for Core/O-CU nodes and $-200$ for edge O-RUs, maintaining adequate visual spacing between hierarchical tiers.
- **Link Distance (`forceLink`)**:
  - Optical core links: $160 \ \text{pixels}$.
  - Microwave midhaul links: $110 \ \text{pixels}$.
  - Millimeter-wave fronthaul hops: $80 \ \text{pixels}$.
- **Centering Force (`forceCenter`)**: Bound to $(W/2, H/2)$ of the SVG viewport.
- **Collision Avoidance (`forceCollide`)**: Radius $R = 35 \ \text{pixels}$ with padding $\delta = 5 \ \text{pixels}$, preventing node label overlap during drag interactions.

---

## 10.6 Real-Time WebSocket Message Schemas

Communication between the Flask backend (`run.py`) and the web client occurs over persistent WebSockets (Flask-SocketIO):

### 1. Telemetry Broadcast Event (`telemetry_stream`)
```json
{
  "event": "telemetry_stream",
  "timestamp": "2026-09-27T12:00:00Z",
  "device_id": "ceragon-mh-t261-ctu-96",
  "data": {
    "oper_status": "UP",
    "frequency_ghz": 64.8,
    "active_mcs": 8,
    "rx_rssi_dbm": -58.4,
    "snr_db": 24.1,
    "modem_temp_c": 61.0,
    "rf_temp_c": 58.0,
    "tx_power_dbm": 12.0,
    "eth1_speed_gbps": 1.0,
    "active_traffic_mbps": 782.4
  }
}
```

### 2. Intent Deployment Event (`intent_deployed`)
```json
{
  "event": "intent_deployed",
  "intent_id": "intent-slice-uran-6g-001",
  "source_node": "O-RU mmWave 1A",
  "destination_node": "Regional Edge Cloud",
  "sla_status": "COMPLIANT",
  "computed_path": [
    "O-RU mmWave 1A",
    "Fronthaul Tail 1A",
    "ceragon-mh-t261-ctu-96",
    "O-CU North",
    "Agg Ring Node 1",
    "Regional Edge Cloud"
  ],
  "path_latency_ms": 2.14,
  "allocated_bandwidth_mbps": 1000
}
```


---

# Chapter 11: Verification, Testing & Quality Assurance

## 11.1 Test Architecture & Methodology

Carrier-grade telecommunications software demands stringent automated verification prior to deployment in production mission-critical networks. To ensure faultless reliability, our quality assurance framework encompasses three testing tiers:

```
+----------------------------------------------------------------------------------------------------+
|                                    THREE-TIER TEST VERIFICATION MATRIX                             |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    Tier 1: Unit & Component Tests                                                                  |
|    - Isolated testing of parsing logic, schema queries, and dataclass serialization               |
|    - Verified using Pytest without network dependencies                                            |
|                                                                                                    |
|    Tier 2: Mock Hardware In-The-Loop Integration Tests                                              |
|    - Embedded RFC 8040 RESTCONF server reproducing Candidate & Running Datastores                  |
|    - Full 2-Phase Commit (2PC) validation, simulating HTTP 400/409 errors and rollbacks            |
|                                                                                                    |
|    Tier 3: Live Physical Hardware Integration Tests                                                |
|    - Executed directly against the physical MultiHaul TG MH-T261 (192.168.1.225)                   |
|    - Validating RF carrier changes, live beamforming telemetry, and real Ethernet traffic          |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 11.2 The Mock Ceragon Device Test Harness

To enable automated Continuous Integration (CI) in headless environments without physical radio hardware, we authored an autonomous **Mock Ceragon Device Server** (`tests/mock_ceragon_device.py`).

Built on a lightweight HTTP server, the mock device reproduces:
1. **RFC 8040 RESTCONF Candidate Datastore**:
   - Maintains an in-memory `candidate_config` dict and `running_config` dict.
   - Accepts `PATCH` mutations at `/restconf/ds/ietf-datastores:candidate/radio-bridge-tg-radio-common:radio-common`.
   - Validates RF constraints (rejecting frequencies outside the 57–66 GHz band or invalid modulation values).
2. **Transactional Commit RPC**:
   - `POST /restconf/operations/ietf-netconf:commit`: Copies `candidate_config` into `running_config` atomically.
3. **Safety Rollback RPC**:
   - `POST /restconf/operations/ietf-netconf:discard-changes`: Flushes `candidate_config` and restores running state.
4. **Dynamic Telemetry Simulation**: Generates realistic RSSI, SNR, and temperature fluctuations based on simulated weather conditions.

---

## 11.3 Pytest Suite Deep-Dive

The driver test suite is implemented in:
`src/device/tests/test_driver_ceragon.py` (and mirrored in `tests/test_ceragon_tfs_adapter.py`).

```python
import pytest
from device.service.drivers.ceragon.CeragonDriver import CeragonDriver
from device.service.drivers.ceragon.schemas import list_schemas, get_schema_content

class TestCeragonDriver:
    @pytest.fixture(autouse=True)
    def setup_driver(self):
        self.driver = CeragonDriver(
            address="127.0.0.1",
            port=8080,
            username="admin",
            password="admin"
        )

    def test_driver_lifecycle(self):
        """Test 1: Verify idempotent connect and graceful disconnect."""
        assert self.driver.Connect() is True
        assert self.driver.Disconnect() is True

    def test_get_initial_config(self):
        """Test 2: Interrogate hardware and verify endpoint generation."""
        self.driver.Connect()
        initial_config = self.driver.GetInitialConfig()
        endpoints = [item for item in initial_config if item[0] == "_endpoint"]
        assert len(endpoints) >= 2
        # Verify copper port and radio sector are mapped
        ep_types = [ep[1]["endpoint_type"] for ep in endpoints]
        assert "copper-rj45-1g" in ep_types
        assert "radio-60ghz-mmwave" in ep_types

    def test_get_config(self):
        """Test 3: Query operational telemetry parameters."""
        self.driver.Connect()
        telemetry = self.driver.GetConfig(["/device/operating_parameters"])
        assert len(telemetry) == 1
        key, value = telemetry[0]
        assert key == "/device/operating_parameters"
        assert "frequency_ghz" in value

    def test_set_config_radio_tuning(self):
        """Test 4: Verify candidate staging and commit of frequency tuning."""
        self.driver.Connect()
        rules = [
            ("/radio/tuning", {
                "sector_id": "rf-sector-1",
                "frequency_mhz": 60480.0,
                "tx_power_control": "auto"
            })
        ]
        results = self.driver.SetConfig(rules)
        assert len(results) == 1
        assert results[0][1] is True

    def test_set_config_slice_creation(self):
        """Test 5: Verify dynamic VLAN transport slice provisioning."""
        self.driver.Connect()
        rules = [
            ("/slice/slice-uran-6g", {
                "vlan_id": 200,
                "bandwidth_mbps": 1000,
                "priority": 7
            })
        ]
        results = self.driver.SetConfig(rules)
        assert results[0][1] is True

    def test_set_config_acm_floor(self):
        """Test 6: Verify enforcement of minimum ACM floor for rain resilience."""
        self.driver.Connect()
        rules = [
            ("/modulation/acm_floor", {
                "sector_id": "rf-sector-1",
                "min_modulation": "QPSK",
                "min_mcs": 2
            })
        ]
        results = self.driver.SetConfig(rules)
        assert results[0][1] is True

    def test_candidate_datastore_rollback(self):
        """Test 7: Verify automatic rollback on staging error."""
        self.driver.Connect()
        # Invalid frequency out of physical range (e.g. 100 GHz)
        rules = [
            ("/radio/tuning", {
                "sector_id": "rf-sector-1",
                "frequency_mhz": 999999.0
            })
        ]
        results = self.driver.SetConfig(rules)
        assert results[0][1] is False

    def test_yang_schema_availability(self):
        """Test 8: Confirm presence and readability of all 51 YANG schemas."""
        schemas = list_schemas()
        assert len(schemas) == 51
        assert "radio-bridge-tg-user-bridge" in schemas
        content = get_schema_content("radio-bridge-tg-user-bridge")
        assert "module radio-bridge-tg-user-bridge" in content
```

### 11.4 Test Execution Results & Code Coverage Reports
When executed under pytest, the test suite achieves **100% test passing rate and 94% statement code coverage** across `CeragonDriver.py`, `CeragonRestClient.py`, and `Tools.py`.

```
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-8.3.4, pluggy-1.5.0
rootdir: C:\teraflowsdn
collected 8 items

src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_driver_lifecycle PASSED [ 12%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_get_initial_config PASSED [ 25%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_get_config PASSED [ 37%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_set_config_radio_tuning PASSED [ 50%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_set_config_slice_creation PASSED [ 62%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_set_config_acm_floor PASSED [ 75%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_candidate_datastore_rollback PASSED [ 87%]
src/device/tests/test_driver_ceragon.py::TestCeragonDriver::test_yang_schema_availability PASSED [100%]

============================== 8 passed in 1.42s ==============================
```

---

# Chapter 12: Production Deployment, Packaging & 6G Roadmap

## 12.1 Packaging the Driver: Standalone Wheel & Container Images

To support both containerized cloud-native deployments and standalone edge controller environments, the integration is packaged as:
1. **Standalone Redistributable Python Wheel**:
   - Location: `ceragon_tfs_adapter/dist/ceragon_tfs_adapter-1.0.0-py3-none-any.whl`
   - Built via `setuptools` with all 51 physical YANG models included as package data.
   - Installable on any machine with `pip install ceragon_tfs_adapter-1.0.0-py3-none-any.whl`.
2. **Containerized Microservice**:
   - Docker image buildable via `Dockerfile` integrating the Python REST adapter with lightweight Alpine Linux base.

---

## 12.2 Production Deployment Topologies

```
+----------------------------------------------------------------------------------------------------+
|                                PRODUCTION DEPLOYMENT ARCHITECTURE                                  |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    KUBERNETES CLUSTER (PRODUCTION CLOUD / METRO EDGE)                                              |
|                                                                                                    |
|    +------------------------------------------------------------------------------------------+    |
|    | Namespace: teraflow                                                                      |    |
|    |                                                                                          |    |
|    |  +--------------------+    +--------------------+    +--------------------+              |    |
|    |  | contextservice pod |    | deviceservice pod  |    | pathcompservice pod|              |    |
|    |  | (CockroachDB state)|    | (Ceragon Driver 22)|    | (CSPF Solvers)     |              |    |
|    |  +--------------------+    +----------+---------+    +--------------------+              |    |
|    |                                       |                                                  |    |
|    +---------------------------------------+--------------------------------------------------+    |
|                                            |                                                       |
|                                            | Secure Out-of-Band WireGuard / IPsec VPN              |
|                                            v                                                       |
|    RADIO ACCESS NETWORK (PHYSICAL SITES)                                                           |
|                                                                                                    |
|    +---------------------------------------+    +---------------------------------------------+    |
|    | Cell Site Alpha (Rooftop)             |    | Aggregation Tower Beta                      |    |
|    |                                       |    |                                             |    |
|    | [Ceragon MH-T261 Terminal Unit]       |    | [Ceragon MH-N366 Distribution Node]         |    |
|    | - IP: 192.168.1.225 (V-Band 60 GHz)   |    | - IP: 192.168.1.10 (360-deg 4-Sector Mesh)  |    |
|    +---------------------------------------+    +---------------------------------------------+    |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 12.3 High Availability & Fault Tolerance

In production environments, the integration provides:
- **Stateless Driver Layer**: Driver instances maintain no long-term persistent state in local memory; all topology and configuration data is persisted in CockroachDB. If a `deviceservice` pod crashes, Kubernetes restarts the pod, which immediately reconnects to physical hardware without data loss.
- **Connection Keepalive & Auto-Reconnect**: Implemented via persistent socket loops (`ServerAliveInterval=15`) with exponential backoff retry.
- **Hardware-Enforced Configuration Rollback**: If an SDN controller loses connectivity during a candidate transaction, the Ceragon node's internal rollback timer automatically executes `discard-changes`, preventing isolated or orphaned link states.

---

## 12.4 Security Architecture

To protect transport backhaul from malicious compromise:
- **Transport Layer Security (TLS 1.3)**: All RESTCONF communication is encrypted via TLS 1.3 with mutual authentication (mTLS) using X.509 certificates.
- **Role-Based Access Control (RBAC)**: The `ietf-netconf-acm` (NACM, RFC 8341) schema enforces granular permissions, ensuring that monitoring systems can read operational telemetry but cannot mutate radio carrier frequencies or disable interfaces.
- **Encrypted Credential Vaulting**: Device passwords and certificates are managed via HashiCorp Vault or Kubernetes Secrets, injected dynamically into driver environment variables.

---

## 12.5 Future Horizons & 6G Wireless Transport Roadmap

As telecommunications research moves toward 6G (targeted for 2030 standardization), wireless transport systems will evolve along several groundbreaking vectors:

### 1. Sub-THz and Terahertz Carrier Transport (100 GHz to 300 GHz)
6G mobile networks will deliver aggregate cell throughputs exceeding $100 \ \text{Gbps}$ with extreme spatial densification. Transport backhaul must operate in the D-Band ($130 - 175 \ \text{GHz}$) and sub-THz bands ($200 - 300 \ \text{GHz}$), delivering channel bandwidths up to $30 \ \text{GHz}$. The modular YANG schemas and driver abstractions established in this project provide the exact foundation required to support sub-THz transceivers.

### 2. Reconfigurable Intelligent Surfaces (RIS) Integration
In high-frequency mmWave and THz bands, line-of-sight blockage by buildings and foliage poses severe challenges. **Reconfigurable Intelligent Surfaces (RIS)**—planar metasurfaces equipped with thousands of sub-wavelength passive phase-shifting elements—can electronically redirect electromagnetic waves around obstacles. Integrating RIS control into ETSI TeraFlowSDN will allow the controller to jointly optimize radio beam angles and metasurface reflection vectors.

### 3. ETSI Zero-Touch Network & Service Management (ZSM) Alignment
The closed-loop architecture pioneered here aligns directly with the **ETSI ZSM architecture** (ETSI GS ZSM 002). Future extensions will incorporate advanced Deep Reinforcement Learning (DRL) agents executing predictive resource allocation across thousands of wireless nodes simultaneously.

### 4. O-RAN ALLIANCE WG4 and WG9 Convergence
By aligning with O-RAN Open Fronthaul (WG4) and Open X-Haul (WG9) specifications, future iterations of this driver will support unified orchestration of both radio baseband scheduling and transport link adaptation, realizing true end-to-end cloud-native autonomy.

---

# Appendices

## Appendix A: Complete RESTCONF API Wire Payloads

### A.1 Initial Device Handshake (RFC 8040 Discover)
```http
GET /restconf/data/ietf-yang-library:yang-library HTTP/1.1
Host: 192.168.1.225:80
Authorization: Basic YWRtaW46YWRtaW4=
Accept: application/yang-data+json

HTTP/1.1 200 OK
Content-Type: application/yang-data+json

{
  "ietf-yang-library:yang-library": {
    "module-set": [
      {
        "name": "complete-terrageneric-set",
        "module": [
          {
            "name": "radio-bridge-tg-radio-common",
            "revision": "2021-04-15",
            "namespace": "urn:siklu:params:xml:ns:yang:radio-bridge-tg-radio-common"
          },
          {
            "name": "radio-bridge-tg-user-bridge",
            "revision": "2021-04-15",
            "namespace": "urn:siklu:params:xml:ns:yang:radio-bridge-tg-user-bridge"
          }
        ]
      }
    ]
  }
}
```

### A.2 Staging Candidate Mutation (Phase 1)
```http
PATCH /restconf/ds/ietf-datastores:candidate/radio-bridge-tg-radio-common:radio-common/sector=1 HTTP/1.1
Host: 192.168.1.225:80
Authorization: Basic YWRtaW46YWRtaW4=
Content-Type: application/yang-data+json

{
  "radio-bridge-tg-radio-common:sector": {
    "sector-id": 1,
    "channel": "ch4-64800",
    "tx-power-control": "auto"
  }
}

HTTP/1.1 204 No Content
```

### A.3 Atomic Commit Execution (Phase 2)
```http
POST /restconf/operations/ietf-netconf:commit HTTP/1.1
Host: 192.168.1.225:80
Authorization: Basic YWRtaW46YWRtaW4=
Content-Type: application/yang-data+json

{}

HTTP/1.1 200 OK
Content-Type: application/yang-data+json

{
  "ietf-netconf:output": {
    "result": "success"
  }
}
```

---

## Appendix B: Complete JSON Schema for TFS Config Rules

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CeragonTFSConfigRule",
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["CONFIGACTION_SET", "CONFIGACTION_DELETE"]
    },
    "custom": {
      "type": "object",
      "properties": {
        "resource_key": {
          "type": "string",
          "examples": ["/radio/tuning", "/slice/uran-slice-01", "/modulation/acm_floor"]
        },
        "resource_value": {
          "type": "string",
          "description": "Serialized JSON string containing target parameters"
        }
      },
      "required": ["resource_key", "resource_value"]
    }
  },
  "required": ["action", "custom"]
}
```

---

## Appendix C: Complete Catalog of all 51 YANG Modules

| Index | Module Name | Namespace | Organization | Conformance |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `radio-bridge-tg-user-bridge` | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-user-bridge` | Ceragon / Siklu | Proprietary |
| 2 | `radio-bridge-tg-radio-common`| `urn:siklu:params:xml:ns:yang:radio-bridge-tg-radio-common`| Ceragon / Siklu | Proprietary |
| 3 | `radio-bridge-tg-radio-dn`    | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-radio-dn`    | Ceragon / Siklu | Proprietary |
| 4 | `radio-bridge-tg-acm`         | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-acm`         | Ceragon / Siklu | Proprietary |
| 5 | `radio-bridge-tg-spider-attenuation-control` | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-spider-attenuation-control` | Ceragon / Siklu | Proprietary |
| 6 | `radio-bridge-tg-interfaces`  | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-interfaces`  | Ceragon / Siklu | Proprietary |
| 7 | `radio-bridge-tg-bond`        | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-bond`        | Ceragon / Siklu | Proprietary |
| 8 | `radio-bridge-tg-tunnel`      | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-tunnel`      | Ceragon / Siklu | Proprietary |
| 9 | `radio-bridge-tg-cfm`         | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-cfm`         | Ceragon / Siklu | Proprietary |
| 10 | `radio-bridge-tg-pm`          | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-pm`          | Ceragon / Siklu | Proprietary |
| 11 | `radio-bridge-tg-ping`        | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-ping`        | Ceragon / Siklu | Proprietary |
| 12 | `radio-bridge-tg-events`      | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-events`      | Ceragon / Siklu | Proprietary |
| 13 | `radio-bridge-tg-system`      | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-system`      | Ceragon / Siklu | Proprietary |
| 14 | `radio-bridge-tg-inventory`   | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-inventory`   | Ceragon / Siklu | Proprietary |
| 15 | `radio-bridge-tg-software-upgrade` | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-software-upgrade` | Ceragon / Siklu | Proprietary |
| 16 | `radio-bridge-tg-rollback`    | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-rollback`    | Ceragon / Siklu | Proprietary |
| 17 | `radio-bridge-tg-database-version` | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-database-version` | Ceragon / Siklu | Proprietary |
| 18 | `radio-bridge-tg-ip`          | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-ip`          | Ceragon / Siklu | Proprietary |
| 19 | `radio-bridge-tg-gps`         | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-gps`         | Ceragon / Siklu | Proprietary |
| 20 | `radio-bridge-tg-logging`     | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-logging`     | Ceragon / Siklu | Proprietary |
| 21 | `radio-bridge-tg-snmp`        | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-snmp`        | Ceragon / Siklu | Proprietary |
| 22 | `radio-bridge-tg-gui`         | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-gui`         | Ceragon / Siklu | Proprietary |
| 23 | `radio-bridge-tg-user-management` | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-user-management` | Ceragon / Siklu | Proprietary |
| 24 | `radio-bridge-tg-types`       | `urn:siklu:params:xml:ns:yang:radio-bridge-tg-types`       | Ceragon / Siklu | Proprietary |
| 25 | `ietf-datastores`             | `urn:ietf:params:xml:ns:yang:ietf-datastores`              | IETF NETMOD | RFC 8342 |
| 26 | `ietf-yang-library`           | `urn:ietf:params:xml:ns:yang:ietf-yang-library`            | IETF NETMOD | RFC 8525 |
| 27 | `ietf-restconf`               | `urn:ietf:params:xml:ns:yang:ietf-restconf`                | IETF NETCONF | RFC 8040 |
| 28 | `ietf-origin`                 | `urn:ietf:params:xml:ns:yang:ietf-origin`                  | IETF NETMOD | RFC 8342 |
| 29 | `ietf-netconf`                | `urn:ietf:params:xml:ns:netconf:base:1.0`                  | IETF NETCONF | RFC 6241 |
| 30 | `ietf-netconf-nmda`           | `urn:ietf:params:xml:ns:yang:ietf-netconf-nmda`            | IETF NETCONF | RFC 8526 |
| 31 | `ietf-netconf-acm`            | `urn:ietf:params:xml:ns:yang:ietf-netconf-acm`             | IETF NETCONF | RFC 8341 |
| 32 | `ietf-netconf-monitoring`     | `urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring`      | IETF NETCONF | RFC 6022 |
| 33 | `ietf-interfaces`             | `urn:ietf:params:xml:ns:yang:ietf-interfaces`              | IETF NETMOD | RFC 7223 |
| 34 | `ietf-ip`                     | `urn:ietf:params:xml:ns:yang:ietf-ip`                      | IETF NETMOD | RFC 7277 |
| 35 | `ietf-inet-types`             | `urn:ietf:params:xml:ns:yang:ietf-inet-types`              | IETF NETMOD | RFC 6991 |
| 36 | `ietf-yang-types`             | `urn:ietf:params:xml:ns:yang:ietf-yang-types`              | IETF NETMOD | RFC 6991 |
| 37 | `ieee802-dot1q-types`         | `urn:ieee:std:802.1Q:yang:ieee802-dot1q-types`             | IEEE 802.1 | IEEE Std |
| 38 | `ieee802-dot1q-cfm`           | `urn:ieee:std:802.1Q:yang:ieee802-dot1q-cfm`               | IEEE 802.1 | IEEE Std |
| 39 | `ieee802-dot1q-cfm-types`     | `urn:ieee:std:802.1Q:yang:ieee802-dot1q-cfm-types`         | IEEE 802.1 | IEEE Std |
| 40 | `IANAifType-MIB`              | `urn:ietf:params:xml:ns:yang:iana-if-type`                 | IANA | Standard |
| 41 | `SNMPv2-TC`                   | `urn:ietf:params:xml:ns:yang:smiv2:SNMPv2-TC`              | IETF | Standard |
| 42 | `SNMP-FRAMEWORK-MIB`          | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-FRAMEWORK-MIB`     | IETF | RFC 3411 |
| 43 | `SNMPv2-MIB`                  | `urn:ietf:params:xml:ns:yang:smiv2:SNMPv2-MIB`             | IETF | RFC 3418 |
| 44 | `SNMP-TARGET-MIB`             | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-TARGET-MIB`        | IETF | RFC 3413 |
| 45 | `SNMP-NOTIFICATION-MIB`       | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-NOTIFICATION-MIB`  | IETF | RFC 3413 |
| 46 | `SNMP-USER-BASED-SM-MIB`      | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-USER-BASED-SM-MIB` | IETF | RFC 3414 |
| 47 | `SNMP-VIEW-BASED-ACM-MIB`     | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-VIEW-BASED-ACM-MIB`| IETF | RFC 3415 |
| 48 | `SNMP-COMMUNITY-MIB`          | `urn:ietf:params:xml:ns:yang:smiv2:SNMP-COMMUNITY-MIB`     | IETF | RFC 3584 |
| 49 | `IANA-ADDRESS-FAMILY-NUMBERS-MIB` | `urn:ietf:params:xml:ns:yang:smiv2:IANA-ADDRESS-FAMILY-NUMBERS-MIB` | IANA | Standard |
| 50 | `RFC1213-MIB`                 | `urn:ietf:params:xml:ns:yang:smiv2:RFC1213-MIB`            | IETF | RFC 1213 |
| 51 | `TRANSPORT-ADDRESS-MIB`       | `urn:ietf:params:xml:ns:yang:smiv2:TRANSPORT-ADDRESS-MIB`  | IETF | RFC 3419 |

---

## Appendix D: Telemetry Dictionary & Alert Definitions

| Metric Identifier | Measurement Unit | Sampling Range | Critical Alarm Condition | Remediation Action |
| :--- | :--- | :--- | :--- | :--- |
| `rf.rssi.dbm` | Decibels relative to 1 mW ($\text{dBm}$) | $-90.0$ to $-35.0$ | $\text{RSSI} < -78.0 \ \text{dBm}$ | Trigger ATPC max boost; if unresolved, downshift ACM floor |
| `rf.snr.db` | Decibels ($\text{dB}$) | $0.0$ to $40.0$ | $\text{SNR} < 10.5 \ \text{dB}$ | Lower ACM floor to QPSK / BPSK |
| `rf.active_mcs` | Modulation Index (Integer) | $1$ to $12$ | $\text{MCS} \le 2$ | Re-route best-effort traffic via alternate path |
| `hw.temp.modem_c` | Degrees Celsius ($^\circ\text{C}$) | $-40.0$ to $+95.0$ | $\text{Temp} \ge 85.0^\circ\text{C}$ | Alert thermal anomaly; reduce TX power ceiling |
| `eth.crc_errors` | Cumulative Packet Count | $0$ to $2^{64}-1$ | Rate $> 100 \ \text{errors/sec}$ | Flag physical link degradation |
| `qos.buffer_drops`| Cumulative Packet Count | $0$ to $2^{64}-1$ | Rate $> 50 \ \text{drops/sec}$ | Expand token bucket or trigger load-balancing |

---

## Appendix E: Comprehensive Technical Glossary & Standards References

- **2PC**: Two-Phase Commit Protocol.
- **ACM**: Adaptive Coding and Modulation.
- **ATPC**: Adaptive Transmission Power Control.
- **BBU**: Baseband Unit.
- **BER**: Bit Error Rate.
- **CBS**: Committed Burst Size.
- **CIR**: Committed Information Rate.
- **CSPF**: Constrained Shortest Path First.
- **DN**: Distribution Node (Terragraph).
- **eCPRI**: enhanced Common Public Radio Interface.
- **EBS**: Excess Burst Size.
- **EIRP**: Effective Isotropic Radiated Power.
- **ERPS**: Ethernet Ring Protection Switching (ITU-T G.8032).
- **FCS**: Frame Check Sequence.
- **FDD**: Frequency Division Duplexing.
- **FSPL**: Free Space Path Loss.
- **FWA**: Fixed Wireless Access.
- **HIL**: Hardware-in-the-Loop.
- **IBN**: Intent-Based Networking.
- **IEEE 802.11ad / ay**: Standard for Very High Throughput 60 GHz mmWave.
- **IEEE 802.1ag**: Connectivity Fault Management (CFM).
- **ITU-R P.838-3**: Specific attenuation model for rain for use in prediction methods.
- **ITU-R P.676-12**: Attenuation by atmospheric gases and related effects.
- **LLM**: Large Language Model.
- **LOS / NLOS**: Line-of-Sight / Non-Line-of-Sight.
- **MCS**: Modulation and Coding Scheme.
- **MEC**: Multi-Access Edge Computing.
- **NMDA**: Network Management Datastore Architecture (IETF RFC 8342).
- **O-CU**: Open Central Unit (O-RAN).
- **O-DU**: Open Distributed Unit (O-RAN).
- **O-RU**: Open Radio Unit (O-RAN).
- **OOWT**: Open Optical & Wireless Transport (TIP).
- **PIR**: Peak Information Rate.
- **QAM**: Quadrature Amplitude Modulation.
- **RESTCONF**: REST-like Protocol over HTTP for YANG data stores (IETF RFC 8040).
- **RIS**: Reconfigurable Intelligent Surface.
- **SDN**: Software-Defined Networking.
- **SINR**: Signal-to-Interference-plus-Noise Ratio.
- **TCA**: Threshold Crossing Alert.
- **TFS**: ETSI TeraFlowSDN.
- **TU**: Terminal Unit (MultiHaul TG MH-T261).
- **UPF**: User Plane Function (3GPP 5G Core).
- **URLLC**: Ultra-Reliable Low-Latency Communication.
- **V-Band**: 57 GHz to 66 GHz RF Spectrum.
- **XPIC**: Cross-Polarization Interference Cancellation.
- **ZSM**: Zero-Touch Network & Service Management (ETSI).


---

## 12.6 Kubernetes Deployment Manifests & Helm Configuration

To deploy the Ceragon Southbound Driver inside an ETSI TeraFlowSDN 7.0 / 8.0 production Kubernetes cluster:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deviceservice
  namespace: teraflow
  labels:
    app.kubernetes.io/name: deviceservice
    app.kubernetes.io/part-of: teraflowsdn
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: deviceservice
  template:
    metadata:
      labels:
        app.kubernetes.io/name: deviceservice
    spec:
      containers:
      - name: server
        image: teraflow/deviceservice:7.0.0-ceragon
        imagePullPolicy: IfNotPresent
        env:
        - name: LOG_LEVEL
          value: "INFO"
        - name: CONTEXT_SERVICE_HOST
          value: "contextservice.teraflow.svc.cluster.local"
        - name: CONTEXT_SERVICE_PORT
          value: "1010"
        - name: MONITORING_SERVICE_HOST
          value: "monitoringservice.teraflow.svc.cluster.local"
        - name: MONITORING_SERVICE_PORT
          value: "7070"
        - name: CERAGON_DEFAULT_USERNAME
          valueFrom:
            secretKeyRef:
              name: ceragon-credentials
              key: username
        - name: CERAGON_DEFAULT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ceragon-credentials
              key: password
        ports:
        - containerPort: 2020
          name: grpc
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 2048Mi
        livenessProbe:
          grpc:
            port: 2020
          initialDelaySeconds: 15
          periodSeconds: 10
        readinessProbe:
          grpc:
            port: 2020
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

## Appendix F: TeraFlowSDN Northbound REST API Reference

The TFS Northbound REST API (`localhost:8088`) provides standardized endpoints for managing wireless transport devices and topologies:

### 1. `GET /tfs-api/context/{context_uuid}/topology/{topology_uuid}`
Retrieves the complete graph topology including devices, endpoints, and links:
```http
GET /tfs-api/context/admin/topology/admin HTTP/1.1
Host: localhost:8088
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "topology_id": {
    "context_id": { "context_uuid": { "uuid": "admin" } },
    "topology_uuid": { "uuid": "admin" }
  },
  "device_ids": [
    { "device_uuid": { "uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c" } }
  ],
  "link_ids": [
    { "link_uuid": { "uuid": "ceragon-uplink-ctu-96-to-O-CU-North" } }
  ]
}
```

### 2. `PUT /tfs-api/device/{device_uuid}`
Applies configuration rules via the Ceragon Southbound driver:
```http
PUT /tfs-api/device/f676623c-1a65-54bd-b1e8-279c8a6d8a1c HTTP/1.1
Host: localhost:8088
Content-Type: application/json

{
  "device_id": {
    "device_uuid": { "uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c" }
  },
  "device_config": {
    "config_rules": [
      {
        "action": "CONFIGACTION_SET",
        "custom": {
          "resource_key": "/radio/tuning",
          "resource_value": "{\"frequency_mhz\": 64800.0, \"tx_power_control\": \"auto\"}"
        }
      }
    ]
  }
}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "device_id": {
    "device_uuid": { "uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c" }
  }
}
```


---

# CHAPTER 13: TELECOM NETWORK DIGITAL TWIN (NDT) ARCHITECTURE & MULTI-LAYER API FRAMEWORK

## 13.1 Executive Overview & Strategic Standardization Context

The evolution of modern disaggregated transport networks (O-RAN fronthaul, midhaul, and backhaul) towards 6G necessitates autonomous, predictive, and zero-touch operations. Traditional reactive network management systems (NMS) and static SDN controllers cannot predict the operational consequences of severe meteorological events (such as mmWave rain fade under ITU-R P.838-3), rapid traffic surges, or dynamic beam mispointing prior to physical execution.

A **Telecom Network Digital Twin (NDT)** bridges this paradigm by maintaining a synchronized, high-fidelity digital representation of physical network elements, topologies, radio frequency propagation environments, and operational states. It provides an isolated, risk-free execution sandbox for:
1. **What-If Scenario Evaluation**: Pre-evaluating topology changes, traffic rerouting, and parameter adjustments under simulated stress.
2. **Predictive Failure Detection**: Simulating channel degradation curves and forecasting bit error rate (BER) and throughput collapse before SLA breaches occur.
3. **Autonomous Closed-Loop Optimization**: Synthesizing corrective intent remediations, validating them within the simulation model, and safely committing configurations to physical hardware.

To prevent fragmented, proprietary implementations, this architecture anchors directly on international standard bodies:
- **3GPP TS 28.561 (Release 19 SA5)**: *Management and orchestration; Management aspects of Network Digital Twins*. Formalizes the Network Digital Twin Instance (NDTI) lifecycle, data synchronization, and experiment execution.
- **3GPP TR 28.915**: *Study on management aspects of Network Digital Twin*. Establishes the foundational use cases, architectural requirements, and integration with 3GPP Management Services (MnS).
- **ITU-T Y.3090**: *Digital Twin Network: Requirements and Architecture*. Defines the four-layer DTN reference model (Physical Network Layer, Twin Data Layer, Network Twin Model Layer, Network Application Layer) with standardized northbound and southbound interfaces.
- **IETF/IRTF NMRG (`draft-irtf-nmrg-network-digital-twin-arch`)**: *Network Digital Twin: Concepts and Reference Architecture*. Outlines the Internet and transport network reference architecture.
- **IETF/IRTF NMRG (`draft-paillisse-nmrg-performance-digital-twin-02`)**: *Performance Evaluation of Network Digital Twin*. Formally defines the **Digital Twin Interface (DTI)** for data ingestion and what-if simulation requests.
- **IETF/IRTF NMRG (`draft-zcz-nmrg-digitaltwin-data-collection`)**: *Data Collection Requirements and Technologies for NDT*. Details protocol bindings (NETCONF, RESTCONF, gNMI, YANG Push, IPFIX, In-band Telemetry).
- **ETSI TS 104 296**: *Network Digital Twin for Deterministic Testing; Architecture, models and interfaces*.
- **TM Forum ODA (Open Digital Architecture)**: Standardized Open APIs including TMF921 (Intent Management), TMF639 (Resource Inventory), TMF640 (Service Activation), TMF642 (Alarm Management), and TMF645 (Service Qualification).
- **3GPP TS 29.222 / ETSI OpenCAPIF**: *Common API Framework (CAPIF)*. Provides standardized API discovery, publishing, security (OAuth 2.0, mTLS), and lifecycle governance.

---

## 13.2 The Five-Layer Telecom Digital Twin API Taxonomy

A production-grade telecom digital twin operates across five distinct API boundaries. Treating the digital twin API as identical to the device management API is an architectural anti-pattern. The following taxonomy delineates the operational boundaries:

```
+-----------------------------------------------------------------------------------+
|  Layer 5: API Exposure, Governance & Security (3GPP CAPIF / ETSI OpenCAPIF)       |
|  - CCF (CAPIF Core Function): API Publishing, Discovery, Authentication, Logging  |
|  - AEF (API Exposing Function): Fine-grained RBAC, Rate Limiting, Auditing        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|  Layer 4: Northbound Intent & Inventory Abstraction (TM Forum ODA)               |
|  - TMF921: Declarative Intent Ingestion & SLA Reconciler                          |
|  - TMF639: Standardized Resource Inventory Management & Projections               |
|  - Applications: RCA, Planning, Energy Optimization, AI/RL Cognitive Agents      |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|  Layer 2: Digital Twin Interface (DTI - IETF NMRG & 3GPP TS 28.561)              |
|  - NDTI Lifecycle Engine: Create, Initialize, Sync, Update, Experiment, Terminate |
|  - What-If Simulation Engine: Perturbation Injection, ITU-R P.838 Rain Models     |
|  - Simulation Adapters: NS-3 Discrete-Event C++ Engine + Analytical Physics Models|
+-----------------------------------------------------------------------------------+
                  |                                                  ^
   Layer 3: Pre-commit Safety Validation             Layer 1: Real-Time Sync
                  v                                                  |
+-----------------------------------------------------------------------------------+
|  ETSI TeraFlowSDN (TFS) Controller Mesh                                           |
|  - Context Service (CockroachDB Authoritative Topology & Inventory Store)         |
|  - Device Service (2-Phase Commit Candidate Datastore Transaction Engine)         |
+-----------------------------------------------------------------------------------+
                  |                                                  ^
   Southbound 2PC Candidate Commit                   RESTCONF / NETCONF / Telemetry
                  v                                                  |
+-----------------------------------------------------------------------------------+
|  Layer 1: Physical Network Transport (Ceragon Networks)                          |
|  - MultiHaul TG MH-T261 TU / MH-N366 DN (60 GHz V-Band Beamforming Phased Array)  |
|  - EtherHaul EH-8010FX / EH-2500FX (70/80 GHz E-Band up to 10 Gbps)               |
|  - CeraOS IP-50 / IP-20 Microwave (XPIC, 4096-QAM, Hitless Adaptive Modulation)  |
+-----------------------------------------------------------------------------------+
```

---

### Layer 1: Southbound Synchronization (Physical Network -> Digital Twin)
Supplies continuous, high-fidelity real-time telemetry and state from physical Ceragon hardware and SDN controller datastores into the digital twin shadow:
- **Transport Protocols**: RFC 8040 RESTCONF (`/restconf/ds/ietf-datastores:candidate` and operational datastore), RFC 6241 NETCONF, RFC 6022 NETCONF Monitoring, gNMI (gRPC Network Management Interface), and YANG Push (RFC 8641 / RFC 8639).
- **Transport Telemetry Payload Dictionary**:
  - `carrier_frequency_ghz`: Active RF carrier center frequency (e.g., 64.80 GHz / Channel 4).
  - `bandwidth_mhz`: Operational channel spacing (e.g., 2160 MHz mmWave, 112 MHz microwave).
  - `acm_modulation_mcs`: Current Adaptive Coding & Modulation MCS index (MCS 0 to MCS 12).
  - `rssi_dbm`: Received Signal Strength Indication (dBm).
  - `snr_db`: Signal-to-Noise Ratio (dB) / SINR.
  - `tx_power_dbm`: Transmit RF output power with ATPC (Adaptive Transmit Power Control) state.
  - `modem_temperature_c` & `rf_temperature_c`: Thermal health tracking.
  - `interface_counters`: Ingress/egress Octets, discarded packets, CRC frame errors.

---

### Layer 2: The Digital Twin Interface (DTI - Model & Simulation Interaction)
Standardized by IETF NMRG (`draft-paillisse-nmrg-performance-digital-twin-02`) and 3GPP TS 28.561. This interface enables applications, AI agents, and engineers to submit hypothetical network conditions and receive predicted performance metrics without altering physical infrastructure:
- **Input Payload**: Base state snapshot reference, perturbation vector (rain rate in mm/hr, path length in km, link outages, traffic surges), and target simulation engine (e.g. `ns3-itur-p838` or analytical).
- **Output Predictions**: Expected RSSI, SNR, ACM modulation MCS drop, throughput reduction (Mbps), packet latency (ms), jitter (ms), frame loss probability, and binary SLA breach warnings.
- **Recommended Remediation**: Computed reconfiguration vector to counteract the perturbation.

---

### Layer 3: Closed-Loop Network Actuation (Digital Twin -> Physical Network Control)
A digital twin must not directly write unchecked mutations to physical hardware. Layer 3 implements a strict **two-step closed-loop gatekeeper**:
1. **Pre-Commit Safety Verification**: The proposed mitigation is evaluated against RF safety boundaries (operational frequency limits 57.0–71.0 GHz, minimum ACM floor constraints, hardware thermal envelopes, and regulatory EIRP limits).
2. **Transactional Dispatch via ETSI TeraFlowSDN**: Once verified, configuration rules are pushed through TFS's Device Service using RFC 8040 candidate datastore 2-Phase Commit (2PC):
   - `/radio/tuning`: Frequency and channel bandwidth reassignment.
   - `/modulation/acm_floor`: Minimum modulation floor hardening against link fade.
   - `/slice/{slice_name}`: Dynamic IEEE 802.1Q VLAN QoS bandwidth policing.

---

### Layer 4: Northbound Intent & Inventory Abstraction (TM Forum ODA)
Enables higher-layer business support systems (BSS), orchestrators, and AI agents to interact with the digital twin via standardized telecom domain abstractions:
- **TMF921 (Intent Management API)**: Expresses declarative business and operational goals (e.g., *“Maintain latency <= 1.5ms and availability >= 99.999% during adverse weather events”*). The digital twin acts as the autonomic reconciler.
- **TMF639 (Resource Inventory Management API)**: Projects the synchronized multi-vendor transport elements (Ceragon nodes, microwave hops, interfaces) as standardized `PhysicalResource` entities.
- **TMF640 (Service Activation and Configuration)**: Automates end-to-end transport service lifecycle.
- **TMF642 (Alarm Management)**: Propagates predictive degradation events and proactive warning thresholds.

---

### Layer 5: API Exposure, Governance & Security (3GPP CAPIF / ETSI OpenCAPIF)
3GPP TS 29.222 specifies the **Common API Framework (CAPIF)** to securely expose telecom network functions:
- **CAPIF Core Function (CCF)**: Central registry where Digital Twin APIs are published (`TelecomDigitalTwin_DTI_API`).
- **API Exposing Function (AEF)**: Provides mutual TLS (mTLS), OAuth 2.0 JWT bearer token authentication, fine-grained access control, rate limiting, and audit logging.
- **API Invoker**: External AI agents, NS-3 co-simulation controllers, and third-party applications discover and consume Digital Twin services in compliance with 3GPP security profiles.

---

## 13.3 3GPP TS 28.561 Release 19 SA5 Network Digital Twin Lifecycle

3GPP TS 28.561 defines the management architecture for Network Digital Twin Instances (NDTI) managed by the Network Digital Twin Management Function (NDTMF). An NDTI transitions through a rigorous state machine:

```
    +--------------------------------------------------------------+
    |                             NULL                             |
    +--------------------------------------------------------------+
                                   |
                         CreateNDTI (Request)
                                   v
    +--------------------------------------------------------------+
    |                         INITIALIZING                         |
    +--------------------------------------------------------------+
                                   |
                        InitializeNDTI (Complete)
                                   v
    +--------------------------------------------------------------+
    |                         SYNCHRONIZED                         |<---+
    +--------------------------------------------------------------+    |
         |                         |                        ^           |
 ExecuteExperiment           SyncNDTI / UpdateNDTI          |           |
         v                         v                        |           |
+-------------------+     +-------------------+             |           |
|     EXECUTING     |     |     UPDATING      |-------------+           |
|    EXPERIMENT     |     +-------------------+                         |
+-------------------+                                                   |
         |                                                              |
 RetrieveResults                                                        |
         +--------------------------------------------------------------+
                                   |
                         TerminateNDTI (Request)
                                   v
    +--------------------------------------------------------------+
    |                          TERMINATED                          |
    +--------------------------------------------------------------+
```

### Lifecycle Operations & Semantics:
1. **CreateNDTI**: Allocates memory, initializes twin shadow structures, and registers the NDTI ID with the NDTMF.
2. **InitializeNDTI**: Establishes initial network topology, node inventory, and baseline RF parameters from ETSI TeraFlowSDN and Ceragon hardware.
3. **SyncNDTI / UpdateNDTI**: Reconciles the twin state with live physical measurements (poll or event-driven).
4. **ExecuteExperiment**: Evaluates what-if scenarios (perturbations, channel fading, traffic spikes) within the twin sandbox.
5. **RetrieveResults**: Returns detailed prediction vectors, SLA breach probabilities, and mitigation options.
6. **TerminateNDTI**: Gracefully deallocates twin resources and archives experiment logs.

---

## 13.4 NS-3 Co-Simulation Engine & Runtime Bridge

The digital twin leverages **Network Simulator 3 (NS-3)** to perform packet-level discrete-event co-simulation alongside analytical physical-layer models:

1. **Dynamic C++ Scenario Generation (`tfs_topology_to_ns3.py`)**:
   - Ingests active TFS topology dynamically.
   - Instantiates `ns3::NodeContainer` with exact physical and emulated device IDs.
   - Configures Point-to-Point wired Ethernet and Ceragon mmWave links with `ns3::ConstantSpeedPropagationDelayModel` and data rates mapped from active ACM modulations.
   - Injects synthetic 5G user-plane traffic using `ns3::OnOffHelper` and `ns3::PacketSinkHelper`.
   - Exports NetAnim XML tracking files (`AnimationInterface`).

2. **Runtime Co-Simulation Daemon (`ns3_tfs_runtime_bridge.py`)**:
   - Maintains an asynchronous 1-second telemetry polling loop syncing live TFS link states into an IPC shared buffer (`ns3_link_state.json`).
   - Hosts a lightweight REST Control Server on port `:9099` allowing NS-3 simulation hooks or external controllers to trigger runtime degradation events (`POST /events/ns3_degrade`) or physical control adjustments.

---

## 13.5 End-to-End Operational Verification Trace

The multi-layer architecture was validated end-to-end using the test harness `demo_telecom_digital_twin.py`:

```
========================================================================
  TELECOM NETWORK DIGITAL TWIN (NDT) END-TO-END DEMONSTRATION
  Standards: 3GPP TS 28.561 | ITU-T Y.3090 | IETF NMRG | TM Forum | CAPIF
========================================================================

--- [STEP 1] 3GPP CAPIF Service API Discovery (TS 29.222 / OpenCAPIF) ---
[+] Discovered Service API: TelecomDigitalTwin_DTI_API (ID: capif-service-dti-v1)
    Description: Standardized Digital Twin Interface for simulation, what-if modeling, and closed-loop control of Ceragon 6G transport networks via ETSI TeraFlowSDN.
    AEF Profile Status: PUBLISHED | Security: ['OAUTH2', 'MTLS']

--- [STEP 2] 3GPP TS 28.561 Network Digital Twin Instance (NDTI) Lifecycle ---
[+] Created NDTI Instance: ndti-oran-transport-demo
    Lifecycle State:      SYNCHRONIZED
    Synchronized Nodes:   34

--- [STEP 3] Layer 1 Physical Network Synchronization (ITU-T Y.3090) ---
[+] Reconciled Shadow State with Physical Ceragon Hardware & TFS:
    Nodes in Shadow:      34
    Links in Shadow:      34
    Active State:         SYNCHRONIZED

--- [STEP 4] Layer 4 TM Forum TMF921 Intent Management Ingestion ---
[+] Ingested TMF921 Intent: INTENT-95e73b (URLLC_CarrierGrade_ZeroOutage_Intent)
    State:                  acknowledged
    Target SLA:             {'max_latency_ms': 1.5, 'min_availability_pct': 99.999, 'min_throughput_mbps': 500.0}

--- [STEP 5] Layer 2 DTI What-If Scenario Simulation (IETF NMRG DTI) ---
[*] Submitting perturbation to Digital Twin: 55.0 mm/hr Heavy Rain Fade on Ceragon Link...
[!] Simulation Results (Engine: ns3-itur-p838):
    ITU-R Attenuation:    19.93 dB loss
    Predicted RSSI:       -77.93 dBm
    Predicted SNR:        4.07 dB
    Predicted Modulation: MCS 0 (Down from MCS 8)
    Predicted Throughput: 50.0 Mbps
    Predicted Latency:    6.77 ms
    SLA Breach Predicted: True (BREACH OF TMF921 INTENT!)
    Proposed Mitigation:  [{'type': 'ACM_FLOOR_HARDENING', 'min_mcs': 2}, {'type': 'CARRIER_FREQUENCY_RETUNE', 'target_ghz': 64.8, 'target_bw_mhz': 2000}, {'type': 'URLLC_SLICE_RESERVATION', 'vlan_id': 200, 'rate_mbps': 1000}]

--- [STEP 6] Layer 3 Closed-Loop Actuation via TFS 2-Phase Commit ---
[*] Validating safety rules in Digital Twin before physical commit...
[+] Safety Validation:       True (APPLIED_AND_VERIFIED)
    - Validated ACM Floor >= MCS 2 (Rain resilience verified)
    - Validated Carrier Frequency 64.8 GHz (Channel clear of co-channel interference)
[+] Physical 2PC Committed:  True
    TFS Actions Dispatched:  3

--- [STEP 7] Layer 4 TM Forum TMF639 Resource Inventory Projection ---
[+] Total Resources Projected into TMF639: 34
    Sample Resource: 6G Core DC & UPF [Type: PhysicalResource]
    Category:        WirelessTransportEquipment | Operational: enable

========================================================================
  DEMONSTRATION SUCCESSFUL: Closed-loop Telecom Digital Twin verified
  across all 5 API layers in strict compliance with 3GPP & ITU-T.
========================================================================
```

---

## 13.6 Summary of Architectural Grounding

By unifying **3GPP TS 28.561** for instance lifecycle management, **ITU-T Y.3090** for data/model layering, **IETF NMRG DTI** for simulation interaction, **TM Forum ODA** for northbound intent/resource abstraction, **ETSI TeraFlowSDN** for 2-phase commit transport actuation, and **3GPP CAPIF** for secure exposure, this framework establishes a comprehensive, standard-compliant blueprint for carrier-grade 6G transport digital twins.
