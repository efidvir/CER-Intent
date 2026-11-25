"""
HTTP interfaces of the intent manager
=====================================
  /api/v2/...                          CER-Intent's own: records, conversation, reading
  /tmf-api/intentManagement/v5/...     TM Forum TMF921 v5
  /3gpp-intent/v1/...                  3GPP TS 28.312 (IntentHandlingFunction / Intent / IntentReport)

Every interface leads to the same records, so an intent submitted as TMF921 can
be answered in the studio and approved over 28.312.

Who acts: the X-User and X-Role headers (viewer, operator, approver, admin).
They are trusted as sent, which suits a lab behind its own access control; a
deployment puts this API behind its identity provider and maps its claims to
these roles.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from cer_intent.imf import standards
from cer_intent.imf.check import TwinClient
from cer_intent.imf.manager import ImfError, IntentManager, describe
from cer_intent.imf.model import IntentRecord, State
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.reader import RuleReader

imf_bp = Blueprint("imf", __name__)
ROLES = ("viewer", "operator", "approver", "admin")
_lock = threading.Lock()
_manager: Optional[IntentManager] = None
_app = None
TMF = "/tmf-api/intentManagement/v5"
G3 = "/3gpp-intent/v1"


def live_network() -> NetworkModel:
    """The network as TeraFlowSDN and the slice controller report it now."""
    from cer_intent.flow.routes import snapshot
    snap = snapshot(twin=False)
    if not snap.get("topology", {}).get("nodes") and os.getenv("CER_IMF_DEMO", "0") == "1":
        return NetworkModel.demo()
    return NetworkModel.from_snapshot(snap)


def _v1_submit(text: str) -> Dict[str, Any]:
    """Device features go through the v1 pipeline (parse, validate, architect, translate, apply)."""
    app = _app or current_app._get_current_object()
    with app.test_client() as c:
        r = c.post("/api/v1/intent", json={"intent": text, "source": "imf"})
        body = r.get_json(silent=True) or {}
        if r.status_code >= 400:
            body.setdefault("error", f"v1 returned {r.status_code}")
        return body


def manager() -> IntentManager:
    global _manager
    with _lock:
        if _manager is None:
            twin = TwinClient() if os.getenv("CER_IMF_TWIN", "1") not in ("0", "false", "off") else None
            _manager = IntentManager(network=live_network, twin=twin, legacy=_v1_submit)
            if os.getenv("CER_IMF_TICK_S", "10") not in ("0", ""):
                _manager.start(float(os.getenv("CER_IMF_TICK_S", "10")))
        return _manager


def set_manager(m: Optional[IntentManager]) -> None:
    global _manager
    _manager = m


@imf_bp.record_once
def _remember_app(state) -> None:
    global _app
    _app = state.app


def _who() -> Tuple[str, str]:
    body = request.get_json(silent=True) or {}
    who = request.headers.get("X-User") or body.get("who") or "operator"
    role = (request.headers.get("X-Role") or body.get("role") or "operator").lower()
    if role not in ROLES:
        raise ImfError(f"unknown role {role}; one of {', '.join(ROLES)}", 400)
    return who, role


@imf_bp.errorhandler(ImfError)
def _imf_error(e: ImfError):
    return jsonify({"error": str(e)}), e.status


def _out(rec: IntentRecord, status: int = 200):
    body = rec.model_dump(mode="json")
    body["reply"] = describe(rec)
    return jsonify(body), status


# ── /api/v2 ─────────────────────────────────────────────────────────────────

@imf_bp.post("/api/v2/intents")
def v2_create():
    who, role = _who()
    body = request.get_json(silent=True) or {}
    m = manager()
    if body.get("expectations"):
        rec = IntentRecord.model_validate({k: v for k, v in body.items() if k in IntentRecord.model_fields and k not in ("id", "state")})
        rec = m.submit(record=rec, channel=body.get("channel", "form"), who=who, role=role, session=body.get("session"),
                       check=body.get("check", True), approve=bool(body.get("approve")))
    else:
        rec = m.submit(body.get("text") or body.get("intent") or "", channel=body.get("channel", "text"), who=who, role=role,
                       session=body.get("session"), check=body.get("check", True), approve=bool(body.get("approve")))
    return _out(rec, 201)


@imf_bp.get("/api/v2/intents")
def v2_list():
    states = [State(s) for s in request.args.getlist("state") if s in State._value2member_map_]
    items = manager().store.all(states=states or None, session=request.args.get("session"))
    return jsonify({"intents": [{"id": r.id, "name": r.name, "state": r.state.value, "kinds": r.kinds(), "text": r.text,
                                 "summary": r.summary(), "channel": r.channel, "owner": r.owner, "updated_at": r.updated_at,
                                 "slices": r.links.get("slices", []), "questions": len(r.questions)}
                                for r in items]})


@imf_bp.get("/api/v2/intents/<rid>")
def v2_get(rid: str):
    return _out(manager()._get(rid))


@imf_bp.delete("/api/v2/intents/<rid>")
def v2_withdraw(rid: str):
    who, role = _who()
    return _out(manager().withdraw(rid, who=who, role=role))


@imf_bp.post("/api/v2/intents/<rid>/answers")
def v2_answer(rid: str):
    who, role = _who()
    body = request.get_json(silent=True) or {}
    return _out(manager().answer(rid, body.get("question"), body.get("value"), who=who, role=role))


@imf_bp.post("/api/v2/intents/<rid>/alternatives/<alt>/accept")
def v2_accept(rid: str, alt: str):
    who, role = _who()
    body = request.get_json(silent=True) or {}
    return _out(manager().accept(rid, alt, who=who, role=role, approve=bool(body.get("approve"))))


@imf_bp.post("/api/v2/intents/<rid>/approve")
def v2_approve(rid: str):
    who, role = _who()
    return _out(manager().approve(rid, who=who, role=role))


@imf_bp.post("/api/v2/intents/<rid>/recheck")
def v2_recheck(rid: str):
    return _out(manager().recheck(rid))


@imf_bp.post("/api/v2/intents/<rid>/suspend")
def v2_suspend(rid: str):
    who, role = _who()
    return _out(manager().suspend(rid, who=who, role=role))


@imf_bp.post("/api/v2/intents/<rid>/resume")
def v2_resume(rid: str):
    who, role = _who()
    return _out(manager().resume(rid, who=who, role=role))


@imf_bp.get("/api/v2/intents/<rid>/report")
def v2_report(rid: str):
    return jsonify(manager().report(rid))


@imf_bp.get("/api/v2/intents/<rid>/audit")
def v2_audit(rid: str):
    return jsonify({"audit": manager().store.audit_log(rid)})


@imf_bp.post("/api/v2/converse")
def v2_converse():
    who, role = _who()
    body = request.get_json(silent=True) or {}
    return jsonify(manager().converse(body.get("session") or "default", body.get("text") or "", who=who, role=role))


@imf_bp.post("/api/v2/read")
def v2_read():
    """How the words read, before anything is stored: rules, and the model when one is configured."""
    body = request.get_json(silent=True) or {}
    m = manager()
    net = m.network()
    rules = RuleReader(net.names(), m.clock()).read(body.get("text") or "")
    return jsonify({"reading": rules.model_dump(mode="json"), "summary": [e.summary() for e in rules.expectations],
                    "names": net.names()})


@imf_bp.get("/api/v2/network")
def v2_network():
    return jsonify(manager().network().to_dict())


@imf_bp.post("/api/v2/tick")
def v2_tick():
    _, role = _who()
    if role not in ("admin", "approver", "operator"):
        raise ImfError("not allowed", 403)
    return jsonify({"events": manager().tick()})


@imf_bp.get("/api/v2/events")
def v2_events():
    return jsonify({"events": manager().events[-100:]})


@imf_bp.get("/api/v2/capabilities")
def v2_capabilities():
    from cer_intent.imf.answers import EXAMPLES
    from cer_intent.imf.lexicon import PROFILES
    from cer_intent.imf.model import METRICS
    m = manager()
    return jsonify({"kinds": EXAMPLES, "metrics": METRICS, "profiles": PROFILES, "roles": list(ROLES),
                    "policy": {"vlan_pool": m.policy.vlan_pool, "approval_roles": m.policy.approval_roles,
                               "act_roles": m.policy.act_roles, "report_every_s": m.policy.report_every_s},
                    "language_model": getattr(m.llm, "name", None) or "none (rules only)",
                    "twin": bool(m.twin), "interfaces": ["/api/v2", TMF, G3, "MCP"]})


# ── TMF921 v5 ───────────────────────────────────────────────────────────────

def _tmf_base() -> str:
    return request.host_url.rstrip("/")


@imf_bp.post(f"{TMF}/intent")
def tmf_create():
    who, role = _who()
    body = request.get_json(silent=True) or {}
    m = manager()
    if (body.get("expression") or {}).get("expressionValue"):
        rec = m.submit(record=standards.from_tmf921(body), channel="tmf921", who=who, role=role)
    else:
        rec = m.submit(body.get("description") or body.get("name") or "", channel="tmf921", who=who, role=role)
        if body.get("id"):
            rec.links["external_id"] = body["id"]
    return jsonify(standards.to_tmf921(rec, _tmf_base())), 201


@imf_bp.get(f"{TMF}/intent")
def tmf_list():
    items = [standards.to_tmf921(r, _tmf_base()) for r in manager().store.all()]
    fields = request.args.get("fields")
    if fields:
        keep = set(fields.split(",")) | {"id", "href", "@type"}
        items = [{k: v for k, v in i.items() if k in keep} for i in items]
    return jsonify(items)


@imf_bp.get(f"{TMF}/intent/<rid>")
def tmf_get(rid: str):
    return jsonify(standards.to_tmf921(manager()._get(rid), _tmf_base()))


@imf_bp.patch(f"{TMF}/intent/<rid>")
def tmf_patch(rid: str):
    who, role = _who()
    body = request.get_json(silent=True) or {}
    m = manager()
    rec = m._get(rid)
    for qid, value in (body.get("cerAnswers") or {}).items():
        rec = m.answer(rid, qid, value, who=who, role=role)
    if body.get("cerSelectedAlternative"):
        rec = m.accept(rid, body["cerSelectedAlternative"], who=who, role=role)
    status = str(body.get("lifecycleStatus") or "").lower()
    if status == "active":
        rec = m.approve(rid, who=who, role=role) if rec.state == State.CHECKED else (m.resume(rid, who=who, role=role)
                                                                                      if rec.state == State.SUSPENDED else rec)
    elif status == "suspended":
        rec = m.suspend(rid, who=who, role=role)
    elif status in ("terminated", "cancelled"):
        rec = m.withdraw(rid, who=who, role=role)
    return jsonify(standards.to_tmf921(rec, _tmf_base()))


@imf_bp.delete(f"{TMF}/intent/<rid>")
def tmf_delete(rid: str):
    who, role = _who()
    manager().withdraw(rid, who=who, role=role)
    return "", 204


@imf_bp.get(f"{TMF}/intent/<rid>/intentReport")
def tmf_reports(rid: str):
    m = manager()
    m.report(rid)
    return jsonify([standards.report_tmf921(m._get(rid), _tmf_base())])


@imf_bp.get(f"{TMF}/intent/<rid>/intentReport/<report_id>")
def tmf_report(rid: str, report_id: str):
    m = manager()
    m.report(rid)
    return jsonify(standards.report_tmf921(m._get(rid), _tmf_base()))


@imf_bp.get(f"{TMF}/intentSpecification")
def tmf_specs():
    from cer_intent.imf.answers import EXAMPLES
    return jsonify([{"id": f"cer-{k}", "name": k, "description": v, "@type": "IntentSpecification", "lifecycleStatus": "active"}
                    for k, v in EXAMPLES.items()])


# ── 3GPP TS 28.312 ──────────────────────────────────────────────────────────

@imf_bp.route(f"{G3}/IntentHandlingFunction=1/Intent=<rid>", methods=["PUT"])
def g3_put(rid: str):
    who, role = _who()
    body = request.get_json(silent=True) or {}
    m = manager()
    if m.store.get(rid) is not None:
        m.withdraw(rid, who=who, role=role)
        m.store.delete(rid)
    rec = standards.from_3gpp(body)
    rec.id = rid
    rec = m.submit(record=rec, channel="3gpp", who=who, role=role)
    intent = body.get("Intent") or body.get("intent") or body
    if str(intent.get("intentAdminState", "ACTIVATED")).upper() == "ACTIVATED" and rec.state == State.CHECKED and \
            not intent.get("cerFeasibilityCheckOnly"):
        rec = m.approve(rid, who=who, role=role)
    return jsonify(standards.to_3gpp(rec) | {"cerState": rec.state.value, "cerReply": describe(rec)}), 201


@imf_bp.post(f"{G3}/intents")
def g3_post():
    who, role = _who()
    body = request.get_json(silent=True) or {}
    m = manager()
    rec = m.submit(record=standards.from_3gpp(body), channel="3gpp", who=who, role=role)
    intent = body.get("Intent") or body.get("intent") or body
    if str(intent.get("intentAdminState", "")).upper() == "ACTIVATED" and rec.state == State.CHECKED and \
            not intent.get("cerFeasibilityCheckOnly"):
        rec = m.approve(rec.id, who=who, role=role)
    return jsonify(standards.to_3gpp(rec) | {"cerState": rec.state.value, "cerReply": describe(rec)}), 201


@imf_bp.get(f"{G3}/intents")
def g3_list():
    return jsonify([standards.to_3gpp(r) for r in manager().store.all()])


@imf_bp.get(f"{G3}/IntentHandlingFunction=1/Intent=<rid>")
def g3_get(rid: str):
    rec = manager()._get(rid)
    return jsonify(standards.to_3gpp(rec) | {"cerState": rec.state.value})


@imf_bp.delete(f"{G3}/IntentHandlingFunction=1/Intent=<rid>")
def g3_delete(rid: str):
    who, role = _who()
    manager().withdraw(rid, who=who, role=role)
    return "", 204


@imf_bp.get(f"{G3}/IntentHandlingFunction=1/Intent=<rid>/IntentReport")
def g3_report(rid: str):
    return jsonify(manager().report(rid))
