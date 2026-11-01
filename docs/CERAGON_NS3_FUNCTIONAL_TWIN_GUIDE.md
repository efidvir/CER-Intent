# Ceragon Functional Digital Twin for NS-3 (`contrib/ceragon`)

This guide documents the native **ns-3.45 C++ contributed module** (`contrib/ceragon`, library `libns3.45-ceragon-default.so`) and its integration with **CER-Intent** and the **TeraFlowSDN Ceragon RESTCONF/YANG Adapter** (`ceragon_tfs_adapter`).

The module implements a packet-level, standards-accurate **Functional Digital Twin** of the entire Ceragon Networks and Siklu-by-Ceragon product portfolio across **all 5 product families (31 explicit hardware models + 5 family fallbacks)** and **all 12 intent/control domains**.

---

## 1. Architecture & Portfolio Parity

The ns-3 `ceragon` module mirrors the exact hardware capability matrix and YANG data models of [`ceragon_tfs_adapter/ceragon_tfs_adapter/portfolio.py`](../ceragon_tfs_adapter/ceragon_tfs_adapter/portfolio.py):

```
┌────────────────────────────────────────────────────────────────────────────┐
│                   CER-Intent / TeraFlowSDN Controller                      │
│   12 Intent Domains · Topologies · What-If Scenarios (Rain, Cuts, TSN)     │
└───────────────────┬────────────────────────────────────┬───────────────────┘
                    │ Southbound RESTCONF/YANG           │ Digital Twin Bridge
                    ▼                                    ▼
┌───────────────────────────────────────┐  ┌─────────────────────────────────┐
│     Physical / Lab Hardware           │  │  NS-3.45 contrib/ceragon Module │
│  ceragon_tfs_adapter (84 YANG files)  │  │  36 Portfolio Entries (C++20)   │
│  MH-T261 (192.168.1.225), IP-50, ...  │  │  ITU-R P.525/676/838/530 PHY    │
└───────────────────────────────────────┘  │  Hitless ACM · XPIC · MultiBand │
                                           │  1+1 HSB/SD · 60 GHz Beamforming│
                                           │  8-CoS SP+DRR · 802.1Qbv/Qbu TSN│
                                           │  MACsec · PTP/SyncE · O-RAN 7.2x│
                                           └─────────────────────────────────┘
```

### 1.1 Supported Product Portfolio (`model/ceragon-portfolio.{h,cc}`)

Every device instantiated in ns-3 resolves a `CeragonSpec` record via `CeragonPortfolio::Get(model)` (with case-insensitive lookup, prefix matching, and family fallback):

| Family (`CeragonFamily`) | API Flavor (`CeragonFlavor`) | Explicit Hardware Models (31) + Family Fallbacks (5) | Frequency Bands (GHz) | Max Channel (MHz) | Max Capacity (Gbps) | Max Modulation | Max Carriers |
|---|---|---|---|---|---|---|---|
| **FibeAir IP-20** (`FAMILY_IP20`) | `FLAVOR_CERAOS` | `IP-20C`, `IP-20C-HP`, `IP-20S`, `IP-20E`, `IP-20V`, `IP-20N`, `IP-20A`, `IP-20A-LH`, `IP-20G`, `IP-20GX`, fallback `IP-20` | 6–42 GHz MW (`18 GHz` default); `71–86 GHz` (`IP-20E`); `57–66 GHz` (`IP-20V`) | `112`–`500` | `0.65`–`4.0` | `2048QAM` / `4096QAM` (`IP-20C-HP`, `IP-20N`, `IP-20A`, `IP-20A-LH`) | `1`–`10` |
| **FibeAir IP-50** (`FAMILY_IP50`) | `FLAVOR_CERAOS` | `IP-50C`, `IP-50CX`, `IP-50E`, `IP-50EX`, `IP-50EXA`, `IP-50FX`, fallback `IP-50` | 6–42 GHz (`IP-50C/CX/FX`); 71–86 GHz (`IP-50E/EX/EXA`) | `224`–`2000` | `4.0`–`40.0` | `1024QAM` (`IP-50E`) / `4096QAM` | `1`–`16` |
| **IP-100** (`FAMILY_IP100`) | `FLAVOR_CERAOS` | `IP-100E`, fallback `IP-100` | 71–86 GHz Dual-Carrier E-Band | `2000` | `25.0` | `4096QAM` | `2` |
| **Siklu EtherHaul** (`FAMILY_ETHERHAUL`) | `FLAVOR_SIKLU_EH` | `EH-614TX`, `EH-710TX`, `EH-1200TX`, `EH-1200FX`, `EH-2500FX`, `EH-8010FX`, `EH-8020FX`, fallback `EtherHaul` | 57–66 GHz (`EH-614TX`); 71–86 GHz (`EH-7xx/1200/2500/8010/8020`) | `500`–`2000` | `0.7`–`20.0` | `64QAM`–`512QAM` | `1` |
| **MultiHaul TG** (`FAMILY_MULTIHAUL_TG`) | `FLAVOR_SIKLU_TG` | `MH-T261` (`api_verified=true`), `MH-T260`, `MH-T265`, `MH-T280`, `MH-N265`, `MH-N366`, `MH-N367`, fallback `MultiHaul TG` | 57–66 / 57–71 GHz (IEEE 802.11ad/ay Terragraph) | `2160` | `1.0`–`16.0` | `MCS9 (16QAM)` / `MCS12 (64QAM)` | `1`–`4` sectors |

