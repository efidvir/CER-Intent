"""
Answers: exploration and questions
==================================
An explore intent (headroom, what-if, "could I...") is answered from the
analytic radio screen and, when it adds a slice and the twin is reachable, from
the twin's NS-3 pre-flight; nothing in the network changes and the answer says
which of the two it rests on. An ask intent is answered from the network model
and the intent store.
"""
from __future__ import annotations

from typing import Any, Dict, List

from cer_intent.imf.model import Expectation, IntentRecord, Kind, State
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.radio import Hop, availability_for, capacity_mbps, MCS_TABLE, pct

RAIN_WORDS = {"light": 2.5, "moderate": 10.0, "heavy": 50.0, "torrential": 100.0}

EXAMPLES = {
    "deliver": "Connect region-a and edge with 300 Mbps, at most 10 ms, gold",
    "change": "Double the backhaul tonight 20:00-23:00, then restore it",
    "lifecycle": "Suspend every slice except the backhaul",
    "keep": "Never let the backhaul drop below 150 Mbps; take it from best effort first",
    "optimise": "Save energy on the hop at night when traffic is below 100 Mbps, keep MCS4",
    "guard": "No changes during business hours without approval",
    "observe": "Report the lowest modulation on the radio link every hour",
    "explore": "How much more can the hop carry in heavy rain?",
    "ask": "What runs over radio-1?",
}


def _rain(e: Expectation, hop: Hop) -> float:
    w = e.context("weather")
    if not w:
        return 0.0
    if w.params.get("rain_mmh") is not None:
        return float(w.params["rain_mmh"])
    word = str(w.params.get("rain") or "design")
    return RAIN_WORDS.get(word, hop.design_rain_mmh)


def _hops_for(e: Expectation, net: NetworkModel) -> List[Hop]:
    hops: List[Hop] = []
    for i in e.object.ids:
        if "|" in i:
            a, _, b = i.partition("|")
            hops.append(net.hop(a, b))
        elif i in net.slices:
            hops += net.hops(net.slices[i].path)
        elif i in net.nodes and net.nodes[i].radio:
            hops += [h for h in net.radio_hops() if i in (h.a, h.b)]
    eps = [x.node for x in e.object.endpoints if x.node]
    if len(eps) == 2:
        hops += net.hops(net.path(eps[0], eps[1]))
    if not hops:
        hops = net.radio_hops()
    seen, out = set(), []
    for h in hops:
        if h.name not in seen:
            seen.add(h.name)
            out.append(h)
    return out


def headroom(e: Expectation, net: NetworkModel) -> Dict[str, Any]:
    rows, lines = [], []
    for hop in _hops_for(e, net):
        rain = _rain(e, hop)
        load = net.load(hop)
        cap = hop.capacity(rain)
        spare = max(0.0, cap - load)
        av_target = e.value("availability") or 99.99
        ok_caps = [capacity_mbps(n) for n, _, _ in MCS_TABLE if hop.availability(n)["availability_pct"] >= float(av_target)]
        keep_av = max(0.0, (max(ok_caps) if ok_caps else 0.0) - load)
        rows.append({"hop": hop.name, "rain_mmh": rain, "mcs": hop.mcs(rain), "capacity_mbps": cap, "load_mbps": load,
                     "spare_mbps": spare, "spare_keeping_availability_mbps": keep_av, "availability_target_pct": av_target,
                     "slices": [s.id for s in net.slices_on(hop)]})
        weather = f" at {rain:g} mm/h" if rain else " in clear sky"
        now = availability_for(hop, load, net.hop_floor(hop))
        now_av = now.get("availability_pct", 0.0)
        if not now.get("mcs"):
            tail = f"The slices on it ask for {load:g} Mbps, more than it carries at any modulation."
        elif keep_av > 0:
            tail = f"To keep {float(av_target):g} % a year (ITU-R), add at most {keep_av:g} Mbps."
        else:
            tail = f"At today's load the hop already gives {pct(now_av)} a year (ITU-R), below {float(av_target):g} %."
        lines.append(f"{hop.name.replace('|', ' – ')}{weather}: {hop.mcs(rain) or 'no link'}, {cap:g} Mbps; {load:g} Mbps in use, "
                     f"{spare:g} Mbps more fits. {tail}")
    return {"question": "headroom", "text": " ".join(lines), "data": rows, "insight": "analytic",
            "basis": "the twin's radio model with ITU-R P.838/P.530; loads from the slices on record"}


