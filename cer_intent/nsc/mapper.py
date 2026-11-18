"""
Slice controller, stage 1: Mapper
=================================
Reads an RFC 9543 Network Slice Service request and extracts what the next
stages need, in the same four parts as the TeraFlowSDN slice controller:

  * Endpoints     the SDPs: node, address, VLAN and IP match criteria
  * SLOs          latency, bandwidth, loss and jitter bounds (per connection
                  group, else from the referenced SLO/SLE template)
  * Connectivity  connection groups and their constructs (sender/receiver SDPs)
  * ACs           attachment circuits: the node and termination point where
                  the customer attaches

Accepted request shapes:
  * the RFC 9543 data tree, with or without the module prefix, wrapping a list
    of slice services or a single slice service;
  * a bare slice-service object;
  * CER-Intent's earlier compact form ({"id", "sdps": [{"node_id", "tp_id",
    "vlan_id", "ip_address"}], "slo_sle_template_ref"}).

Nothing is filled in from defaults: a request with fewer than two SDPs, or an
SDP without a node or termination point, is rejected.
"""
from __future__ import annotations

import ipaddress
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

NSS_PREFIX = "ietf-network-slice-service:"


class MappingError(ValueError):
    """The request cannot be mapped to a slice."""


@dataclass
class AttachmentCircuit:
    ac_id: str
    node_id: str
    tp_id: str
    description: str = ""


@dataclass
class SliceEndpoint:
    sdp_id: str
    node_id: str
    tp_id: str
    ip_address: Optional[str] = None
    prefix_length: Optional[int] = None
    peer_address: Optional[str] = None
    vlan_id: Optional[int] = None
    source_prefixes: List[str] = field(default_factory=list)
    destination_prefixes: List[str] = field(default_factory=list)
    connection_group_id: Optional[str] = None
    attachment_circuits: List[AttachmentCircuit] = field(default_factory=list)


@dataclass
class SLOs:
    max_latency_ms: Optional[float] = None
    bandwidth_mbps: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    jitter_ms: Optional[float] = None
    availability_pct: Optional[float] = None


@dataclass
class ConnectivityConstruct:
    construct_id: str
    sender_sdp: Optional[str]
    receiver_sdp: Optional[str]
    slos: SLOs = field(default_factory=SLOs)


@dataclass
class ConnectionGroup:
    group_id: str
    connectivity_type: str = "point-to-point"
    constructs: List[ConnectivityConstruct] = field(default_factory=list)


@dataclass
class MappedSlice:
    slice_id: str
    description: str
    endpoints: List[SliceEndpoint]
    connection_groups: List[ConnectionGroup]
    slos: SLOs
    sles: Dict[str, Any] = field(default_factory=dict)
    template_ref: Optional[str] = None
    requested_technology: Optional[str] = None
    extensions: Dict[str, Any] = field(default_factory=dict)  # CER-Intent additions (radio, acm, intent text)
    source_format: str = "rfc9543"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _strip(name: Any) -> str:
    return str(name or "").replace(NSS_PREFIX, "")


def _metric_value(bound: Dict[str, Any]) -> Optional[float]:
    for key in ("bound", "value", "metric_value", "percentile-value"):
        if bound.get(key) is not None:
            try:
                return float(bound[key])
            except (TypeError, ValueError):
                return None
    return None


def _to_ms(value: float, unit: str) -> float:
    unit = (unit or "milliseconds").lower()
    if unit.startswith("nano"):
        return value / 1e6
    if unit.startswith("micro"):
        return value / 1e3
    if unit in ("s", "seconds"):
        return value * 1e3
    return value


def _to_mbps(value: float, unit: str) -> float:
    unit = (unit or "mbps").lower()
    return value * {"bps": 1e-6, "kbps": 1e-3, "mbps": 1.0, "gbps": 1e3, "tbps": 1e6}.get(unit, 1.0)


def parse_slos(metric_bounds: List[Dict[str, Any]]) -> SLOs:
    """SLOs from RFC 9543 metric bounds (also accepts CER-Intent's template entries)."""
    slos = SLOs()
    for bound in metric_bounds or []:
        metric = _strip(bound.get("metric-type") or bound.get("metric_type")).lower()
        unit = str(bound.get("metric-unit") or bound.get("metric_unit") or "")
        value = _metric_value(bound)
        if value is None:
            continue
        if "delay" in metric or "latency" in metric:
            slos.max_latency_ms = _to_ms(value, unit)
        elif "bandwidth" in metric:
            slos.bandwidth_mbps = _to_mbps(value, unit)
        elif "loss" in metric:
            slos.packet_loss_pct = value
        elif "jitter" in metric or "delay-variation" in metric:
            slos.jitter_ms = _to_ms(value, unit)
        elif "availability" in metric:
            slos.availability_pct = value
    return slos