### 1.2 Hardware Feature-Bit Gating (`CeragonFeature`)

Just like `DeviceCapabilities.supports()` in the Python adapter, `CeragonRadioNetDevice` enforces hardware capability checks against the resolved `CeragonSpec::features` bitmask before enabling domain features:

| Feature Flag | Value | YANG Module Equivalent | Functional Twin Behavior |
|---|---|---|---|
| `F_RADIO` | `1 << 0` | `ceragon-radio` / `radio-bridge-eh-radio` / `radio-bridge-tg-radio-common` | Frequency, bandwidth, TX power, ATPC, hitless ACM |
| `F_QOS` | `1 << 1` | `ceragon-qos` / `ieee802-dot1q-sched` | 8-CoS SP+DRR scheduler, IEEE 802.1Qbv GCL, IEEE 802.1Qbu preemption |
| `F_SLICE` | `1 << 2` | `ceragon-slice` / `ietf-interfaces` (`user-bridge`) | Per-slice PIR token-bucket shaping & VLAN tag admission |
| `F_PROTECTION` | `1 << 3` | `ceragon-protection` / `radio-bridge-tg-interfaces` (`active-backup`) | 1+1 HSB, Space Diversity (SD), or Terragraph `active-backup` bonding |
| `F_BEAMFORMING` | `1 << 4` | `radio-bridge-tg-radio-dn` / `radio-bridge-tg-actions` | 60 GHz phased-array beam index (`0..64`), pole sway loss, `start-topo-scan` RPC |
| `F_MULTIBAND` | `1 << 5` | `ceragon-multiband` | L1 Multi-Band carrier bonding (E-Band + Microwave anchor) with aperture scaling |
| `F_SYNC` | `1 << 6` | `ceragon-sync` / `ietf-ptp` / `radio-bridge-tg-gps` | IEEE 1588v2 PTP + SyncE cTE/dTE/holdover time-error modeling |
| `F_MACSEC` | `1 << 7` | `ceragon-macsec` / `ieee802-dot1ae-macsec` | Line-rate AES-128/256-GCM SecTAG + ICV byte overhead (24 B / 32 B) |
| `F_ENERGY` | `1 << 8` | `ceragon-energy` | Green-ATPC TX power reduction & low-load secondary carrier sleep |
| `F_ORAN_XHAUL` | `1 << 9` | `ceragon-oran-xhaul` | O-RAN Split 7.2x eCPRI BFP9/12/14 IQ compression & delay-window check |
| `F_XPIC` | `1 << 10` | `ceragon-radio` (`xpic-enabled`) | Dual-polarization V+H cross-polar interference cancellation (up to 28 dB) |

Attempted configurations on unsupported hardware (e.g., enabling MACsec on `MH-T261`, Space Diversity on `IP-20C`, or Multi-Band on `EH-8010FX`) return `false` without mutating device state.

---

## 2. Source Code Layout

All module files reside in [`ns3_ceragon/contrib/ceragon/`](../ns3_ceragon/contrib/ceragon) and are installed into `/home/efid/ns3-dev/contrib/ceragon`:

