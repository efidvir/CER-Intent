"""
Slice controller, stage 3: Realizer
===================================
Turns a mapped slice and the chosen technology into the request for the
TeraFlowSDN controller, as the TeraFlowSDN slice controller does:

  L2VPN -> L2SM, RFC 8466 (ietf-l2vpn-svc) on TFS's L2VPN interface
  L3VPN -> L3SM, RFC 8299 (ietf-l3vpn-svc) on TFS's L3VPN interface

The payloads follow the shapes TeraFlowSDN's IETF interfaces accept (strict
YANG validation). How the request leaves CER-Intent is set by TFS_REALIZATION:

  ietf       (default) send L2SM / L3SM to the TeraFlowSDN controller
  nsc        hand the RFC 9543 request to a TeraFlowSDN slice controller
  tfs-api    earlier behaviour: a custom TFS slice object (kept for the demo)
  dry-run    build everything, send nothing

Radio and ACM settings, decided by CER-Intent's skills, have no place in the
IETF models. They travel as TeraFlowSDN service settings (the "/settings"
rule of the service the VPN created), where the Ceragon service handler
applies them by fixed rules.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cer_intent.nsc.mapper import MappedSlice, SliceEndpoint
from cer_intent.nsc.technology_selector import L2VPN, L3VPN

logger = logging.getLogger("NSC.Realizer")

MODES = ("ietf", "nsc", "tfs-api", "dry-run")
DEFAULT_LATENCY_MS = float(os.getenv("NSC_DEFAULT_LATENCY_MS", "100"))
DEFAULT_MTU = int(os.getenv("NSC_DEFAULT_MTU", "1500"))


class RealizationError(ValueError):
    """The slice cannot be expressed in the chosen technology."""


def realization_mode() -> str:
    mode = os.getenv("TFS_REALIZATION", "ietf").strip().lower()
    return mode if mode in MODES else "ietf"


@dataclass
class Realization:
    slice_id: str
    technology: str
    mode: str
    status: str = "built"                 # built | sent | failed
    payload: Dict[str, Any] = field(default_factory=dict)
    service_settings: Dict[str, Any] = field(default_factory=dict)
    controller_response: Any = None
    defaults_used: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "technology": self.technology,
            "model": "L3SM (RFC 8299)" if self.technology == L3VPN else "L2SM (RFC 8466)",
            "mode": self.mode,
            "status": self.status,
            "payload": self.payload,
            "service_settings": self.service_settings,
            "controller_response": self.controller_response,
            "defaults_used": self.defaults_used,
            "error": self.error,
        }


# ── Payload builders ────────────────────────────────────────────────────────────

def _bandwidth_bps(mapped: MappedSlice) -> Optional[int]:
    if mapped.slos.bandwidth_mbps is None:
        return None
    return int(round(mapped.slos.bandwidth_mbps * 1e6))


def _lan_prefix(ep: SliceEndpoint, customer: str, prefix_len: int) -> str:
    if ep.source_prefixes:
        return str(ipaddress.ip_interface(ep.source_prefixes[0]).network)
    return str(ipaddress.ip_interface(f"{customer}/{prefix_len}").network)


def build_l3sm(mapped: MappedSlice, mtu: int = DEFAULT_MTU) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """RFC 8299 request for TeraFlowSDN's L3VPN interface, and the defaults it needed."""
    defaults: Dict[str, Any] = {}
    latency = mapped.slos.max_latency_ms
    if latency is None:
        latency = DEFAULT_LATENCY_MS
        defaults["latency-boundary"] = latency
    bandwidth = _bandwidth_bps(mapped)
    if bandwidth is None:
        raise RealizationError("an L3VPN needs a bandwidth SLO (one-way-bandwidth)")

    vpn_id = mapped.slice_id
    sites: List[Dict[str, Any]] = []
    for i, ep in enumerate(mapped.endpoints):
        if not ep.ip_address:
            raise RealizationError(f"SDP '{ep.sdp_id}' has no IP address; an L3VPN needs one per SDP")
        prefix_len = ep.prefix_length or 24
        if ep.prefix_length is None:
            defaults.setdefault("prefix-length", prefix_len)
        customer = ep.peer_address or ep.ip_address
        site: Dict[str, Any] = {
            "site-id": f"site_{ep.sdp_id}",
            "management": {"type": "ietf-l3vpn-svc:provider-managed"},
            "locations": {"location": [{"location-id": ep.node_id}]},
            "devices": {"device": [{"device-id": ep.node_id, "location": ep.node_id}]},
            "site-network-accesses": {"site-network-access": [{
                "site-network-access-id": ep.tp_id,
                "site-network-access-type": "ietf-l3vpn-svc:multipoint",
                "device-reference": ep.node_id,
                "vpn-attachment": {
                    "vpn-id": vpn_id,
                    "site-role": "ietf-l3vpn-svc:hub-role" if i == 0 else "ietf-l3vpn-svc:spoke-role",
                },
                "ip-connection": {"ipv4": {
                    "address-allocation-type": "ietf-l3vpn-svc:static-address",
                    "addresses": {
                        "provider-address": ep.ip_address,
                        "customer-address": customer,
                        "prefix-length": prefix_len,
                    },
                }},
                "service": {
                    "svc-mtu": mtu,
                    "svc-input-bandwidth": bandwidth,
                    "svc-output-bandwidth": bandwidth,
                    "qos": {"qos-profile": {"classes": {"class": [{
                        "class-id": "qos-realtime",
                        "direction": "ietf-l3vpn-svc:both",
                        "latency": {"latency-boundary": latency},
                        "bandwidth": {"guaranteed-bw-percent": 100},
                    }]}}},
                },
            }]},
        }
        if ep.vlan_id is not None:
            # TeraFlowSDN takes the access VLAN (the tag on the PE's access interface) from a
            # static route whose next hop is in the attachment subnet.
            site["routing-protocols"] = {"routing-protocol": [{
                "type": "ietf-l3vpn-svc:static",
                "static": {"cascaded-lan-prefixes": {"ipv4-lan-prefixes": [{
                    "lan": _lan_prefix(ep, customer, prefix_len),
                    "lan-tag": str(ep.vlan_id),
                    "next-hop": customer,
                }]}},
            }]}
        sites.append(site)
    payload = {"ietf-l3vpn-svc:l3vpn-svc": {
        "vpn-services": {"vpn-service": [{"vpn-id": vpn_id}]},
        "sites": {"site": sites},
    }}
    return payload, defaults


