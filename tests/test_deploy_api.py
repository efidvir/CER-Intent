"""
What a deployment relies on, through the whole Flask app: the probes, who may act in each
sign-in mode (headers, tokens, the session cookie), the auto-approval endpoints and the
reading preview with the network's own words.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from cer_intent.imf import api as imf_api
from cer_intent.imf.autoapprove import AutoPolicy
from cer_intent.imf.match import Policy
from imf_fakes import build

ADMIN, OPERATOR, VIEWER = "adm-7f3c-token", "op-91aa-token", "view-22b1-token"


@pytest.fixture
def make(monkeypatch, tmp_path):
    def _make(**env):
        base = {"CER_IMF_TICK_S": "0", "CER_IMF_TWIN": "0", "ADAPTER_BACKEND": "simulated", "TERAFLOW_URL": "http://127.0.0.1:9",
                "STATE_FILE": str(tmp_path / "state.json"), "CER_IMF_AUTO_STATE": str(tmp_path / "auto.json"),
                "CER_AUTH": "headers"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        from cer_intent.api.server import create_app
        from cer_intent.assurance.audit_log import AuditLog
        from cer_intent.device.registry import DeviceRegistry
        m, nsc, _, _ = build(twin=True, policy=Policy(auto=AutoPolicy(enabled=True)))
        imf_api.set_manager(m)
        app = create_app(registry=DeviceRegistry(), audit_log=AuditLog(str(tmp_path / "audit.jsonl")))
        return app.test_client(), m, nsc
    yield _make
    imf_api.set_manager(None)


@pytest.fixture
def tokens(tmp_path):
    path = tmp_path / "tokens.yaml"
    path.write_text(
        f"- user: ann\n  role: admin\n  token_sha256: {hashlib.sha256(ADMIN.encode()).hexdigest()}\n"
        f"- user: olga\n  role: operator\n  token: {OPERATOR}\n"
        f"- user: vic\n  role: viewer\n  token: {VIEWER}\n"
        f"- user: nobody\n  role: root\n  token: x\n")                       # an unknown role is left out
    return str(path)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_probes_answer_and_readiness_names_what_it_needs(make, monkeypatch):
    c, _, _ = make()
    h = c.get("/healthz").get_json()
    assert h["status"] == "ok" and h["version"]
    r = c.get("/readyz")
    assert r.status_code == 200 and r.get_json()["checks"]["intent_manager"]["auto_approval"] is True
    monkeypatch.setenv("ADAPTER_BACKEND", "teraflow")                         # TeraFlowSDN is down: reported...
    r = c.get("/readyz")
    assert r.status_code == 200 and r.get_json()["checks"]["teraflow"]["ok"] is False
    monkeypatch.setenv("CER_READY_REQUIRE", "teraflow")                       # ...and required only when asked
    from cer_intent import ops
    ops._cache.clear()
    assert c.get("/readyz").status_code == 503


def test_headers_mode_takes_who_acts_from_the_headers(make):
    c, m, _ = make()
    assert c.get("/api/v2/whoami").get_json()["auth"] == "headers"
    r = c.post("/api/v2/converse", json={"session": "s", "text": "Connect region-a and edge with 50 Mbps"},
               headers={"X-User": "olga", "X-Role": "operator"})
    rec = m.store.get(r.get_json()["intent"]["id"])
    assert (rec.owner, rec.role) == ("olga", "operator")


def test_token_mode_who_acts_comes_from_the_token(make, tokens):
    c, m, nsc = make(CER_AUTH="token", CER_AUTH_TOKENS_FILE=tokens)
    say = {"session": "s", "text": "Connect region-a and edge with 50 Mbps"}
    assert c.post("/api/v2/converse", json=say).status_code == 401
    r = c.post("/api/v2/converse", json=say, headers={**bearer(OPERATOR), "X-User": "mallory", "X-Role": "admin"})
    assert r.status_code == 200
    rec = m.store.get(r.get_json()["intent"]["id"])
    assert (rec.owner, rec.role) == ("olga", "operator") and rec.name in nsc.slices      # applied automatically
    assert c.put("/api/v2/auto-approve", json={"enabled": False}, headers=bearer(OPERATOR)).status_code == 403
    assert c.put("/api/v2/auto-approve", json={"enabled": False}, headers=bearer("guess")).status_code == 401
    r = c.put("/api/v2/auto-approve", json={"enabled": False}, headers=bearer(ADMIN))
    assert r.status_code == 200 and r.get_json()["policy"]["enabled"] is False
    me = c.get("/api/v2/whoami", headers=bearer(ADMIN)).get_json()
    assert (me["auth"], me["user"], me["role"], me["signed_in"]) == ("token", "ann", "admin", True)


def test_a_viewer_may_ask_but_nothing_else_changes(make, tokens):
    c, m, nsc = make(CER_AUTH="token", CER_AUTH_TOKENS_FILE=tokens)
    r = c.post("/api/v2/converse", json={"session": "v", "text": "Connect region-a and edge with 50 Mbps"}, headers=bearer(VIEWER))
    rec = m.store.get(r.get_json()["intent"]["id"])
    assert rec.state.value == "checked" and rec.name not in nsc.slices                    # a viewer's intent waits
    assert {g["id"] for g in rec.links["guardrails"] if not g["ok"]} == {"who"}
    assert c.post(f"/api/v2/intents/{rec.id}/approve", headers=bearer(VIEWER)).status_code == 403
    rfc = "/restconf/data/ietf-network-slice-service:network-slice-services"
    assert c.post(rfc, json={"id": "x"}, headers=bearer(VIEWER)).status_code == 403
    assert c.get("/api/v2/intents").status_code == 200                                    # reading stays open


def test_closed_reading_and_the_sign_in_cookie(make, tokens):
    c, _, _ = make(CER_AUTH="token", CER_AUTH_TOKENS_FILE=tokens, CER_AUTH_OPEN_READ="0")
    assert c.get("/api/v2/intents").status_code == 401
    assert c.get("/healthz").status_code == 200 and c.get("/intent-studio.html").status_code == 200
    assert c.post("/login", data={"token": "wrong"}).status_code == 401
    r = c.post("/login", data={"token": OPERATOR, "next": "/intent-studio.html"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/intent-studio.html")
    assert "HttpOnly" in r.headers["Set-Cookie"] and "SameSite=Strict" in r.headers["Set-Cookie"]
    assert c.get("/api/v2/intents").status_code == 200
    assert c.get("/api/v2/whoami").get_json()["user"] == "olga"
    c.post("/logout")
    assert c.get("/api/v2/intents").status_code == 401
    assert c.post("/login", data={"token": OPERATOR, "next": "//evil.example"}).headers["Location"].endswith("/")


def test_the_reading_preview_is_open_and_names_what_the_network_calls_things(make, tokens):
    c, _, _ = make(CER_AUTH="token", CER_AUTH_TOKENS_FILE=tokens)
    r = c.post("/api/v2/read", json={"text": "Freeze the 60 GHz link and whatever runs over radio-1"})
    assert r.status_code == 200
    body = r.get_json()
    assert {"phrase": "60 GHz link", "id": "radio-1|radio-2"}.items() <= next(w for w in body["words"] if w["phrase"] == "60 GHz link").items()
    assert any(x["ids"] == ["backhaul-ran"] for x in body["references"])


def test_auto_approve_endpoint_lists_policy_rules_and_decisions(make):
    c, _, _ = make()
    r = c.post("/api/v2/converse", json={"session": "a", "text": "Connect region-a and edge with 50 Mbps"},
               headers={"X-User": "olga", "X-Role": "operator"})
    assert r.get_json()["intent"]["state"] == "active"
    out = c.get("/api/v2/auto-approve").get_json()
    assert out["policy"]["enabled"] is True and out["rules"] == []
    assert [x["event"] for x in out["recent"]] == ["auto-approved"]
    bad = c.put("/api/v2/auto-approve", json={"per_hour": -1}, headers={"X-Role": "admin"})
    assert bad.status_code == 400 and "per_hour" in bad.get_json()["error"]
    assert json.loads(c.get("/api/v2/auto-approve").data)["policy"]["per_hour"] == 10