def _merge(primary: SLOs, fallback: SLOs) -> SLOs:
    merged = SLOs()
    for name in asdict(merged):
        value = getattr(primary, name)
        setattr(merged, name, value if value is not None else getattr(fallback, name))
    return merged


def _strictest(slos: List[SLOs]) -> SLOs:
    """One SLO set for the slice: tightest latency/loss/jitter, largest bandwidth."""
    out = SLOs()
    for s in slos:
        for name, pick in (("max_latency_ms", min), ("packet_loss_pct", min), ("jitter_ms", min),
                           ("bandwidth_mbps", max), ("availability_pct", max)):
            value = getattr(s, name)
            if value is None:
                continue
            current = getattr(out, name)
            setattr(out, name, value if current is None else pick(current, value))
    return out


def _split_prefix(text: str) -> Tuple[Optional[str], Optional[int]]:
    try:
        iface = ipaddress.ip_interface(text)
    except ValueError:
        return None, None
    return str(iface.ip), (iface.network.prefixlen if "/" in text else None)


# ── Request unwrapping ────────────────────────────────────────────────────────

def unwrap_slice_service(request: Dict[str, Any]) -> Dict[str, Any]:
    """Return the single slice-service object inside any accepted request shape."""
    if not isinstance(request, dict):
        raise MappingError("request body must be a JSON object")
    body = request
    for key in (NSS_PREFIX + "network-slice-services", "network-slice-services"):
        if key in body:
            body = body[key]
            break
    for key in (NSS_PREFIX + "slice-service", "slice-service"):
        if key in body:
            items = body[key]
            if isinstance(items, list):
                if len(items) != 1:
                    raise MappingError("exactly one slice-service per request")
                return items[0]
            return items
    return body


# ── Mapper ─────────────────────────────────────────────────────────────────────

def _endpoint_from_sdp(sdp: Dict[str, Any]) -> SliceEndpoint:
    sdp_id = str(sdp.get("id") or sdp.get("sdp_id") or "")
    node_id = sdp.get("node-id") or sdp.get("node_id")
    acs: List[AttachmentCircuit] = []
    for ac in (sdp.get("attachment-circuits") or {}).get("attachment-circuit", []) or []:
        acs.append(AttachmentCircuit(
            ac_id=str(ac.get("id", len(acs))),
            node_id=str(ac.get("ac-node-id") or node_id or ""),
            tp_id=str(ac.get("ac-tp-id") or ""),
            description=str(ac.get("description", "")),
        ))
    tp_id = (acs[0].tp_id if acs and acs[0].tp_id else None) or sdp.get("tp-id") or sdp.get("tp_id")

    ip_address, prefix_length = None, None
    ips = sdp.get("sdp-ip-address") or sdp.get("ip_address")
    if isinstance(ips, list):
        ips = ips[0] if ips else None
    if ips:
        ip_address, prefix_length = _split_prefix(str(ips))

    vlan_id = sdp.get("vlan_id")
    src_prefixes: List[str] = []
    dst_prefixes: List[str] = []
    group_id = None
    for criterion in (sdp.get("service-match-criteria") or {}).get("match-criterion", []) or []:
        group_id = criterion.get("target-connection-group-id", group_id)
        match_types = criterion.get("match-type", [])
        if isinstance(match_types, dict):
            match_types = [match_types]
        for item in match_types:
            kind = _strip(item.get("type"))
            values = item.get("value", [])
            values = values if isinstance(values, list) else [values]
            if kind in ("vlan", "vlan-id") and values:
                vlan_id = values[0]
            elif kind == "source-ip-prefix":
                src_prefixes.extend(str(v) for v in values)
            elif kind == "destination-ip-prefix":
                dst_prefixes.extend(str(v) for v in values)
        # CER-Intent's earlier flat criteria: {"type": "vlan-id", "value": "100"}
        kind = _strip(criterion.get("type"))
        if kind in ("vlan", "vlan-id") and criterion.get("value") is not None:
            vlan_id = criterion["value"]
        elif kind == "interface" and not tp_id:
            tp_id = criterion.get("value")
        elif kind == "ip-address" and not ip_address:
            ip_address, prefix_length = _split_prefix(str(criterion.get("value")))

    if not node_id or not tp_id:
        raise MappingError(f"SDP '{sdp_id or '?'}' needs a node-id and an attachment circuit (ac-tp-id)")
    if prefix_length is None and src_prefixes:
        _, prefix_length = _split_prefix(src_prefixes[0])

    return SliceEndpoint(
        sdp_id=sdp_id or f"{node_id}:{tp_id}",
        node_id=str(node_id),
        tp_id=str(tp_id),
        ip_address=ip_address,
        prefix_length=prefix_length,
        peer_address=sdp.get("peer_address") or sdp.get("customer_address"),
        vlan_id=int(vlan_id) if vlan_id not in (None, "") else None,
        source_prefixes=src_prefixes,
        destination_prefixes=dst_prefixes,
        connection_group_id=group_id,
        attachment_circuits=acs,
    )


