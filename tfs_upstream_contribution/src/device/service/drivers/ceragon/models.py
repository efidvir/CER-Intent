# Copyright 2026 Ceragon Networks Ltd. & ETSI TeraFlowSDN Authors
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Normalized Domain Models for Ceragon Wireless Transport Devices
================================================================
Defines structured dataclasses representing physical chassis, radio sectors,
Ethernet ports, and operating parameters aligned with ETSI TeraFlowSDN schemas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CeragonHardwareInfo:
    """Hardware inventory & physical identification."""
    vendor: str = "Ceragon"
    model: str = "MH-T261"
    serial_number: str = ""
    hardware_rev: str = "A0"
    software_version: str = ""
    management_ip: str = "127.0.0.1"
    management_port: int = 80
    uptime: str = ""
    device_type: str = "teragroup-tu"  # "teragroup-tu", "etherhaul-eband", "ceraos-microwave"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CeragonInterface:
    """Physical or logical network endpoint."""
    name: str
    interface_type: str = "ethernetCsmacd"
    oper_status: str = "up"
    admin_status: str = "up"
    speed_bps: int = 1_000_000_000
    mtu: int = 1500
    mac_address: str = ""
    peer_device_id: Optional[str] = None
    peer_endpoint_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CeragonRadioSector:
    """Wireless radio frequency sector & beamforming parameters."""
    sector_id: str
    frequency_mhz: float = 60480.0
    channel_id: int = 2
    bandwidth_mhz: float = 2160.0
    tx_power_dbm: float = 20.0
    atpc_enabled: bool = True
    current_mcs: str = "MCS9"
    min_mcs_floor: str = "MCS2"  # Hardened floor during rain fade
    max_mcs_ceiling: str = "MCS12"
    antenna_profile: str = "massive2"
    beamforming_capable: bool = True
    polarization: str = "vertical"
    oper_status: str = "up"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CeragonOperatingParameters:
    """Real-time operational parameters & telemetry."""
    frequency_ghz: float = 60.48
    frequency_mhz: float = 60480.0
    channel_id: int = 2
    tx_power_control: str = "auto"
    tx_power_dbm: float = 20.0
    modem_temperature_c: int = 61
    rf_temperature_c: int = 58
    snr_db: float = 28.5
    rssi_dbm: float = -42.0
    link_loss_ratio: float = 0.0
    admin_status: str = "up"
    oper_status: str = "up"
    active_slice_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CeragonDeviceState:
    """Comprehensive device state snapshot for TeraFlowSDN driver."""
    hardware_info: CeragonHardwareInfo = field(default_factory=CeragonHardwareInfo)
    operating_parameters: CeragonOperatingParameters = field(default_factory=CeragonOperatingParameters)
    interfaces: List[CeragonInterface] = field(default_factory=list)
    radio_sectors: List[CeragonRadioSector] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    applied_configs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hardware_info": self.hardware_info.to_dict(),
            "operating_parameters": self.operating_parameters.to_dict(),
            "interfaces": [i.to_dict() for i in self.interfaces],
            "radio_sectors": [s.to_dict() for s in self.radio_sectors],
            "capabilities": self.capabilities,
            "applied_configs": self.applied_configs,
        }
