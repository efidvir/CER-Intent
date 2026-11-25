"""
When the network cannot do what was asked: alternatives
=======================================================
3GPP TS 28.312 (Rel-19) lets an intent handler answer an infeasible intent with
what it can do instead; TMF921 v5 carries the same exchange. Each alternative
here says what changes, what it costs, and how it was checked:

  most_that_fits     the largest bandwidth that fits on every hop in design rain
  keep_availability  the bandwidth that still gives the asked availability (ITU-R)
  accept_availability  the asked bandwidth, with the availability the hop gives
  lower_floor        the highest modulation floor the hop holds in design rain
  best_effort        no guarantee: carried when there is room
  take_from          shrink a lower-priority slice on the same hop by the shortfall

Accepting one changes the intent (values marked "negotiated") and checks it again.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from cer_intent.imf.model import Expectation, IntentRecord, Kind, Source, Strictness
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.radio import MCS_TABLE, availability_for, capacity_mbps, mcs_index, pct


def _floor10(x: float) -> float:
    return float(max(0, math.floor(x / 10.0) * 10)) if x >= 10 else round(max(0.0, x), 1)


def twin_max(twin, e: Expectation, lo: float, hi: float, slice_id: Optional[str], runs: int = 3) -> Optional[float]:
    """The largest bandwidth in [lo, hi) the twin's NS-3 run carries with every objective met (bisection, 10 Mbps steps)."""
    from cer_intent.imf.check import candidate_for
    probe = e.model_copy(deep=True)
    best = None
    if lo <= 0:
        # does a small slice pass at all? if not, the miss does not depend on bandwidth
        small = _floor10(max(10.0, 0.1 * hi))
        probe.set_target("bandwidth", "ge", small, "Mbps")
        res = twin.preflight(candidate_for(probe, slice_id))
        if res is None or res.get("verdict") != "pass":
            return None
        best, lo = small, small
    a, b = lo, hi
    for _ in range(runs):
        mid = _floor10((a + b) / 2.0)
        if mid <= a or mid >= b:
            break
        probe.set_target("bandwidth", "ge", mid, "Mbps")
        res = twin.preflight(candidate_for(probe, slice_id))
        if res is None:
            return best
        if res.get("verdict") == "pass":
            best, a = mid, mid
        else:
            b = mid
    if best is None and lo >= 10:
        probe.set_target("bandwidth", "ge", lo, "Mbps")
        res = twin.preflight(candidate_for(probe, slice_id))
        if res is not None and res.get("verdict") == "pass":
            best = lo
    return best


