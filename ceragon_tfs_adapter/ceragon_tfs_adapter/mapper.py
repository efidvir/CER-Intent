"""
Schema Mapper: Ceragon <--> TeraFlowSDN (TFS)
==============================================
Translates Ceragon domain models into TFS-compliant device descriptors, endpoints,
and JSON-serialized config rules.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from ceragon_tfs_adapter.models import CeragonDeviceState

NAMESPACE_CERAGON = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_tfs_uuid(identifier: str) -> str:
    """Generate a deterministic RFC 4122 UUID5 string for a given identifier."""
    return str(uuid.uuid5(NAMESPACE_CERAGON, str(identifier)))


class CeragonTFSMapper:
    """Transforms Ceragon live device state into TFS Northbound REST payloads."""

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

        endpoint_definitions = []
        for iface in state.interfaces:
            ep_uuid = generate_tfs_uuid(f"{dev_uuid}-{iface.name}")
            endpoint_definitions.append({
                "uuid": ep_uuid,
                "name": f"{state.node_name}:{iface.name}",
                "type": f"copper-rj45-{int(iface.speed_gbps)}g",
                "sample_types": [],
            })

        for sec in state.sectors:
            ep_uuid = generate_tfs_uuid(f"{dev_uuid}-rf-sector-{sec.index}")
            endpoint_definitions.append({
                "uuid": ep_uuid,
                "name": f"{state.node_name}:rf-sector-{sec.index}",
                "type": "radio-60ghz-mmwave",
                "sample_types": [],
            })

        settings_dict = {
            "endpoints": endpoint_definitions,
            "username": "admin",
            "model": state.model,
            "vendor": state.vendor,
            "protocol": "restconf",
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

        # 1. Device Capabilities
        caps = {
            "vendor": state.vendor,
            "model": state.model,
            "role": "transport_mmwave",
            "max_throughput_gbps": state.max_throughput_gbps,
            "frequency_band_ghz": 60,
            "beamforming": True,
            "interfaces_count": len(state.interfaces),
            "sectors_count": len(state.sectors),
        }
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

        # 3. Operating Parameters
        primary_sec = state.sectors[0] if state.sectors else None
        op_params = {
            "admin_status": "UP" if state.is_operational else "DOWN",
            "frequency_mhz": primary_sec.frequency_mhz if primary_sec else 58320,
            "frequency_ghz": primary_sec.frequency_ghz if primary_sec else 58.32,
            "antenna_mode": primary_sec.antenna_mode if primary_sec else "beamforming",
            "tx_power_control": primary_sec.tx_power_control if primary_sec else "auto",
            "modem_temperature_c": primary_sec.modem_temperature_c if primary_sec else 0,
            "rf_temperature_c": primary_sec.rf_temperature_c if primary_sec else 0,
            "last_synced_at": state.last_synced_at,
        }
        rules.append({
            "action": "CONFIGACTION_SET",
            "custom": {
                "resource_key": "/device/operating_parameters",
                "resource_value": json.dumps(op_params),
            }
        })

        return rules