```
ns3_ceragon/
├── deploy_to_ns3.sh                             # Automated installer & builder for ns-3.45
├── tools/
│   └── tfs_to_ceragon_twin.py                   # CER-Intent / TeraFlowSDN JSON -> .twin converter
└── contrib/ceragon/
    ├── CMakeLists.txt                           # ns-3 module definition (libns3.45-ceragon)
    ├── README.md                                # Module quick-reference
    ├── doc/
    │   └── ceragon.rst                          # Sphinx documentation for ns-3 manual
    ├── model/
    │   ├── ceragon-portfolio.{h,cc}             # 36-entry product catalog & feature flags
    │   ├── ceragon-acm.{h,cc}                   # CeraOS MRMC & 802.11ad MCS hitless ACM engine
    │   ├── ceragon-propagation.{h,cc}           # ITU-R P.525, P.676, P.838-3, P.530-17 & weather
    │   ├── ceragon-radio-header.{h,cc}          # On-air frame header (CoS, Slice, Carrier, MCS)
    │   ├── ceragon-radio-channel.{h,cc}         # Full-duplex multi-carrier radio link channel
    │   ├── ceragon-radio-net-device.{h,cc}      # Complete Ceragon/Siklu NetDevice digital twin
    │   ├── ceragon-qos-queue-disc.{h,cc}        # 8-CoS SP+DRR + Slice PIR + 802.1Qbv/Qbu QueueDisc
    │   └── ceragon-oran-xhaul.{h,cc}            # O-RAN Split 7.2x eCPRI calculator & burst source
    ├── helper/
    │   ├── ceragon-helper.{h,cc}                # Point-to-point & sector link installer + QoS binder
    │   └── ceragon-twin-helper.{h,cc}           # Declarative .twin parser, event scheduler & JSON exporter
    ├── test/
    │   └── ceragon-test-suite.cc                # 11 C++ unit & system tests
    └── examples/
        ├── CMakeLists.txt
        ├── ceragon-portfolio-twin.cc            # Sweeps all 36 portfolio entries vs rain rates
        ├── ceragon-multiband-rain.cc            # IP-50EX E-band + 18 GHz MW cloudburst survival
        ├── ceragon-tsn-fronthaul.cc             # IP-50FX O-RAN Split 7.2x with IEEE 802.1Qbv GCL
        ├── ceragon-terragraph-mesh.cc           # MH-N366 DN + MH-T261 CN 60 GHz sway & topo-scan
        ├── ceragon-protection-switchover.cc     # 1+1 HSB, Space Diversity & TG active-backup
        ├── ceragon-twin-from-file.cc            # Generic .twin topology runner (installed in scratch/)
        └── topologies/
            └── metro-ring.twin                  # Sample 7-node multi-family metro + access topology
```

---

## 3. Physical, Link, and Transport Layer Models

### 3.1 ITU-R Millimeter-Wave & Microwave Propagation (`model/ceragon-propagation.{h,cc}`)

For each carrier $i$ operating at center frequency $f_i$ (GHz) over path distance $d$ (km), `CeragonLinkBudget::Evaluate` computes the instantaneous link budget:

1. **Free-Space Path Loss (ITU-R P.525-4)**:
   $$\text{FSPL}(f_i, d) = 92.45 + 20 \log_{10}(f_i\text{ [GHz]}) + 20 \log_{10}(d\text{ [km]}) \quad [\text{dB}]$$

2. **Specific Gaseous Attenuation (ITU-R P.676-13)**:
   Models dry-air oxygen ($O_2$) absorption — including the Lorentzian resonance complex at **57–64 GHz** ($\sim 14.8\text{ dB/km}$ at 60.5 GHz) and the 118.75 GHz line — plus water-vapor ($H_2O$) absorption at **22.235 GHz** and the **71–86 GHz E-band continuum** ($\sim 0.35\text{–}0.48\text{ dB/km}$).

