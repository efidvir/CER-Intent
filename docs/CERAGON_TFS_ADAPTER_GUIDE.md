# Ceragon TeraFlowSDN (TFS) REST Adapter — Complete Technical Guide

This document provides a comprehensive technical guide to the **Ceragon TeraFlowSDN REST Adapter** (`ceragon-tfs-adapter`). It explains the architecture, hardware matrix, protocol specifications, installation, CLI usage, intent execution, and integration with ETSI TeraFlowSDN (TFS) and CER-Intent.

---

## 1. Architecture Overview

The adapter serves as an autonomous, bi-directional mediator connecting physical Ceragon wireless transport nodes to ETSI TeraFlowSDN:

```
+-------------------------------------------------------------------------------+
|                             CER-Intent System                                 |
|          (Intent Ingestion, Assurance Reconciler, Topology Dashboard)         |
+---------------------------------------+---------------------------------------+
                                        |
                            NBI REST / Socket.IO
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                             ETSI TeraFlowSDN                                  |
|          (Context, Device, Service, Slice, PathComp Microservices)             |
|                 Authoritative Network Source of Truth                         |
+---------------------------------------+---------------------------------------+
                                        |
                          TFS REST NBI (:8088) / gRPC
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                       Ceragon TFS REST Adapter                                |
|  - CeragonRestClient    : Auto-negotiates RESTCONF (Terragraph & CeraOS)     |
|  - CeragonTFSMapper     : Schema translation (Protobuf / JSON <-> YANG)       |
|  - TFSRegistrar         : Registers devices & establishes peer topology links |
|  - TFSCeragonDriver     : Translates TFS intents to REST candidate mutations  |
|  - AdapterService       : Continuous 15s telemetry polling & health sync      |
+---------------------------------------+---------------------------------------+
                                        |
                       RFC 8040 RESTCONF / HTTP(S) Basic Auth
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                      Physical Ceragon Transport Nodes                         |
|   [MultiHaul TG MH-T261]   [IP-50C / IP-50E]   [IP-50FX]   [IP-20C / IP-20N]  |
|     60 GHz mmWave Sector      MRMC Microwave     10G Carrier    1+1 HSB Radio |
+-------------------------------------------------------------------------------+
```

---

## 2. Hardware Compatibility Matrix

The adapter auto-detects the connected device family upon initial handshake:

| Family | Models | Management Interface | Protocol | Key Supported Capabilities |
|---|---|---|---|---|
| **MultiHaul TG / Terragraph** | `MH-T261`, `MH-T280`, `MH-N366` | `http(s)://<ip>:80/443` | RESTCONF RFC 8040 (`candidate` datastore) | 60 GHz V-Band (57-66 GHz), Beamforming (`massive2`), 1 Gbps Ethernet (`eth1`), User Bridges/VLANs, auto TX power. |
| **EtherHaul** | `EH-8010FX`, `EH-2500FX`, `EH-1200TX` | `http(s)://<ip>:80/443` | RESTCONF / CLI | 70/80 GHz E-Band Millimeter Wave, up to 10 Gbps throughput. |
| **CeraOS Multi-Core** | `IP-50C`, `IP-50E`, `IP-20C`, `IP-20N` | `https://<ip>:443` | RESTCONF RFC 8040 (`data` datastore) | Up to 4096 QAM, XPIC (cross-polarization), MRMC scripts, channel spacing up to 112 MHz, 2.5–20 Gbps. |
| **CeraOS Disaggregated** | `IP-50FX` | `https://<ip>:443` | RESTCONF RFC 8040 (`data` datastore) | 10G/25G carrier ethernet interfaces, ultra-low latency Expedited Forwarding queues, hierarchical QoS. |

---

## 3. Physical Network Setup & Addressing

1. **Physical Connection**:
   - Connect the PC/server Ethernet port to the Ceragon unit's management port (`MGT` or `P6`), or an active traffic interface (`eth1`).
2. **IP Addressing**:
   - **MultiHaul TG Default**: `192.168.1.225` (or `192.168.1.1`), Subnet: `255.255.255.0` (`/24`).
   - **CeraOS Default**: `192.168.1.1` (or `192.168.1.10`), Subnet: `255.255.255.0` (`/24`).
   - **Host Setup**: Ensure your host Ethernet adapter has an address in `192.168.1.0/24` (e.g. `192.168.1.200`):
     ```powershell
     # Windows PowerShell (as Admin):
     netsh interface ipv4 add address "Ethernet" 192.168.1.200 255.255.255.0
     ```

---

## 4. Package Installation & Wheel Deployment

The adapter is built as an independent, packable Python component located at `ceragon_tfs_adapter/`.

### Option A: Install from Source (Development / Editable Mode)
```bash
cd ceragon_tfs_adapter
pip install -e .
```

### Option B: Deploy Pre-Built Wheel (.whl)
A pre-built wheel is packaged and stored in `dist/`:
```bash
pip install ceragon_tfs_adapter/dist/ceragon_tfs_adapter-1.0.0-py3-none-any.whl
```

### Option C: Rebuild Wheel
```bash
cd ceragon_tfs_adapter
python setup.py bdist_wheel
```

---

## 5. Command-Line Interface (CLI) Guide

Once installed, the CLI executable `ceragon-tfs-adapter` is available system-wide (or executable via `python -m ceragon_tfs_adapter.cli`).