def alternatives(rec: IntentRecord, net: NetworkModel, check: Dict[str, Any], twin=None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sc in check.get("screens", []):
        if sc.get("ok") is not False:
            continue
        e = next((x for x in rec.expectations if x.id == sc.get("expectation")), None)
        if e is None or e.kind not in (Kind.DELIVER, Kind.CHANGE):
            continue
        asked = float(e.value("bandwidth") or 0.0)
        hops = sc.get("hops") or []
        if not hops:
            continue
        spare = min(h.get("spare_in_rain_mbps", 0.0) for h in hops)
        target_av = e.value("availability")
        floor = sc.get("floor")
        # 1. the most that fits (the twin finds it when it ran; the analytic screen otherwise)
        fit = _floor10(spare)
        basis = "in design rain"
        if twin is not None and (check.get("twin") or {}).get("ran") and e.kind in (Kind.DELIVER, Kind.CHANGE):
            sid = e.name if e.kind == Kind.DELIVER else (e.object.ids or [None])[0]
            probe = e
            if e.kind == Kind.CHANGE and sid in net.slices:
                from cer_intent.imf.model import Endpoint
                probe = e.model_copy(deep=True)
                probe.object.endpoints = [Endpoint(node=x["node"], vlan=x.get("vlan"), port=x.get("port"), ip=x.get("ip"))
                                          for x in net.slices[sid].endpoints[:2]]
            twin_failed_here = sc.get("twin_why") is not None
            lo = 0.0 if twin_failed_here else max(0.0, min(fit, asked))
            found = twin_max(twin, probe, lo, asked if not twin_failed_here else min(asked, max(fit, 10.0) if fit < asked else asked),
                             sid, runs=4 if twin_failed_here else 3)
            if found is not None:
                fit, basis = found, "with every objective met on the twin's NS-3 run"
            elif twin_failed_here:
                fit = 0.0
        # the twin's measured value for a target it found missed, as an alternative to accept
        for c in ((check.get("twin") or {}).get("checks") or []):
            if c.get("ok") or c.get("id") not in ("loss", "latency"):
                continue
            m = re.search(r"([\d.]+)", str(c.get("value") or ""))
            if not m:
                continue
            got = float(m.group(1))
            relaxed = math.ceil(got * 100) / 100 if c["id"] == "loss" else math.ceil(got * 10) / 10
            unit = "%" if c["id"] == "loss" else "ms"
            out.append(_alt(e, f"accept_{c['id']}", f"Accept {c['id']} ≤ {relaxed:g} {unit} at {asked:g} Mbps (the twin's run gives {c['value']})",
                            [{"metric": c["id"], "op": "le", "value": relaxed}],
                            f"{c['id']} objective relaxed from {c.get('target')} to ≤ {relaxed:g} {unit}"))
        if e.kind == Kind.CHANGE:
            cur = (net.slices.get((e.object.ids or [""])[0]) or None)
            if cur is not None and cur.bandwidth_mbps is not None and fit <= cur.bandwidth_mbps:
                fit = 0.0
        if fit >= max(10.0, 0.05 * asked) and fit < asked:
            changes = [{"metric": "bandwidth", "op": "ge", "value": fit}]
            verb = "Deliver" if e.kind == Kind.DELIVER else f"Set {(e.object.ids or ['it'])[0]} to"
            label = f"{verb} {fit:g} Mbps: the most that fits {basis}"
            trade = f"{asked - fit:g} Mbps less than asked"
            if target_av is not None:
                worst = 100.0
                for h in hops:
                    a, _, b = h["hop"].partition("|")
                    av = availability_for(net.hop(a, b), h.get("existing_mbps", 0.0) + fit, floor)
                    worst = min(worst, av.get("availability_pct", 0.0))
                if worst < float(target_av):
                    changes.append({"metric": "availability", "op": "ge", "value": math.floor(worst * 1000) / 1000})
                    label = f"{verb} {fit:g} Mbps with {pct(worst)} availability: the most that fits {basis}"
                    trade += f"; {float(target_av):g} % is not reachable on this hop at today's load (ITU-R)"
            out.append(_alt(e, "most_that_fits", label, changes, trade))
        # 2. availability: keep it with less bandwidth, or accept what the hop gives
        if target_av is not None:
            limits = []
            for h in hops:
                a, _, b = h["hop"].partition("|")
                hop = net.hop(a, b)
                ok_caps = [capacity_mbps(n) for n, _, _ in MCS_TABLE
                           if hop.availability(n)["availability_pct"] >= float(target_av)
                           and (not floor or (mcs_index(n) or 0) >= (mcs_index(floor) or 0))]
                limits.append((max(ok_caps) if ok_caps else 0.0) - h.get("existing_mbps", 0.0))
            best_total = _floor10(min(limits)) if limits else 0.0
            if 0 < best_total < asked:
                out.append(_alt(e, "keep_availability", f"Deliver {best_total:g} Mbps and keep {float(target_av):g} % availability",
                                [{"metric": "bandwidth", "op": "ge", "value": best_total}],
                                f"{asked - best_total:g} Mbps less; ITU-R availability stays at the asked value"))
            worst = min((h["availability"].get("availability_pct", 0.0) for h in hops), default=0.0)
            if worst > 0 and asked <= spare + 1e-9 and sc.get("twin_why") is None:
                out.append(_alt(e, "accept_availability", f"Deliver {asked:g} Mbps with {pct(worst)} availability",
                                [{"metric": "availability", "op": "ge", "value": math.floor(worst * 1000) / 1000}],
                                f"about {(float(target_av) - worst) / 100 * 525960:.0f} more minutes a year below the asked rate"))
        # 3. a floor the hop holds in design rain
        if floor and any(h.get("floor_holds_in_rain") is False for h in hops):
            holds = min((mcs_index(h.get("rain_mcs")) or 0) for h in hops)
            if holds > 0:
                new_floor = f"MCS{holds}"
                out.append(_alt(e, "lower_floor", f"Hold {new_floor} instead of {floor} in rain",
                                [{"metric": "modulation_floor", "op": "ge", "value": new_floor}],
                                f"in design rain the hop keeps carrying at {new_floor} ({capacity_mbps(new_floor):g} Mbps) instead of dropping"))
        # 4. take the shortfall from a lower-priority slice on the hop
        shortfall = asked - spare
        if shortfall > 0:
            mine = e.priority or 5
            for h in hops:
                a, _, b = h["hop"].partition("|")
                for s in net.slices_on(net.hop(a, b)):
                    if s.id == e.name or not s.bandwidth_mbps:
                        continue
                    other_prio = _priority_of(s.id, net)
                    if other_prio is None or other_prio >= mine:
                        continue
                    floor_kept = _kept_floor(s.id, net)
                    if floor_kept is not None and s.bandwidth_mbps - shortfall < floor_kept:
                        continue
                    if s.bandwidth_mbps - shortfall < 10:
                        continue
                    new_other = _floor10(s.bandwidth_mbps - shortfall)
                    checked = ""
                    if twin is not None and (check.get("twin") or {}).get("ran"):
                        from cer_intent.imf.check import candidate_for
                        res = twin.preflight(candidate_for(e), overrides={s.id: {"bandwidth_mbps": new_other}})
                        if res is None or res.get("verdict") != "pass":
                            continue
                        checked = " (the twin's NS-3 run passes)"
                    alt = _alt(e, "take_from", f"Take {s.bandwidth_mbps - new_other:g} Mbps from {s.id} ({s.bandwidth_mbps:g} → {new_other:g} Mbps){checked}",
                               [], f"{s.id} runs with {new_other:g} Mbps while this slice runs",
                               extra=[{"kind": "change", "slice": s.id, "metric": "bandwidth", "value": new_other,
                                       "before": s.bandwidth_mbps}])
                    out.append(alt)
                    break
        # 5. best effort, when it fits in clear sky
        clear_spare = min((h.get("clear_capacity_mbps", 0.0) - h.get("existing_mbps", 0.0) for h in hops), default=0.0)
        if e.strictness != Strictness.BEST_EFFORT and e.kind == Kind.DELIVER and asked <= clear_spare + 1e-9:
            out.append(_alt(e, "best_effort", f"Deliver {asked:g} Mbps as best effort",
                            [{"strictness": "best_effort"}],
                            "no guarantee: it gets what is left after the guaranteed slices, and less in heavy rain"))
    for i, a in enumerate(out, 1):
        a["id"] = f"alt-{i}"
        a["n"] = i
    return out


def _kept_floor(slice_id: str, net: NetworkModel) -> Optional[float]:
    """The bandwidth a keep intent holds this slice at, if any."""
    return max([float(k) for i in net.intents for k in (i.get("keeps") or {}).get(slice_id, [])] or [0.0]) or None


def _priority_of(slice_id: str, net: NetworkModel) -> Optional[int]:
    for i in net.intents:
        if slice_id in (i.get("slices") or []):
            return i.get("priority")
    return None


def _alt(e: Expectation, kind: str, label: str, changes: List[Dict[str, Any]], trade_off: str,
         extra: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {"kind": kind, "expectation": e.id, "label": label, "changes": changes, "trade_off": trade_off,
            "extra": extra or []}


def apply_alternative(rec: IntentRecord, alt: Dict[str, Any], stable: bool = False) -> None:
    """Accepting an alternative: the changed values are recorded as negotiated (stable: re-applied on a re-check)."""
    e = next((x for x in rec.expectations if x.id == alt["expectation"]), None)
    if e is None:
        return
    for ch in alt.get("changes", []):
        if "strictness" in ch:
            e.strictness = Strictness(ch["strictness"])
            if e.strictness == Strictness.BEST_EFFORT:      # no guarantee: the objectives become preferences
                e.targets = [t for t in e.targets if t.metric not in ("availability", "loss", "latency", "jitter")]
                e.priority = 1
            continue
        unit = {"bandwidth": "Mbps", "availability": "%", "modulation_floor": "MCS", "latency": "ms"}.get(ch["metric"])
        e.set_target(ch["metric"], ch["op"], ch["value"], unit, Source.NEGOTIATED, note=alt["label"])
        if e.kind == Kind.CHANGE and ch["metric"] == e.action.get("metric"):
            e.action.update({"op": "set", "value": ch["value"]})
    if not stable:
        rec.links.setdefault("negotiated", []).append({"alternative": alt["label"], "kind": alt["kind"]})
    for i, x in enumerate(alt.get("extra", [])):
        if x.get("kind") == "change":
            from cer_intent.imf.model import ObjectRef
            ne = Expectation(id=f"{alt['id']}-x{i}", kind=Kind.CHANGE, verb="negotiated",
                             object=ObjectRef(type="slice", ids=[x["slice"]], mentions=[x["slice"]]),
                             action={"op": "set", "metric": x["metric"], "value": x["value"], "negotiated": True,
                                     "before": {x["slice"]: {x["metric"]: x.get("before")}}, "revert_with": e.id},
                             text=alt["label"])
            ne.set_target(x["metric"], "ge", x["value"], "Mbps", Source.NEGOTIATED, note=alt["label"])
            if not any(y.id == ne.id for y in rec.expectations):
                rec.expectations.append(ne)
