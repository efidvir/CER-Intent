# TFS-NS3 Telecom Network Digital Twin: System Architecture

## 1. Executive Architectural Overview

The TFS-NS3 Telecom Network Digital Twin (NDT) provides a real-time, bi-directional cyber-physical bridge between physical telecommunications networks (specifically ETSI TeraFlowSDN and Ceragon microwave/millimeter-wave transceivers) and discrete-event simulation platforms (NS-3), cognitive AI agents, and northbound intent orchestrators.

A foundational architectural finding embodied in this framework is:
> **The Digital Twin Interface (DTI) and the Device Management Interface are decoupled.**
> Device controllers (such as ETSI TeraFlowSDN's SBI) manage configuration state, telemetry streaming, and transaction lifecycles on live hardware. The Digital Twin Interface (DTI) exposes simulation models, what-if scenario sandboxing, risk-free validation, and intent assessment.

---

## 2. Multi-Domain Telecom Simulation Framework

The Digital Twin co-simulation engine with NS-3 is engineered as a **generic, multi-domain platform** accommodating diverse telecommunications operational scenarios:

```
                            +-----------------------------------+
                            |       Cognitive AI & Intent       |
                            |   (TMF921 / 3GPP TS 28.561 MnS)   |
                            +-----------------+-----------------+
                                              |
                             POST /api/v1/dti/scenarios
                                              |
                                              v
+------------------------------------------------------------------------------------------------+
|                        Generic Telecom Digital Twin Simulation Engine                         |
|                                                                                                |
|  +--------------------+  +--------------------+  +--------------------+  +--------------------+|
|  |   Traffic Surge    |  |    Fiber Cut &     |  |    Green Telco     |  |  Slice Admission   ||
|  |    & Congestion    |  |    Link Outage     |  |    Energy Sleep    |  |       & SLAs       ||
|  | (Queue / Loss / MS)|  | (TI-LFA / Alt Path)|  | (Carrier Off-Peak) |  | (URLLC / eMBB PDB) ||
|  +---------+----------+  +---------+----------+  +---------+----------+  +---------+----------+|
|            |                       |                       |                       |           |
|  +---------+----------+  +---------+----------+  +---------+----------+  +---------+----------+|
|  | Channel Fade (Rain)|  |  Mobility Handover |  |  Security / DDoS   |  | Routing Flap /    ||
|  | (ITU-R P.838 / ACM)|  | (Ping-Pong / RLF)  |  |  (Anomaly Surge)   |  | Convergence Time   ||
|  +---------+----------+  +---------+----------+  +---------+----------+  +---------+----------+|
|            +-----------------------+-----------------------+-----------------------+           |
|                                    v                                                           |
|                 +---------------------------------------------------+                          |
|                 |     NS-3 Discrete-Event Simulation Core (C++)     |                          |
|                 |   PointToPoint / QueueDisc / Csma / Propagation   |                          |
|                 +---------------------------------------------------+                          |
+------------------------------------------------------------------------------------------------+
```

### Supported Simulation Domains

1. **Traffic Surge & Buffer Congestion**:
   - Models sudden multi-gigabit traffic spikes (e.g., flash crowds, stadium events, major breaking broadcasts).
   - Simulates queue backlog growth, bufferbloat latency degradation (M/M/1/K queueing dynamics), and tail-drop packet loss.
   - Evaluates proactive QoS bandwidth reservation and dynamic flow policing before deployment.

2. **Topology Perturbations & Link Outages**:
   - Simulates fiber cuts, hardware port failures, and sudden backhaul node failures.
   - Evaluates sub-50ms Topology-Independent Loop-Free Alternate (TI-LFA) fast reroute and CSPF route recalculation.
   - Predicts congestion on secondary and tertiary links prior to failover execution.

3. **Green Telco & Energy Optimization**:
   - Simulates selective carrier sleep modes during off-peak windows (e.g., powering down secondary carrier frequencies or standby transponders).
   - Computes dynamic energy savings in Watts and kWh while verifying that remaining operational capacity strictly honors all traffic SLAs.

4. **Multi-Tenant Network Slice Admission**:
   - Evaluates incoming 5G/6G Network Slice requests (e.g., URLLC vs eMBB) against active transport bandwidth.
   - Verifies Packet Delay Budget (PDB $\le$ 1.5ms) and Packet Error Rate (PER $\le 10^{-6}$) admission boundaries.
   - Prevents slice oversubscription and SLA financial penalties.

5. **Physical-Layer Channel Perturbations (e.g., Rain Fade, Obstacles)**:
   - Illustrative physical perturbation module computing ITU-R P.838 mmWave rain attenuation ($\gamma_R = k \cdot R^\alpha$).
   - Simulates hitless Adaptive Coding and Modulation (ACM) down-stepping, SNR degradation, and capacity shrinkage.
   - Formulates carrier retuning and modulation floor hardening.

6. **Mobility & Handover Dynamics**:
   - Models mobile terminal velocity, handover hysteresis, and Radio Link Failure (RLF) risk during dense cell transitions.

---

## 3. The 5-Layer Architectural Stack

```
+-----------------------------------------------------------------------------+
| Layer 5: API Exposure, Governance & Security                                 |
| 3GPP TS 29.222 CAPIF Core Function (CCF) & API Exposing Function (AEF)      |
| OAuth 2.0 Bearer Tokens, mTLS, Catalog Discovery (/api/v1/capif/service-apis)|
+-----------------------------------------------------------------------------+
                                       |
+-----------------------------------------------------------------------------+
| Layer 4: Northbound Intent & Inventory Abstraction                           |
| TM Forum ODA: TMF921 Intent Management & TMF639 Resource Inventory          |
| Declarative SLA Contracts (/api/v1/tmf/tmf921/intent)                        |
+-----------------------------------------------------------------------------+
                                       |
+-----------------------------------------------------------------------------+
| Layer 2: Digital Twin Interface (DTI - Model & Simulation Interaction)      |
| IETF NMRG DTI (draft-paillisse-02) & 3GPP TS 28.561 NDTI Lifecycle           |
| Multi-Domain Scenario Sandbox (/api/v1/dti/scenarios)                        |
| Co-Simulation Engine: NS-3 C++ Discrete-Event + Analytical Physics           |
+-----------------------------------------------------------------------------+
          |                                                       |
          | Pre-Flight Verification                               | Shadow Telemetry Sync
          v                                                       v
+------------------------------------+  +-------------------------------------+
| Layer 3: Closed-Loop Actuation     |  | Layer 1: Southbound Synchronization |
| ETSI TeraFlowSDN 2-Phase Commit    |  | Physical Network -> Digital Twin    |
| Safety Gatekeeper Boundaries       |  | RFC 8040 RESTCONF, NETCONF, gNMI    |
| Device Candidate Datastore (/radio)|  | YANG Push Subscriptions (RFC 8641)  |
+------------------------------------+  +-------------------------------------+
          |                                                       ^
          +-------------------+               +-------------------+
                              |               |
                              v               |
+-----------------------------------------------------------------------------+
| Physical Telecommunications Network                                         |
| Ceragon MultiHaul TG (60 GHz V-Band), CeraOS Microwave Links, O-RAN Routers |
+-----------------------------------------------------------------------------+
```

---

## 4. Digital Twin Lifecycle (3GPP TS 28.561)

The Network Digital Twin Instance (NDTI) state machine is governed by 3GPP TS 28.561 Section 5:

1. **`NULL` $\rightarrow$ `INITIALIZING` (`CreateNDTI`)**: Allocates internal shadow state, data structures, and registers the NDTI ID.
2. **`INITIALIZING` $\rightarrow$ `SYNCHRONIZED` (`InitializeNDTI`)**: Baseline topology and hardware profiles are loaded from ETSI TeraFlowSDN Context Service.
3. **`SYNCHRONIZED` $\leftrightarrow$ `UPDATING` (`SyncNDTI`)**: Operational state (carrier frequencies, modulations, power, queue metrics) is continuously reconciled.
4. **`SYNCHRONIZED` $\leftrightarrow$ `EXECUTING_EXPERIMENT` (`ExecuteExperiment`)**: A what-if perturbation request is evaluated within the NS-3 co-simulation sandbox.
5. **`ANY` $\rightarrow$ `TERMINATED` (`TerminateNDTI`)**: The instance is cleanly retired, freeing simulator processes and archiving execution telemetry.

---

## 5. Pre-Commit Safety Gatekeeper & 2-Phase Commit

A key safety principle of this architecture is that **no optimization is applied directly to the physical network without automated pre-flight safety verification within the twin**:

1. **Safety Envelopes**:
   - Carrier frequency limits (e.g., 57.0–71.0 GHz for V-Band, 71.0–86.0 GHz for E-Band).
   - Minimum ACM modulation floor (e.g., MCS $\ge$ 1 to prevent complete link drops).
   - Maximum transmission power and thermal safety thresholds.
   - Minimum reserve bandwidth for critical slices (URLLC $\ge 100\text{ Mbps}$).
2. **Transactional Commit**:
   - If verified safe, rules are written to ETSI TeraFlowSDN's candidate datastore.
   - TeraFlowSDN executes a 2-Phase Commit (2PC) to ensure atomic deployment across all impacted nodes. If any node rejects the configuration, automatic rollback is triggered.
