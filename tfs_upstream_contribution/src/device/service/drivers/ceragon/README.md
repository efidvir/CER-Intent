# Ceragon Wireless Radio Transport Driver for ETSI TeraFlowSDN

The **Ceragon Southbound Driver** (`src/device/service/drivers/ceragon/`) enables ETSI TeraFlowSDN to natively discover, monitor, configure, and manage Ceragon wireless radio links and millimeter-wave transport equipment via RFC 8040 RESTCONF.

---

## 1. Module Structure

```
src/device/service/drivers/ceragon/
├── __init__.py               # Exports CeragonDriver
├── CeragonDriver.py          # Main TFS driver implementation (_Driver subclass)
├── client.py                 # RFC 8040 RESTCONF client with 2-phase candidate datastore commit
├── models.py                 # Transport domain models (RadioSector, NetworkInterface, SliceConfig)
├── portfolio.py              # Full Ceragon 5-family product catalog & capability gating
├── templates.py              # Candidate datastore JSON/XML payload templates
├── Tools.py                  # Endpoint generation and TFS resource rule parser
├── README.md                 # This documentation file
└── schemas/                  # 84 RFC-compliant YANG 1.1 data models (100% dependency closure)
    ├── __init__.py           # Schema accessor, family filter & closure validation utilities
    └── yang/                 # Bundled YANG definitions across MultiHaul TG, EtherHaul, CeraOS & IETF/IEEE
        ├── radio-bridge-tg-*.yang
        ├── radio-bridge-eh-radio.yang
        ├── ceragon-*.yang
        ├── ieee802-dot1*.yang
        └── ietf-*.yang
```

---

## 2. Supported Hardware (Full Ceragon Portfolio)

| Family | Model Series | Spectrum | Max Throughput | Transport Role |
| :--- | :--- | :--- | :--- | :--- |
| **MultiHaul TG** | `MH-T261` *(lab-verified)*, `MH-T260`, `MH-T265`, `MH-T280`, `MH-N265`, `MH-N366`, `MH-N367` | 57–71 GHz (V-Band) | Up to 7.2 Gbps | mmWave Mesh / PtMP / Terragraph |
| **EtherHaul** | `EH-614TX`, `EH-710TX`, `EH-1200TX`, `EH-1200FX`, `EH-2500FX`, `EH-8010FX`, `EH-8020FX` | 60 GHz (V-Band) / 70–80 GHz (E-Band) | Up to 20 Gbps | Ultra-High-Capacity PtP Carrier Link |
| **FibeAir IP-20** | `IP-20C`, `IP-20C-HP`, `IP-20S`, `IP-20E`, `IP-20V`, `IP-20N`, `IP-20A`, `IP-20A-LH`, `IP-20G`, `IP-20GX` | 4–86 GHz (MW / E-Band / V-Band) | Up to 10 Gbps | Split-Mount & All-Outdoor Microwave / Trunk |
| **IP-50** | `IP-50C`, `IP-50CX`, `IP-50E`, `IP-50EX`, `IP-50EXA`, `IP-50FX` | 6–42 GHz MW & 70/80 GHz E-Band | Up to 25 Gbps | Disaggregated Multi-Core MW, Multi-Band & Nodal |
| **IP-100** | `IP-100E` | 70/80 GHz (Dual-Carrier E-Band) | Up to 25 Gbps | Next-Gen Ultra-Capacity E-Band |

---

## 3. Supported TFS Configuration Rules

The driver processes TFS `ConfigRule` structures dispatched by the TFS Device Service.

