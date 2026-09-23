# Ceragon Wireless Transport Southbound Driver Specification

## 1. Executive Summary & Purpose

This document specifies the technical design, architectural interfaces, data models, and operational workflows of the **Ceragon Southbound Driver** (`src/device/service/drivers/ceragon/`) for **ETSI TeraFlowSDN (TFS)**.

The driver provides native SDN control, monitoring, dynamic configuration, and network slicing over Ceragon wireless radio links and transport equipment—including **MultiHaul TG mmWave (Terragraph)**, **EtherHaul E-Band**, and **CeraOS multi-core microwave systems**—using **RFC 8040 RESTCONF** and the **RFC 8342 Network Management Datastore Architecture (NMDA)**.

---

## 2. System Architecture

```mermaid
flowchart TD
    subgraph TFS_CORE ["ETSI TeraFlowSDN Core"]
        NBI["Northbound API (REST / IETF Network)"]
        TOPOLOGY["Topology Service"]
        MONITORING["Monitoring & Telemetry Service"]
        CONTEXT["Context Service (CRDB)"]
        DEVICE_SVC["Device Service (gRPC :2020)"]
    end

    subgraph DRIVER_LAYER ["Ceragon Southbound Driver (SBI)"]
        DF["DriverFactory"]
        CD["CeragonDriver (implements _Driver)"]
        TOOLS["Tools (Resource Rules & Endpoint Mapping)"]
        CLIENT["CeragonRestClient (RFC 8040 Engine)"]
        MODELS["Normalized Transport Domain Models"]
        SCHEMAS["51 Bundled YANG Schemas"]
    end

    subgraph HARDWARE_PLANE ["Physical Wireless Transport Equipment"]
        T261["Ceragon / Siklu MultiHaul TG MH-T261\n(60 GHz V-Band Terragraph)"]
        EH["Ceragon EtherHaul EH-8010FX\n(70/80 GHz E-Band Multi-Gigabit)"]
        IP50["Ceragon CeraOS IP-50C / IP-50E\n(Multi-Core Microwave XPIC)"]
    end

    NBI --> DEVICE_SVC
    DEVICE_SVC --> CONTEXT
    DEVICE_SVC --> TOPOLOGY
    MONITORING -.-> DEVICE_SVC
    DEVICE_SVC --> DF
    DF --> CD

    CD --> TOOLS
    CD --> CLIENT
    CLIENT --> MODELS
    CD -.-> SCHEMAS

    CLIENT ===|"RESTCONF HTTP/HTTPS :80/:443\n(RFC 8040 Candidate Datastore / 2PC)"| T261
    CLIENT ===|"RESTCONF HTTP/HTTPS :80/:443"| EH
    CLIENT ===|"REST / NETCONF :80/:830"| IP50
```

---

## 3. Class Design & Component Responsibilities

```mermaid
classDiagram
    class _Driver {
        <<abstract>>
        +Connect() bool
        +Disconnect() bool
        +GetInitialConfig() list
        +GetConfig(resource_keys) list
        +SetConfig(resources) list
        +DeleteConfig(resources) list
        +SubscribeState(subscriber) bool
        +UnsubscribeState(subscriber) bool
    }

    class CeragonDriver {
        -str address
        -int port
        -dict settings
        -CeragonRestClient client
        -Lock lock
        +Connect() bool
        +Disconnect() bool
        +GetInitialConfig() list
        +GetConfig(resource_keys) list
        +SetConfig(resources) list
        +DeleteConfig(resources) list
        +SubscribeState(subscriber) bool
        +UnsubscribeState(subscriber) bool
    }

    class CeragonRestClient {
        -str base_url
        -Session session
        -int timeout
        +probe_device() dict
        +get_system_info() dict
        +get_interfaces() list
        +get_radio_sectors() list
        +stage_candidate(path, payload) bool
        +commit_candidate() bool
        +discard_candidate() bool
    }

    class Tools {
        <<utility>>
        +extract_endpoints(device_state) list
        +format_resource_rules(device_state) list
        +parse_config_rule(key, value) tuple
    }

    class CeragonDeviceState {
        +str node_name
        +str serial_number
        +str hardware_rev
        +str software_version
        +list interfaces
        +list radio_sectors
        +dict operating_params
    }

    _Driver <|-- CeragonDriver
    CeragonDriver --> CeragonRestClient
    CeragonDriver --> Tools
    CeragonRestClient --> CeragonDeviceState
```

---

## 4. RESTCONF Candidate Datastore & Transaction Management