### 1. Hardware Discovery (`discover`)
Probes the connected device, tests credentials, reads hardware inventory, interfaces, and radio state:
```bash
ceragon-tfs-adapter discover --ip 192.168.1.225
```
**Example Output:**
```
[*] Probing Ceragon device at http://192.168.1.225:80...
[+] Connected to Ceragon (TERRAGRAPH) at http://192.168.1.225:80/restconf/ds/ietf-datastores:candidate (HTTP 200)
[*] Fetching live operational state...

============================================================
  Device: Siklu / Ceragon MH-T261 (ctu-96)
============================================================
  Serial Number:    AE09100255
  Hardware Rev:     A0
  Software Rev:     3.4.0-4377-5faacf06a
  Operation Mode:   TU
  Uptime:           00079:01:36:55
  Operational:      YES
  Max Throughput:   1.0 Gbps

  [Network Interfaces]
   - eth1: eth1 RJ-45 1Gbps | Speed: 1.0G | Oper: UP
   - Host: Host CPU interface | Speed: 0.0G | Oper: UP

  [Radio Sectors]
   - Sector 1: Freq 64.8 GHz (64800.0 MHz) | Antenna: massive2 | Temp: 61 C | Oper: UP
============================================================
```

### 2. TeraFlowSDN Synchronization (`sync`)
Performs an immediate one-shot synchronization: registers the device in TFS, updates endpoints and configuration rules, and attaches the node to active topology links:
```bash
ceragon-tfs-adapter sync --ip 192.168.1.225 --tfs-url http://localhost:8088
```

### 3. Status Verification (`status`)
Verifies live reachability of the hardware and confirms its registration status in TeraFlowSDN:
```bash
ceragon-tfs-adapter status --ip 192.168.1.225 --tfs-url http://localhost:8088
```
**Example Output:**
```
--- Ceragon Hardware Status ---
Node:        ctu-96 (MH-T261)
IP:          192.168.1.225:80
Operational: YES

--- TeraFlowSDN Status ---
Registered:  YES (UUID: f676623c-1a65-54bd-b1e8-279c8a6d8a1c)
TFS Name:    Ceragon-MH-T261-ctu-96
TFS Status:  DEVICEOPERATIONALSTATUS_ENABLED
```

### 4. Background Telemetry Daemon (`daemon`)
Runs continuously in the background, interrogating the device every `interval` seconds, pushing telemetry updates to TFS, and handling reconnection:
```bash
ceragon-tfs-adapter daemon --interval 15
```

---

## 6. TeraFlowSDN Representation & Config Rules

In ETSI TeraFlowSDN, the device is represented with:
- **Device UUID**: Deterministic UUID5 based on serial number (`f676623c-1a65-54bd-b1e8-279c8a6d8a1c`).
- **Context & Topology**: Context `admin`, Topology `admin`.
- **Operational Status**: `DEVICEOPERATIONALSTATUS_ENABLED`.
- **Endpoints**:
  - `ctu-96:eth1` (`copper-rj45-1g`)
  - `ctu-96:rf-sector-1` (`radio-60ghz-mmwave`)
  - `ctu-96:Host` (`copper-rj45-0g`)
- **Topology Links**:
  - `ceragon-uplink-ctu-96-to-O-CU North`: 1.0 Gbps bidirectional copper link connecting `eth1` to the adjacent transport node.
- **Config Rules**:
  - `/device/capabilities`: Maximum throughput, frequency bands, beamforming capabilities, interface counts.
  - `/device/hardware_info`: Serial number, firmware revision, hardware revision, management endpoint.
  - `/device/operating_parameters`: Live operating frequency, modem/RF temperatures, TX power mode, admin status.

---

## 7. Intent Execution: Controlling the Device via TFS

### A. Network Slicing & VLAN Intents
When an intent is issued for a network slice or VLAN:
1. CER-Intent pushes a `CONFIGACTION_SET` rule to TFS:
   - Resource Key: `/interface[name=ctu-96]/slice`
   - Resource Value: `{"vlan_id": 200, "slice_name": "Slice-URAN-6G", "bandwidth_mbps": 1000}`
2. The adapter intercepts the configuration and executes:
   - **MultiHaul TG**: Provisions a VLAN bridge entry in `radio-bridge-tg-user-bridge:user-bridge/vlan-config/vlan=200`.
   - **CeraOS**: Provisions `ceragon-slice:slice-config` with rate limiting and queue priority.

### B. Radio Frequency & Power Tuning
To tune radio parameters:
```bash
curl -X PUT http://localhost:8088/tfs-api/device/f676623c-1a65-54bd-b1e8-279c8a6d8a1c \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": {"device_uuid": {"uuid": "f676623c-1a65-54bd-b1e8-279c8a6d8a1c"}},
    "device_config": {
      "config_rules": [
        {
          "action": "CONFIGACTION_SET",
          "custom": {
            "resource_key": "/device/operating_parameters",
            "resource_value": "{\"frequency_mhz\": 60480.0, \"tx_power_control\": \"auto\"}"
          }
        }
      ]
    }
  }'
```
The adapter issues an RFC 8040 `PATCH` to the radio configuration container and confirms the change.

---

## 8. Configuration Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `CERAGON_IP` | `192.168.1.225` | Management IP address of the Ceragon unit. |
| `CERAGON_PORT` | `80` | Management port (`80` for HTTP, `443` for HTTPS). |
| `CERAGON_USER` | `admin` | RESTCONF username. |
| `CERAGON_PASSWORD` | `admin` | RESTCONF password. |
| `CERAGON_USE_HTTPS` | `false` | Set `true` if connecting over HTTPS. |
| `CERAGON_VERIFY_TLS`| `false` | Set `false` to bypass self-signed TLS certificates. |
| `TERAFLOW_URL` | `http://localhost:8088` | TeraFlowSDN Northbound REST URL. |
| `TFS_CONTEXT` | `admin` | Target TFS Context. |
| `TFS_TOPOLOGY` | `admin` | Target TFS Topology. |
| `ADAPTER_SYNC_INTERVAL_SEC` | `15` | Periodic synchronization interval for daemon. |
