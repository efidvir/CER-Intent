"""
IETF Transport Slicing, Topology & Energy Data Models (D3.1 Alignment)
======================================================================
Defines standard-compliant data structures corresponding to:
  1. IETF RFC 9543: Network Slice Service YANG model (ietf-network-slice-service)
     - SLOs (Directly Measurable: bandwidth, latency, jitter, loss)
     - SLEs (Non-Measurable: security, isolation, geographic constraints)
     - SDPs (Service Demarcation Points) & Connectivity Constructs
  2. IETF RFC 9291 (L2SM) & IETF RFC 9182 (L3SM) Service Models
  3. IETF RFC 8345: Network Topology & draft-ietf-teas-network-slice-topology-yang
  4. IETF TVR (Time-Variant Routing): ietf-tvr-topology
  5. Telefónica Transport Energy YANG Models (D3.1 Section 4.2.5):
     - instantaneous-device-energy-tid
     - static-device-energy-tid
  6. RFC 8639 / RFC 8641: IETF Subscribed Notifications
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union


# ---------------------------------------------------------------------------
# 1. IETF RFC 9543: SLO / SLE Templates & Slice Services
# ---------------------------------------------------------------------------

@dataclass
class ServiceLevelObjective:
    """Directly measurable performance metrics (SLOs) - RFC 9543 Sec 3.1"""
    metric_type: str  # e.g., "one-way-delay-maximum", "two-way-delay-maximum", "bandwidth-guaranteed", "packet-loss-ratio"
    metric_unit: str  # "milliseconds", "mbps", "percentage"
    metric_value: float
    slo_status: str = "COMPLIANT"


@dataclass
class ServiceLevelExpectation:
    """Non-measurable operational expectations (SLEs) - RFC 9543 Sec 3.1"""
    expectation_type: str  # "security", "isolation", "geographic-restriction", "availability"
    expectation_value: str  # e.g. "dedicated-hardware", "logical-isolation", "99.999%"
    enforcement_rule: Optional[str] = None


@dataclass
class SLOSLETemplate:
    """
    RFC 9543 slo-sle-template: Reusable template containing measurable SLOs
    and non-measurable SLEs referenced by one or multiple slice services.
    """
    id: str
    description: str
    slos: List[Dict[str, Any]] = field(default_factory=list)
    sles: List[Dict[str, Any]] = field(default_factory=list)

    def to_ietf_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "metric-bounds": {
                "metric-bound": [
                    {
                        "metric-type": slo.get("metric_type"),
                        "metric-unit": slo.get("metric_unit"),
                        "bound": slo.get("metric_value")
                    } for slo in self.slos
                ]
            },
            "service-level-expectations": {
                "expectation": [
                    {
                        "expectation-type": sle.get("expectation_type"),
                        "value": sle.get("expectation_value"),
                        "policy": sle.get("enforcement_rule", "strict")
                    } for sle in self.sles
                ]
            }
        }


@dataclass
class ServiceDemarcationPoint:
    """
    RFC 9543 Service Demarcation Point (SDP):
    The ingress/egress boundaries where the slice service is delivered.
    """
    sdp_id: str
    node_id: str
    tp_id: str  # Termination point (port/interface name)
    ip_address: Optional[str] = None
    vlan_id: Optional[int] = None
    dscp_code: Optional[int] = None

    def to_ietf_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.sdp_id,
            "node-id": self.node_id,
            "service-match-criteria": {
                "match-criterion": [
                    {"type": "interface", "value": self.tp_id}
                ]
            }
        }
        if self.ip_address:
            d["service-match-criteria"]["match-criterion"].append({"type": "ip-address", "value": self.ip_address})
        if self.vlan_id:
            d["service-match-criteria"]["match-criterion"].append({"type": "vlan-id", "value": str(self.vlan_id)})
        if self.dscp_code is not None:
            d["service-match-criteria"]["match-criterion"].append({"type": "dscp", "value": str(self.dscp_code)})
        return d


@dataclass
class ConnectivityConstruct:
    """RFC 9543 connectivity-construct: P2P or P2MP traffic flows between SDPs."""
    construct_id: str
    connectivity_type: str  # "point-to-point" or "point-to-multipoint"
    src_sdp_id: str
    dst_sdp_id: str
    slo_sle_policy: Optional[str] = None


@dataclass
class IETFSliceService:
    """
    Full RFC 9543 Network Slice Service representation.
    """
    slice_id: str
    description: str
    slo_sle_template_ref: str
    sdps: List[ServiceDemarcationPoint] = field(default_factory=list)
    connectivity_constructs: List[ConnectivityConstruct] = field(default_factory=list)
    status: str = "planned"  # "planned", "path-computed", "realized", "active", "degraded"
    
    # Realizer & Planner Outputs (D3.1 Figure 2-18)
    computed_path: List[str] = field(default_factory=list)  # Populated by NDT PCE Planner
    realization_technology: str = "L2SM"  # "L2SM" (RFC 9291) or "L3SM" (RFC 9182)
    controller_reference: str = "TeraFlowSDN"
    created_at: float = field(default_factory=time.time)

    def to_ietf_dict(self) -> Dict[str, Any]:
        return {
            "id": self.slice_id,
            "description": self.description,
            "slo-sle-policy": {
                "slo-sle-template": self.slo_sle_template_ref
            },
            "status": self.status,
            "sdps": {
                "sdp": [sdp.to_ietf_dict() for sdp in self.sdps]
            },
            "connection-groups": {
                "connection-group": [
                    {
                        "id": f"cg-{self.slice_id}",
                        "connectivity-construct": [
                            {
                                "id": cc.construct_id,
                                "type": cc.connectivity_type,
                                "p2p-sender-sdp": cc.src_sdp_id,
                                "p2p-receiver-sdp": cc.dst_sdp_id
                            } for cc in self.connectivity_constructs
                        ]
                    }
                ]
            },
            "custom-topology": {
                "realization-technology": self.realization_technology,
                "computed-path": self.computed_path,
                "controller": self.controller_reference
            }
        }


# ---------------------------------------------------------------------------
# 2. IETF RFC 9291 (L2SM) & IETF RFC 9182 (L3SM) Service Realization
# ---------------------------------------------------------------------------

def generate_ietf_l2sm_payload(slice_service: IETFSliceService, dscp: int = 46) -> Dict[str, Any]:
    """
    Generate an IETF RFC 9291 Layer 2 Service Model (L2SM) configuration payload
    to be ingested by TeraFlowSDN L2VPN NBI.
    """
    vpn_id = f"l2vpn-{slice_service.slice_id}"
    sites = []
    for sdp in slice_service.sdps:
        sites.append({
            "site-id": f"site-{sdp.node_id}",
            "site-network-accesses": {
                "site-network-access": [
                    {
                        "site-network-access-id": f"sna-{sdp.sdp_id}",
                        "bearer": {
                            "bearer-reference": sdp.tp_id
                        },
                        "service": {
                            "svc-qos": {
                                "qos-profile": {
                                    "qos-profile-id": f"qos-{slice_service.slo_sle_template_ref}",
                                    "direction": "both"
                                }
                            }
                        }
                    }
                ]
            }
        })

    return {
        "ietf-l2vpn-svc:l2vpn-svc": {
            "vpn-services": {
                "vpn-service": [
                    {
                        "vpn-id": vpn_id,
                        "vpn-type": "vpws",
                        "customer-name": "UNITY-6G-Transport",
                        "cloud-identifier": "edge-cloud-1",
                        "custom-underlay-path": slice_service.computed_path
                    }
                ]
            },
            "sites": {"site": sites}
        }
    }


def generate_ietf_l3sm_payload(slice_service: IETFSliceService, dscp: int = 46) -> Dict[str, Any]:
    """
    Generate an IETF RFC 9182 Layer 3 Service Model (L3SM) configuration payload
    to be ingested by TeraFlowSDN L3VPN NBI.
    """
    vpn_id = f"l3vpn-{slice_service.slice_id}"
    sites = []
    for sdp in slice_service.sdps:
        sites.append({
            "site-id": f"site-{sdp.node_id}",
            "site-network-accesses": {
                "site-network-access": [
                    {
                        "site-network-access-id": f"sna-{sdp.sdp_id}",
                        "ip-connection": {
                            "ipv4": {
                                "address-allocation-type": "static-address",
                                "addresses": [sdp.ip_address or "10.100.1.1"]
                            }
                        },
                        "routing-protocols": {
                            "routing-protocol": [{"type": "bgp"}]
                        },
                        "service": {
                            "qos": {
                                "qos-classification-policy": {
                                    "rule": [{"id": "dscp-rule", "target-class-id": str(dscp)}]
                                }
                            }
                        }
                    }
                ]
            }
        })

    return {
        "ietf-l3vpn-svc:l3vpn-svc": {
            "vpn-services": {
                "vpn-service": [
                    {
                        "vpn-id": vpn_id,
                        "vpn-description": slice_service.description,
                        "customer-name": "UNITY-6G-Transport",
                        "computed-underlay-hops": slice_service.computed_path
                    }
                ]
            },
            "sites": {"site": sites}
        }
    }


# ---------------------------------------------------------------------------
# 3. IETF RFC 8345 & draft-ietf-teas-network-slice-topology-yang
# ---------------------------------------------------------------------------

@dataclass
class RFC8345Topology:
    """IETF RFC 8345 YANG Data Model for Network Topologies"""
    network_id: str
    network_types: List[str] = field(default_factory=lambda: ["ietf-network-topology:network-topology"])
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, Any]] = field(default_factory=list)

    def to_ietf_dict(self) -> Dict[str, Any]:
        return {
            "ietf-network:network": [
                {
                    "network-id": self.network_id,
                    "network-types": {nt: {} for nt in self.network_types},
                    "node": self.nodes,
                    "ietf-network-topology:link": self.links
                }
            ]
        }


# ---------------------------------------------------------------------------
# 4. IETF TVR (Time-Variant Routing): ietf-tvr-topology (Section 4.2.4.3)
# ---------------------------------------------------------------------------

@dataclass
class TVRScheduleItem:
    """Time-scheduled topological change (e.g. maintenance, weather rain fade, satellite pass)"""
    schedule_id: str
    target_element_id: str  # link-id or node-id
    element_type: str  # "link" or "node"
    start_time_iso: str
    duration_seconds: int
    scheduled_state: str  # "available", "unavailable", "degraded"
    predicted_capacity_mbps: Optional[float] = None
    predicted_attenuation_db: Optional[float] = None
    reason: str = "scheduled-event"


# ---------------------------------------------------------------------------
# 5. Telefónica Transport Energy YANG Models (D3.1 Section 4.2.5, pp. 104-107)
# ---------------------------------------------------------------------------

@dataclass
class InstantaneousDeviceEnergy:
    """YANG module: instantaneous-device-energy-tid (Figure 4-12 & 4-13)"""
    name: str
    power: float  # Watts (W)
    energy_mode: str  # "basic", "saving", "eco-sleep"
    energy_efficiency: float  # Watts per frame per second (W/fps)
    configuration_summary: str
    transceivers_summary: str
    boards_summary: str
    ambient_temperature: float  # °C
    cpu_load: int  # 0..100 %
    fan_speed: int  # RPM or 0..100 %
    traffic_type: str
    traffic_throughput_gbps: float
    traffic_packet_size_bytes: int
    power_supplies: List[Dict[str, Any]] = field(default_factory=list)
    boards: List[Dict[str, Any]] = field(default_factory=list)
    transceivers: List[Dict[str, Any]] = field(default_factory=list)
    components: List[Dict[str, Any]] = field(default_factory=list)

    def to_yang_dict(self) -> Dict[str, Any]:
        return {
            "instantaneous-device-energy-tid:device": {
                "name": self.name,
                "power": str(round(self.power, 2)),
                "energy-mode": self.energy_mode,
                "energy-efficiency": str(round(self.energy_efficiency, 6)),
                "configuration": {
                    "configuration": self.configuration_summary,
                    "transceivers": self.transceivers_summary,
                    "boards": self.boards_summary,
                },
                "performance-metrics": {
                    "ambient-temperature": round(self.ambient_temperature, 1),
                    "cpu-load": self.cpu_load,
                    "fan-speed": self.fan_speed,
                    "traffic-type": self.traffic_type,
                    "traffic-throughput": str(round(self.traffic_throughput_gbps, 3)),
                    "traffic-packet-size": self.traffic_packet_size_bytes,
                },
                "power-supply": self.power_supplies,
                "boards": self.boards,
                "transceivers": self.transceivers,
                "components": self.components,
            }
        }


@dataclass
class StaticDeviceEnergy:
    """YANG module: static-device-energy-tid (Figure 4-14 & 4-15)"""
    name: str
    typical_power: float  # W
    nominal_power: float  # W
    max_power: float  # W
    maximum_traffic_throughput: str  # e.g., "10Gbps"
    efficiency: float  # W/fps
    power_supplies: List[Dict[str, Any]] = field(default_factory=list)
    boards: List[Dict[str, Any]] = field(default_factory=list)
    transceivers: List[Dict[str, Any]] = field(default_factory=list)

    def to_yang_dict(self) -> Dict[str, Any]:
        return {
            "static-device-energy-tid:device": {
                "name": self.name,
                "typical-power": round(self.typical_power, 2),
                "nominal-power": round(self.nominal_power, 2),
                "max-power": round(self.max_power, 2),
                "maximum-traffic-throughput": self.maximum_traffic_throughput,
                "efficiency": round(self.efficiency, 6),
                "power-supply": self.power_supplies,
                "boards": self.boards,
                "transceivers": self.transceivers,
            }
        }


# ---------------------------------------------------------------------------
# 6. RFC 8639 / RFC 8641 IETF Subscribed Notifications
# ---------------------------------------------------------------------------

@dataclass
class IETFTelemetrySubscription:
    """RFC 8639 Subscription to Slice Telemetry & SLO/SLE Compliance"""
    subscription_id: str
    slice_id: str
    notification_destination: str  # URL endpoint for HTTP callbacks
    period_seconds: int = 5
    active: bool = True
    created_at: float = field(default_factory=time.time)
    last_notified: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)
