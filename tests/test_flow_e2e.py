"""
The end-to-end flow: intent -> RFC 9543 slice controller -> NS-3 twin -> TeraFlowSDN
stand-in (the fork's Ceragon handler and driver) -> emulated radios.

The whole stack runs in one Python process on the virtual network
(emulation/vnet.py), in a subprocess so its patches stay out of this test
session. The twin replays recorded NS-3.45 runs. Needs the TeraFlowSDN fork and
the twin repository next to this one (TFS_FORK_SRC, TWIN_SRC).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emulation"))
FORK = Path(os.getenv("TFS_FORK_SRC", str(ROOT.parent / "teraflowsdn" / "src")))
TWIN = Path(os.getenv("TWIN_SRC", str(ROOT.parent / "tfs-ns3-digital-twin")))
RECORDINGS = ROOT / "emulation" / "flow" / "ns3_recordings.json"

needs_stack = pytest.mark.skipif(
    not ((FORK / "device" / "service" / "drivers" / "ceragon").exists()
         and (TWIN / "ceragon_preflight.py").exists() and RECORDINGS.exists()),
    reason="needs the TeraFlowSDN fork and the twin repository next to this one",
)

L2 = "Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; keep the radio link at MCS4 or better"
L2_BIG = "Connect region-a and edge over VLAN 310 with 800 Mbps, at most 10 ms latency and 0.1% loss"
L3 = ("Routed L3VPN slice between region-a 192.0.2.1/30 and edge 198.51.100.1/30 with 50 Mbps "
      "and at most 5 ms latency; keep the radio at MCS6 or better")


# ── parsing and classification (no stack) ────────────────────────────────────

def test_slice_intents_are_parsed_from_text():
    from cer_intent.intent_parser import parse_slice_endpoints

    p = parse_slice_endpoints(L2)["parameters"]
    assert p["slice_id"] == "slice-region-a-edge-300"
    assert [(s["node_id"], s["tp_id"], s["vlan_id"]) for s in p["sdps"]] == [("region-a", "eth1", 300), ("edge", "eth1", 300)]
    assert (p["bandwidth_mbps"], p["max_latency_ms"], p["acm"]) == (500.0, 10.0, {"min_modulation": "MCS4"})

    p = parse_slice_endpoints(L2_BIG)["parameters"]
    assert (p["bandwidth_mbps"], p["packet_loss_pct"], "acm" in p) == (800.0, 0.1, False)

    p = parse_slice_endpoints(L3)["parameters"]
    assert p["realization_technology"] == "L3VPN" and p["vlan_id"] is None
    assert [s["ip_address"] for s in p["sdps"]] == ["192.0.2.1/30", "198.51.100.1/30"]

    assert parse_slice_endpoints("Increase capacity on all links") is None


def test_each_exchange_is_named_by_its_standard():
    from cer_intent.flow.standards import classify

    cases = {
        ("POST", "/api/v1/intent"): "Intent API",
        ("POST", "/restconf/data/ietf-network-slice-service:network-slice-services"): "RFC 9543",
        ("POST", "http://tfs/restconf/data/ietf-l2vpn-svc:l2vpn-svc/vpn-services"): "RFC 8466",
        ("POST", "/restconf/data/ietf-l3vpn-svc:l3vpn-svc/vpn-services"): "RFC 8299",
        ("GET", "/restconf/data/ietf-network:networks/"): "RFC 8345",
        ("GET", "/tfs-api/device/radio-1"): "TFS-API",
        ("PATCH", "http://127.0.0.1:8101/restconf/ds/ietf-datastores:candidate/x:y"): "RFC 8040",
        ("POST", "/restconf/operations/ietf-netconf:commit"): "RFC 8040",
        ("POST", "/api/v1/dti/ceragon/preflight"): "Twin API",
    }
    for (method, url), std in cases.items():
        assert classify(method, url)["std"] == std, url


def test_leaf_diff_names_changed_leaves():
    from cer_intent.flow.routes import leaf_diff

    before = {"/restconf/ub": {"bridge": [{"bridge-id": 38, "bridge-port": [{"bridge-port-id": 1, "c-vlan": 100}]}]}}
    after = {"/restconf/ub": {"bridge": [{"bridge-id": 38, "bridge-port": [{"bridge-port-id": 1, "c-vlan": 100}]},
                                         {"bridge-id": 49, "bridge-port": [{"bridge-port-id": 1, "c-vlan": 300}]}]},
             "/x": {"rssi": -40, "speed": 1}}
    rows = leaf_diff(before, after)
    assert {"resource": "/restconf/ub", "leaf": "bridge[49]/bridge-port[1]/c-vlan", "before": None, "after": 300} in rows
    assert all("rssi" not in r["leaf"] and "speed" not in r["leaf"] for r in rows)


def test_virtual_network_serves_handlers_and_wsgi_apps():
    import requests
    import radio_emulator
    import vnet
    from flask import Flask

    app = Flask("t")
    app.add_url_rule("/hello", "hello", lambda: {"ok": True})
    vnet.install(strict=True)
    vnet.add_wsgi("localhost", 59001, app)
    state = radio_emulator.RadioState("r", "MH-T261", "EMU-r")
    vnet.add_handler("127.0.0.1", 59002, radio_emulator.make_handler(state))
    try:
        assert requests.get("http://localhost:59001/hello").json() == {"ok": True}
        r = requests.get("http://127.0.0.1:59002/restconf/ds/ietf-datastores:running/radio-bridge-tg-system:system")
        assert r.status_code == 200 and r.json()["radio-bridge-tg-system:system"]["name"] == "r"
        with pytest.raises(requests.exceptions.ConnectionError):
            requests.get("http://localhost:59003/")
    finally:
        vnet.remove("localhost", 59001)
        vnet.remove("127.0.0.1", 59002)
        vnet.uninstall()


# ── the whole flow ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("flow")
    env = {**os.environ, "CERAGON_TWIN_BINARY": "", "NS3_TWIN_RECORDINGS": str(RECORDINGS),
           "TFS_FORK_SRC": str(FORK), "TWIN_SRC": str(TWIN), "TMPDIR": str(tmp),
           "STATE_FILE": str(tmp / "state.json"), "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, str(ROOT / "emulation" / "flow_stack.py"), "check"],
                          capture_output=True, text=True, timeout=600, env=env, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout[proc.stdout.index("{"):])


@needs_stack
def test_l2_slice_runs_every_stage_and_is_verified_on_the_radios(flow):
    step = flow["l2"]
    assert flow["existing"] == 201
    assert step["intent"] == 202 and step["strategy"] == "Transport slice through the slice controller"
    assert step["candidate"]["technology"] == "L2VPN" and step["candidate"]["vlan_id"] == 300
    assert step["verdict"] == "pass" and step["engine"] == "replay"
    assert step["approve"] == 200
    checks = {c["id"]: c for c in step["verify"]["checks"]}
    assert step["verify"]["ok"], step["verify"]["checks"]
    assert checks["outcome"]["value"] == "acknowledged_verified"
    assert checks["service"]["value"] == "SERVICESTATUS_ACTIVE"
    assert step["verify"]["radios"]["radio-1"]["vlans"] == [100, 300]
    assert step["verify"]["radios"]["radio-2"]["node_config"]["link-distance"] == "Long"


@needs_stack
def test_twin_holds_a_slice_the_hop_cannot_carry_in_rain(flow):
    step = flow["l2_big"]
    assert step["verdict"] == "fail"
    failed = {c["id"] for c in step["checks"] if not c["ok"]}
    assert "bandwidth" in failed or "loss" in failed
    assert step["approve"] == 409 and "verify" not in step
    l2sm_posts = [e for e in flow["wire"] if e["std"] == "RFC 8466" and e["method"] == "POST"]
    assert len(l2sm_posts) == 1          # only the 500 Mbps slice reached TeraFlowSDN


@needs_stack
def test_removing_the_slice_leaves_only_the_slice_in_service(flow):
    assert flow["remove"] == 204
    assert flow["radios_after_remove"] == {"radio-1": [38], "radio-2": [38]}


@needs_stack
def test_the_wire_shows_every_standard_hop(flow):
    stds = {e["std"] for e in flow["wire"]}
    assert {"Intent API", "RFC 9543", "RFC 8466", "TFS-API", "RFC 8040", "RFC 8345", "Twin API"} <= stds
    assert any(e["std"] == "RFC 9543" and e["transport"] == "in-process" for e in flow["wire"])
    commits = [e for e in flow["wire"] if e["src"] == "TeraFlowSDN" and e["path"].endswith("ietf-netconf:commit")]
    assert {e["dst"] for e in commits} == {"radio-1", "radio-2"}
    assert any(e["src"] == "Digital twin" and e["std"] == "RFC 8345" for e in flow["wire"])