3. **Rain Attenuation & Path Reduction Factor (ITU-R P.838-3 & P.530-17)**:
   Given instantaneous rain rate $R$ (mm/h) from `CeragonWeatherModel`:
   $$\gamma_R = k(f_i, \text{pol}) \cdot R^{\alpha(f_i, \text{pol})} \quad [\text{dB/km}], \qquad A_{\text{rain}} = \gamma_R \cdot d \cdot r(d, f_i, R) \quad [\text{dB}]$$
   where $k, \alpha$ are log-interpolated from ITU-R P.838-3 horizontal/vertical tables from 4 GHz to 100 GHz and $r(d, f_i, R)$ is the ITU-R P.530-17 effective path reduction factor.

4. **Rain-Induced Depolarization & XPIC (`CeragonLinkBudget`)**:
   Rain canting degrades Cross-Polarization Discrimination (XPD) according to ITU-R P.530-17:
   $$\text{XPD}_{\text{rain}} = U_0(f_i) - V(f_i) \log_{10}(A_{\text{rain}})$$
   When `XPIC` is enabled on a dual-polarized (`2+0`) carrier, the cross-polar canceller suppresses cross-pol leakage by `XpicSuppressionDb` (default `28 dB`) up to the hardware's minimum operational XPD threshold.

5. **Multi-Band Shared-Aperture Gain Scaling (`CeragonRadioChannel`)**:
   On Multi-Band links (`IP-50EX` / `IP-50EXA`), carrier 0 (E-band, e.g. 73.5 GHz) and carrier 1 (Microwave anchor, e.g. 18 GHz) share a dual-band parabolic dish. The secondary carrier's antenna gain at each end is scaled by $20 \log_{10}(f_i / f_0)$ so the 18 GHz carrier reflects its true physical aperture gain.

### 3.2 Hitless Adaptive Coding & Modulation (`model/ceragon-acm.{h,cc}`)

`CeragonAcmEngine` maintains two complete ACM profile tables:
- **CeraOS MRMC Table (`GetCeraOsTable`)**: 12 profiles from `BPSK` (`0.65 bps/Hz`, required $\text{SINR} = 4.5\text{ dB}$) through `4096QAM` (`9.90 bps/Hz`, required $\text{SINR} = 39.5\text{ dB}$).
- **Siklu 802.11ad/ay DMG Table (`GetSikluTgTable`)**: 12 MCS indices (`MCS1` BPSK $1/2$ at $385\text{ Mbps}$ up to `MCS12` 64QAM $3/4$ at $4620\text{ Mbps}$ on a $2160\text{ MHz}$ channel).

To prevent ping-pong oscillation during rain fades, **down-shifts are immediate** when $\text{SINR} < \text{SINR}_{\text{req}}(m) - \Delta_{\text{down}}$, whereas **up-shifts require** $\text{SINR} \ge \text{SINR}_{\text{req}}(m+1) + \Delta_{\text{up}}$, clamped to `[minModulation, maxModulation]` and the hardware's `maxModulation` ceiling. Post-LDPC/Reed-Solomon residual BER is computed via `EstimateBer(sinrDb, profile)` and converted into packet corruption probability over frame length.

### 3.3 60 GHz Beamforming, Pole Sway & Topology Scan (`CeragonRadioNetDevice`)

For `MultiHaul TG` nodes (`F_BEAMFORMING`):
- **Wind-Induced Pole Sway**: Wind velocity from `CeragonWeatherModel` induces angular deflection $\theta_{\text{sway}}(t)$ against the narrow $\sim 2.5^\circ$ 60 GHz beamwidth. When auto-beamtracking (`m_beamAutoTrack`) is active, the phased array compensates up to $80\%$ of sway misalignment; when locked to a manual beam override (`SetBeamIndex(idx, true)`), misalignment produces parabolic main-lobe roll-off loss.
- **`RunTopoScan()` RPC**: Emulates `/ radio-bridge-tg-actions:start-topo-scan`, sweeping all 65 codebook beams (`0..64`), selecting the highest-SNR beam index, and returning a structured JSON report.

### 3.4 1+1 HSB, Space Diversity & Terragraph Active-Backup (`CeragonRadioChannel`)