def whatif(e: Expectation, net: NetworkModel, twin=None) -> Dict[str, Any]:
    if e.action.get("remove"):
        r = net.resolve(e.action["remove"], ("slice", "service"))
        sid = r.id if r.ok else e.action["remove"]
        s = net.slices.get(sid)
        if s is None:
            return {"question": "whatif", "text": f"There is no slice called {e.action['remove']}.", "insight": "state"}
        rows = []
        for hop in net.hops(s.path):
            rows.append({"hop": hop.name, "load_now": net.load(hop), "load_after": net.load(hop, exclude=[sid]),
                         "spare_after_in_rain": max(0.0, hop.capacity(hop.design_rain_mmh) - net.load(hop, exclude=[sid]))})
        watchers = [i.get("name") or i.get("id") for i in net.intents if sid in (i.get("slices") or [])]
        txt = f"Without {sid}: " + "; ".join(f"{r['hop'].replace('|', ' – ')} carries {r['load_after']:g} Mbps instead of "
                                              f"{r['load_now']:g}, {r['spare_after_in_rain']:g} Mbps spare in design rain" for r in rows)
        if watchers:
            txt += f". Intents that refer to it: {', '.join(watchers)}."
        return {"question": "whatif", "text": txt, "data": rows, "insight": "analytic"}
    if e.action.get("failure"):
        r = net.resolve(e.action["failure"], ("radio", "site", "hop"))
        node = r.id if r.ok else e.action["failure"]
        if "|" in node:
            a, _, b = node.partition("|")
            hit = [s for s in net.slices.values() if a in s.path and b in s.path]
        else:
            hit = [s for s in net.slices.values() if node in s.path]
        rerouted = []
        for s in hit:
            if len(s.path) >= 2:
                saved = net.links
                net.links = [l for l in saved if node not in (l.a, l.b) and node != f"{l.a}|{l.b}"]
                if net.path(s.path[0], s.path[-1]):
                    rerouted.append(s.id)
                net.links = saved
        lost = [s.id for s in hit if s.id not in rerouted]
        txt = f"No slice runs through {node}." if not hit else (
            f"If {node} fails, {len(hit)} slice(s) are affected: {', '.join(s.id for s in hit)}. "
            + (f"{', '.join(lost)} lose their only path." if lost else "") + (f" {', '.join(rerouted)} can take another path." if rerouted else ""))
        return {"question": "whatif", "text": txt.strip(), "data": {"affected": [s.id for s in hit], "lost": lost, "rerouted": rerouted},
                "insight": "analytic"}
    w = e.context("weather")
    if w is not None and not e.target("bandwidth"):
        out = headroom(e, net)
        out["question"] = "whatif"
        rows = out["data"]
        lines = []
        for row in rows:
            if row["load_mbps"] > row["capacity_mbps"]:
                lines.append(f"{row['hop'].replace('|', ' – ')} at {row['rain_mmh']:g} mm/h carries {row['capacity_mbps']:g} Mbps for "
                             f"{row['load_mbps']:g} Mbps asked: best-effort traffic is cut first, then the lowest priority")
        if lines:
            out["text"] += " " + " ".join(lines)
        return out
    if e.target("bandwidth") is not None:
        return feasible(e, net, twin)
    return {"question": "whatif", "text": "Tell me what to change: a slice to remove, a radio that fails, a rain rate, or traffic to add.",
            "insight": "none"}


def feasible(e: Expectation, net: NetworkModel, twin=None) -> Dict[str, Any]:
    from cer_intent.imf.check import candidate_for, screen_delivery, summarise_twin
    probe = e.model_copy(deep=True)
    probe.kind = Kind.DELIVER
    eps = [x.node for x in probe.object.endpoints if x.node]
    if len(eps) < 2:
        sites = net.sites()
        if len(sites) == 2:
            from cer_intent.imf.model import Endpoint
            probe.object.endpoints = [Endpoint(node=sites[0]), Endpoint(node=sites[1])]
        else:
            return {"question": "feasible", "text": "Between which two sites?", "insight": "none"}
    bw = float(probe.value("bandwidth") or 0.0)
    rain = None
    w = e.context("weather")
    if w is not None:
        hop0 = (net.radio_hops() or [None])[0]
        rain = _rain(e, hop0) if hop0 else None
    sc = screen_delivery(net, probe)
    if rain is not None:
        for row in sc.get("hops", []):
            a, _, b = row["hop"].partition("|")
            hop = net.hop(a, b)
            cap = hop.capacity(rain)
            row.update({"rain_mmh": rain, "rain_mcs": hop.mcs(rain), "rain_capacity_mbps": cap})
            if row["existing_mbps"] + bw > cap:
                sc["ok"] = False
                sc["why"] = f"{row['hop']}: at {rain:g} mm/h it carries {cap:g} Mbps; {row['existing_mbps']:g} + {bw:g} asked"
    out = {"question": "feasible", "data": sc, "insight": "analytic", "basis": sc.get("basis")}
    verdict = "Yes" if sc.get("ok") else "No"
    out["text"] = f"{verdict}: {sc.get('why')}."
    if twin is not None and sc.get("ok") is not False:
        probe.name = probe.name or "what-if"
        cand = candidate_for(probe, "what-if-" + "-".join(eps or ["slice"]))
        res = twin.preflight(cand) if cand else None
        tw = summarise_twin(res, twin.last_error)
        out["twin"] = tw
        if tw.get("ran"):
            out["insight"] = "simulated"
            out["text"] += f" The twin's NS-3 run says {tw.get('verdict')}."
    return out


