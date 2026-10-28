"""
Schema Mapper: Ceragon <--> TeraFlowSDN (TFS)
==============================================
Translates Ceragon domain models and live PM telemetry streams into TFS-compliant
device descriptors, endpoints, and JSON-serialized config rules.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from ceragon_tfs_adapter.models import CeragonDeviceState, PMTelemetrySample
from ceragon_tfs_adapter.portfolio import ProductSpec

NAMESPACE_CERAGON = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_tfs_uuid(identifier: str) -> str:
    """Generate a deterministic RFC 4122 UUID5 string for a given identifier."""
    return str(uuid.uuid5(NAMESPACE_CERAGON, str(identifier)))


def radio_endpoint_type(spec: Optional[ProductSpec], frequency_mhz: Optional[float] = None) -> str:
    """
    TFS endpoint type for a radio carrier, derived from the band actually in use
    (multiband nodes expose MW and E-band carriers) or the product's primary band.
    """
    if spec:
        if frequency_mhz:
            ghz = frequency_mhz / 1000.0
            for band in spec.bands:
                if band.freq_min_ghz <= ghz <= band.freq_max_ghz:
                    return band.endpoint_type
        return spec.primary_band.endpoint_type
    if frequency_mhz:
        ghz = frequency_mhz / 1000.0
        if 57 <= ghz <= 71:
            return "radio-v-band"
        if 71 < ghz <= 86:
            return "radio-e-band"
        return "radio-mw"
    return "radio"


class CeragonTFSMapper:
    """Transforms Ceragon live device state and telemetry into TFS Northbound REST payloads."""

    @staticmethod
    def to_tfs_add_device_descriptor(state: CeragonDeviceState) -> Dict[str, Any]:
        """
        Build the initial AddDevice descriptor.
        TFS AddDevice RPC enforces:
          1. device_endpoints must be EMPTY ([]).
          2. config_rules must ONLY contain '_connect/' prefixed keys.
          3. Endpoints are passed via _connect/settings['endpoints'] with mandatory 'uuid' and 'name'.
        """
        dev_uuid = generate_tfs_uuid(f"ceragon-{state.serial_number}")
        spec = state.product_spec

        endpoint_definitions = []
        for iface in state.interfaces:
            ep_uuid = generate_tfs_uuid(f"{dev_uuid}-{iface.name}")
            speed = iface.speed_gbps
            endpoint_definitions.append({
                "uuid": ep_uuid,
                "name": f"{state.node_name}:{iface.name}",
                "type": f"ethernet-{int(speed) if speed >= 1 else speed}g",
                "sample_types": [101, 102, 201, 202],  # PACKETS_TRANSMITTED/RECEIVED, BYTES_TRANSMITTED/RECEIVED
            })

        for sec in state.sectors:
            ep_uuid = generate_tfs_uuid(f"{dev_uuid}-rf-sector-{sec.index}")
            endpoint_definitions.append({
                "uuid": ep_uuid,
                "name": f"{state.node_name}:rf-sector-{sec.index}",
                "type": radio_endpoint_type(spec, sec.frequency_mhz),
                "sample_types": [101, 102, 201, 202],
            })

        settings_dict = {
            "endpoints": endpoint_definitions,
            "username": "admin",
            "model": state.model,
            "vendor": state.vendor,
            "protocol": "restconf",
            "product_family": spec.family if spec else "unknown",
            "api_flavor": spec.api_flavor if spec else "unknown",
        }

        connect_rules = [
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "_connect/address",
                    "resource_value": state.management_ip,
                }
            },
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "_connect/port",
                    "resource_value": str(state.management_port),
                }
            },
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "_connect/settings",
                    "resource_value": json.dumps(settings_dict),
                }
            }
        ]

        oper_status = "DEVICEOPERATIONALSTATUS_ENABLED" if state.is_operational else "DEVICEOPERATIONALSTATUS_DISABLED"

        return {
            "device_id": {"device_uuid": {"uuid": dev_uuid}},
            "name": f"Ceragon-{state.model}-{state.node_name}",
            "device_type": "emu-packet-router",
            "device_operational_status": oper_status,
            "device_drivers": [0],  # DEVICEDRIVER_UNDEFINED
            "device_endpoints": [],  # MUST BE EMPTY for AddDevice RPC
            "device_config": {"config_rules": connect_rules},
        }

    @staticmethod
    def to_tfs_operational_config_rules(state: CeragonDeviceState) -> List[Dict[str, Any]]:
        """
        Build operational config rules to apply via ConfigureDevice (PUT /tfs-api/device/{uuid}).
        """
        rules = []
        spec = state.product_spec

        # 1. Device Capabilities (portfolio catalog + live counts)
        if spec:
            caps = spec.to_capabilities()
        else:
            caps = {
                "vendor": state.vendor,
                "model": state.model,
                "role": "transport",
                "catalog_match": "none",
                "max_throughput_gbps": state.port_throughput_gbps,
            }
        caps.update({
            "vendor": state.vendor or caps.get("vendor"),
            "reported_model": state.model,
            "interfaces_count": len(state.interfaces),
            "sectors_count": len(state.sectors),
            "active_links_count": len(state.active_links),
            "yang_modules_count": len(state.yang_modules),
            "port_throughput_gbps": state.port_throughput_gbps,
        })
        rules.append({
            "action": "CONFIGACTION_SET",
            "custom": {
                "resource_key": "/device/capabilities",
                "resource_value": json.dumps(caps),
            }
        })

        # 2. Live Hardware Info
        inv = {
            "serial_number": state.serial_number,
            "node_name": state.node_name,
            "hardware_rev": state.hardware_rev,
            "software_version": state.software_version,
            "management_ip": state.management_ip,
            "management_port": state.management_port,
            "operation_mode": state.operation_mode,
            "uptime": state.uptime,
            "model": state.model,
            "vendor": state.vendor,
        }
        rules.append({
            "action": "CONFIGACTION_SET",
            "custom": {
                "resource_key": "/device/hardware_info",
                "resource_value": json.dumps(inv),
            }
        })

        # 3. Operating Parameters (one entry per radio carrier/sector + active links)
        primary_sec = state.sectors[0] if state.sectors else None
        default_freq = spec.default_frequency_mhz if spec else 0.0
        op_params = {
            "admin_status": "UP" if state.is_operational else "DOWN",
            "frequency_mhz": primary_sec.frequency_mhz if primary_sec else default_freq,
            "frequency_ghz": primary_sec.frequency_ghz if primary_sec else round(default_freq / 1000.0, 2),
            "antenna_mode": primary_sec.antenna_mode if primary_sec else ("beamforming" if spec and spec.supports("beamforming") else "fixed"),
            "tx_power_control": primary_sec.tx_power_control if primary_sec else "auto",
            "modem_temperature_c": primary_sec.modem_temperature_c if primary_sec else None,
            "rf_temperature_c": primary_sec.rf_temperature_c if primary_sec else None,
            "rsl_dbm": primary_sec.rsl_dbm if primary_sec else None,
            "snr_db": primary_sec.snr_db if primary_sec else None,
            "carriers": [
                {
                    "index": s.index,
                    "admin_status": s.admin_status,
                    "frequency_mhz": s.frequency_mhz,
                    "antenna_mode": s.antenna_mode,
                    "tx_power_control": s.tx_power_control,
                    "rsl_dbm": s.rsl_dbm,
                    "snr_db": s.snr_db,
                    "current_modulation": s.current_modulation,
                }
                for s in state.sectors
            ],
            "active_links": [lnk.to_dict() for lnk in state.active_links],
            "last_synced_at": state.last_synced_at,
        }
        rules.append({
            "action": "CONFIGACTION_SET",
            "custom": {
                "resource_key": "/device/operating_parameters",
                "resource_value": json.dumps(op_params),
            }
        })

        # 4. Bundled / Advertised YANG Schema Manifest
        if state.yang_modules:
            rules.append({
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/yang_schemas",
                    "resource_value": json.dumps({
                        "api_flavor": spec.api_flavor if spec else "unknown",
                        "count": len(state.yang_modules),
                        "modules": state.yang_modules,
                    }),
                }
            })

        return rules

    @staticmethod
    def to_tfs_telemetry_rules(sample: PMTelemetrySample) -> List[Dict[str, Any]]:
        """Convert a real-time PMTelemetrySample into TFS config rules for Northbound streaming."""
        return [
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/pm_telemetry",
                    "resource_value": json.dumps(sample.to_dict()),
                }
            },
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/events",
                    "resource_value": json.dumps({
                        "timestamp": sample.timestamp,
                        "count": len(sample.recent_events),
                        "events": sample.recent_events,
                    }),
                }
            },
        ]