| Resource Key | Action | Type | Description |
| :--- | :--- | :--- | :--- |
| `_connect/address` | Read/Write | `string` | IP address or hostname of the Ceragon node (e.g. `192.168.1.225`). |
| `_connect/port` | Read/Write | `integer` | RESTCONF management port (Default: `80` for HTTP, `443` for HTTPS). |
| `_connect/settings` | Read/Write | `dict` | Connection options: `{"username": "admin", "password": "...", "scheme": "http", "timeout": 15}`. |
| `/device/hardware_info` | Read-Only | `dict` | Inventory metadata: serial number, hardware revision, software version, uptime. |
| `/device/capabilities` | Read-Only | `dict` | Transport capabilities: supported bands, beamforming profile, max throughput, portfolio features. |
| `/device/operating_parameters` | Read/Write | `dict` | Live telemetry & radio tuning: frequency, TX power, channel BW, temperatures, ATPC state, admin status. |
| `/device/yang_schemas` | Read-Only | `dict` | Bundled & live RFC 8525 YANG 1.1 schema catalog + closure verification. |
| `/device/pm_telemetry` | Stream / Read | `dict` | Live northbound PM counters (`in-octets`, `out-octets`, BER/FER, 15-min/24-hr bins, RSL, SNR, MCS/QAM). |
| `/device/events` | Stream / Read | `list` | Live alarm and system event notifications (`radio-bridge-tg-events` / `ceragon-pm-telemetry`). |
| `/interface[name=*]/slice` | Write / Delete | `dict` | Creates/deletes IEEE 802.1Q VLAN bridges (`c-vlan`, `s-vlan`, `q-in-q`) and slice rate limits. |
| `/interface[name=*]/radio` | Write | `dict` | Tunes carrier frequency (`frequency_mhz`), channel BW, MRMC script, TX power, and ATPC. |
| `/interface[name=*]/acm` | Write | `dict` | Configures Adaptive Coding & Modulation min/max profile (`QPSK`..`4096QAM`, `MCS2`..`MCS12`). |
| `/interface[name=*]/qos` | Write | `dict` | Configures 8-queue scheduler, CIR/PIR/CBS/EBS shaper, and WRED/tail-drop profiles. |
| `/interface[name=*]/tsn` | Write | `dict` | Configures IEEE 802.1Qbv Gate Control List (GCL) and 802.1Qbu frame preemption. |
| `/interface[name=*]/beamforming` | Write | `dict` | Overrides 60 GHz TX/RX beam index and invokes `radio-bridge-tg-radio-dn:start-topo-scan`. |
| `/interface[name=*]/multiband` | Write | `dict` | Bonds E-Band + Microwave carriers (`ceragon-multiband`) with hitless L1 failover. |
| `/interface[name=*]/protection` | Write | `dict` | Configures `1+1 HSB`, `2+0 XPIC`, or `active-backup` bonding + manual switchover RPC. |
| `/interface[name=*]/sync` | Write | `dict` | Configures IEEE 1588v2 PTP (`G.8275.1`/`G.8275.2`), SyncE SSM, and GPS/RF timing sources. |
| `/interface[name=*]/security` | Write | `dict` | Configures IEEE 802.1AE MACsec (`GCM-AES-128`/`256`) and air-interface AES encryption. |
| `/interface[name=*]/oran_xhaul` | Write | `dict` | Configures O-RAN Split 7.2x eCPRI BFP9 IQ compression and delay windows. |
| `/interface[name=*]/energy` | Write | `dict` | Configures Green-ATPC target RSL and low-load secondary carrier sleep. |

---

## 4. RESTCONF Candidate Datastore & 2-Phase Commit

Ceragon devices implement the RFC 8342 Network Management Datastore Architecture (NMDA) with a candidate datastore engine. All mutations must follow a strict transactional workflow to prevent partial state corruption:

```mermaid
sequenceDiagram
    autonumber
    participant TFS as TFS DeviceService
    participant CD as CeragonDriver
    participant CLI as CeragonRestClient
    participant DEV as Ceragon Node (Candidate DS)

    TFS->>CD: SetConfig([rule1, rule2])
    CD->>CLI: stage_candidate(path, payload)
    CLI->>DEV: PATCH /restconf/ds/ietf-datastores:candidate
    DEV-->>CLI: 200 OK / 204 No Content
    
    alt Staging Succeeded
        CD->>CLI: commit_candidate()
        CLI->>DEV: POST /restconf/operations/ietf-netconf:commit
        DEV-->>CLI: 200 OK (Committed to Running DS)
        CD-->>TFS: Success [(rule1, True), (rule2, True)]
    else Staging or Validation Failed
        CD->>CLI: discard_candidate()
        CLI->>DEV: POST /restconf/operations/ietf-netconf:discard-changes
        DEV-->>CLI: 200 OK (Rollback Complete)
        CD-->>TFS: Failure [(rule1, False), ...]
    end
```

---

## 5. Driver Lifecycle Details

### `Connect()`
- Initializes a persistent `requests.Session` with HTTP Basic Authentication.
- Verifies datastore reachability via `/restconf/data/ietf-yang-library:yang-library`.
- Thread-safe and idempotent.

### `GetInitialConfig()`
- Queries `/restconf/ds/ietf-datastores:candidate/ietf-system:system` and inventory modules.
- Generates TFS `EndPoint` structures for all physical copper ports (`eth1`, `eth2`) and wireless radio sectors (`rf-sector-1`).
- Populates initial resource rules (`/device/hardware_info`, `/device/capabilities`, `/device/operating_parameters`).

### `GetConfig(resource_keys)`
- Queries operational state for requested keys:
  - Thermal sensors (modem temp, RF temp)
  - RSSI, SNR, and modulation levels
  - Port operational status (`UP` / `DOWN`), speed, and MTU.

### `SetConfig(resources)`
- Maps TFS resource rules into candidate datastore payloads via `templates.py`.
- Stages changes in candidate datastore.
- Executes atomic commit.
- Triggers automatic rollback (`discard-changes`) if any operation fails.

### `DeleteConfig(resources)`
- Removes VLAN bridges and sub-interfaces created by network slices.
- Re-tunes radio parameters to defaults when slice reservations terminate.

---

## 6. Running Unit Tests

Execute the driver unit tests with pytest:

```bash
# From repository root:
PYTHONPATH=src pytest -v src/device/tests/test_driver_ceragon.py
```

**Test Coverage**:
- `test_driver_lifecycle`: Connect and Disconnect verification.
- `test_get_initial_config`: Inventory parsing and endpoint generation.
- `test_get_config`: Telemetry extraction (temperatures, frequency, ATPC).
- `test_set_config_radio_tuning`: Channel frequency tuning with 2-phase commit.
- `test_set_config_slice_creation`: IEEE 802.1Q VLAN slicing and rate limiting.
- `test_set_config_acm_floor`: Adaptive modulation floor hardening.
- `test_candidate_datastore_rollback`: Verifies `discard-changes` on simulated HTTP error.
- `test_yang_schema_availability`: Asserts all 51 physical YANG models are bundled and parseable.

---

## 7. Device Onboarding Example

Create a descriptor file (e.g., `manifests/ceragon_mh_t261_descriptor.json`) and upload via TFS REST API:

```bash
curl -X POST http://localhost:8088/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {
        "device_id": {"device_uuid": {"uuid": "ceragon-mh-t261-ctu-96"}},
        "device_type": "microwave-radio-system",
        "device_config": {
          "config_rules": [
            {"action": 1, "custom": {"resource_key": "_connect/address", "resource_value": "192.168.1.225"}},
            {"action": 1, "custom": {"resource_key": "_connect/port", "resource_value": "80"}},
            {"action": 1, "custom": {"resource_key": "_connect/settings", "resource_value": {
              "username": "admin", "password": "admin", "scheme": "http", "timeout": 15
            }}}
          ]
        },
        "device_operational_status": 1,
        "device_drivers": [22],
        "device_endpoints": []
      }
    ]
  }'
```
