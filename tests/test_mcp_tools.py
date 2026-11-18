"""MCP tools: advise/act authority, slice lifecycle, radio-link view, twin labelling, registration."""
from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from cer_intent.mcp import tools
from cer_intent.nsc import reset_shared_controller

from tests.test_nsc_pipeline import FakeTFS, rfc9543


@pytest.fixture
def fake_tfs(monkeypatch):
    reset_shared_controller()
    monkeypatch.setenv("TFS_REALIZATION", "ietf")
    fake = FakeTFS()
    tools.CONTEXT.tfs = fake
    yield fake
    tools.CONTEXT.tfs = None
    reset_shared_controller()


def test_advise_mode_previews_without_touching_the_network(fake_tfs, monkeypatch):
    monkeypatch.delenv("CER_INTENT_MCP_MODE", raising=False)
    out = tools.create_network_slice(rfc9543())
    assert out["mode"] == "advise" and out["applied"] is False
    assert out["preview"]["technology"]["technology"] == "L3VPN"
    assert "ietf-l3vpn-svc:l3vpn-svc" in out["preview"]["realization"]["payload"]
    assert tools.delete_network_slice("slice-a")["applied"] is False
    assert fake_tfs.names() == []


def test_act_mode_runs_the_slice_lifecycle(fake_tfs, monkeypatch):
    monkeypatch.setenv("CER_INTENT_MCP_MODE", "act")
    created = tools.create_network_slice(rfc9543())
    assert created["applied"] is True
    assert tools.list_network_slices()["slices"][0]["id"] == "slice-a"
    assert tools.get_network_slice("slice-a")["realization"]["technology"] == "L3VPN"
    deleted = tools.delete_network_slice("slice-a")
    assert deleted["applied"] is True
    assert fake_tfs.names() == ["create_l3vpn", "delete_l3vpn"]
    assert "error" in tools.get_network_slice("slice-a")


def test_preview_reports_mapping_errors(fake_tfs):
    assert tools.preview_network_slice({"id": "x"})["stage"] == "mapper"


def test_radio_link_view_comes_from_the_device_config(monkeypatch):
    view = {"ietf-interfaces:interfaces": {"interface": [{"name": "rf-sector-1"}]}}

    class TFS:
        def get_device(self, device):
            return {"device_config": {"config_rules": [
                {"custom": {"resource_key": "/device/hardware_info", "resource_value": "{}"}},
                {"custom": {"resource_key": "/microwave-radio-link", "resource_value": json.dumps(view)}},
            ]}}

    tools.CONTEXT.tfs = TFS()
    try:
        assert tools.get_radio_link("radio-a") == view
    finally:
        tools.CONTEXT.tfs = None


def test_what_if_answers_are_labelled_simulated(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"predicted_capacity_gbps": 0.8}

    monkeypatch.setattr(tools.requests, "post", lambda *a, **k: Resp())
    assert tools.run_what_if({"rain_mm_h": 30})["insight"] == "simulated"


def test_registration_on_the_mcp_sdk_server():
    from cer_intent.mcp.server import build_server

    server = build_server()
    listed = server.list_tools()
    listed = asyncio.run(listed) if inspect.isawaitable(listed) else listed
    by_name = {t.name: t for t in listed}
    assert set(by_name) == {spec.name for spec in tools.TOOLS}
    delete = by_name["delete_network_slice"].annotations.model_dump(by_alias=True)
    assert delete["destructiveHint"] is True and delete["readOnlyHint"] is False


def test_registration_on_a_server_without_annotations():
    class OldServer:
        def __init__(self):
            self.added = []

        def add_tool(self, fn, name=None, description=None):
            self.added.append((name, description))

    server = OldServer()
    names = tools.register(server, prefix="cer_")
    assert names[0] == "cer_preview_network_slice" and len(server.added) == len(tools.TOOLS)


def test_proxy_mode_uses_the_api_slice_datastore(monkeypatch):
    """With CER_INTENT_MCP_PROXY=1 the tools go through the API's RFC 9543 interface."""
    from flask import Flask
    from cer_intent.api import restconf_routes

    monkeypatch.setenv("TFS_REALIZATION", "dry-run")
    monkeypatch.setenv("CER_INTENT_MCP_MODE", "act")
    monkeypatch.setenv("CER_INTENT_MCP_PROXY", "1")
    reset_shared_controller()
    monkeypatch.setattr(restconf_routes, "_nsc_instance", None)
    app = Flask(__name__)
    app.config["adapter"] = None
    app.register_blueprint(restconf_routes.restconf_bp)
    client = app.test_client()

    class Resp:
        def __init__(self, r):
            self.status_code, self._r = r.status_code, r

        def json(self):
            return self._r.get_json()

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    def path(url):
        return url.split("localhost:5000", 1)[1]

    monkeypatch.setattr(tools.requests, "post", lambda url, json=None, timeout=None: Resp(client.post(path(url), json=json)))
    monkeypatch.setattr(tools.requests, "get", lambda url, timeout=None: Resp(client.get(path(url))))
    monkeypatch.setattr(tools.requests, "delete", lambda url, timeout=None: Resp(client.delete(path(url))))

    created = tools.create_network_slice(rfc9543())
    assert created["pipeline"]["realizer"]["status"] == "built"   # dry-run in the API process
    assert [s["id"] for s in tools.list_network_slices()["slices"]] == ["slice-a"]
    assert tools.get_network_slice("slice-a")["slice-service"]["id"] == "slice-a"
    assert tools.delete_network_slice("slice-a")["applied"] is True
    assert "error" in tools.get_network_slice("slice-a")
    reset_shared_controller()