`SetProtection(mode, DiversitySpacingMeters)` models three resilience schemes (`F_PROTECTION`):
- **`PROT_1P1_HSB` (1+1 Hot-Standby)**: Monitors active carrier SINR; triggers hitless or $<50\text{ ms}$ protection switchover (`ProtectionSwitch` trace) upon outage or severe fade, adding a standby receiver margin.
- **`PROT_SPACE_DIVERSITY` (1+1 Space Diversity)**: Models vertically separated main and diversity antennas (`DiversitySpacingMeters`), mitigating multipath/selective fading according to the diversity improvement factor. Requires models with `F_PROTECTION` excluding compact `IP-20C`/`IP-20S`/`IP-20E`/`IP-20V` (matching the CER-Intent Smart Reconciliation Engine rule).
- **`PROT_TG_ACTIVE_BACKUP`**: Models Terragraph Layer-2 `active-backup` bonding across DN/CN sectors.

### 3.5 8-CoS SP+DRR Scheduler, Slice Shapers & IEEE 802.1Qbv / 802.1Qbu (`model/ceragon-qos-queue-disc.{h,cc}`)

`CeragonQosQueueDisc` (subclass of `ns3::QueueDisc`) implements the full CeraOS / IEEE 802.1Q queuing pipeline:
1. **Classification**: Reads CoS (`0..7`) and Slice ID from `CeragonFrameTag` or maps IP DSCP/TOS (`EF`/`46` $\rightarrow$ CoS 7, `CS6` $\rightarrow$ CoS 6, `AF4x` $\rightarrow$ CoS 5, etc.).
2. **Per-Slice PIR Token Bucket (`F_SLICE`)**: Enforces configured slice bandwidth percentage (`SetSliceWeight(sliceId, vlanId, bwPct, priority)`).
3. **IEEE 802.1Qbv Time-Aware Shaper (TAS)**: Cycles through a programmable Gate Control List (`AddGclEntry(gateMask, durationNs)`). At simulation time $t$, the active entry is determined by $(t \bmod T_{\text{cycle}})$ and only CoS queues whose bit in `gateMask` is `1` are eligible for transmission.
4. **Strict Priority + Deficit Round-Robin (SP+DRR)**: CoS 7 and CoS 6 are served with Strict Priority (for O-RAN eCPRI / PTP / URLLC); CoS `0..5` are served via Deficit Round-Robin according to configured quantum weights.
5. **IEEE 802.1Qbu Frame Preemption**: When enabled (`EnableFramePreemption(true)`), express CoS 7 frames preempt lower-priority frames with only a single 64-byte fragment overhead.

### 3.6 IEEE 1588v2 PTP & SyncE Timing Model (`CeragonRadioNetDevice`)

When `EnableSync(ptpEnabled, synceEnabled, profile)` is configured (`F_SYNC`), `SampleState` tracks cumulative and dynamic time error (`m_timeErrorNs`):
- **Locked Mode (Link Up + SyncE physical frequency lock)**: Bounded dynamic time error $\pm 6\text{ ns}$ (`ITU-T G.8275.1 Class C` T-BC).
- **Packet-Only PTP (without SyncE)**: PDV-induced time error proportional to link load.
- **Holdover Mode (Link Outage)**: Quadratic oscillator phase drift ($+3.5\text{ ns}$ per sample interval) until lock is restored.

### 3.7 O-RAN Split 7.2x Fronthaul Dimensioning (`model/ceragon-oran-xhaul.{h,cc}`)

`CeragonOranXhaul::ComputeRequiredGbps` calculates exact Split 7.2x eCPRI line rate from carrier bandwidth, MIMO layers, numerology $\mu$, and IQ compression format:
- **Uncompressed (16-bit I + 16-bit Q)**: $\sim 9.83\text{ Gbps}$ for 100 MHz, 4T4R.
- **BFP-14bit**: $\sim 6.84\text{ Gbps}$.
- **BFP-12bit**: $\sim 5.90\text{ Gbps}$.
- **BFP-9bit**: $\sim 4.42\text{ Gbps}$ (fits within a single 10 Gbps E-Band or IP-50FX link with `< 100 us` one-way latency budget).

---

## 4. Declarative `.twin` Topology Format

`CeragonTwinHelper` reads declarative `.twin` specifications (whitespace-tokenized, `#` comments) and constructs the full ns-3 simulation:

