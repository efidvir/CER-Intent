"""The end-to-end demo's requests, and the demo slice as CER-Intent realizes it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emulation"))

import e2e_demo  # noqa: E402

from cer_intent.nsc.mapper import map_request  # noqa: E402
from cer_intent.nsc.realizer import build_l3sm  # noqa: E402
from cer_intent.nsc.technology_selector import select_technology  # noqa: E402


def test_dry_run_sequence():
    lines = []
    demo = e2e_demo.Demo("http://tfs", "http://cer:5000", dry_run=True, out=lines.append)
    topology = json.loads((ROOT / "emulation/containerlab/tfs-topology.json").read_text())
    request = json.loads((ROOT / "emulation/containerlab/slice-request.json").read_text())
    demo.onboard(topology)
    demo.order_slice(request)
    demo.delete_slice(request["id"])
    assert [(c["method"], c["url"]) for c in demo.sent] == [
        ("POST", "http://tfs/tfs-api/contexts"),
        ("POST", "http://tfs/tfs-api/context/admin/topologies"),
        ("POST", "http://tfs/tfs-api/devices"),
        ("POST", "http://tfs/tfs-api/links"),
        ("POST", "http://cer:5000/restconf/data/ietf-network-slice-service:network-slice-services"),
        ("DELETE", "http://cer:5000/restconf/data/ietf-network-slice-service:network-slice-services/slice-service=slice-dc1-dc2"),
    ]
    assert e2e_demo.main(["--dry-run"]) == 0


def test_topology_links_the_radios_between_r2_and_r3():
    topology = json.loads((ROOT / "emulation/containerlab/tfs-topology.json").read_text())
    radios = [d for d in topology["devices"] if d["device_type"] == "ceragon-wireless"]
    assert {d["device_drivers"][0] for d in radios} == {"DEVICEDRIVER_CERAGON"}
    link_ids = {l["link_id"]["link_uuid"]["uuid"] for l in topology["links"]}
    assert {"r2/Ethernet3==radio-a/eth1", "radio-a/rf-sector-1==radio-b/rf-sector-1", "radio-b/eth1==r3/Ethernet2"} <= link_ids


def test_demo_slice_becomes_the_l3vpn_teraflowsdn_tests_with():
    request = json.loads((ROOT / "emulation/containerlab/slice-request.json").read_text())
    mapped = map_request(request)
    assert select_technology(mapped).technology == "L3VPN"
    payload, defaults = build_l3sm(mapped)
    assert defaults == {}
    sna = payload["ietf-l3vpn-svc:l3vpn-svc"]["sites"]["site"][0]["site-network-accesses"]["site-network-access"][0]
    # same access as TeraFlowSDN's eucnc24 L3VPN test: dc1/eth1, 172.16.1.1 <-> 172.16.1.10 /24
    assert (sna["device-reference"], sna["site-network-access-id"]) == ("dc1", "eth1")
    assert sna["ip-connection"]["ipv4"]["addresses"] == {
        "provider-address": "172.16.1.1", "customer-address": "172.16.1.10", "prefix-length": 24}
