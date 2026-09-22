"""
Domain Models for Ceragon Device State & Capabilities
======================================================
Normalized representation of physical Ceragon device inventory, interfaces, and radio state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class NetworkInterface:
    index: int
    name: str
    description: str
    if_type: str
    speed_bps: int
    mtu: int
    admin_status: str
    oper_status: str
    mac_address: Optional[str] = None
    in_octets: int = 0
    out_octets: int = 0

    @property
    def speed_gbps(self) -> float:
        return round(self.speed_bps / 1_000_000_000.0, 2)


@dataclass
class RadioSector:
    index: int
    admin_status: str
    frequency_mhz: float
    antenna_mode: str
    mac_address: Optional[str] = None
    polarity: Optional[str] = None
    tx_power_control: str = "auto"
    modem_temperature_c: Optional[float] = None
    rf_temperature_c: Optional[float] = None

    @property
    def frequency_ghz(self) -> float:
        return round(self.frequency_mhz / 1000.0, 2)


@dataclass
class CeragonDeviceState:
    device_id: str                      # Serial number or unique node name
    node_name: str                     # e.g., "ctu-96"
    model: str                         # e.g., "MH-T261", "IP-50C"
    vendor: str                        # e.g., "Ceragon / Siklu"
    serial_number: str
    hardware_rev: str
    software_version: str
    management_ip: str
    management_port: int
    operation_mode: str                # "TU", "DN", "P2P", "Generic"
    uptime: str
    interfaces: List[NetworkInterface] = field(default_factory=list)
    sectors: List[RadioSector] = field(default_factory=list)
    raw_datastore: Dict[str, Any] = field(default_factory=dict)
    last_synced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_operational(self) -> bool:
        return any(iface.oper_status.lower() == "up" for iface in self.interfaces)

    @property
    def max_throughput_gbps(self) -> float:
        speeds = [iface.speed_gbps for iface in self.interfaces if iface.speed_gbps > 0]
        return max(speeds) if speeds else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "node_name": self.node_name,
            "model": self.model,
            "vendor": self.vendor,
            "serial_number": self.serial_number,
            "hardware_rev": self.hardware_rev,
            "software_version": self.software_version,
            "management_ip": self.management_ip,
            "management_port": self.management_port,
            "operation_mode": self.operation_mode,
            "uptime": self.uptime,
            "is_operational": self.is_operational,
            "max_throughput_gbps": self.max_throughput_gbps,
            "interfaces": [
                {
                    "name": i.name,
                    "description": i.description,
                    "type": i.if_type,
                    "speed_gbps": i.speed_gbps,
                    "oper_status": i.oper_status,
                }
                for i in self.interfaces
            ],
            "sectors": [
                {
                    "index": s.index,
                    "frequency_ghz": s.frequency_ghz,
                    "antenna_mode": s.antenna_mode,
                    "mac_address": s.mac_address,
                    "modem_temp_c": s.modem_temperature_c,
                }
                for s in self.sectors
            ],
            "last_synced_at": self.last_synced_at,
        }
