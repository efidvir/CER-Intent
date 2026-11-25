"""
OpenSlice service characteristics -> RFC 9543 request
=====================================================
The catalogue item ``integrations/openslice/cer-intent-transport-slice.tmf633.json``
lets an OpenSlice user order a CER-Intent transport slice. This module turns
the ordered characteristics (TMF638 service characteristics, or a plain
name -> value dict) into the RFC 9543 request CER-Intent's slice controller
takes, so any OpenSlice controller or LCM rule can forward the order.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Union

Characteristics = Union[Dict[str, Any], Iterable[Dict[str, Any]]]


class OrderError(ValueError):
    """The ordered characteristics do not describe a slice."""


def _flatten(characteristics: Characteristics) -> Dict[str, Any]:
    if isinstance(characteristics, dict):
        return dict(characteristics)
    flat: Dict[str, Any] = {}
    for item in characteristics:
        value = item.get("value")
        if isinstance(value, dict) and "value" in value:
            value = value["value"]
        flat[item.get("name")] = value
    return flat


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _endpoint(text: str, label: str) -> Dict[str, str]:
    if _blank(text) or ":" not in str(text):
        raise OrderError(f"{label} must be node:port")
    node, port = str(text).split(":", 1)
    return {"node": node.strip(), "port": port.strip()}


def characteristics_to_rfc9543(characteristics: Characteristics) -> Dict[str, Any]:
    chars = _flatten(characteristics)
    full = chars.get("networkSliceService")
    if not _blank(full):
        return json.loads(full) if isinstance(full, str) else full

    slice_id = chars.get("sliceId")
    if _blank(slice_id):
        raise OrderError("sliceId is required")
    a = _endpoint(chars.get("endpointA"), "endpointA")
    b = _endpoint(chars.get("endpointB"), "endpointB")
    addresses: List[Optional[str]] = [None, None]
    if not _blank(chars.get("endpointAddresses")):
        parts = [p.strip() for p in str(chars["endpointAddresses"]).split(",")]
        if len(parts) != 2:
            raise OrderError("endpointAddresses needs two addresses")
        addresses = parts
    vlan = None if _blank(chars.get("vlanId")) else str(int(chars["vlanId"]))

    sdps = []
    for sdp_id, ep, address in (("1", a, addresses[0]), ("2", b, addresses[1])):
        match = [{"type": "ietf-network-slice-service:vlan", "value": [vlan]}] if vlan else []
        sdp: Dict[str, Any] = {
            "id": sdp_id,
            "node-id": ep["node"],
            "attachment-circuits": {"attachment-circuit": [{"id": "0", "ac-node-id": ep["node"], "ac-tp-id": ep["port"]}]},
            "service-match-criteria": {"match-criterion": [{"index": 1, "match-type": match,
                                                            "target-connection-group-id": f"{slice_id}-cg"}]},
        }
        if address:
            sdp["sdp-ip-address"] = [address]
        sdps.append(sdp)

    bounds = []
    if not _blank(chars.get("maxLatencyMs")):
        bounds.append({"metric-type": "ietf-network-slice-service:one-way-delay-maximum",
                       "metric-unit": "milliseconds", "bound": float(chars["maxLatencyMs"])})
    if not _blank(chars.get("bandwidthMbps")):
        bounds.append({"metric-type": "ietf-network-slice-service:one-way-bandwidth",
                       "metric-unit": "Mbps", "bound": float(chars["bandwidthMbps"])})
    service: Dict[str, Any] = {
        "id": str(slice_id),
        "description": f"Ordered through OpenSlice: {slice_id}",
        "sdps": {"sdp": sdps},
        "connection-groups": {"connection-group": [{
            "id": f"{slice_id}-cg",
            "connectivity-type": "point-to-point",
            "connectivity-construct": [
                {"id": 1, "p2p-sender-sdp": "1", "p2p-receiver-sdp": "2",
                 "service-slo-sle-policy": {"slo-policy": {"metric-bound": bounds}}},
                {"id": 2, "p2p-sender-sdp": "2", "p2p-receiver-sdp": "1",
                 "service-slo-sle-policy": {"slo-policy": {"metric-bound": bounds}}},
            ],
        }]},
    }
    technology = str(chars.get("realizationTechnology") or "auto")
    if technology.upper() in ("L2VPN", "L3VPN"):
        service["realization_technology"] = technology.upper()
    if not _blank(chars.get("intentText")):
        service["intent_text"] = str(chars["intentText"])
    return {"network-slice-services": {"slice-service": [service]}}
