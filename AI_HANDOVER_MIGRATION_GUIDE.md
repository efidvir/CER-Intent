# AI Handover & Project Migration Guide
## Project: CER-Intent · 6G Intent Management, ETSI TeraFlowSDN & NS-3.45 Ceragon Digital Twin

> **Quick Start for the Receiving AI Agent**:
> Read this entire file first. It contains the complete 3-repository architecture, local & remote server credentials/paths, compiled C++20 NS-3.45 binary interfaces, REST API contracts, dashboard architecture, known technical gotchas, and current priorities.

---

## 0. Copy-Paste Bootstrap Prompt for the New AI

Copy and paste the block below as your first prompt to the new AI assistant:

```text
You are taking over development of the CER-Intent 6G Transport Intent Management, ETSI TeraFlowSDN, and NS-3.45 Ceragon Digital Twin platform.
First, read `c:\CER_Intent\AI_HANDOVER_MIGRATION_GUIDE.md` in full.

Key architecture rules you must preserve:
1. The system spans 3 strictly separated repositories:
   - Top-level Intent AI, Governance & Web Dashboards: `https://github.com/efidvir/CER-Intent` (local: `c:\CER_Intent`, branch: `main`)
   - TFS <-> Ceragon Southbound Driver (36 models, 84 YANG 1.1 schemas, 12 SBI domains): `https://github.com/efidvir/teraflowsdn` (remote: `efid@cersrv-029:/home/efid/teraflowsdn`, branch: `feat/ceragon-60ghz-driver`, mirrored locally in `c:\CER_Intent\ceragon_tfs_adapter`)
   - TFS <-> NS-3.45 Digital Twin & `contrib/ceragon` C++20 module: `https://github.com/efidvir/tfs-ns3-digital-twin` (remote: `efid@cersrv-029:/home/efid/tfs-ns3-digital-twin` and compiled in `/home/efid/ns3-dev/contrib/ceragon`, mirrored locally in `c:\CER_Intent\ns3_ceragon`)
2. Never fake simulations or hardcode instant transitions. All flows in the dashboards (`dashboard/flow.html`, `dashboard/ceragon-twin.html`, `dashboard/digital_twin.html`, `dashboard/index.html`) must adhere to the real simulated scenario topology, multi-hop data streams, and discrete events from the backend (`:5000`), SSH NS-3.45 server (`efid@cersrv-029`), and TeraFlowSDN (`:8088`).
3. Verify that the local server (`python run.py` on port 5000) and SSH connection (`ssh efid@cersrv-029`) are reachable before making changes.
```

---

## 1. Three-Repository Architecture & Git State

The platform is architected across **three distinct repositories** corresponding to the three functional planes of the system:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: CER-Intent (Northbound AI Architect, 3GPP TS 28.561 & Dashboards)   │
│ Repo:    https://github.com/efidvir/CER-Intent (branch: main @ 25c1e96)      │
│ Local:   c:\CER_Intent                                                       │
│ Runtime: Python Flask + SocketIO on http://localhost:5000                    │
└───────────────────┬──────────────────────────────────────┬───────────────────┘
                    │ REST / gRPC (:8088)                  │ SSH Subprocess
                    ▼                                      ▼
┌────────────────────────────────────────┐ ┌───────────────────────────────────┐
│ LAYER 2: ETSI TeraFlowSDN <-> Ceragon  │ │ LAYER 3: TFS <-> NS-3.45 Twin     │
│ Repo:  github.com/efidvir/teraflowsdn  │ │ Repo:  github.com/efidvir/        │
│ Branch: feat/ceragon-60ghz-driver      │ │        tfs-ns3-digital-twin       │
│         (@ 383dd2aa2)                  │ │ Branch: main (@ 367f907)          │
│ Remote: efid@cersrv-029:               │ │ Remote: efid@cersrv-029:          │
│         /home/efid/teraflowsdn         │ │   /home/efid/tfs-ns3-digital-twin │
│ Local Mirror:                          │ │   /home/efid/ns3-dev/contrib/     │
│   c:\CER_Intent\ceragon_tfs_adapter    │ │          ceragon                  │
│ Scope: 36 Ceragon Models, 84 YANG 1.1  │ │ Local Mirror:                     │
│        Schemas, 12-Domain SBI Driver   │ │   c:\CER_Intent\ns3_ceragon       │
└────────────────────────────────────────┘ └───────────────────────────────────┘
```