```text
# Nodes: node <id> <model> <x_m> <y_m> <z_m>
node node-A  IP-50FX  0     0     30
node node-B  IP-50EX  1800  0     35

# Links: link <id> <nodeA> <nodeB> <model> [freq=GHz] [bw=MHz] [txp=dBm] [gain=dBi]
#        [xpic=0|1] [multiband=0|1] [mb_freq=GHz] [mb_bw=MHz] [prot=none|1+1-hsb|space-diversity|active-backup]
#        [macsec=0|128|256] [atpc=0|1] [energy=0|1] [sync=0|1] [tas_cycle_ns=N] [preempt=0|1]
link link-A-B node-A node-B IP-50EX freq=73.5 bw=1000 txp=18 gain=44 multiband=1 mb_freq=18.0 mb_bw=112 prot=1+1-hsb tas_cycle_ns=500000 preempt=1

# Weather cells: rain <start_s> <end_s> <rain_mm_hr> [wind_mps] [interferer_dbm]
rain 1.0 3.0 80.0 14.0 -90.0

# Scheduled faults: fault <time_s> <linkId> <cut|restore>
fault 2.0 link-A-B cut
fault 2.5 link-A-B restore

# Traffic flows: flow <srcNode> <dstNode> <rate_mbps> <pkt_bytes> <cos:0..7> <start_s> <end_s>
flow node-A node-B 850.0 1200 7 0.2 3.8
```

### Converting CER-Intent or TeraFlowSDN Topologies to `.twin`

Use [`ns3_ceragon/tools/tfs_to_ceragon_twin.py`](../ns3_ceragon/tools/tfs_to_ceragon_twin.py) to convert `cer_intent/device/registry.py` or a TeraFlowSDN context export directly into `.twin`:

```bash
python ns3_ceragon/tools/tfs_to_ceragon_twin.py --from-cer-intent -o cer_topology.twin
```

---

## 5. Building, Running Examples & Validation Suite

### 5.1 One-Step Installation into NS-3.45

On the ns-3 host (`efid@cersrv-029`):

```bash
export TMPDIR=$HOME/.ceragon_tmp
/home/efid/ns3_ceragon/deploy_to_ns3.sh /home/efid/ns3-dev
```

This builds:
- Shared module library: `/home/efid/ns3-dev/build/lib/libns3.45-ceragon-default.so`
- Generic `.twin` executable: `/home/efid/ns3-dev/build/scratch/ns3.45-ceragon-twin-default`

### 5.2 C++ Unit & System Test Suite (`test/ceragon-test-suite.cc`)

Run all 11 test cases:

```bash
./ns3 run --no-build "test-runner --suite=ceragon --verbose"
```

| # | TestCase Name | What It Verifies | Status |
|---|---|---|---|
| 1 | `Portfolio completeness (36 entries, MH-T261 api_verified)` | All 31 explicit models + 5 family fallbacks resolve; `MH-T261` has `api_verified=true`; feature bitmasks match Python adapter | **PASS** |
| 2 | `ITU-R P.525, P.676, P.838, P.530 propagation sanity` | 60 GHz $O_2$ absorption peak ($>12\text{ dB/km}$ vs $<1\text{ dB/km}$ at 73.5 GHz), rain attenuation scaling, XPD degradation | **PASS** |
| 3 | `Hitless ACM state machine with hysteresis` | CeraOS (`BPSK`..`4096QAM`) & Siklu (`MCS1`..`MCS12`) transitions, hysteresis deadband, hardware ceiling clamping | **PASS** |
| 4 | `Multi-band E-band + Microwave rain failover` | `IP-50EX` bonds 80 GHz + 18 GHz in clear sky ($>7\text{ Gbps}$) and survives $120\text{ mm/h}$ rain via 18 GHz anchor ($>500\text{ Mbps}$) | **PASS** |
| 5 | `XPIC 2x capacity and rain XPD degradation` | `IP-20C` XPIC doubles clear-sky capacity (`2+0` V+H) and models cross-pol leakage under heavy rain | **PASS** |
| 6 | `1+1 HSB protection and Space Diversity hardware gating` | `IP-20C` rejects Space Diversity (`F_PROTECTION` hardware rule) while accepting `1+1 HSB`; `IP-20N` accepts SD and gains SNR margin | **PASS** |
| 7 | `60 GHz beamforming, pole sway and start-topo-scan RPC` | `MH-T261` beam override misalignment loss, `RunTopoScan()` optimal beam discovery (`beamIdx=32`), MACsec rejection | **PASS** |
| 8 | `8-CoS SP+DRR, slice shaper and IEEE 802.1Qbv GCL` | CoS 7 preempts/prioritizes over CoS 0 under congestion; 802.1Qbv GCL gates closed queues | **PASS** |
| 9 | `MACsec overhead, Green-ATPC carrier sleep and PTP/SyncE` | AES-256-GCM reduces net payload rate; Green-ATPC puts secondary carriers to sleep at low load; PTP holdover drift on outage | **PASS** |
| 10 | `O-RAN Split 7.2x BFP9 compression admissibility` | Uncompressed 100 MHz 4T4R ($\sim 9.8\text{ Gbps}$) exceeds 6 Gbps link; BFP9 ($\sim 4.4\text{ Gbps}$) passes admissibility check | **PASS** |
| 11 | `Declarative .twin end-to-end simulation with rain & cut` | Multi-node `.twin` topology runs with rain fade, fiber/radio cut, and JSON telemetry export | **PASS** |