def map_request(request: Dict[str, Any], templates: Optional[Dict[str, Any]] = None) -> MappedSlice:
    """Stage 1 of the slice controller: RFC 9543 request -> MappedSlice."""
    templates = templates or {}
    svc = unwrap_slice_service(request)

    slice_id = svc.get("id") or svc.get("slice_id")
    if not slice_id:
        raise MappingError("slice-service needs an id")

    sdps_raw = svc.get("sdps", [])
    if isinstance(sdps_raw, dict):
        sdps_raw = sdps_raw.get("sdp", [])
    endpoints = [_endpoint_from_sdp(s) for s in sdps_raw or []]
    if len(endpoints) < 2:
        raise MappingError("a slice needs at least two SDPs")

    template_ref = (
        svc.get("slo_sle_template_ref")
        or (svc.get("slo-sle-policy") or {}).get("slo-sle-template")
        or svc.get("slo-sle-template")
    )
    template_slos = SLOs()
    sles: Dict[str, Any] = {}
    template = templates.get(template_ref) if template_ref else None
    if template is not None:
        template_slos = parse_slos(getattr(template, "slos", []) or [])
        for sle in getattr(template, "sles", []) or []:
            sles[str(sle.get("expectation_type"))] = sle.get("expectation_value")
    # Compact form: SLOs given directly on the request take precedence over the template.
    request_slos = SLOs(**{name: float(svc[name]) for name in asdict(SLOs()) if svc.get(name) is not None})
    template_slos = _merge(request_slos, template_slos)

    groups: List[ConnectionGroup] = []
    cg_raw = svc.get("connection-groups") or {}
    for cg in cg_raw.get("connection-group", []) if isinstance(cg_raw, dict) else []:
        group = ConnectionGroup(group_id=str(cg.get("id")), connectivity_type=_strip(cg.get("connectivity-type")) or "point-to-point")
        group_slos = parse_slos(((cg.get("service-slo-sle-policy") or {}).get("slo-policy") or {}).get("metric-bound", []))
        for cc in cg.get("connectivity-construct", []) or []:
            cc_slos = parse_slos(((cc.get("service-slo-sle-policy") or {}).get("slo-policy") or {}).get("metric-bound", []))
            group.constructs.append(ConnectivityConstruct(
                construct_id=str(cc.get("id")),
                sender_sdp=str(cc["p2p-sender-sdp"]) if cc.get("p2p-sender-sdp") is not None else None,
                receiver_sdp=str(cc["p2p-receiver-sdp"]) if cc.get("p2p-receiver-sdp") is not None else None,
                slos=_merge(_merge(cc_slos, group_slos), template_slos),
            ))
        groups.append(group)

    if not groups:  # compact form: one point-to-point group between the first two SDPs
        groups.append(ConnectionGroup(group_id=f"{slice_id}-cg", constructs=[ConnectivityConstruct(
            construct_id="1", sender_sdp=endpoints[0].sdp_id, receiver_sdp=endpoints[1].sdp_id, slos=template_slos)]))

    construct_slos = [cc.slos for g in groups for cc in g.constructs]
    slos = _merge(_strictest(construct_slos), template_slos) if construct_slos else template_slos

    extensions = {k: svc[k] for k in ("radio", "acm", "intent_text") if k in svc}
    return MappedSlice(
        slice_id=str(slice_id),
        description=str(svc.get("description") or f"Network slice {slice_id}"),
        endpoints=endpoints,
        connection_groups=groups,
        slos=slos,
        sles=sles,
        template_ref=template_ref,
        requested_technology=svc.get("realization_technology") or svc.get("technology"),
        extensions=extensions,
        source_format="rfc9543" if ("sdps" in svc and isinstance(svc.get("sdps"), dict)) else "compact",
    )