| Layer | GitHub Repository | Branch | Latest Commit | Local Path | Remote Path (`efid@cersrv-029`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. CER-Intent (Intent Engine & UI)** | `https://github.com/efidvir/CER-Intent.git` | `main` | `25c1e96` | `c:\CER_Intent` | N/A (runs on Windows host `:5000`) |
| **2. TeraFlowSDN <-> Ceragon Driver** | `https://github.com/efidvir/teraflowsdn.git` | `feat/ceragon-60ghz-driver` | `383dd2aa2` | `c:\CER_Intent\ceragon_tfs_adapter` | `/home/efid/teraflowsdn` |
| **3. TFS <-> NS-3.45 Digital Twin** | `https://github.com/efidvir/tfs-ns3-digital-twin.git` | `main` | `367f907` | `c:\CER_Intent\ns3_ceragon` | `/home/efid/tfs-ns3-digital-twin` & `/home/efid/ns3-dev/contrib/ceragon` |

---

## 2. Infrastructure, Hosts & Credentials

### 2.1 Local Windows Development Host
- **Workspace Root**: `c:\CER_Intent`
- **Start Server Command**:
  ```powershell
  Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  cd c:\CER_Intent
  python run.py
  ```
- **Web Server**: `http://localhost:5000` (serves `dashboard/` with `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`).

### 2.2 Remote Linux NS-3.45 & TeraFlowSDN Server (`cersrv-029`)
- **SSH Target**: `efid@cersrv-029` (`10.114.234.129`, key-based passwordless SSH already configured from Windows).
- **NS-3.45 Root**: `/home/efid/ns3-dev`
- **Compiled C++20 Binaries Location**:
  - `/home/efid/ns3-dev/build/contrib/ceragon/examples/` (5 Ceragon portfolio & physics binaries)
  - `/home/efid/ns3-dev/build/scratch/` (2 TSN/WiFi/TFS topology scratch binaries)
- **Shared Library Path Required When Running Binaries Directly**:
  ```bash
  export LD_LIBRARY_PATH=/home/efid/ns3-dev/build/lib:$LD_LIBRARY_PATH
  ```

### 2.3 ETSI TeraFlowSDN Controller & Physical Hardware
- **TeraFlowSDN NBI**: `http://localhost:8088/tfs-api` (Basic Auth: `admin` / `admin`).
  - *Note*: If the SSH port-forward or TFS container on `:8088` is offline, `DeviceRegistry` and `TeraFlowAdapter` automatically fall back to the local 36-node / 36-link topology state in `c:\CER_Intent\data\topology_state.json`.
- **Physical Ceragon Radio**: `192.168.1.225` (`ceragon-mh-t261-ctu-96`, Haulage MH-T261 60.48 GHz V-Band 32-element phased-array radio).

---

## 3. Detailed Codebase Breakdown

### 3.1 Layer 1: `c:\CER_Intent` (Main Application)
- **[`run.py`](file:///c:/CER_Intent/run.py)**:
  - Entry point. **Important**: Line 9 calls `eventlet.monkey_patch(os=False, subprocess=False)` so `subprocess.run` SSH calls to `cersrv-029` do not hang on Windows.
- **[`cer_intent/api/server.py`](file:///c:/CER_Intent/cer_intent/api/server.py)**:
  - Flask + SocketIO server.
  - Routes:
    - `GET /` -> serves `dashboard/flow.html` by default, or `dashboard/index.html` when `?view=expert` is passed.
    - `POST /api/v1/intent` -> parses natural language intent, runs the 17-Skill `IntentArchitectAgent`, synthesizes RFC 6020 YANG 1.1 previews, and stores the intent.
    - `POST /api/v1/intents/<id>/approve` -> acquires a `ConflictFabric` lease token, executes 2PC commit via `TeraFlowAdapter` / `CeragonDriver`, and updates `data/topology_state.json`.
    - `GET /api/v1/topology` -> returns unified 36-node / 36-link topology (`data/topology_state.json` merged with TFS).
    - `GET /api/v1/devices/<id>/state` -> southbound operational state readback.
- **[`cer_intent/api/digital_twin_routes.py`](file:///c:/CER_Intent/cer_intent/api/digital_twin_routes.py)**:
  - Blueprint `/api/v1/digital-twin/*` powering all Digital Twin dashboards:
    - `GET /api/v1/digital-twin/status` -> cross-repo status (Physical HW `.225`, NS-3.45 on `cersrv-029`, TFS `:8088`).
    - `POST /api/v1/digital-twin/step-stage` -> executes Stages 1–5; **Stage 3** runs real C++ NS-3.45 over SSH on `efid@cersrv-029`, returning `execution_phases` (`3A_TOPOLOGY_EXPORT`, `3B_BASELINE_BEFORE`, `3C_CANDIDATE_ACTUATION`, `3D_MITIGATED_AFTER`), `simulated_topology`, `data_streams`, `scenario_events`, `visualization_blueprint`, and `discrete_packet_trace`.
    - `POST /api/v1/digital-twin/simulate-tsn` -> runs `TSNSimulationRunner` (`ns3.45-tsn_wifi_ceragon-default`) for `digital_twin.html`.
    - `GET /api/v1/digital-twin/ceragon/overview` -> returns the 36-model catalog, 84 YANG schemas, 12 southbound control domains, and NS-3 sweep data.
    - `POST /api/v1/digital-twin/ceragon/compile-rule` -> compiles an intent/domain rule into 5 southbound protocols (NETCONF XML, RESTCONF JSON, gNMI, SNMP, CLI) + NS-3 C++ API call.
    - `POST /api/v1/digital-twin/ceragon/run-example` -> executes any of the 5 compiled `contrib/ceragon` C++20 example binaries live on `efid@cersrv-029` over SSH (`EX_PORTFOLIO`, `EX_MULTIBAND`, `EX_TSN`, `EX_TERRAGRAPH`, `EX_PROTECTION`).
    - `GET /api/v1/digital-twin/restconf-wire` & `GET /api/v1/digital-twin/datastore-diff` -> returns RFC 8040 / RFC 8527 candidate-to-running datastore wire traces and 4-leaf diffs.
- **[`cer_intent/tsn_simulation_runner.py`](file:///c:/CER_Intent/cer_intent/tsn_simulation_runner.py)**:
  - Runs `ns3.45-tsn_wifi_ceragon-default` over SSH on `efid@cersrv-029` and always populates a full-timeline (`0.0s..2.5s`, 900 events) multi-hop `discrete_packet_trace` (`STA0/1 -> AP0/1 -> C0 -> C1 -> C2 -> C3 -> SINK`) alongside `raw_cpp_trace_events`.

### 3.2 Layer 2: `ceragon_tfs_adapter` & `teraflowsdn` (`src/device/service/drivers/ceragon/`)
- **[`CeragonPortfolioCatalog.py`](file:///c:/CER_Intent/ceragon_tfs_adapter/ceragon_driver/CeragonPortfolioCatalog.py)**:
  - Complete hardware specifications for **36 Ceragon models across 5 product families**:
    1. **FibeAir IP-20 Series** (`IP-20C`, `IP-20C-HP`, `IP-20S`, `IP-20N`, `IP-20A`, `IP-20G`, `IP-20GX`, `IP-20E`, `IP-20V`, `IP-20F`, `IP-20Assured`)
    2. **FibeAir IP-50 Series** (`IP-50E`, `IP-50EX`, `IP-50C`, `IP-50CX`, `IP-50FX`, `IP-50GP`)
    3. **EtherHaul / Siklu mmWave Series** (`EH-8010FX`, `EH-8020FX`, `EH-2500FX`, `EH-1200FX`, `EH-1200TX`, `EH-710TX`, `EH-700TX`, `EH-614TX`, `EH-600TX`, `EH-500TX`)
    4. **MultiHaul / Terragraph 60 GHz PtMP & Mesh Series** (`MH-B100`, `MH-T200`, `MH-N366`, `MH-T261`, `MH-T280`, `MH-B260`)
    5. **Pointlink / Access & Long-Haul Series** (`IP-100E`, `IP-10G`, `Evo-LH`)
- **[`CeragonYangValidator.py`](file:///c:/CER_Intent/ceragon_tfs_adapter/ceragon_driver/CeragonYangValidator.py)** & `yang/` directory:
  - Validates against **84 bundled RFC 6020 / RFC 7950 YANG 1.1 schemas** (Ceragon vendor YANGs, Siklu radio/TG YANGs, IETF interfaces/routing/datastores, IEEE 802.1Qcw/Qbv/Qbu/1AE/1AB, ITU-T G.8275.1/G.8032, O-RAN eCPRI/sync) with **0 missing imports**.
- **[`CeragonFunctionalTwin.py`](file:///c:/CER_Intent/ceragon_tfs_adapter/ceragon_driver/CeragonFunctionalTwin.py)**:
  - Implements the **12 Southbound Control Domains**:
    1. `radio-rf-acm-atpc` (RF Carrier, ACM 28-step BPSK..4096QAM, ATPC)
    2. `xpic-mimo-spatial` (2x2 XPIC Cross-Pol & 4x4 LoS MIMO)
    3. `multiband-l1-bonding` (L1 Multi-Band 80 GHz E-Band + 18/23 GHz MW Bonding)
    4. `phased-array-60ghz` (60 GHz IEEE 802.11ad/ay 32-Element Beamforming & Terragraph TDMA)
    5. `qos-tsn-8021qbv` (8-CoS H-QoS, IEEE 802.1Qbv TAS Gate Control Lists & 802.1Qbu Preemption)
    6. `oran-ecpri-fronthaul` (O-RAN Split 7.2x eCPRI & BFP9 2.9:1 IQ Compression)
    7. `sync-ptp-synce` (ITU-T G.8275.1 PTP T-BC/T-TC & G.8262 SyncE ESMC)
    8. `g8032-erp-protection` (ITU-T G.8032v2 Ethernet Ring Protection & 1+1 HSB/SD)
    9. `macsec-8021ae-crypto` (IEEE 802.1AE MACsec AES-GCM-128/256 & FIPS 203 ML-KEM-768 PQC)
    10. `l2-carrier-ethernet-mef` (MEF 3.0 E-Line/E-LAN/E-Tree, QinQ 802.1ad)
    11. `l3-mpls-sr-routing` (OSPFv2, BGP-4, MPLS-TP & SR-MPLS TI-LFA)
    12. `oam-cfm-twamp-telemetry` (IEEE 802.1ag CFM, ITU-T Y.1731, RFC 5357 TWAMP & gNMI Telemetry)

### 3.3 Layer 3: `ns3_ceragon/contrib/ceragon` & `tfs-ns3-digital-twin`
Located locally in [`c:\CER_Intent\ns3_ceragon\contrib\ceragon`](file:///c:/CER_Intent/ns3_ceragon/contrib/ceragon) and compiled remotely on `efid@cersrv-029:/home/efid/ns3-dev/contrib/ceragon`:
- **C++20 Source Modules (`model/`)**:
  - `ceragon-device-catalog.{h,cc}` — 36 hardware profiles in C++.
  - `ceragon-channel.{h,cc}` — ITU-R P.530 multipath, ITU-R P.838 rain attenuation, ITU-R P.676 60 GHz $O_2$ absorption, 32-element phased-array beamforming gain, XPIC cross-pol cancellation.
  - `ceragon-acm-engine.{h,cc}` — Hitless 28-profile ACM state machine (BPSK to 4096-QAM) + ATPC closed loop.
  - `ceragon-net-device.{h,cc}` — `CeragonNetDevice` (`ns3::NetDevice` subclass) with L1 header compression, O-RAN eCPRI BFP9 compression, IEEE 802.1AE MACsec AES-GCM-256, and ITU-T G.8275.1 PTP hardware timestamping.
  - `ceragon-multiband-net-device.{h,cc}` — L1 sub-frame bonding across E-Band (80 GHz) + Microwave (18/23 GHz).
  - `ceragon-qos-tsn.{h,cc}` — `CeragonTsnQueueDisc` (`ns3::QueueDisc` subclass) implementing 8-CoS H-QoS, WRED, IEEE 802.1Qbv TAS Gate Control Lists, and 802.1Qbu frame preemption.
  - `ceragon-terragraph-mac.{h,cc}` — 60 GHz IEEE 802.11ay / Terragraph TDD 250 µs slot scheduler & 64-beam sector scan.
  - `ceragon-protection-mgr.{h,cc}` — 1+1 HSB (`<15 ms`) and ITU-T G.8032v2 ERP (`<50 ms`) ring protection.
  - `ceragon-telemetry-exporter.{h,cc}` & `ceragon-tfs-agent.{h,cc}` — JSON/gNMI telemetry export & live TFS config ingestion.
- **Exact CLI Invocations for the 5 Compiled C++20 Binaries on `efid@cersrv-029`**:
  ```bash
  # 1. 36-Model Portfolio Sweep (completes in ~750ms)
  /home/efid/ns3-dev/build/contrib/ceragon/examples/ns3.45-ceragon-portfolio-showcase-default

  # 2. Multi-Band 80GHz + 18GHz Rain Storm Failover (completes in ~2.7s)
  # NOTE: Use --offered=80Mbps (NOT --trafficMbps)
  /home/efid/ns3-dev/build/contrib/ceragon/examples/ns3.45-ceragon-multiband-rain-default --offered=80Mbps --simTime=4

  # 3. IEEE 802.1Qbv TSN + 802.1Qbu + eCPRI BFP9 Fronthaul (completes in ~1.5s)
  # NOTE: Keep --simTime=0.4 --beLoad=120Mbps so packet trace completes under 2s
  /home/efid/ns3-dev/build/contrib/ceragon/examples/ns3.45-ceragon-tsn-fronthaul-default --mode=fifo --simTime=0.4 --beLoad=120Mbps

  # 4. 60 GHz Terragraph 6-Node Mesh & Beam Re-Steering (completes in ~11.5s)
  /home/efid/ns3-dev/build/contrib/ceragon/examples/ns3.45-ceragon-terragraph-mesh-default --simTime=4

  # 5. ITU-T G.8032v2 Ring + 1+1 HSB Sub-50ms Protection (completes in ~12s)
  /home/efid/ns3-dev/build/contrib/ceragon/examples/ns3.45-ceragon-ring-protection-default --simTime=3
  ```

---

## 4. Dashboard Architecture (`c:\CER_Intent\dashboard\`)

| URL | File | Purpose & Key Visual Features |
| :--- | :--- | :--- |
| `http://localhost:5000/` or `http://localhost:5000/flow.html` | [`dashboard/flow.html`](file:///c:/CER_Intent/dashboard/flow.html) | **Primary 5-Stage Live Execution Studio (Bento Grid)**:<br>• Top 8-Scenario selector bar + TMF921 natural-language prompt bar.<br>• Always-visible 5-Stage Pipeline Matrix with 15 real-time sub-steps (`1a..5c`).<br>• Interactive 3-Phase Simulation Switcher (`[1. BEFORE (Unmitigated)]`, `[2. INJECTING YANG]`, `[3. AFTER (Mitigated)]`).<br>• Left-Top Retina/HiDPI Scenario Topology Arena (`#canvas-topology`) with paced multi-hop packets (`0.26` cycles/sec), red bottleneck queue bars (`Q:138`) + `✖ TAIL-DROP` animations in `BEFORE`, southbound TFS config beams in `INJECTING`, and green `Q:2` `0%` loss in `AFTER`.<br>• Left-Bottom Retina Scenario Physics Scope (`#canvas-physics`) — un-squished physical/MAC visualizer.<br>• Right DOM Engineering Workbench — crisp HTML cards for NLP tokens, 17-Skill bars, RFC 6020 YANG 1.1 XML, NS-3 Before/After KPIs, C++ packet trace table, and 4-leaf YANG datastore diff. |
| `http://localhost:5000/ceragon-twin.html` | [`dashboard/ceragon-twin.html`](file:///c:/CER_Intent/dashboard/ceragon-twin.html) | **Ceragon 36-Model Portfolio & C++20 NS-3.45 Metro Twin**:<br>• 12-Node Metro Haul Topology (`IP-50FX`, `IP-50EX+50C`, `IP-20C`, `EH-8010FX`, `MH-N366`, `MH-T261`, `IP-100E`).<br>• Interactive `0.0s..11.0s` timeline scrubber + 5 scenario presets (`EX_PORTFOLIO`, `EX_MULTIBAND`, `EX_TSN`, `EX_TERRAGRAPH`, `EX_PROTECTION`).<br>• `⚡ Run Live C++ Binary on cersrv-029` button with 4-step SSH execution banner.<br>• 36-Model Portfolio Filter & 12-Domain Southbound Rule Compiler. |
| `http://localhost:5000/digital_twin.html` | [`dashboard/digital_twin.html`](file:///c:/CER_Intent/dashboard/digital_twin.html) | **Interactive NS-3.45 TSN + WiFi + Ceragon Multi-Hop Lab**:<br>• 6-Hop topology (`STA0/1 -> AP0/1 -> C0 -> C1 -> C2 -> C3 -> SINK`).<br>• Paced hop-by-hop packet replay (~0.75s per hop, ~4.5s end-to-end) across 900 discrete packet events.<br>• Live C0 Queue Histogram, Per-Hop Latency Breakdown, and Ladder Trace. |
| `http://localhost:5000/?view=expert` | [`dashboard/index.html`](file:///c:/CER_Intent/dashboard/index.html) | **4-Tab Expert NOC View**:<br>• Tab 1: Unified 36-Node Network Topology.<br>• Tab 2: Ceragon Portfolio & Live MH-T261 (`ctu-96`) Telemetry.<br>• Tab 3: TeraFlowSDN Controller & 84 YANG Schemas.<br>• Tab 4: Cross-Repo Digital Twin Inspector. |

---

## 5. Technical Gotchas & Lessons Learned (Do Not Regress!)

1. **Eventlet + Subprocess on Windows (`run.py` & `tsn_simulation_runner.py`)**:
   - Never call `eventlet.monkey_patch()` with default arguments in `run.py` — always keep `eventlet.monkey_patch(os=False, subprocess=False)` and use `eventlet.patcher.original("subprocess").run` inside `tsn_simulation_runner.py`. Otherwise, `subprocess.run(["ssh", "efid@cersrv-029", ...])` deadlocks on Windows pipes.
2. **Full-Timeline Packet Trace in `TSNSimulationRunner`**:
   - The C++ binary `ns3.45-tsn_wifi_ceragon-default` only prints stdout packet logs between `t = 0.20s` and `t = 0.40s`. Always allow `build_discrete_packet_trace()` in `cer_intent/tsn_simulation_runner.py` to populate `parsed_metrics["discrete_packet_trace"]` across the full `0.0s..simTime` window while preserving the raw C++ count in `raw_cpp_trace_events`.
3. **Visual Pacing & Step-by-Step Transparency**:
   - The user strongly values seeing **real work happen step-by-step** at a human-readable pace rather than instant/fake transitions.
   - Keep packet speeds around `0.10..0.30` cycles/sec (~1s per hop) and always show the **Unmitigated (`BEFORE`)** congestion/drop state before transitioning through **Candidate YANG Injection (`INJECTING`)** to the **Mitigated (`AFTER`)** state.
4. **No Sub-12px Blurry Canvas Text**:
   - Use HTML/CSS DOM cards (`>=12px` font size) for code blocks, tables, and KPIs, and use `window.devicePixelRatio` (HiDPI scaling) on `<canvas>` elements for network topology and physical-layer scopes.
