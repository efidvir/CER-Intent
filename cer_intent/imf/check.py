"""
Checking an intent before anything changes
==========================================
Three layers, each saying what it is based on:

  1. rules       the operator's guard intents (freeze windows, approval, a
                 minimum modulation, headroom) and the record's role
  2. conflicts   other intents: a keep objective a change would break, two
                 scheduled windows that together overfill a hop, an objective
                 that cannot hold given what already runs
  3. feasibility the analytic radio screen on every hop of the path (load,
                 modulation in design rain, ITU-R availability; cer_intent/imf/radio.py)
                 and, when the digital twin is reachable, its NS-3 pre-flight,
                 which decides.

A check result is stored on the record as `check` and in the 28.312 report as
the feasibility check report.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from cer_intent.imf.model import ACTING_KINDS, Expectation, IntentRecord, Kind, State
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.radio import availability_for, mcs_index, pct, screen
from cer_intent.imf.timex import window_bounds


class TwinClient:
    """The digital twin's pre-flight (POST /api/v1/dti/ceragon/preflight), after a sync."""

    def __init__(self, base: Optional[str] = None, session: Optional[requests.Session] = None, timeout: Optional[float] = None):
        self.base = (base or os.getenv("TWIN_URL", "http://localhost:9100")).rstrip("/")
        if session is None:
            try:
                from cer_intent.flow.routes import _session
                session = _session()
            except Exception:  # pylint: disable=broad-except
                session = requests.Session()
        self.session = session
        self.timeout = timeout or float(os.getenv("TWIN_PREFLIGHT_TIMEOUT_SEC", "300"))
        self.last_error: Optional[str] = None

    def enabled(self) -> bool:
        return os.getenv("CER_IMF_TWIN", "1") not in ("0", "false", "off")

    def preflight(self, candidate: Dict[str, Any], plan: Optional[Dict[str, Any]] = None,
                  exclude: Optional[List[str]] = None, overrides: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled():
            self.last_error = "the twin check is turned off (CER_IMF_TWIN=0)"
            return None
        body: Dict[str, Any] = {"candidate": candidate}
        if plan:
            body["plan"] = plan
        if exclude:
            body["exclude"] = exclude
        if overrides:
            body["overrides"] = overrides
        try:
            self.session.post(f"{self.base}/api/v1/dti/sync", json={}, timeout=60).raise_for_status()
            r = self.session.post(f"{self.base}/api/v1/dti/ceragon/preflight", json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            self.last_error = f"digital twin not reachable: {exc.__class__.__name__}"
            return None
        try:
            data = r.json()
        except ValueError:
            data = {"error": r.text[:300]}
        if r.status_code != 200:
            self.last_error = data.get("error") or f"pre-flight returned {r.status_code}"
            return None
        self.last_error = None
        return data


def candidate_for(e: Expectation, slice_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    eps = e.object.endpoints
    if len(eps) < 2 or not eps[0].node or not eps[1].node:
        return None
    return {"slice_id": slice_id or e.name, "src": eps[0].node, "dst": eps[1].node,
            "bandwidth_mbps": e.value("bandwidth"), "max_latency_ms": e.value("latency"),
            "max_loss_pct": e.value("loss"), "acm_floor": e.value("modulation_floor"),
            "vlan_id": eps[0].vlan, "technology": e.value("technology") or "L2VPN"}


def held_request(req: Any) -> Optional[Dict[str, Any]]:
    """A slice request a suspend put aside, read the way the slice controller reads it."""
    if not isinstance(req, dict):
        return None
    try:
        from cer_intent.nsc.mapper import map_request
        m = map_request(req)
    except Exception:  # pylint: disable=broad-except
        return None
    acm = m.extensions.get("acm") if isinstance(m.extensions.get("acm"), dict) else {}
    return {"endpoints": [{"node": e.node_id, "port": e.tp_id, "vlan": e.vlan_id, "ip": e.ip_address} for e in m.endpoints],
            "bandwidth_mbps": m.slos.bandwidth_mbps, "max_latency_ms": m.slos.max_latency_ms,
            "floor": (acm or {}).get("min_modulation"), "description": getattr(m, "description", None)}


def resume_probe(sid: str, records: List[IntentRecord]) -> Optional[Expectation]:
    """The slice a suspend put aside (kept on the intent that suspended it), as a delivery to screen."""
    from cer_intent.imf.model import Endpoint
    req = next(((r.links.get("suspended") or {}).get(sid) for r in records if (r.links.get("suspended") or {}).get(sid)), None)
    held = held_request(req)
    if not held or len(held["endpoints"]) < 2:
        return None
    probe = Expectation(kind=Kind.DELIVER, name=sid, object={"type": "slice", "ids": [sid]})
    probe.object.endpoints = [Endpoint(node=x["node"], port=x["port"], vlan=x["vlan"], ip=x["ip"]) for x in held["endpoints"][:2]]
    if held["bandwidth_mbps"]:
        probe.set_target("bandwidth", "ge", float(held["bandwidth_mbps"]), "Mbps")
    if held["max_latency_ms"]:
        probe.set_target("latency", "le", float(held["max_latency_ms"]), "ms")
    if held["floor"]:
        probe.set_target("modulation_floor", "ge", held["floor"], "MCS")
    return probe


# ── rules from guard intents ───────────────────────────────────────────────────

def active_guards(store_items: List[IntentRecord]) -> List[Tuple[IntentRecord, Expectation]]:
    out = []
    for r in store_items:
        if r.state not in (State.ACTIVE, State.SCHEDULED):
            continue
        for e in r.expectations:
            if e.kind == Kind.GUARD:
                out.append((r, e))
    return out


def _in_window(e: Expectation, now: dt.datetime) -> bool:
    w = e.context("window")
    if w is None:
        return True
    start, end = window_bounds(w.params, now)
    if start is None:
        return True
    return start <= now < end if end else start <= now


def touches(expectations: List[Expectation], net: NetworkModel) -> set:
    """What these expectations act on: named ids, endpoint sites, and the nodes and hops on their path."""
    touched = set()
    for e in expectations:
        touched |= set(e.object.ids) | {ep.node for ep in e.object.endpoints if ep.node}
        eps = [ep.node for ep in e.object.endpoints if ep.node]
        if len(eps) == 2:
            path = net.path(eps[0], eps[1])
            touched |= set(path) | {h.name for h in net.hops(path)}
        for sid in e.object.ids:                       # a slice touches what its path crosses
            sl = net.slices.get(sid)
            if sl is not None and sl.path:
                touched |= set(sl.path) | {h.name for h in net.hops(sl.path)}
    return touched


def in_scope(scope: set, touched: set) -> bool:
    return not scope or bool(scope & touched) or any(s in t for s in scope for t in touched)


def guard_findings(rec: IntentRecord, guards: List[Tuple[IntentRecord, Expectation]], now: dt.datetime,
                   net: NetworkModel) -> List[Dict[str, Any]]:
    out = []
    acting = [e for e in rec.expectations if e.kind in ACTING_KINDS]
    if not acting:
        return out
    touched = touches(acting, net)
    for g_rec, g in guards:
        if g_rec.id == rec.id:
            continue
        rule = g.action.get("rule")
        if not in_scope(set(g.object.ids), touched):
            continue
        if g.action.get("kinds") and not any(e.kind.value in g.action["kinds"] for e in acting):
            continue
        base = {"rule": rule, "guard": g_rec.id, "text": g_rec.text}
        if rule == "freeze" and _in_window(g, now):
            out.append({**base, "effect": "hold", "why": f"changes are frozen by {g_rec.name or g_rec.id}"})
        elif rule == "approval":
            out.append({**base, "effect": "approval",
                        "why": f"{g_rec.name or g_rec.id} asks a person to approve this" if g.action.get("no_auto") else
                        "an approver must approve this change"})
        elif rule == "floor" and g.action.get("value"):
            out.append({**base, "effect": "floor", "value": g.action["value"],
                        "why": f"radios hold at least {g.action['value']} ({g_rec.name or g_rec.id})"})
        elif rule == "headroom" and g.action.get("value") is not None:
            out.append({**base, "effect": "headroom", "value": g.action["value"], "unit": g.action.get("unit", "%"),
                        "why": f"keep {g.action['value']:g}{g.action.get('unit', '%')} spare on every hop"})
    return out


# ── the analytic screen ────────────────────────────────────────────────────────

def screen_delivery(net: NetworkModel, e: Expectation, replacing: Optional[str] = None,
                    headroom: Optional[Tuple[float, str]] = None, guard_floor: Optional[str] = None) -> Dict[str, Any]:
    eps = e.object.endpoints
    if len(eps) < 2 or not (eps[0].node and eps[1].node):
        return {"ok": None, "why": "endpoints not known"}
    path = net.path(eps[0].node, eps[1].node)
    if not path:
        return {"ok": False, "why": f"no path between {eps[0].node} and {eps[1].node}", "path": []}
    bw = float(e.value("bandwidth") or 0.0)
    floor = e.value("modulation_floor")
    if guard_floor and (mcs_index(guard_floor) or 0) > (mcs_index(floor) or 0):
        floor = guard_floor
    hops = []
    ok = True
    reasons: List[str] = []
    for hop in net.hops(path):
        exclude = [replacing] if replacing else []
        existing = net.load(hop, exclude=exclude)
        hop_floor = net.hop_floor(hop, exclude=exclude)
        eff_floor = max([f for f in (floor, hop_floor) if f], key=lambda f: mcs_index(f) or 0, default=None)
        sc = screen(hop, existing + bw, eff_floor)
        row = {**sc.to_dict(), "existing_mbps": existing, "slice_mbps": bw, "hop_floor": hop_floor, "floor": eff_floor}
        limit = sc.rain_capacity_mbps
        if headroom:
            value, unit = headroom
            limit = limit * (1 - value / 100.0) if unit == "%" else limit - value
            row["headroom_limit_mbps"] = round(limit, 1)
        row["spare_in_rain_mbps"] = round(max(0.0, limit - existing), 1)
        if existing + bw > limit + 1e-9:
            ok = False
            reasons.append(f"{hop.name}: {existing:g} + {bw:g} Mbps is more than the {limit:g} Mbps it holds at "
                           f"{sc.rain_mmh:g} mm/h ({sc.rain_mcs})" + (" with the headroom rule" if headroom else ""))
        if eff_floor and sc.floor_holds_in_rain is False:
            reasons.append(f"{hop.name}: at {sc.rain_mmh:g} mm/h the hop falls to {sc.rain_mcs}, below the {eff_floor} floor: "
                           "the link would drop instead of slowing down")
            ok = False
        target = e.value("availability")
        av = row["availability"]
        if target is not None and av.get("mcs") and av.get("availability_pct") is not None and av["availability_pct"] < float(target) - 1e-6:
            ok = False
            reasons.append(f"{hop.name}: holding {av['mcs']} for {existing + bw:g} Mbps gives {pct(av['availability_pct'])} "
                           f"a year (ITU-R), below {float(target):g} %")
        live = net.live_mcs(hop)
        if live:
            from cer_intent.imf.radio import capacity_mbps as _cap
            now_cap = min(hop.port_mbps, _cap(live))
            row.update({"live_mcs": live, "live_capacity_mbps": now_cap,
                        # below clear sky in rate (MCS9 and up all carry the radio's 1 Gbps: not fading)
                        "fading_now": now_cap + 1e-9 < min(hop.port_mbps, _cap(sc.clear_mcs)),
                        "fits_now": existing + bw <= now_cap + 1e-9})
        hops.append(row)
    now_notes = [f"{h['hop']} runs {h['live_mcs']} now ({h['live_capacity_mbps']:g} Mbps): it carries this "
                 + ("now as well" if h["fits_now"] else "when the hop recovers, not right now")
                 for h in hops if h.get("fading_now")]
    return {"ok": ok, "path": path, "hops": hops, "why": "; ".join(reasons) or "fits on every hop", "floor": floor,
            "now": "; ".join(now_notes) or None, "basis": "analytic: ITU-R P.838/P.530 on the twin's radio model"}


def keep_screen(net: NetworkModel, e: Expectation) -> Dict[str, Any]:
    """Can a standing objective hold, given what runs now?"""
    findings = []
    ok = True
    for sid in e.object.ids:
        s = net.slices.get(sid)
        if s is None:
            continue
        for hop in net.hops(s.path):
            load = net.load(hop)
            floor = net.hop_floor(hop)
            av = availability_for(hop, load, floor)
            row = {"slice": sid, "hop": hop.name, "load_mbps": load, "availability": av}
            target_av = e.value("availability")
            if target_av is not None and av.get("availability_pct", 0) < float(target_av):
                ok = False
                row["why"] = f"the hop holds {av.get('mcs')} for {load:g} Mbps only {pct(av.get('availability_pct', 0))} of the year"
            bw = e.value("bandwidth")
            if bw is not None and hop.capacity(hop.design_rain_mmh) < load:
                row["rain"] = f"in {hop.design_rain_mmh:g} mm/h the hop carries {hop.capacity(hop.design_rain_mmh):g} Mbps for {load:g} Mbps asked"
            findings.append(row)
    return {"ok": ok, "findings": findings}


def check_record(rec: IntentRecord, net: NetworkModel, guards: List[Tuple[IntentRecord, Expectation]],
                 others: List[IntentRecord], twin: Optional[TwinClient] = None, now: Optional[dt.datetime] = None,
                 use_twin: bool = True) -> Dict[str, Any]:
    now = now or dt.datetime.now()
    out: Dict[str, Any] = {"at": time.time(), "verdict": "pass", "rules": [], "conflicts": [], "screens": [],
                           "twin": None, "notes": []}
    rules = guard_findings(rec, guards, now, net)
    out["rules"] = rules
    if any(r["effect"] == "hold" for r in rules):
        out["verdict"] = "held"
    headroom = next(((float(r["value"]), r.get("unit", "%")) for r in rules if r["effect"] == "headroom"), None)
    guard_floor = max((r["value"] for r in rules if r["effect"] == "floor"), key=lambda v: mcs_index(v) or 0, default=None)

    for e in rec.expectations:
        if e.kind == Kind.DELIVER and e.strictness.value == "best_effort":
            # no objectives of its own; the radios queue every slice in one class, so it must not
            # take what the running slices use in clear sky (in rain a keep intent can shed it first)
            sc = screen_delivery(net, e, headroom=headroom, guard_floor=guard_floor)
            over = [h for h in sc.get("hops", []) if h["existing_mbps"] + h["slice_mbps"] > h["clear_capacity_mbps"] + 1e-9]
            if over:
                h = over[0]
                sc.update({"ok": False, "why": f"{h['hop']}: {h['existing_mbps']:g} Mbps already runs and the hop carries "
                                               f"{h['clear_capacity_mbps']:g} Mbps in clear sky; as best effort it would still take "
                                               "capacity from the running slices (one queue)"})
                out["verdict"] = "fail" if out["verdict"] == "pass" else out["verdict"]
            else:
                spare = min((h.get("spare_in_rain_mbps", 0.0) for h in sc.get("hops", [])), default=None)
                sc.update({"ok": True, "why": "best effort: no objectives of its own; it fits in clear sky" +
                           (f", and {spare:g} Mbps is left for it in design rain" if spare is not None else "")})
            out["screens"].append({"expectation": e.id, **sc})
        elif e.kind == Kind.DELIVER:
            sc = screen_delivery(net, e, headroom=headroom, guard_floor=guard_floor)
            entry = {"expectation": e.id, **sc}
            out["screens"].append(entry)
            cand = candidate_for(e)
            if cand and guard_floor and (mcs_index(guard_floor) or 0) > (mcs_index(cand.get("acm_floor")) or 0):
                cand["acm_floor"] = guard_floor
            tw = run_twin(twin, cand) if use_twin and twin is not None and cand and not _capacity_only(sc, headroom) else None
            out["twin"] = tw or out["twin"]
            _decide(out, entry, tw)
        elif e.kind == Kind.CHANGE:
            for sid in e.object.ids:
                s = net.slices.get(sid)
                if s is None:
                    continue
                new_bw = e.value("bandwidth") if e.action.get("metric") == "bandwidth" or e.target("bandwidth") else None
                probe = Expectation(kind=Kind.DELIVER, name=sid, object=e.object.model_copy(deep=True))
                from cer_intent.imf.model import Endpoint
                probe.object.endpoints = [Endpoint(node=x["node"], vlan=x.get("vlan"), port=x.get("port"), ip=x.get("ip"))
                                          for x in s.endpoints[:2]]
                probe.set_target("bandwidth", "ge", float(new_bw if new_bw is not None else (s.bandwidth_mbps or 0)), "Mbps")
                floor = e.value("modulation_floor") or s.acm_floor
                if floor:
                    probe.set_target("modulation_floor", "ge", floor, "MCS")
                if e.value("availability") is not None:
                    probe.set_target("availability", "ge", e.value("availability"), "%")
                sc = screen_delivery(net, probe, replacing=sid, headroom=headroom, guard_floor=guard_floor)
                entry = {"expectation": e.id, "slice": sid, **sc}
                out["screens"].append(entry)
                out["conflicts"] += keep_conflicts(rec, e, sid, new_bw, others)
                tw = None
                if use_twin and twin is not None and new_bw is not None and not _capacity_only(sc, headroom):
                    tw = run_twin(twin, candidate_for(probe, sid))
                    out["twin"] = tw
                _decide(out, entry, tw)
        elif e.kind == Kind.LIFECYCLE and e.action.get("op") == "resume":
            # a resume puts the slice's load back: screened (and run on the twin) like delivering it again
            for sid in e.object.ids:
                probe = resume_probe(sid, others)
                if probe is None:
                    continue
                sc = screen_delivery(net, probe, headroom=headroom, guard_floor=guard_floor)
                entry = {"expectation": e.id, "slice": sid, **sc}
                out["screens"].append(entry)
                tw = None
                if use_twin and twin is not None and not _capacity_only(sc, headroom):
                    tw = run_twin(twin, candidate_for(probe, sid))
                    out["twin"] = tw
                _decide(out, entry, tw)
        elif e.kind == Kind.LIFECYCLE and e.action.get("op") in ("suspend", "delete"):
            for sid in e.object.ids:
                for o in others:
                    if o.id == rec.id or o.state not in (State.ACTIVE, State.DEGRADED, State.SCHEDULED):
                        continue
                    for oe in o.expectations:
                        if oe.kind in (Kind.KEEP, Kind.OBSERVE) and sid in oe.object.ids:
                            out["conflicts"].append({"with": o.id, "why": f"{o.name or o.id} watches {sid}; it ends when {sid} goes",
                                                     "severity": "warn"})
        elif e.kind == Kind.KEEP:
            ks = keep_screen(net, e)
            out["screens"].append({"expectation": e.id, **ks})
            if not ks["ok"]:
                out["notes"].append("the objective may not hold all year at the current load; see the availability per hop")
        elif e.kind == Kind.OPTIMISE and e.action.get("objective") == "energy":
            out["screens"].append({"expectation": e.id, **energy_screen(net, e)})
    out["conflicts"] += window_conflicts(rec, others, net)
    if any(c.get("severity") == "block" for c in out["conflicts"]) and out["verdict"] == "pass":
        out["verdict"] = "fail"
    if not any(e.kind in ACTING_KINDS or e.kind == Kind.KEEP for e in rec.expectations):
        out["verdict"] = "pass"
    return out


def run_twin(twin: "TwinClient", cand: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not cand:
        return None
    return summarise_twin(twin.preflight(cand), twin.last_error)


def _capacity_only(sc: Dict[str, Any], headroom) -> bool:
    """A screen failure the twin cannot overrule: an operator rule (headroom) or more than the hop carries in clear sky."""
    if sc.get("ok") is not False:
        return False
    if headroom:
        return True
    return any(h.get("existing_mbps", 0) + h.get("slice_mbps", 0) > h.get("clear_capacity_mbps", 0) for h in sc.get("hops", []))


def _decide(out: Dict[str, Any], entry: Dict[str, Any], tw: Optional[Dict[str, Any]]) -> None:
    """The twin's NS-3 run decides when it ran; the analytic screen otherwise."""
    if tw and tw.get("ran"):
        failed = [c for c in tw.get("checks", []) if not c.get("ok")]
        if tw.get("verdict") == "fail":
            entry["twin_why"] = "; ".join(f"{c.get('id')} {c.get('value')} (asked {c.get('target', c.get('limit', '?'))})"
                                          for c in failed) or "the twin's run failed"
            if entry.get("ok") is not False:
                entry["why"] = "the twin's NS-3 run: " + entry["twin_why"]
            entry["ok"] = False
        elif entry.get("ok") is False:
            entry["analytic_why"] = entry.get("why")
            entry["why"] = "the twin's NS-3 run carries it with every objective met (the analytic screen alone was stricter: " \
                           + str(entry.get("analytic_why")) + ")"
            entry["ok"] = True
    if entry.get("ok") is False and out["verdict"] == "pass":
        out["verdict"] = "fail"


def summarise_twin(res: Optional[Dict[str, Any]], error: Optional[str]) -> Dict[str, Any]:
    if res is None:
        return {"ran": False, "why": error or "not run"}
    after = ((res.get("scenarios") or {}).get("after") or {})
    replay = ((res.get("engine") or {}).get("replay") or {})
    if replay and not replay.get("exact", True):
        # a recorded run for another load stands in for this one: shown, but it does not decide
        return {"ran": False, "approximate": True, "verdict": res.get("verdict"), "checks": res.get("checks", []),
                "why": "the twin replayed a recorded run for a different load (no NS-3 binary here); the analytic screen decides",
                "engine": (res.get("engine") or {}).get("engine"), "insight": "simulated (nearest recorded run)"}
    return {"ran": True, "verdict": res.get("verdict"), "checks": res.get("checks", []),
            "engine": (res.get("engine") or {}).get("engine") or (res.get("engine") or {}).get("mode"),
            "path": (res.get("network") or {}).get("path"), "hops": after.get("hops"),
            "existing": [f.get("name") for f in (res.get("network") or {}).get("existing_services", [])],
            "insight": res.get("insight", "simulated")}


def keep_conflicts(rec: IntentRecord, e: Expectation, sid: str, new_bw: Optional[float],
                   others: List[IntentRecord]) -> List[Dict[str, Any]]:
    out = []
    if new_bw is None:
        return out
    for o in others:
        if o.id == rec.id or o.state not in (State.ACTIVE, State.DEGRADED):
            continue
        for oe in o.expectations:
            if oe.kind == Kind.KEEP and sid in oe.object.ids:
                kept = oe.value("bandwidth")
                if kept is not None and float(new_bw) < float(kept):
                    out.append({"with": o.id, "severity": "block",
                                "why": f"{o.name or o.id} keeps {sid} at ≥ {float(kept):g} Mbps; this sets {float(new_bw):g}"})
    return out


def window_conflicts(rec: IntentRecord, others: List[IntentRecord], net: NetworkModel) -> List[Dict[str, Any]]:
    """Scheduled deliveries or increases whose windows overlap and together overfill a hop."""
    out = []
    mine = [e for e in rec.expectations if e.kind in (Kind.DELIVER, Kind.CHANGE) and e.context("window")]
    if not mine:
        return out
    now = dt.datetime.now()
    for e in mine:
        s0, e0 = window_bounds(e.context("window").params, now)
        if s0 is None:
            continue
        extra = float(e.value("bandwidth") or 0.0)
        for o in others:
            if o.id == rec.id or o.state != State.SCHEDULED:
                continue
            for oe in o.expectations:
                w = oe.context("window")
                if not w or oe.kind not in (Kind.DELIVER, Kind.CHANGE):
                    continue
                s1, e1 = window_bounds(w.params, now)
                if s1 is None or (e0 and s1 >= e0) or (e1 and s0 >= e1):
                    continue
                total = extra + float(oe.value("bandwidth") or 0.0)
                for hop in net.radio_hops():
                    cap = hop.capacity(hop.design_rain_mmh)
                    if net.load(hop) + total > cap:
                        out.append({"with": o.id, "severity": "block",
                                    "why": f"{o.name or o.id} runs in an overlapping window; together "
                                           f"{net.load(hop) + total:g} Mbps on {hop.name}, which holds {cap:g} Mbps in design rain"})
    return out


def energy_screen(net: NetworkModel, e: Expectation) -> Dict[str, Any]:
    """How far transmit power can come down while the hop keeps the floor and the availability it needs."""
    rows = []
    floor = e.value("modulation_floor")
    for hid in e.object.ids or [h.name for h in net.radio_hops()]:
        a, _, b = hid.partition("|")
        hop = net.hop(a, b)
        cond = next((c for c in e.contexts if c.kind == "condition"), None)
        load = float(cond.params.get("value")) if cond and cond.params.get("value") is not None else net.load(hop)
        from cer_intent.imf.radio import needed_mcs, threshold_db
        need = needed_mcs(load, floor) or "MCS1"
        base = hop.availability(need)
        # automatic transmit power control: in clear sky the radios lower power to what the needed
        # MCS takes (plus a 3 dB safety margin) and raise it again as rain fades the hop, so the
        # availability of that MCS stays where it is
        cut = max(0.0, float(int(base["margin_db"] - 3.0)))
        cut = min(cut, 20.0)
        rows.append({"hop": hid, "load_mbps": load, "needs": need, "threshold_db": threshold_db(need),
                     "margin_db": base["margin_db"], "tx_cut_db": cut, "availability_pct": base["availability_pct"],
                     "why": f"{hid}: {load:g} Mbps needs {need}; in clear sky automatic power control can take transmit power "
                            f"down about {cut:g} dB and brings it back as rain fades the hop, so {need} keeps its "
                            f"{pct(base['availability_pct'])} a year (ITU-R)"})
    return {"ok": True, "hops": rows, "basis": "analytic: clear-sky margin above the needed MCS; ITU-R P.530-18 availability"}