def answer_explore(e: Expectation, net: NetworkModel, twin=None) -> Dict[str, Any]:
    q = e.action.get("question") or "headroom"
    if q == "headroom":
        return headroom(e, net)
    if q == "whatif":
        return whatif(e, net, twin)
    return feasible(e, net, twin)


def answer_ask(e: Expectation, net: NetworkModel, records: List[IntentRecord]) -> Dict[str, Any]:
    q = e.action.get("question") or "status"
    if q == "capability":
        return {"question": q, "insight": "none",
                "text": "I read requests of nine kinds: deliver, change, lifecycle, keep, optimise, guard, observe, explore and ask. "
                        "Each becomes one intent record with objects, targets and contexts; I ask when something is missing.",
                "data": EXAMPLES}
    if q == "inventory":
        rows = []
        for hop in _hops_for(e, net):
            for s in net.slices_on(hop):
                rows.append({"hop": hop.name, "slice": s.id, "bandwidth_mbps": s.bandwidth_mbps, "vlans": s.vlans(),
                             "technology": s.technology, "floor": s.acm_floor})
        names = sorted({r["slice"] for r in rows})
        return {"question": q, "insight": "state", "data": rows,
                "text": (f"{len(names)} slice(s): " + ", ".join(f"{r['slice']} ({r['bandwidth_mbps']:g} Mbps, VLAN {','.join(map(str, r['vlans'])) or '-'})"
                                                                for r in rows if r['bandwidth_mbps'] is not None)) if rows else "Nothing runs there."}
    if q == "list":
        active = [r for r in records if r.state not in (State.WITHDRAWN, State.REJECTED, State.ANSWERED)]
        guards = [r for r in active if any(x.kind == Kind.GUARD for x in r.expectations)]
        return {"question": q, "insight": "state",
                "data": {"intents": [{"id": r.id, "name": r.name, "state": r.state.value, "summary": r.summary()} for r in active],
                         "slices": list(net.slices)},
                "text": f"{len(active)} intent(s), {len(guards)} rule(s), {len(net.slices)} slice(s): "
                        + "; ".join(f"{r.name or r.id} ({r.state.value})" for r in active[-8:])}
    if q == "explain":
        target = None
        for m in e.object.mentions + e.object.ids:
            target = next((r for r in records if m in (r.id, r.name) or m in (r.links.get("slices") or [])), None)
            if target:
                break
        if target is None and records:
            target = sorted(records, key=lambda r: r.updated_at)[-1]
        if target is None:
            return {"question": q, "insight": "none", "text": "There is no intent to explain yet."}
        if target.state == State.DEGRADED and target.reports:
            reasons = [target.reports[-1].get("why") or "an objective is not met"]
            radios = target.reports[-1].get("radios") or {}
            if radios:
                reasons.append("The radios report " + ", ".join(f"{k} at {v.get('mcs')}" for k, v in radios.items()) + ".")
        elif target.state in (State.HELD, State.NEGOTIATING, State.FAILED):
            check = target.check or {}
            reasons = [s.get("why") for s in check.get("screens", []) if s.get("ok") is False and s.get("why")] + \
                      [r["why"] for r in check.get("rules", []) if r["effect"] == "hold"] + \
                      [c["why"] for c in check.get("conflicts", []) if c.get("severity") == "block"] + \
                      ([(target.answer or {}).get("text")] if target.state == State.FAILED else [])
        else:
            check = target.check or {}
            reasons = [s.get("why") for s in check.get("screens", []) if s.get("why")]
        events = [h["event"] for h in target.history[-4:]]
        return {"question": q, "insight": "state", "data": {"intent": target.id, "state": target.state.value, "events": events},
                "text": f"{target.name or target.id} is {target.state.value}. " + " ".join(r for r in reasons[:3] if r)}
    # status / metric
    rows = []
    for hop in _hops_for(e, net):
        load = net.load(hop)
        rows.append({"hop": hop.name, "load_mbps": load, "clear_capacity_mbps": hop.capacity(0),
                     "rain_capacity_mbps": hop.capacity(hop.design_rain_mmh), "floor": net.hop_floor(hop),
                     "availability": availability_for(hop, load, net.hop_floor(hop))})
    degraded = [r for r in records if r.state == State.DEGRADED]
    text = "; ".join(f"{r['hop'].replace('|', ' – ')}: {r['load_mbps']:g} of {r['clear_capacity_mbps']:g} Mbps in use "
                     f"({r['rain_capacity_mbps']:g} in design rain), availability {pct(r['availability'].get('availability_pct', 0))}"
                     for r in rows)
    text += f". {len(net.slices)} slice(s); " + (f"{len(degraded)} intent(s) degraded." if degraded else "every intent is met.")
    return {"question": q, "insight": "analytic", "data": rows, "text": text}
