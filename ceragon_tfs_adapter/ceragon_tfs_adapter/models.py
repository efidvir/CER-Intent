"""
Domain Models for Ceragon Device State, RF Links & Telemetry Streaming
=======================================================================
Normalized representation of physical Ceragon device inventory, interfaces,
radio sectors, active RF links, and real-time Performance Monitoring (PM) streams.
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
    in_errors: int = 0
    out_errors: int = 0
    in_discards: int = 0
    out_discards: int = 0

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
    channel_bandwidth_mhz: Optional[float] = None
    current_modulation: Optional[str] = None
    rsl_dbm: Optional[float] = None
    tsl_dbm: Optional[float] = None
    snr_db: Optional[float] = None

    @property
    def frequency_ghz(self) -> float:
        return round(self.frequency_mhz / 1000.0, 2)


@dataclass
class RadioLinkState:
    """Active RF link state and over-the-air health counters."""
    remote_assigned_name: str
    local_sector_index: int = 1
    remote_sector_index: int = 1
    remote_mac_address: Optional[str] = None
    local_role: str = "initiator"
    uptime_seconds: int = 0
    rssi_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    mcs_tx: Optional[int] = None
    mcs_rx: Optional[int] = None
    tx_power_index: Optional[int] = None
    speed_tx_mbps: Optional[float] = None
    speed_rx_mbps: Optional[float] = None
    tx_per_pct: Optional[float] = None
    rx_per_pct: Optional[float] = None
    beam_azimuth_tx_deg: Optional[int] = None
    beam_elevation_tx_deg: Optional[int] = None
    beam_azimuth_rx_deg: Optional[int] = None
    beam_elevation_rx_deg: Optional[int] = None
    tx_ok_frames: int = 0
    rx_ok_frames: int = 0
    tx_fail_frames: int = 0
    rx_fail_frames: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "remote_assigned_name": self.remote_assigned_name,
            "local_sector_index": self.local_sector_index,
            "remote_sector_index": self.remote_sector_index,
            "remote_mac_address": self.remote_mac_address,
            "local_role": self.local_role,
            "uptime_seconds": self.uptime_seconds,
            "rssi_dbm": self.rssi_dbm,
            "snr_db": self.snr_db,
            "mcs_tx": self.mcs_tx,
            "mcs_rx": self.mcs_rx,
            "tx_power_index": self.tx_power_index,
            "speed_tx_mbps": self.speed_tx_mbps,
            "speed_rx_mbps": self.speed_rx_mbps,
            "tx_per_pct": self.tx_per_pct,
            "rx_per_pct": self.rx_per_pct,
            "beam_azimuth_tx_deg": self.beam_azimuth_tx_deg,
            "beam_elevation_tx_deg": self.beam_elevation_tx_deg,
            "beam_azimuth_rx_deg": self.beam_azimuth_rx_deg,
            "beam_elevation_rx_deg": self.beam_elevation_rx_deg,
            "tx_ok_frames": self.tx_ok_frames,
            "rx_ok_frames": self.rx_ok_frames,
            "tx_fail_frames": self.tx_fail_frames,
            "rx_fail_frames": self.rx_fail_frames,
        }


@dataclass
class PMTelemetrySample:
    """Normalized bidirectional telemetry snapshot across MultiHaul TG, EtherHaul, and CeraOS."""
    device_id: str
    node_name: str
    model: str
    api_flavor: str
    period_type: str = "instantaneous"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    rsl_dbm: Optional[float] = None
    tsl_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    mse_db: Optional[float] = None
    xpi_db: Optional[float] = None
    modulation: Optional[str] = None
    air_capacity_mbps: Optional[float] = None
    in_octets_total: int = 0
    out_octets_total: int = 0
    in_errors_total: int = 0
    out_errors_total: int = 0
    errored_seconds: int = 0
    severely_errored_seconds: int = 0
    unavailable_seconds: int = 0
    modem_temperature_c: Optional[float] = None
    rf_temperature_c: Optional[float] = None
    active_links: List[Dict[str, Any]] = field(default_factory=list)
    pm_intervals: List[Dict[str, Any]] = field(default_factory=list)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "node_name": self.node_name,
            "model": self.model,
            "api_flavor": self.api_flavor,
            "period_type": self.period_type,
            "timestamp": self.timestamp,
            "rsl_dbm": self.rsl_dbm,
            "tsl_dbm": self.tsl_dbm,
            "snr_db": self.snr_db,
            "mse_db": self.mse_db,
            "xpi_db": self.xpi_db,
            "modulation": self.modulation,
            "air_capacity_mbps": self.air_capacity_mbps,
            "in_octets_total": self.in_octets_total,
            "out_octets_total": self.out_octets_total,
            "in_errors_total": self.in_errors_total,
            "out_errors_total": self.out_errors_total,
            "errored_seconds": self.errored_seconds,
            "severely_errored_seconds": self.severely_errored_seconds,
            "unavailable_seconds": self.unavailable_seconds,
            "modem_temperature_c": self.modem_temperature_c,
            "rf_temperature_c": self.rf_temperature_c,
            "active_links": self.active_links,
            "pm_intervals": self.pm_intervals,
            "recent_events": self.recent_events,
        }


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
    operation_mode: str                # "TU", "DN", "P2P", "FDD-P2P"
    uptime: str
    interfaces: List[NetworkInterface] = field(default_factory=list)
    sectors: List[RadioSector] = field(default_factory=list)
    active_links: List[RadioLinkState] = field(default_factory=list)
    yang_modules: List[str] = field(default_factory=list)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)
    raw_datastore: Dict[str, Any] = field(default_factory=dict)
    last_synced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def product_spec(self):
        """Portfolio catalog entry for this device (exact model or family fallback)."""
        from ceragon_tfs_adapter.portfolio import resolve_model
        return resolve_model(self.model)

    @property
    def is_operational(self) -> bool:
        return any(iface.oper_status.lower() == "up" for iface in self.interfaces)

    @property
    def port_throughput_gbps(self) -> float:
        speeds = [iface.speed_gbps for iface in self.interfaces if iface.speed_gbps > 0]
        return max(speeds) if speeds else 1.0

    @property
    def max_throughput_gbps(self) -> float:
        """Nominal radio capacity from the portfolio catalog, else fastest port speed."""
        spec = self.product_spec
        return spec.max_capacity_gbps if spec else self.port_throughput_gbps

    def to_dict(self) -> Dict[str, Any]:
        spec = self.product_spec
        return {
            "device_id": self.device_id,
            "node_name": self.node_name,
            "model": self.model,
            "family": spec.family if spec else None,
            "api_flavor": spec.api_flavor if spec else None,
            "catalog_match": (None if not spec else ("family_fallback" if spec.is_family_fallback else "exact")),
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
                    "in_octets": i.in_octets,
                    "out_octets": i.out_octets,
                    "in_errors": i.in_errors,
                    "out_errors": i.out_errors,
                }
                for i in self.interfaces
            ],
            "sectors": [
                {
                    "index": s.index,
                    "admin_status": s.admin_status,
                    "frequency_ghz": s.frequency_ghz,
                    "frequency_mhz": s.frequency_mhz,
                    "antenna_mode": s.antenna_mode,
                    "mac_address": s.mac_address,
                    "polarity": s.polarity,
                    "tx_power_control": s.tx_power_control,
                    "modem_temp_c": s.modem_temperature_c,
                    "rf_temp_c": s.rf_temperature_c,
                    "rsl_dbm": s.rsl_dbm,
                    "tsl_dbm": s.tsl_dbm,
                    "snr_db": s.snr_db,
                    "current_modulation": s.current_modulation,
                }
                for s in self.sectors
            ],
            "active_links": [lnk.to_dict() for lnk in self.active_links],
            "yang_modules_count": len(self.yang_modules),
            "recent_events": self.recent_events,
            "last_synced_at": self.last_synced_at,
        }
