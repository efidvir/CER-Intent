"""
End-to-end flow: intent -> slice controller -> digital twin -> TeraFlowSDN -> radios
==================================================================================
Support for the flow dashboard (dashboard/intent-flow.html). Every stage runs
the real component and every exchange between components is recorded, so the
dashboard can show the standards each hop speaks.

  GET  /api/v1/flow/status            components, transport topology, services, slices
  POST /api/v1/flow/preview           {intent_id}: RFC 9543 request, Mapper, Technology
                                      Selector and the L2SM / L3SM request, nothing sent
  POST /api/v1/flow/simulate          {intent_id}: twin sync, then the slice's pre-flight
                                      on NS-3.45 (before / after) and its SLO verdict
  POST /api/v1/flow/verify            {intent_id}: read-back from TeraFlowSDN and the
                                      radios, configuration diff, twin re-sync
  GET  /api/v1/flow/wire?since=<c>    exchanges since cursor c (CER-Intent's own, and the
                                      TeraFlowSDN stand-in's north and south sides)
  GET  /api/v1/flow/runs/<intent_id>  what the flow recorded for an intent

The intent itself goes through CER-Intent's own interfaces (POST /api/v1/intent,
POST /api/v1/intents/<id>/approve, the RFC 9543 RESTCONF interface). The flow
adds one rule there: an approval is held (409) while the twin's last pre-flight
of that intent predicts an SLO breach (?override=1 approves anyway).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Blueprint, current_app, jsonify, request

from cer_intent.flow import wiretap
from cer_intent.flow.standards import RFC9543, classify

logger = logging.getLogger("CER-Intent.flow")

flow_bp = Blueprint("flow", __name__, url_prefix="/api/v1/flow")

RFC9543_PATH = "/restconf/data/ietf-network-slice-service:network-slice-services"
STATUS_AGENT = "CER-Intent/1.0 (status)"          # status reads stay off the wire panel
RUNS: Dict[str, Dict[str, Any]] = {}
_runs_lock = threading.Lock()
_VOLATILE = re.compile(r"(octets|counters|uptime|rssi|snr|speed|rsl|sinr|temperature|timestamp)", re.I)
_APPROVE = re.compile(r"^/api/v1/intents/([^/]+)/approve/?$")

wiretap.install()


def _slice_request_hook(kind: str, slice_id: Optional[str], request: Any, response: Any, t0: float) -> None:
    status = 201 if isinstance(response, dict) and "nsc_pipeline" in response else 400
    summary = response
    if isinstance(response, dict) and "nsc_pipeline" in response:
        pipe = response["nsc_pipeline"]
        summary = {
            "ietf-network-slice-service:network-slice-services": response.get(
                "ietf-network-slice-service:network-slice-services"),
            "technology": pipe["technology_selector"],
            "realization": {k: pipe["realizer"].get(k) for k in ("model", "mode", "status", "error")},
        }
    wiretap.record_internal("Intent engine", "Slice controller", "POST", RFC9543_PATH, request, summary, status, t0)


wiretap.on_slice_request(_slice_request_hook)


# ── helpers ──────────────────────────────────────────────────────────────────

def _tfs() -> str:
    return os.getenv("TERAFLOW_URL", "http://localhost:8088").rstrip("/")


def _twin() -> str:
    return os.getenv("TWIN_URL", "http://localhost:9100").rstrip("/")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": wiretap.USER_AGENT, "Accept": "application/json"})
    return s


def _quiet() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": STATUS_AGENT, "Accept": "application/json", "X-Flow-Quiet": "1"})
    return s


def _intent(intent_id: Optional[str]):
    store = current_app.config.get("intent_store", {})
    return store.get(intent_id or "")


def _run(intent_id: str) -> Dict[str, Any]:
    with _runs_lock:
        return RUNS.setdefault(intent_id, {"intent_id": intent_id, "created": time.time()})


def _value(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _rules(device: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for rule in (device or {}).get("device_config", {}).get("config_rules", []):
        custom = rule.get("custom") or {}
        key = custom.get("resource_key")
        if not key or str(key).startswith("_connect/"):
            continue
        value = custom.get("resource_value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        out[key] = value
    return out


def _flatten(value: Any, prefix: str = "") -> Dict[str, Any]:
    """Leaves of a JSON value, keyed by a readable path (list entries by their key leaf)."""
    out: Dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}/{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            key = i
            if isinstance(v, dict):
                key = next((v[k] for k in ("bridge-id", "bridge-port-id", "index", "name", "id", "slice-id")
                            if k in v), i)
            out.update(_flatten(v, f"{prefix}[{key}]"))
    else:
        out[prefix] = value
    return out


def leaf_diff(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for key in sorted(set(before) | set(after)):
        b, a = _flatten(before.get(key)), _flatten(after.get(key))
        for leaf in sorted(set(b) | set(a)):
            if _VOLATILE.search(leaf):
                continue
            if b.get(leaf) != a.get(leaf):
                rows.append({"resource": key, "leaf": leaf, "before": b.get(leaf), "after": a.get(leaf)})
    return rows


def _devices(session: requests.Session) -> Tuple[List[Dict[str, Any]], bool]:
    r = session.get(f"{_tfs()}/tfs-api/devices", timeout=5)
    r.raise_for_status()
    return r.json().get("devices", []), r.headers.get("X-TFS-Standin") == "1"


def _is_ceragon(dev: Dict[str, Any]) -> bool:
    return "DEVICEDRIVER_CERAGON" in (dev.get("device_drivers") or [])


def _model(dev: Dict[str, Any]) -> Optional[str]:
    info = _rules(dev).get("/device/hardware_info")
    return info.get("model") if isinstance(info, dict) else None


# ── inbound log and the approval gate ────────────────────────────────────────

def _logged_inbound(method: str, path: str) -> bool:
    if method == "POST" and (path.rstrip("/") == "/api/v1/intent" or _APPROVE.match(path)):
        return True
    if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith(("/api/v2/intents", "/api/v2/converse",
                                                                          "/tmf-api/intentManagement/v5", "/3gpp-intent/")):
        return True
    if method == "DELETE" and path.startswith("/api/v1/intents/"):
        return True
    return path.startswith(RFC9543_PATH) and method in ("POST", "PUT", "PATCH", "DELETE")


@flow_bp.before_app_request
def _before():
    request.environ["flow.t0"] = time.time()
    m = _APPROVE.match(request.path)
    if request.method == "POST" and m and request.args.get("override") != "1":
        preflight = (RUNS.get(m.group(1)) or {}).get("preflight")
        if preflight and preflight.get("verdict") == "fail":
            return jsonify({
                "status": "held",
                "error": "the digital twin predicts an SLO breach for this intent; approval held",
                "checks": preflight.get("checks", []),
                "hint": "change the intent, or approve with ?override=1",
            }), 409
    return None


@flow_bp.after_app_request
def _after(resp):
    try:
        if _logged_inbound(request.method, request.path):
            who = request.headers.get("X-Flow-Client", "Operator")
            body = resp.get_data() if resp.mimetype == "application/json" else None
            wiretap.record_inbound(who, request.method, request.full_path.rstrip("?"), resp.status_code,
                                   request.get_data(), body, request.environ.get("flow.t0", time.time()))
            m = _APPROVE.match(request.path)
            if m and body:
                _run(m.group(1))["apply"] = {"status": resp.status_code, "body": json.loads(body)}
            if request.path.rstrip("/") == "/api/v1/intent" and body:
                data = json.loads(body)
                if data.get("intent_id"):
                    _run(data["intent_id"])["text"] = (request.get_json(silent=True) or {}).get("intent")
    except Exception:  # the dashboard log never breaks a request
        logger.debug("flow log failed", exc_info=True)
    return resp


# ── status ───────────────────────────────────────────────────────────────────

@flow_bp.get("/status")
def status():
    adapter = current_app.config.get("adapter")
    return jsonify(snapshot(adapter_name=type(adapter).__name__ if adapter else None))


def snapshot(adapter_name: Optional[str] = None, twin: bool = True) -> Dict[str, Any]:
    """The network as CER-Intent sees it: TeraFlowSDN topology and services, the twin, the slices."""
    from cer_intent.api.restconf_routes import get_nsc
    from cer_intent.nsc.realizer import realization_mode

    quiet = _quiet()
    out: Dict[str, Any] = {
        "cer_intent": {"ok": True, "adapter": adapter_name, "realization": realization_mode()},
        "teraflowsdn": {"url": _tfs(), "ok": False},
        "twin": {"url": _twin(), "ok": False},
        "topology": {"nodes": [], "links": []},
        "services": [],
        "slices": [],
    }
    try:
        r = quiet.get(f"{_tfs()}/tfs-api/context/admin/topology_details/admin", timeout=4)
        r.raise_for_status()
        topo = r.json()
        out["teraflowsdn"].update({"ok": True, "standin": r.headers.get("X-TFS-Standin") == "1"})
        for dev in topo.get("devices", []):
            out["topology"]["nodes"].append({
                "id": dev.get("name") or dev["device_id"]["device_uuid"]["uuid"],
                "uuid": dev["device_id"]["device_uuid"]["uuid"],
                "type": dev.get("device_type"),
                "radio": _is_ceragon(dev),
                "model": _model(dev),
                "status": dev.get("device_operational_status"),
                "endpoints": [e.get("name") for e in dev.get("device_endpoints", [])],
            })
        for lk in topo.get("links", []):
            eps = lk.get("link_endpoint_ids", [])
            if len(eps) >= 2:
                a, b = eps[0], eps[1]
                ea, eb = a["endpoint_uuid"]["uuid"], b["endpoint_uuid"]["uuid"]
                out["topology"]["links"].append({
                    "id": lk.get("name") or lk["link_id"]["link_uuid"]["uuid"],
                    "a": a["device_id"]["device_uuid"]["uuid"], "a_ep": ea,
                    "b": b["device_id"]["device_uuid"]["uuid"], "b_ep": eb,
                    "radio": ea.startswith("rf-sector") or eb.startswith("rf-sector"),
                })
        try:
            from cer_intent.intent_parser import register_network_names
            register_network_names(n["id"] for n in out["topology"]["nodes"])
        except Exception:  # pylint: disable=broad-except
            pass
        s = quiet.get(f"{_tfs()}/tfs-api/context/admin/services", timeout=4)
        for svc in (s.json().get("services", []) if s.ok else []):
            cap = next((c["sla_capacity"]["capacity_gbps"] for c in svc.get("service_constraints", [])
                        if "sla_capacity" in c), None)
            lat = next((c["sla_latency"].get("e2e_latency_ms") for c in svc.get("service_constraints", [])
                        if "sla_latency" in c), None)
            ports, vlans = {}, {}
            for rule in (svc.get("service_config") or {}).get("config_rules", []):
                m = re.match(r"/device\[([^\]]+)\]/endpoint\[([^\]]+)\]/settings", (rule.get("custom") or {}).get("resource_key", ""))
                if m:
                    try:
                        val = rule["custom"].get("resource_value")
                        val = json.loads(val) if isinstance(val, str) else (val or {})
                    except ValueError:
                        val = {}
                    ports[m.group(1)] = m.group(2)
                    if val.get("vlan_id") is not None:
                        vlans[m.group(1)] = val.get("vlan_id")
                    if val.get("address_ip"):
                        vlans.setdefault("_ip_" + m.group(1), val.get("address_ip"))
            out["services"].append({
                "name": svc.get("name"),
                "uuid": ((svc.get("service_id") or {}).get("service_uuid") or {}).get("uuid"),
                "type": svc.get("service_type"),
                "status": (svc.get("service_status") or {}).get("service_status"),
                "capacity_mbps": round(float(cap) * 1000, 1) if cap else None,
                "latency_ms": lat,
                "endpoints": [e["device_id"]["device_uuid"]["uuid"] for e in svc.get("service_endpoint_ids", [])],
                "ports": [e.get("endpoint_uuid", {}).get("uuid") for e in svc.get("service_endpoint_ids", [])],
                "vlans": {k: v for k, v in vlans.items() if not k.startswith("_ip_")},
                "ips": {k[4:]: v for k, v in vlans.items() if k.startswith("_ip_")},
            })
    except (requests.RequestException, ValueError, KeyError) as exc:
        out["teraflowsdn"]["error"] = str(exc)
    try:
        if not twin:
            raise requests.RequestException("twin not asked")
        h = quiet.get(f"{_twin()}/healthz", timeout=3)
        out["twin"].update({"ok": h.ok, "health": h.json() if h.ok else None})
        e = quiet.get(f"{_twin()}/api/v1/dti/ceragon/engine", timeout=3)
        if e.ok:
            out["twin"]["engine"] = e.json()
    except (requests.RequestException, ValueError) as exc:
        out["twin"]["error"] = str(exc)
    nsc = get_nsc()
    for sid, svc in nsc.slices.items():
        r = nsc.realizations.get(sid)
        req = nsc.requests.get(sid) or {}
        slos = req.get("slos") or {}
        out["slices"].append({
            "id": sid, "status": svc.status, "model": svc.realization_technology,
            "path": list(svc.computed_path), "realization": r.status if r else None,
            "endpoints": [{"node": p.node_id, "port": p.tp_id, "vlan": p.vlan_id, "ip": p.ip_address} for p in svc.sdps],
            "bandwidth_mbps": slos.get("bandwidth_mbps"), "max_latency_ms": slos.get("max_latency_ms"),
            "loss_pct": slos.get("packet_loss_pct"), "availability_pct": slos.get("availability_pct"),
            "acm_floor": (req.get("acm") or {}).get("min_modulation") if isinstance(req.get("acm"), dict) else None,
            "hop_floor": nsc.hop_floors.get(sid), "technology": req.get("technology"),
            "description": (req.get("service") or {}).get("description"),
        })
    return out


# ── stage 2: what the slice controller would send ────────────────────────────

@flow_bp.post("/preview")
def preview():
    from cer_intent.api.restconf_routes import get_nsc
    from cer_intent.translators.slice_translator import SliceTranslator

    body = request.get_json(silent=True) or {}
    intent = _intent(body.get("intent_id"))
    if intent is None:
        return jsonify({"error": "intent not found"}), 404
    translation = SliceTranslator().translate(intent, [])
    config = next((c for c in translation.device_configs if c.config_type == "slice_service"), None)
    if config is None:
        return jsonify({"error": "not an end-to-end slice: the intent names fewer than two endpoints"}), 400
    slice_request = config.parameters
    result = get_nsc().preview_slice_service(slice_request)
    if "nsc_pipeline" not in result:
        return jsonify({"error": result.get("error"), "stage": result.get("stage")}), 400
    pipe = result["nsc_pipeline"]
    endpoints, slos = pipe["mapper"]["endpoints"], pipe["mapper"]["slos"]
    acm = slice_request.get("acm") or {}
    candidate = {
        "slice_id": pipe["realizer"]["slice_id"],
        "src": endpoints[0]["node"], "dst": endpoints[1]["node"],
        "bandwidth_mbps": slos.get("bandwidth_mbps"),
        "max_latency_ms": slos.get("max_latency_ms"),
        "max_loss_pct": slos.get("packet_loss_pct"),
        "acm_floor": acm.get("min_modulation") if isinstance(acm, dict) else None,
        "vlan_id": endpoints[0].get("vlan"),
        "technology": pipe["technology_selector"]["technology"],
    }
    run = _run(intent.intent_id)
    run.update({"slice_id": candidate["slice_id"], "request": slice_request, "candidate": candidate,
                "path": pipe["planner"].get("computed_path") or [e["node"] for e in endpoints]})
    run.pop("preflight", None)
    # configuration of the radios before anything is applied, for the read-back diff
    try:
        devices, _ = _devices(_quiet())
        quiet = _quiet()
        run["before"] = {}
        for dev in devices:
            if _is_ceragon(dev):
                name = dev.get("name")
                r = quiet.get(f"{_tfs()}/tfs-api/device/{name}", timeout=8, headers={"Cache-Control": "no-cache"})
                if r.ok:
                    run["before"][name] = _rules(r.json())
    except (requests.RequestException, ValueError) as exc:
        logger.info("no configuration snapshot: %s", exc)
    plan = intent.architect_plan or {}
    return jsonify({
        "intent": {
            "id": intent.intent_id, "text": intent.raw_input, "type": _value(intent.intent_type),
            "target": intent.target.identifier if intent.target else None,
            "parameters": intent.parameters, "status": _value(intent.status),
        },
        "architect": {
            "selected": plan.get("selected_strategy"),
            "candidates": plan.get("candidate_strategies") or plan.get("candidates") or [],
            "trace": plan.get("reasoning_trace") or [],
        },
        "rfc9543": {"request": slice_request,
                    "ietf": result["ietf-network-slice-service:network-slice-services"]},
        "pipeline": pipe,
        "candidate": candidate,
        "translation": translation.explanation,
    })


# ── stage 3: the digital twin ────────────────────────────────────────────────

@flow_bp.post("/simulate")
def simulate():
    body = request.get_json(silent=True) or {}
    intent_id = body.get("intent_id")
    run = RUNS.get(intent_id or "")
    if not run or "candidate" not in run:
        return jsonify({"error": "preview the intent first"}), 409
    s = _session()
    try:
        sync = s.post(f"{_twin()}/api/v1/dti/sync", json={}, timeout=60)
        sync.raise_for_status()
        pf = s.post(f"{_twin()}/api/v1/dti/ceragon/preflight",
                    json={"candidate": run["candidate"], **({"plan": body["plan"]} if body.get("plan") else {})},
                    timeout=float(os.getenv("TWIN_PREFLIGHT_TIMEOUT_SEC", "300")))
    except requests.RequestException as exc:
        return jsonify({"error": f"digital twin not reachable: {exc}"}), 503
    result = pf.json() if pf.headers.get("Content-Type", "").startswith("application/json") else {"error": pf.text}
    if pf.status_code != 200:
        return jsonify({"error": result.get("error", "pre-flight failed"), "status": pf.status_code}), 502
    run["preflight"] = {"verdict": result.get("verdict"), "checks": result.get("checks", []), "at": time.time()}
    return jsonify({"sync": sync.json(), "preflight": result})


# ── stage 5: read-back ───────────────────────────────────────────────────────

def _bridge_vlans(rules: Dict[str, Any]) -> List[int]:
    tree = rules.get("/restconf/radio-bridge-tg-user-bridge:user-bridge") or {}
    bridges = (tree.get("radio-bridge-tg-user-bridge:user-bridge") or tree).get("bridge", []) or []
    vlans = []
    for b in bridges:
        for port in b.get("bridge-port", []) or []:
            if port.get("c-vlan") is not None:
                vlans.append(int(port["c-vlan"]))
    return sorted(set(vlans))


def _node_config(rules: Dict[str, Any]) -> Dict[str, Any]:
    tree = rules.get("/restconf/radio-bridge-tg-radio-common:radio-common") or {}
    return ((tree.get("radio-bridge-tg-radio-common:radio-common") or tree).get("node-config") or {})


@flow_bp.post("/verify")
def verify():
    body = request.get_json(silent=True) or {}
    intent_id = body.get("intent_id")
    run = RUNS.get(intent_id or "")
    intent = _intent(intent_id)
    if not run or intent is None:
        return jsonify({"error": "unknown intent"}), 404
    s = _session()
    checks: List[Dict[str, Any]] = []
    status = _value(intent.status)
    outcome = _value(getattr(intent, "actuation_outcome", None))
    checks.append({"id": "intent", "label": "Intent state", "value": f"{status} · {_value(intent.state_3gpp)}",
                   "ok": status == "applied"})
    checks.append({"id": "outcome", "label": "Actuation outcome", "value": outcome or "none",
                   "ok": outcome == "acknowledged_verified"})
    service: Dict[str, Any] = {}
    try:
        r = s.get(f"{_tfs()}/tfs-api/context/admin/service/{run['slice_id']}", timeout=8)
        if r.ok:
            svc = r.json()
            service = {
                "name": svc.get("name"), "uuid": svc["service_id"]["service_uuid"]["uuid"],
                "type": svc.get("service_type"),
                "status": (svc.get("service_status") or {}).get("service_status"),
                "constraints": svc.get("service_constraints", []),
            }
        checks.append({"id": "service", "label": "TeraFlowSDN service",
                       "value": service.get("status") or f"HTTP {r.status_code}",
                       "ok": service.get("status") == "SERVICESTATUS_ACTIVE"})
    except requests.RequestException as exc:
        checks.append({"id": "service", "label": "TeraFlowSDN service", "value": str(exc), "ok": False})

    rows: List[Dict[str, Any]] = []
    radios: Dict[str, Dict[str, Any]] = {}
    vlan = (run.get("candidate") or {}).get("vlan_id")
    floor = (run.get("candidate") or {}).get("acm_floor")
    try:
        devices, _ = _devices(_quiet())
        for dev in devices:
            name = dev.get("name")
            if not _is_ceragon(dev) or name not in (run.get("path") or []):
                continue
            r = s.get(f"{_tfs()}/tfs-api/device/{name}", timeout=10, headers={"Cache-Control": "no-cache"})
            if not r.ok:
                checks.append({"id": f"read:{name}", "label": f"{name} read-back", "value": f"HTTP {r.status_code}",
                               "ok": False})
                continue
            after = _rules(r.json())
            for row in leaf_diff((run.get("before") or {}).get(name, {}), after):
                rows.append({"device": name, **row})
            vlans, node = _bridge_vlans(after), _node_config(after)
            radios[name] = {"model": _model(r.json()), "vlans": vlans, "node_config": node}
            if vlan is not None and (run.get("candidate") or {}).get("technology") == "L2VPN":
                checks.append({"id": f"vlan:{name}", "label": f"{name}: bridge for VLAN {vlan}",
                               "value": ", ".join(map(str, vlans)) or "none", "ok": int(vlan) in vlans})
            if floor:
                checks.append({"id": f"acm:{name}", "label": f"{name}: ACM range ({floor} floor)",
                               "value": f"link-distance {node.get('link-distance', 'unset')}",
                               "ok": "link-distance" in node})
    except (requests.RequestException, ValueError) as exc:
        checks.append({"id": "radios", "label": "Radio read-back", "value": str(exc), "ok": False})

    twin: Dict[str, Any] = {}
    try:
        t = s.post(f"{_twin()}/api/v1/dti/sync", json={}, timeout=60)
        twin = t.json() if t.ok else {"error": t.text[:200]}
        checks.append({"id": "twin", "label": "Twin re-synced from the network",
                       "value": f"{twin.get('nodes_count', '?')} nodes · {twin.get('links_count', '?')} links "
                                f"({twin.get('topology_source', '?')})", "ok": t.ok})
    except requests.RequestException as exc:
        checks.append({"id": "twin", "label": "Twin re-synced from the network", "value": str(exc), "ok": False})

    result = {"checks": checks, "ok": all(c["ok"] for c in checks), "diff": rows, "radios": radios,
              "service": service, "twin": twin,
              "intent": {"id": intent.intent_id, "status": status, "state_3gpp": _value(intent.state_3gpp),
                         "outcome": outcome, "readback": getattr(intent, "readback_evidence", None)}}
    run["verify"] = {"ok": result["ok"], "at": time.time()}
    return jsonify(result)


# ── the wire ─────────────────────────────────────────────────────────────────

_standin_cursor_lock = threading.Lock()


def _standin_entries(since: int) -> Tuple[List[Dict[str, Any]], int]:
    try:
        r = _quiet().get(f"{_tfs()}/standin/wire", params={"since": since}, timeout=3)
        if not r.ok:
            return [], since
        data = r.json()
        return data.get("items", []), int(data.get("seq", since))
    except (requests.RequestException, ValueError):
        return [], since


def _normalise(entry: Dict[str, Any], origin: str) -> Dict[str, Any]:
    url = entry.get("url", "")
    path = url.split("://", 1)[-1]
    path = path[path.find("/"):] if "/" in path else "/"
    std = RFC9543 if entry.get("transport") == "in-process" else classify(entry.get("method", "GET"), url)
    return {
        "id": f"{origin}{entry['seq']}",
        "t": entry.get("t"), "ms": entry.get("ms"),
        "src": entry.get("src"), "dst": entry.get("dst"),
        "method": entry.get("method"), "path": path, "url": url,
        "status": entry.get("status"),
        "req": entry.get("req"), "res": entry.get("res"),
        "transport": entry.get("transport", "http"),
        "std": std,
    }


@flow_bp.get("/wire")
def wire():
    cursor = request.args.get("since", "0:0")
    try:
        own_since, tfs_since = (int(x) for x in cursor.split(":", 1))
    except ValueError:
        own_since, tfs_since = 0, 0
    items = [_normalise(e, "c") for e in wiretap.LOG.since(own_since)]
    with _standin_cursor_lock:
        standin, tfs_seq = _standin_entries(tfs_since)
    for e in standin:
        if e.get("dir") == "north" and e.get("src") == "CER-Intent":
            continue                      # already in CER-Intent's own log
        items.append(_normalise(e, "t"))
    items.sort(key=lambda e: (e.get("t") or 0, e["id"]))
    return jsonify({"cursor": f"{wiretap.LOG.seq}:{tfs_seq}", "items": items})


@flow_bp.get("/runs/<intent_id>")
def get_run(intent_id: str):
    run = RUNS.get(intent_id)
    return (jsonify(run), 200) if run else (jsonify({"error": "unknown intent"}), 404)