### 5.3 Example Scenarios (`contrib/ceragon/examples/`)

1. **`ceragon-portfolio-twin`**: Instantiates every model in the Ceragon/Siklu catalog and sweeps rain rates ($0, 25, 80\text{ mm/h}$).
2. **`ceragon-multiband-rain`**: Simulates an `IP-50EX` Multi-Band link through a $100\text{ mm/h}$ cloudburst, contrasting E-band-only outage against hitless 18 GHz microwave anchor retention (`99.71%` packet delivery, `0.00 s` outage).
3. **`ceragon-tsn-fronthaul`**: Simulates O-RAN Split 7.2x eCPRI (CoS 7) competing with best-effort eMBB saturation on an `IP-50FX`; enabling IEEE 802.1Qbv + 802.1Qbu reduces fronthaul mean delay from **1473.8 us** to **72.0 us** (`< 100 us` O-RAN budget).
4. **`ceragon-terragraph-mesh`**: Simulates a 60 GHz Terragraph sector (`MH-N366` DN + 3 `MH-T261` CNs) with $18\text{ m/s}$ wind gusts and executes `start-topo-scan`.
5. **`ceragon-protection-switchover`**: Compares unprotected, `1+1 HSB`, `Space Diversity`, and Terragraph `active-backup` links across a $95\text{ mm/h}$ fade.
6. **`ceragon-twin-from-file`**: Runs any `.twin` file with CLI overrides (`--rain=start,end,mmhr`, `--cut=time,linkId`, `--restore=time,linkId`, `--override=linkId,key,val`, `--jsonOut=path`).

---

## 6. CER-Intent Digital Twin REST API Integration

CER-Intent exposes the ns-3 Ceragon Functional Twin through [`cer_intent/ceragon_ns3_twin_runner.py`](../cer_intent/ceragon_ns3_twin_runner.py) and [`cer_intent/api/digital_twin_routes.py`](../cer_intent/api/digital_twin_routes.py):

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/digital-twin/ceragon/portfolio` | Queries the compiled ns-3 `contrib/ceragon` binary (`--listPortfolio`) and returns all 36 hardware models and capabilities |
| `GET` | `/api/v1/digital-twin/ceragon/topology` | Exports the active CER-Intent / TeraFlowSDN topology in `.twin` format |
| `POST` | `/api/v1/digital-twin/ceragon/run` | Executes a live ns-3.45 functional twin simulation with optional rain cells, link cuts/restores, and link parameter overrides |

### Example `POST /api/v1/digital-twin/ceragon/run` Request

```bash
curl -X POST http://localhost:5000/api/v1/digital-twin/ceragon/run \
  -H "Content-Type: application/json" \
  -d '{
    "sim_time": 4.0,
    "rain": [[1.0, 2.5, 80.0]],
    "cuts": [[1.5, "link-A-B"]],
    "restores": [[2.2, "link-A-B"]],
    "overrides": [["link-D-E", "xpic", "1"]]
  }'
```

The response returns per-link time-series telemetry (`rslDbm`, `sinrDb`, `modulation`, `capacityMbps`, `activeCarriers`, `powerWatts`, `timeErrorNs`, `availPct`, `rxFrames`, `txDrops`), per-flow end-to-end throughput/latency/jitter/loss metrics, and the `.twin` specification used for the run.
