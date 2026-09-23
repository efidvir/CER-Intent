# Ceragon Wireless Transport Southbound Driver for ETSI TeraFlowSDN

## 1. Overview & Architectural Scope

The **Ceragon Southbound Driver** (`src/device/service/drivers/ceragon/`) provides native ETSI TeraFlowSDN (TFS) control over Ceragon wireless radio links and transport equipment.

It interacts with the physical equipment via **RFC 8040 RESTCONF** and the **RFC 6834 / RFC 7950 candidate datastore architecture**, translating high-level transport intents into atomic configuration mutations across millimeter-wave (mmWave), E-band, and multi-core microwave radio networks.

```
                      ┌──────────────────────────────────────┐
                      │      ETSI TeraFlowSDN Controller     │
                      │               Release 7.0            │
                      └──────────────────┬───────────────────┘
                                         │
                         gRPC Internal Service Bus
                                         │
                      ┌──────────────────▼───────────────────┐
                      │           TFS DeviceService          │
                      │  src/device/service/drivers/ceragon/ │
                      │                                      │
                      │      ┌─────────────────────────┐     │
                      │      │      CeragonDriver      │     │
                      │      │   (_Driver Subclass)    │     │
                      │      └────────────┬────────────┘     │
                      │                   │                  │
                      │      ┌────────────▼────────────┐     │
                      │      │    CeragonRestClient    │     │
                      │      │  RFC 8040 Candidate/Tx  │     │
                      │      └────────────┬────────────┘     │
                      └───────────────────┼──────────────────┘
                                          │
                  RFC 8040 RESTCONF HTTP/HTTPS Basic Auth
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         │                                │                                │
┌────────▼──────────────┐      ┌──────────▼────────────┐       ┌───────────▼───────────┐
│     MultiHaul TG      │      │       EtherHaul       │       │        CeraOS         │
│  MH-T261, T280, N366  │      │  EH-8010FX, EH-2500   │       │   IP-50C, IP-50E,     │
│ 60 GHz Terragraph     │      │ 70/80 GHz E-Band      │       │   IP-20C, IP-20N      │
│ Beamforming mmWave    │      │ Multi-Gigabit Carrier │       │ Multi-Core Microwave  │
└───────────────────────┘      └───────────────────────┘       └───────────────────────┘
```

---

## 2. Hardware Compatibility Matrix

| Product Family | Supported Models | Frequency Band | Modulation / Capacity | Interface Types | Datastore Architecture |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MultiHaul TG** | `MH-T261`, `MH-T280`, `MH-N366` | 57–66 GHz (V-Band) | MCS1–MCS12 (up to 3.8 Gbps) | 1G/10G RJ-45 & SFP+ | Clixon RFC 8040 Candidate |
| **EtherHaul** | `EH-8010FX`, `EH-2500FX`, `EH-1200` | 70/80 GHz (E-Band) | QPSK to 128QAM (up to 10 Gbps) | 1G/10G SFP+ | RESTCONF Candidate |
| **CeraOS Microwave**| `IP-50C`, `IP-50E`, `IP-20C`, `IP-20N` | 6–42 GHz (Microwave) | 4QAM to 4096QAM, XPIC, MRMC | Multi-Gigabit Carrier Ethernet | CeraOS REST / NETCONF |

---

## 3. TFS Driver Lifecycle Implementation

The driver subclasses `device.service.driver_api._Driver._Driver` and implements all standard methods:

### 3.1. `Connect()`
* Establishes a session pool using `requests.Session` with HTTP Basic Authentication.
* Verifies datastore reachability via `/restconf/data/ietf-yang-library:yang-library`.
* Re-connection is idempotent and thread-safe via `threading.Lock`.

### 3.2. `GetInitialConfig()`
* Discovers physical hardware inventory (`serial_number`, `hardware_rev`, `software_version`, `model`).
* Extracts all physical and radio interfaces, creating standard TFS `EndPoint` tuples:
  * Copper endpoints: `(endpoint_uuid, "copper", [101, 102, 201, 202])`
  * Radio endpoints: `(endpoint_uuid, "radio", [101, 102, 201, 202])`
* Populates initial resource rules:
  * `/device/hardware_info`
  * `/device/capabilities`
  * `/device/operating_parameters`
  * `/device/endpoints`
  * `/radio/sector[...]`

### 3.3. `GetConfig(resource_keys)`
* Queries live operational telemetry from the physical hardware:
  * Frequency (`frequency_ghz`, `frequency_mhz`, `channel_id`)
  * Transmit power control status (`tx_power_control: "auto"` / ATPC)
  * Thermal sensors (`modem_temperature_c`, `rf_temperature_c`)
  * Link health (`snr_db`, `rssi_dbm`, `link_loss_ratio`)

### 3.4. `SetConfig(resources)`
Translates TFS resource mutations into RFC 8040 candidate datastore modifications using a **2-Phase Commit** sequence:
1. **Stage**: Dispatches `PATCH` to `/restconf/ds/ietf-datastores:candidate`.
2. **Commit**: Executes `POST /restconf/operations/ietf-netconf:commit`.
3. **Rollback**: If validation fails or the physical link drops, triggers `POST /restconf/operations/ietf-netconf:discard-changes`.

Supported Resource Keys:
* `/radio/tuning` $\rightarrow$ tunes channel frequency, channel bandwidth, and ATPC parameters.
* `/slice[...]` or `/vlan[...]` $\rightarrow$ provisions IEEE 802.1Q sub-interfaces, VLAN tags, and bandwidth shaping.
* `/modulation/acm_floor` $\rightarrow$ sets minimum ACM modulation floor for rain-fade protection.

### 3.5. `DeleteConfig(resources)`
* Teardown of VLAN sub-interfaces and release of allocated QoS capacity.

---

## 4. Bundled YANG Schema Library

The driver includes all **51 RFC-compliant YANG schema data models** directly extracted from physical hardware:
* **RFC 7950 / RFC 8040 NMDA Models**: `ietf-datastores`, `ietf-yang-library`, `ietf-netconf`, `ietf-netconf-nmda`.
* **Interface & Bridge Models**: `ietf-interfaces`, `iana-if-type`, `ieee802-dot1q-types`, `ieee802-dot1q-cfm`.
* **Hardware & System Models**: `ietf-hardware`, `ietf-system`, `ietf-snmp`.
* **Wireless mmWave & Radio Models**: `radio-bridge-tg`, `radio-bridge-tg-acm`, `radio-bridge-tg-bond`, `radio-bridge-tg-gps`.

---

## 5. Sample TFS Device Descriptors

To onboard a Ceragon node in TFS:

```json
{
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
}
```