def build_l2sm(mapped: MappedSlice, mtu: int = DEFAULT_MTU) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """RFC 8466 request for TeraFlowSDN's L2VPN interface, and the defaults it needed."""
    defaults: Dict[str, Any] = {}
    vlans = {ep.vlan_id for ep in mapped.endpoints if ep.vlan_id is not None}
    if not vlans:
        raise RealizationError("an L2VPN needs a VLAN on the SDPs (vlan match criterion)")
    vpn_id = mapped.slice_id
    bandwidth = _bandwidth_bps(mapped)
    sites: List[Dict[str, Any]] = []
    for ep in mapped.endpoints:
        vlan = ep.vlan_id if ep.vlan_id is not None else sorted(vlans)[0]
        service: Dict[str, Any] = {"svc-mtu": mtu}
        if bandwidth is not None:
            service["svc-input-bandwidth"] = bandwidth
            service["svc-output-bandwidth"] = bandwidth
        if mapped.slos.max_latency_ms is not None:
            service["qos"] = {"qos-profile": {"classes": {"class": [{
                "class-id": "qos-realtime",
                "direction": "ietf-l2vpn-svc:both",
                "latency": {"latency-boundary": mapped.slos.max_latency_ms},
                "bandwidth": {"guaranteed-bw-percent": 100},
            }]}}}
        sites.append({
            "site-id": f"site_{ep.sdp_id}",
            "management": {"type": "ietf-l2vpn-svc:provider-managed"},
            "locations": {"location": [{"location-id": ep.node_id}]},
            "devices": {"device": [{"device-id": ep.node_id, "location": ep.node_id}]},
            "default-ce-vlan-id": 1,
            "site-network-accesses": {"site-network-access": [{
                "network-access-id": ep.tp_id,
                "type": "ietf-l2vpn-svc:multipoint",
                "device-reference": ep.node_id,
                "vpn-attachment": {"vpn-id": vpn_id, "site-role": "ietf-l2vpn-svc:any-to-any-role"},
                "bearer": {"bearer-reference": f"{ep.node_id}:{ep.tp_id}"},
                "service": service,
                "connection": {
                    "encapsulation-type": "vlan",
                    "eth-inf-type": "ietf-l2vpn-svc:tagged",
                    "tagged-interface": {
                        "type": "ietf-l2vpn-svc:dot1q",
                        "dot1q-vlan-tagged": {"cvlan-id": vlan},
                    },
                },
            }]},
        })
    payload = {"ietf-l2vpn-svc:l2vpn-svc": {
        "vpn-services": {"vpn-service": [{
            "vpn-id": vpn_id,
            "vpn-svc-type": "vpws" if len(mapped.endpoints) == 2 else "vpls",
            "svc-topo": "any-to-any",
            "customer-name": "cer-intent",
            "ce-vlan-preservation": True,
            "ce-vlan-cos-preservation": True,
        }]},
        "sites": {"site": sites},
    }}
    return payload, defaults