Ceragon devices employ a candidate datastore engine. Applying configuration changes directly to the running datastore is prohibited by hardware security policies to prevent service interruption during multi-attribute mutations.

### The 2-Phase Commit (2PC) Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Operator as TFS Service / Intent Layer
    participant DEV_SVC as TFS DeviceService
    participant DRIVER as CeragonDriver
    participant REST as CeragonRestClient
    participant HW as Ceragon Hardware (Candidate DS)

    Operator->>DEV_SVC: ConfigureDevice(DeviceConfigRules)
    DEV_SVC->>DRIVER: SetConfig(resources)

    Note over DRIVER,HW: Phase 1: Staging Mutation in Candidate Datastore
    DRIVER->>REST: stage_candidate(path, payload)
    REST->>HW: PATCH /restconf/ds/ietf-datastores:candidate/ietf-interfaces:interfaces
    
    alt Staging Accepted (HTTP 200 / 204)
        HW-->>REST: 204 No Content
        Note over DRIVER,HW: Phase 2: Atomic Commit to Running Datastore
        DRIVER->>REST: commit_candidate()
        REST->>HW: POST /restconf/operations/ietf-netconf:commit
        
        alt Commit Accepted (HTTP 200)
            HW-->>REST: 200 OK
            DRIVER-->>DEV_SVC: [(rule_key, True)]
            DEV_SVC-->>Operator: Configuration Applied Successfully
        else Commit Rejected (Validation / Conflict)
            HW-->>REST: 409 Conflict / 400 Bad Request
            DRIVER->>REST: discard_candidate()
            REST->>HW: POST /restconf/operations/ietf-netconf:discard-changes
            HW-->>REST: 200 OK (Rolled Back)
            DRIVER-->>DEV_SVC: [(rule_key, False)]
            DEV_SVC-->>Operator: Error: Commit Failed (Rolled Back)
        end
    else Staging Rejected (HTTP 4xx / 5xx)
        HW-->>REST: 400 Bad Request (Invalid Payload)
        DRIVER->>REST: discard_candidate()
        REST->>HW: POST /restconf/operations/ietf-netconf:discard-changes
        HW-->>REST: 200 OK
        DRIVER-->>DEV_SVC: [(rule_key, False)]
        DEV_SVC-->>Operator: Error: Staging Rejected
    end
