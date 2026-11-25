"""OpenSlice catalogue item and order conversion to RFC 9543."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cer_intent.integrations.openslice import OrderError, characteristics_to_rfc9543
from cer_intent.nsc.mapper import map_request
from cer_intent.nsc.technology_selector import select_technology

SPEC = Path(__file__).resolve().parents[1] / "integrations" / "openslice" / "cer-intent-transport-slice.tmf633.json"

ORDER = {
    "sliceId": "osl-slice-1",
    "endpointA": "pe-1:ge-0/0/1",
    "endpointB": "pe-2:ge-0/0/1",
    "endpointAddresses": "10.10.1.1/24, 10.10.2.1/24",
    "vlanId": 300,
    "bandwidthMbps": 400,
    "maxLatencyMs": 8,
    "realizationTechnology": "auto",
    "intentText": "keep latency under 8 ms during rain",
}


def test_catalogue_item_declares_every_ordered_characteristic():
    spec = json.loads(SPEC.read_text())
    names = {c["name"] for c in spec["serviceSpecCharacteristic"]}
    assert set(ORDER) | {"networkSliceService"} <= names
    tech = next(c for c in spec["serviceSpecCharacteristic"] if c["name"] == "realizationTechnology")
    assert {v["value"]["value"] for v in tech["serviceSpecCharacteristicValue"]} == {"auto", "L2VPN", "L3VPN"}


def test_order_becomes_a_slice_the_controller_can_map():
    request = characteristics_to_rfc9543(ORDER)
    mapped = map_request(request)
    assert [ep.node_id for ep in mapped.endpoints] == ["pe-1", "pe-2"]
    assert mapped.endpoints[0].vlan_id == 300 and mapped.endpoints[1].ip_address == "10.10.2.1"
    assert (mapped.slos.bandwidth_mbps, mapped.slos.max_latency_ms) == (400, 8)
    assert mapped.extensions["intent_text"].startswith("keep latency")
    assert select_technology(mapped).technology == "L3VPN"


def test_tmf638_characteristic_list_form():
    as_list = [{"name": k, "value": {"value": v, "alias": ""}} for k, v in ORDER.items()]
    assert characteristics_to_rfc9543(as_list) == characteristics_to_rfc9543(ORDER)


def test_full_request_passes_through():
    full = {"network-slice-services": {"slice-service": [{"id": "x"}]}}
    assert characteristics_to_rfc9543({"networkSliceService": json.dumps(full)}) == full


@pytest.mark.parametrize("change,message", [
    ({"sliceId": ""}, "sliceId"),
    ({"endpointA": "pe-1"}, "endpointA"),
    ({"endpointAddresses": "10.0.0.1/30"}, "two addresses"),
])
def test_incomplete_orders_are_rejected(change, message):
    with pytest.raises(OrderError, match=message):
        characteristics_to_rfc9543({**ORDER, **change})