def build_rfc9543(mapped: MappedSlice) -> Dict[str, Any]:
    """RFC 9543 request in the shape TeraFlowSDN's slice controller accepts (two SDPs, one AC each)."""
    group_id = mapped.connection_groups[0].group_id if mapped.connection_groups else f"{mapped.slice_id}-cg"
    sdps = []
    for ep in mapped.endpoints:
        match_types = []
        if ep.vlan_id is not None:
            match_types.append({"type": "ietf-network-slice-service:vlan", "value": [str(ep.vlan_id)]})
        for prefix in ep.source_prefixes:
            match_types.append({"type": "ietf-network-slice-service:source-ip-prefix", "value": [prefix]})
        for prefix in ep.destination_prefixes:
            match_types.append({"type": "ietf-network-slice-service:destination-ip-prefix", "value": [prefix]})
        sdp: Dict[str, Any] = {
            "id": ep.sdp_id,
            "node-id": ep.node_id,
            "attachment-circuits": {"attachment-circuit": [{
                "id": ep.attachment_circuits[0].ac_id if ep.attachment_circuits else "0",
                "ac-node-id": ep.node_id,
                "ac-tp-id": ep.tp_id,
            }]},
            "service-match-criteria": {"match-criterion": [{
                "index": 1, "match-type": match_types, "target-connection-group-id": group_id,
            }]},
        }
        if ep.ip_address:
            sdp["sdp-ip-address"] = [ep.ip_address]
        sdps.append(sdp)

    def bounds(slos) -> List[Dict[str, Any]]:
        out = []
        if slos.max_latency_ms is not None:
            out.append({"metric-type": "ietf-network-slice-service:one-way-delay-maximum",
                        "metric-unit": "milliseconds", "bound": slos.max_latency_ms})
        if slos.bandwidth_mbps is not None:
            out.append({"metric-type": "ietf-network-slice-service:one-way-bandwidth",
                        "metric-unit": "Mbps", "bound": slos.bandwidth_mbps})
        if slos.packet_loss_pct is not None:
            out.append({"metric-type": "ietf-network-slice-service:two-way-packet-loss",
                        "metric-unit": "percentage", "percentile-value": slos.packet_loss_pct})
        return out

    constructs = []
    for group in mapped.connection_groups[:1]:
        for cc in group.constructs:
            constructs.append({
                "id": cc.construct_id,
                "p2p-sender-sdp": cc.sender_sdp,
                "p2p-receiver-sdp": cc.receiver_sdp,
                "service-slo-sle-policy": {"slo-policy": {"metric-bound": bounds(cc.slos)}},
            })
    return {"network-slice-services": {"slice-service": [{
        "id": mapped.slice_id,
        "description": mapped.description,
        "sdps": {"sdp": sdps},
        "connection-groups": {"connection-group": [{
            "id": group_id,
            "connectivity-type": "point-to-point",
            "connectivity-construct": constructs,
        }]},
    }]}}


def service_settings_for(mapped: MappedSlice) -> Dict[str, Any]:
    """TFS service settings carrying what the IETF models cannot: radio and ACM decisions."""
    settings: Dict[str, Any] = {}
    for key in ("radio", "acm"):
        value = mapped.extensions.get(key)
        if isinstance(value, dict) and value:
            settings[key] = value
    return settings


# ── Realizer ───────────────────────────────────────────────────────────────────

class Realizer:
    def __init__(self, tfs_client=None, mode: Optional[str] = None):
        self.tfs_client = tfs_client
        self.mode = mode or realization_mode()

    def build(self, mapped: MappedSlice, technology: str) -> Realization:
        result = Realization(slice_id=mapped.slice_id, technology=technology, mode=self.mode)
        try:
            if self.mode == "nsc":
                result.payload = build_rfc9543(mapped)
            elif technology == L2VPN:
                result.payload, result.defaults_used = build_l2sm(mapped)
            else:
                result.payload, result.defaults_used = build_l3sm(mapped)
        except RealizationError as e:
            result.status, result.error = "failed", str(e)
            return result
        result.service_settings = service_settings_for(mapped)
        return result

    def realize(self, mapped: MappedSlice, technology: str) -> Realization:
        result = self.build(mapped, technology)
        if result.status == "failed" or self.mode in ("dry-run", "tfs-api"):
            return result
        if self.tfs_client is None:
            result.status, result.error = "failed", "no TeraFlowSDN client configured"
            return result
        try:
            if self.mode == "nsc":
                result.controller_response = self.tfs_client.create_network_slice(result.payload)
            elif technology == L2VPN:
                result.controller_response = self.tfs_client.create_l2vpn(result.payload)
            else:
                result.controller_response = self.tfs_client.create_l3vpn(result.payload)
            if result.service_settings and self.mode == "ietf":
                self.tfs_client.update_service_settings(mapped.slice_id, result.service_settings)
            result.status = "sent"
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Realization of %s failed: %s", mapped.slice_id, e)
            result.status, result.error = "failed", str(e)
        return result

    def withdraw(self, slice_id: str, technology: str) -> Dict[str, Any]:
        if self.mode in ("dry-run", "tfs-api") or self.tfs_client is None:
            return {"slice_id": slice_id, "status": "local-only"}
        try:
            if self.mode == "nsc":
                self.tfs_client.delete_network_slice(slice_id)
            elif technology == L2VPN:
                self.tfs_client.delete_l2vpn(slice_id)
            else:
                self.tfs_client.delete_l3vpn(slice_id)
            return {"slice_id": slice_id, "status": "withdrawn"}
        except Exception as e:  # pylint: disable=broad-except
            return {"slice_id": slice_id, "status": "failed", "error": str(e)}
