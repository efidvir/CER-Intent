"""
Dashboard view of the ETSI chain: the planner's topology file, the status and
what-if endpoints behind slice-controller.html, and the page itself.
"""
import json
import re
from pathlib import Path

import pytest
import requests
from flask import Flask

from cer_intent.nsc import reset_shared_controller, shared_controller
from cer_intent.nsc.topology_file import load_topology_file, normalize_descriptor

ROOT = Path(__file__).resolve().parents[1]
TESTBED = ROOT / "emulation" / "containerlab" / "tfs-topology.json"
REQUEST = ROOT / "emulation" / "containerlab" / "slice-request.json"
SLICES = "/restconf/data/ietf-network-slice-service:network-slice-services"


@pytest.fixture
def app(monkeypatch):
    from cer_intent.api import etsi_routes, restconf_routes

    monkeypatch.setenv("TFS_REALIZATION", "dry-run")
    monkeypatch.setenv("CER_INTENT_TOPOLOGY_FILE", str(TESTBED))
    monkeypatch.setenv("CER_INTENT_MCP_MODE", "advise")
    reset_shared_controller()
    monkeypatch.setattr(restconf_routes, "_nsc_instance", None)
    flask_app = Flask(__name__)
    flask_app.config["adapter"] = None
    flask_app.register_blueprint(restconf_routes.restconf_bp)
    flask_app.register_blueprint(etsi_routes.etsi_bp)
    yield flask_app
    reset_shared_controller()


# ── Topology file ───────────────────────────────────────────────────────────────

def test_descriptor_becomes_one_edge_per_link():
    topo = normalize_descriptor(json.loads(TESTBED.read_text()), source="file:test")
    assert sorted(n["id"] for n in topo["nodes"]) == ["dc1", "dc2", "r1", "r2", "r3", "radio-a", "radio-b"]
    assert len(topo["links"]) == 6  # the descriptor lists both directions
    radio = [l for l in topo["links"] if l["type"] == "wireless-microwave"]
    assert len(radio) == 1 and {radio[0]["source"], radio[0]["target"]} == {"radio-a", "radio-b"}
    assert {n["id"] for n in topo["nodes"] if n["role"] == "radio"} == {"radio-a", "radio-b"}


def test_link_capacity_attribute_is_read():
    data = {"devices": [{"device_id": {"device_uuid": {"uuid": "a"}}}, {"device_id": {"device_uuid": {"uuid": "b"}}}],
            "links": [{"link_id": {"link_uuid": {"uuid": "a==b"}}, "attributes": {"total_capacity_gbps": 1.8},
                       "link_endpoint_ids": [{"device_id": {"device_uuid": {"uuid": "a"}}, "endpoint_uuid": {"uuid": "1"}},
                                             {"device_id": {"device_uuid": {"uuid": "b"}}, "endpoint_uuid": {"uuid": "1"}}]}]}
    assert normalize_descriptor(data)["links"][0]["capacity_mbps"] == 1800.0


def test_unset_or_unreadable_file_gives_none(monkeypatch, tmp_path):
    monkeypatch.delenv("CER_INTENT_TOPOLOGY_FILE", raising=False)
    assert load_topology_file() is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_topology_file(str(bad)) is None


def test_planner_checks_the_path_over_the_testbed(monkeypatch):
    monkeypatch.setenv("TFS_REALIZATION", "dry-run")
    monkeypatch.setenv("CER_INTENT_TOPOLOGY_FILE", str(TESTBED))
    reset_shared_controller()
    nsc = shared_controller(tfs_client=None)
    res = nsc.create_or_update_slice_service(json.loads(REQUEST.read_text()))
    plan = res["nsc_pipeline"]["planner"]
    assert plan["feasible"] is True
    assert plan["computed_path"] == ["dc1", "r1", "r2", "radio-a", "radio-b", "r3", "dc2"]
    assert nsc.topology_source == "file:tfs-topology.json"
    reset_shared_controller()


# ── Endpoints ───────────────────────────────────────────────────────────────────

def test_status_reports_mode_topology_tools_and_slices(app):
    client = app.test_client()
    st = client.get("/api/v1/etsi/status").get_json()
    assert st["realization"] == {"mode": "dry-run", "controller_configured": False}
    assert st["topology"]["source"] == "file:tfs-topology.json"
    assert len(st["topology"]["nodes"]) == 7 and len(st["topology"]["links"]) == 6
    tools = {t["name"]: t for t in st["mcp"]["tools"]}
    assert st["mcp"]["mode"] == "advise"
    assert tools["preview_network_slice"]["read_only"] and tools["delete_network_slice"]["destructive"]
    assert st["slices"] == []

    assert client.post(SLICES, json=json.loads(REQUEST.read_text())).status_code == 201
    (row,) = client.get("/api/v1/etsi/status").get_json()["slices"]
    assert row["id"] == "slice-dc1-dc2" and row["technology"] == "L3VPN" and row["model"] == "L3SM"
    assert row["mode"] == "dry-run" and row["realization_status"] == "built" and row["status"] == "planned"
    assert len(row["path"]) == 7


def test_what_if_is_labelled_simulated(app, monkeypatch):
    from cer_intent.api import etsi_routes
    monkeypatch.setattr(etsi_routes, "run_what_if", lambda scenario: {"predicted_impacts": [], "insight": "measured?"})
    body = app.test_client().post("/api/v1/etsi/what-if", json={"perturbations": []}).get_json()
    assert body["insight"] == "simulated"


def test_what_if_without_a_twin_is_503(app, monkeypatch):
    from cer_intent.api import etsi_routes

    def down(scenario):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(etsi_routes, "run_what_if", down)
    res = app.test_client().post("/api/v1/etsi/what-if", json={})
    assert res.status_code == 503 and res.get_json()["insight"] == "simulated"


# ── Page ────────────────────────────────────────────────────────────────────────

def test_page_is_linked_and_carries_no_lab_literals():
    page = (ROOT / "dashboard" / "slice-controller.html").read_text()
    for name in ("flow.html", "index.html"):
        assert "/slice-controller.html" in (ROOT / "dashboard" / name).read_text()
    for api in ("/api/v1/etsi/status", "/api/v1/etsi/what-if", "ietf-network-slice-service:network-slice-services"):
        assert api in page
    assert not re.search(r"cersrv|ctu-\d+|:8088|MH-T\d+|\b10\.\d+\.\d+\.\d+", page)