```

---

## 5. Supported TFS Configuration Rules & Resource Keys

### 5.1. Connection Management Rules

| Resource Key | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `_connect/address` | `string` | Target node IPv4 or IPv6 address | `"192.168.1.225"` |
| `_connect/port` | `integer` | RESTCONF management port | `80` (HTTP) or `443` (HTTPS) |
| `_connect/settings` | `dict` | Credentials and connection timeout | `{"username": "admin", "password": "...", "scheme": "http", "timeout": 15}` |

### 5.2. Telemetry & Inventory Rules (Read-Only)

| Resource Key | Return Type | Description |
| :--- | :--- | :--- |
| `/device/hardware_info` | `dict` | Vendor metadata: `{"serial_number": "AE09100255", "hardware_rev": "A0", "software_version": "3.4.0-...", "uptime": "..."}` |
| `/device/capabilities` | `dict` | Device capabilities: `{"vendor": "Ceragon", "model": "MH-T261", "role": "transport_mmwave", "max_throughput_gbps": 1.0, "beamforming": true}` |
| `/device/operating_parameters` | `dict` | Live telemetry: `{"admin_status": "UP", "frequency_ghz": 60.48, "modem_temperature_c": 61, "rf_temperature_c": 58, "tx_power_control": "auto"}` |

### 5.3. Dynamic Control Rules (Read/Write)

#### `/radio/tuning`
Configures carrier channel frequency and ATPC:
```json
{
  "action": 1,
  "custom": {
    "resource_key": "/radio/tuning",
    "resource_value": {
      "sector_id": "rf-sector-1",
      "frequency_mhz": 60480.0,
      "tx_power_control": "auto",
      "target_mcs": 8
    }
  }
}
```

#### `/slice/<slice_name>`
Allocates an IEEE 802.1Q transport slice:
```json
{
  "action": 1,
  "custom": {
    "resource_key": "/slice/slice-uran-6g",
    "resource_value": {
      "vlan_id": 200,
      "bandwidth_mbps": 1000,
      "priority": 7,
      "member_interfaces": ["eth1", "rf-sector-1"]
    }
  }
}
```

#### `/modulation/acm_floor`
Enforces minimum Adaptive Coding and Modulation (ACM) floor for rain fade resilience:
```json
{
  "action": 1,
  "custom": {
    "resource_key": "/modulation/acm_floor",
    "resource_value": {
      "sector_id": "rf-sector-1",
      "min_modulation": "QPSK",
      "min_mcs": 2,
      "atpc_boost_dbm": 3.0
    }
  }
}
```

---

## 6. Bundled YANG Schema Catalog (51 Models)

All 51 RFC-compliant data models bundled in `src/device/service/drivers/ceragon/schemas/yang/` are extracted directly from production hardware:

### A. Radio & Wireless Millimeter-Wave Models
- `radio-bridge-tg-radio-common.yang`: Core radio parameters, channel plans, antenna profiles.
- `radio-bridge-tg-radio-dn.yang`: Terragraph Distribution Node (DN) beamforming and sectors.
- `radio-bridge-tg-acm.yang`: Adaptive Coding and Modulation state machines and hysteresis.
- `radio-bridge-tg-bond.yang`: Wireless link bonding and LAG aggregation.
- `radio-bridge-tg-spider-attenuation-control.yang`: Dynamic RF attenuation and beam shaping.
- `radio-bridge-tg-gps.yang`: Synchronous Ethernet and GPS timing synchronization.

### B. Transport & Bridging Models
- `radio-bridge-tg-interfaces.yang`: Physical port and radio interface definitions.
- `radio-bridge-tg-user-bridge.yang`: User plane Ethernet bridging and VLAN isolation.
- `radio-bridge-tg-tunnel.yang`: Point-to-Point and Point-to-Multipoint transport tunneling.
- `radio-bridge-tg-cfm.yang`: IEEE 802.1ag Connectivity Fault Management (CFM).
- `ieee802-dot1q-cfm.yang`, `ieee802-dot1q-cfm-types.yang`, `ieee802-dot1q-types.yang`: Standard IEEE 802.1Q definitions.

### C. System, OAM & Maintenance Models
- `radio-bridge-tg-system.yang`: System hostname, location, operational mode.
- `radio-bridge-tg-inventory.yang`: Hardware inventory, board revisions, serial numbers.
- `radio-bridge-tg-software-upgrade.yang`: Dual-image software upgrade and bank switching.
- `radio-bridge-tg-rollback.yang`: Automatic configuration rollback timer.
- `radio-bridge-tg-pm.yang`: Performance monitoring and 15-min / 24-hr historical bins.
- `radio-bridge-tg-events.yang`, `radio-bridge-tg-logging.yang`: Alarm and syslog notifications.

### D. IETF & Standard Base Models
- `ietf-datastores.yang`: RFC 8342 NMDA datastore definitions.
- `ietf-yang-library.yang`: RFC 8525 YANG library module catalog.
- `ietf-restconf.yang`: RFC 8040 RESTCONF protocol definitions.
- `ietf-netconf.yang`, `ietf-netconf-nmda.yang`, `ietf-netconf-acm.yang`: Netconf access control and operations.
- `ietf-interfaces.yang`, `ietf-ip.yang`, `ietf-inet-types.yang`, `ietf-yang-types.yang`: Standard network primitives.

---

## 7. Quality Assurance & Test Verification

The driver includes a comprehensive test suite in [`src/device/tests/test_driver_ceragon.py`](../src/device/tests/test_driver_ceragon.py) covering:

| Test Case | Method Verified | Success Criteria |
| :--- | :--- | :--- |
| `test_driver_lifecycle` | `Connect()` / `Disconnect()` | Session creation, keepalive verification, idempotent teardown. |
| `test_get_initial_config` | `GetInitialConfig()` | Accurate extraction of inventory and generation of TFS `EndPoint` structures. |
| `test_get_config` | `GetConfig()` | Telemetry retrieval for operating parameters, temperatures, and link metrics. |
| `test_set_config_radio_tuning` | `SetConfig()` | Candidate staging of frequency tuning and atomic commit. |
| `test_set_config_slice_creation` | `SetConfig()` | Dynamic IEEE 802.1Q sub-interface creation and token-bucket bandwidth reservation. |
| `test_set_config_acm_floor` | `SetConfig()` | Enforcing ACM minimum modulation floor for rain-fade mitigation. |
| `test_candidate_datastore_rollback`| `SetConfig()` | Validates execution of `discard-changes` when candidate staging rejects payload. |
| `test_yang_schema_availability` | `schemas` module | Confirms presence, integrity, and readability of all 51 YANG definitions. |
