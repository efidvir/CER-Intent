# Ceragon TeraFlowSDN (TFS) Device Adapter

A standalone, packable REST / RESTCONF adapter that connects the Ceragon wireless transport portfolio to ETSI TeraFlowSDN (TFS). It covers FibeAir IP-20, IP-50 and IP-100 (CeraOS), plus Siklu EtherHaul and MultiHaul TG. See [Supported Portfolio](#supported-portfolio).

---

## Features

- **Automated RESTCONF Discovery**: Probes physical Ceragon hardware, auto-negotiating datastore paths (`/restconf/ds/ietf-datastores:candidate` or `/restconf/data`).
- **TeraFlowSDN Source-of-Truth Sync**: Registers hardware inventory, network interfaces (`eth1`), radio sectors (60GHz mmWave), frequencies, and operational statuses into TFS Context and Topology.
- **Bi-Directional Intent Execution**: Translates TFS configuration rules into Ceragon RESTCONF candidate mutations and commits.
- **Packable & Distributable**: Standard Python package with `pyproject.toml`, `setup.py`, and CLI command `ceragon-tfs-adapter`.

---

## Installation

### From Source (Editable Mode)
```bash
cd c:\CER_Intent\ceragon_tfs_adapter
pip install -e .
```

### Build Wheel (.whl)
```bash
cd c:\CER_Intent\ceragon_tfs_adapter
pip install build
python -m build
# Produces dist/ceragon_tfs_adapter-1.0.0-py3-none-any.whl
```

---

## CLI Usage

### 1. Discover Connected Hardware
```bash
ceragon-tfs-adapter discover --ip 192.168.1.225
```

### 2. Synchronize to TeraFlowSDN
```bash
ceragon-tfs-adapter sync --ip 192.168.1.225 --tfs-url http://localhost:8088
```

### 3. Run Continuous Daemon
```bash
ceragon-tfs-adapter daemon --interval 15
```

### 4. Check Status
```bash
ceragon-tfs-adapter status
```

### 5. Validate & Inspect Bundled YANG Schemas
```bash
ceragon-tfs-adapter schemas validate
ceragon-tfs-adapter schemas list --family ceraos
ceragon-tfs-adapter schemas show ceragon-radio-link
```

### 6. Stream Real-Time Telemetry & Events
```bash
ceragon-tfs-adapter stream --ip 192.168.1.225 --interval 2 --samples 5
```

### 7. Execute Bidirectional Southbound Control
```bash
ceragon-tfs-adapter control --ip 192.168.1.225 --model MH-T261 \
  --key "/interface[name=MH-T261]/slice" \
  --value '{"vlan_id": 150, "slice_name": "urllc-slice", "bandwidth_mbps": 1000}'
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CERAGON_IP` | `192.168.1.225` | Ceragon device management IP |
| `CERAGON_PORT` | `80` | Ceragon management port |
| `CERAGON_USER` | `admin` | RESTCONF username |
| `CERAGON_PASSWORD` | `admin` | RESTCONF password |
| `TERAFLOW_URL` | `http://localhost:8088` | TeraFlowSDN NBI base URL |
| `TFS_CONTEXT` | `admin` | TFS Context name |
| `TFS_TOPOLOGY` | `admin` | TFS Topology name |
| `ADAPTER_SYNC_INTERVAL_SEC` | `15` | Periodic sync interval |
| `CERAGON_MODEL` | *(none)* | Product hint (e.g. `IP-50C`, `EH-8010FX`, `MH-N366`) used to pick the API flavor before probing |
| `CERAGON_DEVICE_MAP` | `{}` | *(cer_intent)* Map device IDs to physical radios: `{"node-A": {"ip": "10.0.0.5", "model": "IP-50FX"}}` |

---

## Supported Portfolio

`ceragon_tfs_adapter/portfolio.py` is the catalog for every supported product. Run
`ceragon-tfs-adapter portfolio list` to print it, or `ceragon-tfs-adapter portfolio resolve "FibeAir IP20C"` to see how a string resolves.

| Family | Models | Southbound API flavor |
|---|---|---|
| FibeAir IP-20 | IP-20C, IP-20C-HP, IP-20S, IP-20E, IP-20V, IP-20N, IP-20A, IP-20A-LH (Evolution LH), IP-20G, IP-20GX | `ceraos` (RESTCONF `/restconf/data`) |
| IP-50 | IP-50C, IP-50CX, IP-50E, IP-50EX, IP-50EXA, IP-50FX | `ceraos` |
| IP-100 | IP-100E | `ceraos` |
| EtherHaul | EH-614TX, EH-710TX, EH-1200TX/FX, EH-2500FX, EH-8010FX, EH-8020FX | `siklu_eh` (radio-bridge RESTCONF) |
| MultiHaul TG | MH-T260, MH-T261, MH-T265, MH-T280, MH-N265, MH-N366, MH-N367 | `siklu_tg` (radio-bridge-tg RESTCONF, candidate DS) |

If a model isn't listed (for example a new variant like `IP-50XYZ` or `EH-9010FX`), it falls back to its **family**
profile, so it still gets the right API flavor and a baseline capability set.

The catalog drives:
- **TFS registration**: `/device/capabilities` (bands, capacity, carriers, XPIC/multiband/beamforming, topology) and the endpoint types per band: `radio-mw`, `radio-mw-lh`, `radio-e-band`, `radio-v-band`.
- **Capability gating**: `SetConfig` rejects config the hardware can't do, such as beamforming on an IP-20C, multiband on an EH-8010FX, XPIC on an IP-20S, or a frequency outside the product's band(s). You get the reason back instead of a silent "ack".

> [!WARNING]
> Only the **MH-T261** southbound API has been tested against real hardware. The other entries come from the public product catalog. Their capacities, bands and feature flags are nominal, so check them against the datasheets. The CeraOS RESTCONF module paths and the EtherHaul paths haven't been tested on real devices yet.

---

## Bundled YANG 1.1 Schema Catalog (85 Modules — 100% Closure)

`ceragon_tfs_adapter/schemas/yang/` bundles **85 YANG 1.1 modules and submodules** with zero missing `import` or `include` dependencies (`validate_schema_closure()`):

- **MultiHaul TG & Clixon/NACM/SNMP (`siklu_tg`, 62 schemas)**: All 51 modules and 11 `ietf-snmp-*` submodules advertised by physical hardware (`radio-bridge-tg-radio-common`, `radio-bridge-tg-radio-dn`, `radio-bridge-tg-user-bridge`, `radio-bridge-tg-bond`, `radio-bridge-tg-tunnel`, `radio-bridge-tg-pm`, `radio-bridge-tg-events`, `radio-bridge-tg-ptp`, `radio-bridge-tg-gps`, `radio-bridge-tg-rollback`, etc.). Also supports live on-device retrieval via RFC 6022 `POST /restconf/operations/ietf-netconf-monitoring:get-schema` and RFC 8525 `/restconf/data/ietf-yang-library:yang-library`.
- **EtherHaul E-Band / V-Band P2P (`siklu_eh`)**: `radio-bridge-eh-radio.yang` plus shared `radio-bridge-tg-*` bridge, bonding, and PM modules.
- **FibeAir IP-20, IP-50 & IP-100 CeraOS (`ceraos`, 10 modules)**: `ceragon-common-types`, `ceragon-radio-link`, `ceragon-qos`, `ceragon-protection`, `ceragon-slice`, `ceragon-multiband`, `ceragon-sync`, `ceragon-macsec`, `ceragon-oran-xhaul`, and `ceragon-pm-telemetry`.
- **Standard IETF / IEEE / IANA Transport Modules (12 modules)**: `ietf-microwave-radio-link` (RFC 8561), `ietf-microwave-types`, `ietf-interfaces` (RFC 8343), `iana-if-type`, `ietf-ip`, `ietf-hardware` (RFC 8348), `iana-hardware`, `ietf-system`, `ietf-ptp` (RFC 8575), `ieee802-dot1q-types`, `ieee802-dot1q-sched` (IEEE 802.1Qbv TAS), and `ieee802-dot1ae-macsec` (IEEE 802.1AE MACsec).

---

## Bidirectional Control & Data Streaming

### Southbound Control (TFS / CER-Intent $\rightarrow$ Adapter $\rightarrow$ Device)
`TFSCeragonDriver.set_config()` and `delete_config()` translate intent rules across **12 transport domains** with portfolio capability gating and 2-phase candidate commit/rollback (`ietf-netconf:commit` / `ietf-netconf:discard-changes`):
1. **Network Slicing & VLANs (`slice` / `vlan`)**: `radio-bridge-tg-user-bridge:user-bridge/bridge={id}` (`c-vlan` / `q-in-q`) & `ceragon-slice:slice-config`
2. **Radio Tuning (`radio` / `operating_parameters`)**: Frequency, channel bandwidth, TX power, ATPC, MRMC script ID, sector admin state
3. **Adaptive Coding & Modulation (`acm`)**: Modulation floor/ceiling (`BPSK` .. `4096-QAM`) and link-distance profiles
4. **Hierarchical QoS (`qos`)**: 8-CoS queue weights, CIR/EIR policers, WRED curves
5. **TSN Scheduled Traffic (`tsn`)**: IEEE 802.1Qbv Time-Aware Shaper Gate Control Lists & 802.1Qbu preemption
6. **60 GHz Beamforming (`beamforming`)**: Phased-array topology scan (`radio-bridge-tg-radio-dn:start-topo-scan`) & Golay/sector steering
7. **Multi-Band Bonding (`multiband`)**: L1 E-Band + Microwave carrier bonding (`ceragon-multiband`), EtherHaul ExtendMM, and TG interface bonding (`radio-bridge-tg-bond`)
8. **Hitless Protection (`protection`)**: 1+1 HSB, 2+0 aggregation, XPIC, Space Diversity, 4x4 LoS MIMO, and manual switchover RPC (`ceragon-protection:trigger-protection-switch`)
9. **Synchronization (`sync`)**: ITU-T G.8275.1/G.8275.2 IEEE 1588v2 PTP, SyncE SSM (`QL-PRC`), and GPS/RF sync
10. **Security (`security`)**: IEEE 802.1AE MACsec (`GCM-AES-256`) and FIPS 140-2 AES-256 radio encryption
11. **O-RAN xHaul (`oran_xhaul`)**: Split 7.2x eCPRI fronthaul IQ compression (`BFP9`) & CTI capacity reporting
12. **Green Energy Policy (`energy`)**: Green ATPC target RSL and secondary carrier sleep

### Northbound & Bidirectional Streaming (Device $\leftrightarrow$ Adapter $\leftrightarrow$ TFS)
- **Live PM & Event RPCs**: Collects real-time interface counters, active RF link KPIs (RSL, TSL, SNR/MSE, MCS/QAM, beam azimuth/elevation), 15-minute/24-hour PM intervals (`radio-bridge-tg-pm:get-pm-items` / `ceragon-pm-telemetry:get-pm-bins`), and hardware event logs (`radio-bridge-tg-events:get-events` / `ceragon-pm-telemetry:get-events`).
- **TFS State Subscriptions**: `subscribe_state()` and `unsubscribe_state()` manage background telemetry streaming threads, ring-buffer history, Socket.IO `ceragon_telemetry_stream` push events, and TFS `/device/pm_telemetry` + `/device/events` updates.
- **CER-Intent REST API Endpoints**:
  - `GET /api/v1/adapter/portfolio` (`?model=...`)
  - `GET /api/v1/adapter/schemas` (`?family=ceraos|siklu_eh|siklu_tg`)
  - `GET /api/v1/adapter/schemas/<module_name>` (`?live=true`)
  - `GET /api/v1/adapter/telemetry` (`?ip=...&model=...&period=quarter`)
  - `POST /api/v1/adapter/control` (`action: set|delete|get`)
  - `POST /api/v1/adapter/subscribe` (`action: subscribe|unsubscribe`)
