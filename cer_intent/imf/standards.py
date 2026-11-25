"""
The intent record in the standards' shapes
==========================================
3GPP TS 28.312 (intent-driven management, Rel-18/19)
  Intent { id, userLabel, intentExpectations[], intentContexts[], intentPriority,
           observationPeriod, intentAdminState }
  IntentExpectation { expectationId, expectationVerb, expectationObject
           { objectType, objectInstance, objectContexts[] }, expectationTargets
           [ { targetName, targetCondition, targetValueRange, targetContexts[] } ],
           expectationContexts[] }
  IntentReport { intentFulfilmentReport, intentConflictReports[],
           intentFeasibilityCheckReport, lastUpdatedTime }
  Conditions: IS_EQUAL_TO, IS_LESS_THAN, IS_GREATER_THAN, IS_WITHIN_RANGE,
  IS_EQUAL_TO_OR_LESS_THAN, IS_EQUAL_TO_OR_GREATER_THAN, IS_ONE_OF ...

TM Forum TMF921 v5 (Intent Management API)
  Intent { id, href, name, description, priority, lifecycleStatus, creationDate,
           lastUpdate, expression { @type JsonLdExpression, expressionValue } }
  The expression follows the TM Forum Intent Ontology's structure (icm:Intent
  with delivery, property and reporting expectations). Metric names are
  CER-Intent's own (namespace cer:), as the TIO leaves domain vocabularies to
  their owners.

Both map to and from the same IntentRecord, so a request that arrives as
TMF921 or 28.312 is matched, checked, negotiated and reported like a typed one.
Values CER-Intent adds that the standards have no name for are carried with a
"cer" prefix (for example targetCondition "IS_MINIMIZED" for an optimisation).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from cer_intent.imf.model import (Context, Endpoint, Expectation, IntentRecord, Kind, ObjectRef, Source, State,
                                  Target)

TARGET_NAMES = {"bandwidth": "oneWayBandwidth", "latency": "oneWayDelayMaximum", "jitter": "oneWayDelayVariationMaximum",
                "loss": "oneWayPacketLoss", "availability": "serviceAvailability", "modulation_floor": "minModulation",
                "energy": "energyConsumption", "tx_power": "txPower", "headroom": "capacityHeadroom",
                "vlan": "vlanId", "technology": "realizationTechnology", "throughput": "throughput",
                "utilisation": "utilisation", "priority": "priority", "capacity": "capacity",
                "lowest_modulation": "lowestModulation"}
TARGET_BY_NAME = {v: k for k, v in TARGET_NAMES.items()}
CONDITIONS = {"ge": "IS_EQUAL_TO_OR_GREATER_THAN", "le": "IS_EQUAL_TO_OR_LESS_THAN", "gt": "IS_GREATER_THAN",
              "lt": "IS_LESS_THAN", "eq": "IS_EQUAL_TO", "between": "IS_WITHIN_RANGE", "set": "IS_EQUAL_TO",
              "minimize": "IS_MINIMIZED", "maximize": "IS_MAXIMIZED", "scale": "IS_EQUAL_TO", "add": "IS_EQUAL_TO"}
CONDITION_OPS = {"IS_EQUAL_TO_OR_GREATER_THAN": "ge", "IS_EQUAL_TO_OR_LESS_THAN": "le", "IS_GREATER_THAN": "gt",
                 "IS_LESS_THAN": "lt", "IS_EQUAL_TO": "eq", "IS_WITHIN_RANGE": "between", "IS_MINIMIZED": "minimize",
                 "IS_MAXIMIZED": "maximize", "IS_ONE_OF": "eq"}
VERBS = {Kind.DELIVER: "DELIVER", Kind.CHANGE: "DELIVER", Kind.LIFECYCLE: "DELIVER", Kind.KEEP: "ENSURE",
         Kind.OPTIMISE: "ENSURE", Kind.GUARD: "ENSURE", Kind.OBSERVE: "ENSURE", Kind.EXPLORE: "ENSURE", Kind.ASK: "ENSURE"}
OBJECT_TYPES = {"slice": "TransportNetworkSlice", "service": "TransportNetworkSlice", "hop": "RadioHop",
                "radio": "RadioNode", "site": "Site", "network": "TransportNetwork", "intent": "Intent", "link": "RadioHop"}
OBJECT_BY_TYPE = {"TransportNetworkSlice": "slice", "RadioHop": "hop", "RadioNode": "radio", "Site": "site",
                  "TransportNetwork": "network", "Intent": "intent", "NetworkSlice": "slice", "NetworkSliceSubnet": "slice"}
TMF_STATUS = {State.DRAFT: "acknowledged", State.CLARIFYING: "pending", State.CHECKED: "pending",
              State.NEGOTIATING: "pending", State.HELD: "held", State.SCHEDULED: "scheduled", State.ACTIVE: "active",
              State.DEGRADED: "degraded", State.SUSPENDED: "suspended", State.ANSWERED: "completed",
              State.WITHDRAWN: "terminated", State.COMPLETED: "completed", State.FAILED: "failed", State.REJECTED: "rejected"}
FULFILMENT = {State.ACTIVE: ("FULFILLED", None), State.ANSWERED: ("FULFILLED", None), State.COMPLETED: ("FULFILLED", None),
              State.DEGRADED: ("NOT_FULFILLED", "DEGRADED"), State.SUSPENDED: ("NOT_FULFILLED", "SUSPENDED"),
              State.WITHDRAWN: ("NOT_FULFILLED", "TERMINATED"), State.FAILED: ("NOT_FULFILLED", "FULFILMENTFAILED"),
              State.REJECTED: ("NOT_FULFILLED", "FULFILMENTFAILED"), State.HELD: ("NOT_FULFILLED", "ACKNOWLEDGED")}


def _iso(t: Optional[float]) -> Optional[str]:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat() if t else None


# ── 3GPP TS 28.312 ────────────────────────────────────────────────────────────

def _context_3gpp(c: Context) -> Dict[str, Any]:
    p = c.params
    if c.kind == "window":
        return {"contextAttribute": "timeWindow", "contextCondition": "IS_WITHIN_RANGE",
                "contextValueRange": {k: p[k] for k in ("start", "end", "days", "label", "date", "duration_s", "until") if p.get(k)}}
    if c.kind == "schedule":
        return {"contextAttribute": "observationPeriod", "contextCondition": "IS_EQUAL_TO", "contextValueRange": p.get("seconds")}
    if c.kind == "weather":
        return {"contextAttribute": "rainRate", "contextCondition": CONDITIONS.get(p.get("op", "ge"), "IS_EQUAL_TO_OR_GREATER_THAN"),
                "contextValueRange": p.get("rain_mmh", p.get("rain"))}
    if c.kind == "condition":
        return {"contextAttribute": TARGET_NAMES.get(p.get("metric"), p.get("metric")),
                "contextCondition": CONDITIONS.get(p.get("op", "eq"), "IS_EQUAL_TO"), "contextValueRange": p.get("value")}
    return {"contextAttribute": c.kind, "contextCondition": "IS_EQUAL_TO", "contextValueRange": p}


def _context_from_3gpp(c: Dict[str, Any]) -> Context:
    attr, cond, val = c.get("contextAttribute"), c.get("contextCondition"), c.get("contextValueRange")
    if attr == "timeWindow" and isinstance(val, dict):
        return Context(kind="window", params=val)
    if attr == "observationPeriod":
        return Context(kind="schedule", params={"seconds": val, "every": f"{int(val or 0) // 60} min"})
    if attr == "rainRate":
        return Context(kind="weather", params={"rain_mmh": val, "op": CONDITION_OPS.get(cond, "ge")})
    return Context(kind="condition", params={"metric": TARGET_BY_NAME.get(attr, attr), "op": CONDITION_OPS.get(cond, "eq"), "value": val})


def to_3gpp(rec: IntentRecord) -> Dict[str, Any]:
    exps = []
    for e in rec.expectations:
        instance = e.object.ids or ([e.name] if e.name else []) or e.object.mentions
        obj: Dict[str, Any] = {"objectType": OBJECT_TYPES.get(e.object.type, e.object.type),
                               "objectInstance": instance[0] if len(instance) == 1 else instance}
        if e.object.endpoints:
            obj["objectContexts"] = [{"contextAttribute": "serviceDemarcationPoints", "contextCondition": "IS_ALL_OF",
                                      "contextValueRange": [{"node": x.node, "port": x.port, "vlan": x.vlan, "ip": x.ip}
                                                            for x in e.object.endpoints]}]
        targets = [{"targetName": TARGET_NAMES.get(t.metric, t.metric), "targetCondition": CONDITIONS.get(t.op, "IS_EQUAL_TO"),
                    "targetValueRange": t.value, **({"targetUnit": t.unit} if t.unit else {}),
                    "cerSource": t.source.value} for t in e.targets]
        item = {"expectationId": e.id, "expectationVerb": VERBS[e.kind], "expectationObject": obj,
                "expectationTargets": targets, "expectationContexts": [_context_3gpp(c) for c in e.contexts],
                "cerKind": e.kind.value}
        if e.action.get("op") or e.action.get("rule"):
            item["cerAction"] = {k: v for k, v in e.action.items() if k in ("op", "rule", "metric", "value", "objective", "revert")}
        exps.append(item)
    prio = max([e.priority for e in rec.expectations if e.priority] or [5])
    sched = next((c for e in rec.expectations for c in e.contexts if c.kind == "schedule"), None)
    return {"id": rec.id, "userLabel": rec.name or rec.text, "intentExpectations": exps, "intentPriority": prio,
            **({"observationPeriod": sched.params.get("seconds")} if sched else {}),
            "intentAdminState": "DEACTIVATED" if rec.state in (State.SUSPENDED, State.WITHDRAWN) else "ACTIVATED"}


def from_3gpp(body: Dict[str, Any]) -> IntentRecord:
    intent = body.get("Intent") or body.get("intent") or body
    exps = []
    for x in intent.get("intentExpectations") or []:
        kind = x.get("cerKind")
        verb = (x.get("expectationVerb") or "DELIVER").upper()
        obj = x.get("expectationObject") or {}
        otype = OBJECT_BY_TYPE.get(obj.get("objectType"), "slice")
        targets = []
        for t in x.get("expectationTargets") or []:
            metric = TARGET_BY_NAME.get(t.get("targetName"), t.get("targetName"))
            targets.append(Target(metric=metric, op=CONDITION_OPS.get(t.get("targetCondition"), "eq"),
                                  value=t.get("targetValueRange"), unit=t.get("targetUnit"), source=Source.STATED))
        eps = []
        for c in obj.get("objectContexts") or []:
            if c.get("contextAttribute") == "serviceDemarcationPoints":
                for p in c.get("contextValueRange") or []:
                    eps.append(Endpoint(mention=p.get("node"), port=p.get("port"), vlan=p.get("vlan"), ip=p.get("ip")))
        inst = obj.get("objectInstance")
        insts = inst if isinstance(inst, list) else ([inst] if inst else [])
        if kind is None:
            if verb == "DELIVER":
                kind = "deliver" if eps else "change"
            elif any(t.op in ("minimize", "maximize") for t in targets):
                kind = "optimise"
            else:
                kind = "keep"
        e = Expectation(kind=Kind(kind), verb=verb.lower(), targets=targets,
                        object=ObjectRef(type=otype, mentions=[str(i) for i in insts] if not eps else [], endpoints=eps),
                        contexts=[_context_from_3gpp(c) for c in x.get("expectationContexts") or []],
                        action=dict(x.get("cerAction") or {}))
        if e.kind == Kind.DELIVER and insts and not eps:
            e.name = str(insts[0])
        if e.kind == Kind.DELIVER and eps and insts:
            e.name = str(insts[0])
        if e.kind == Kind.CHANGE and not e.action.get("op") and targets:
            e.action = {"op": "set", "metric": targets[0].metric, "value": targets[0].value}
        if e.kind == Kind.OPTIMISE and not e.action.get("op"):
            t = next((t for t in targets if t.op in ("minimize", "maximize")), None)
            if t:
                e.action = {"op": t.op, "objective": t.metric}
                targets.remove(t)
        exps.append(e)
    if intent.get("observationPeriod"):
        for e in exps:
            if not e.context("schedule") and e.kind in (Kind.OBSERVE, Kind.KEEP):
                e.contexts.append(Context(kind="schedule", params={"seconds": intent["observationPeriod"]}))
    rec = IntentRecord(name=intent.get("userLabel"), text=intent.get("userLabel"), channel="3gpp", expectations=exps)
    if intent.get("id"):
        rec.links["external_id"] = intent["id"]
    return rec


def report_3gpp(rec: IntentRecord) -> Dict[str, Any]:
    status, nf_state = FULFILMENT.get(rec.state, ("NOT_FULFILLED", "ACKNOWLEDGED"))
    last = rec.reports[-1] if rec.reports else {}
    results = []
    for e in rec.expectations:
        er = (last.get("expectations") or {}).get(e.id, {})
        results.append({"expectationId": e.id,
                        "expectationFulfilmentInfo": {"fulfilmentStatus": er.get("status", status)},
                        "targetFulfilmentResults": [
                            {"targetName": TARGET_NAMES.get(t.metric, t.metric),
                             "targetFulfilmentInfo": {"fulfilmentStatus": (er.get("targets") or {}).get(t.metric, {}).get("status", status)},
                             "targetAchievedValue": (er.get("targets") or {}).get(t.metric, {}).get("achieved")}
                            for t in e.targets]})
    check = rec.check or {}
    out: Dict[str, Any] = {
        "intentReference": rec.id,
        "intentFulfilmentReport": {"intentFulfilmentInfo": {"fulfilmentStatus": status,
                                                            **({"notFulfilledState": nf_state} if nf_state else {}),
                                                            **({"notFulfilledReasons": [s.get("why") for s in check.get("screens", []) if s.get("ok") is False]}
                                                               if status != "FULFILLED" else {})},
                                   "expectationFulfilmentResults": results},
        "intentConflictReports": [{"conflictType": "INTENT_CONFLICT", "conflictingIntent": c.get("with"),
                                   "conflictReason": c.get("why"), "recommendedSolutions": [a["label"] for a in rec.alternatives][:3]}
                                  for c in check.get("conflicts", [])],
        "lastUpdatedTime": _iso(rec.updated_at),
    }
    if check:
        feasible = check.get("verdict") in ("pass",)
        out["intentFeasibilityCheckReport"] = {
            "feasibilityCheckResult": "FEASIBLE" if feasible else "INFEASIBLE",
            **({} if feasible else {"infeasibilityReason": "; ".join(s.get("why") for s in check.get("screens", []) if s.get("ok") is False)
                                   or "; ".join(r["why"] for r in check.get("rules", []))}),
            "cerTwin": check.get("twin"),
        }
        if rec.alternatives:
            out["intentFeasibilityCheckReport"]["cerAlternatives"] = [{"id": a["id"], "label": a["label"], "tradeOff": a["trade_off"],
                                                                       "changes": a["changes"]} for a in rec.alternatives]
    if rec.answer:
        out["cerExplorationResult"] = rec.answer
    return out


# ── TM Forum TMF921 v5 ────────────────────────────────────────────────────────

TIO_CONTEXT = {"icm": "http://tio.models.tmforum.org/tio/v3.6.0/IntentCommonModel/",
               "quan": "http://tio.models.tmforum.org/tio/v3.6.0/QuantityOntology/",
               "set": "http://tio.models.tmforum.org/tio/v3.6.0/SetOperators/",
               "t": "http://www.w3.org/2006/time#",
               "cer": "https://cer-intent.example/ns#"}
QUAN = {"ge": "quan:atLeast", "le": "quan:atMost", "gt": "quan:larger", "lt": "quan:smaller", "eq": "quan:equal",
        "between": "quan:inRange", "minimize": "cer:minimize", "maximize": "cer:maximize", "set": "quan:equal"}
QUAN_OPS = {v: k for k, v in QUAN.items()}


def expression(rec: IntentRecord) -> Dict[str, Any]:
    exps: List[Dict[str, Any]] = []
    for e in rec.expectations:
        target = f"cer:{(e.object.ids or [e.name] or ['network'])[0] if (e.object.ids or e.name) else e.object.type}"
        if e.kind == Kind.DELIVER:
            exps.append({"@id": f"cer:{e.id}", "@type": "icm:DeliveryExpectation", "icm:target": target,
                         "cer:kind": e.kind.value,
                         "icm:params": {"cer:endpoints": [{"cer:node": x.node or x.mention, "cer:port": x.port, "cer:vlan": x.vlan,
                                                           "cer:ip": x.ip} for x in e.object.endpoints]}})
        elif e.kind == Kind.OBSERVE:
            exps.append({"@id": f"cer:{e.id}", "@type": "icm:ReportingExpectation", "icm:target": target,
                         "cer:kind": e.kind.value, "cer:metrics": e.action.get("metrics"),
                         "icm:reportingInterval": (e.context("schedule").params.get("seconds") if e.context("schedule") else None)})
            continue
        conditions = []
        for t in e.targets:
            unit = {"quan:unit": t.unit} if t.unit else {}
            value = {"@value": t.value, **unit} if t.op != "between" else {"quan:min": t.value[0], "quan:max": t.value[1], **unit}
            conditions.append({"@type": "icm:Condition", "cer:metric": t.metric, QUAN.get(t.op, "quan:equal"): value,
                               "cer:source": t.source.value})
        if e.action.get("objective"):
            conditions.append({"@type": "icm:Condition", "cer:metric": e.action["objective"], QUAN.get(e.action.get("op"), "cer:minimize"): {}})
        if conditions or e.kind != Kind.DELIVER:
            exps.append({"@id": f"cer:{e.id}-p", "@type": "icm:PropertyExpectation", "icm:target": target, "cer:kind": e.kind.value,
                         **({"cer:action": {k: v for k, v in e.action.items() if k in ("op", "rule", "metric", "value", "revert")}}
                            if e.action.get("op") or e.action.get("rule") else {}),
                         "log:allOf": conditions,
                         **({"icm:context": [_context_3gpp(c) for c in e.contexts]} if e.contexts else {})})
    return {"@type": "JsonLdExpression",
            "expressionValue": {"@context": TIO_CONTEXT, "@id": f"cer:{rec.id}", "@type": "icm:Intent",
                                "icm:hasExpectation": exps}}


def to_tmf921(rec: IntentRecord, base: str = "") -> Dict[str, Any]:
    return {"id": rec.id, "href": f"{base}/tmf-api/intentManagement/v5/intent/{rec.id}", "@type": "Intent",
            "name": rec.name or rec.id, "description": rec.text, "version": "1",
            "priority": str(max([e.priority for e in rec.expectations if e.priority] or [5])),
            "lifecycleStatus": TMF_STATUS.get(rec.state, rec.state.value), "statusChangeDate": _iso(rec.updated_at),
            "creationDate": _iso(rec.created_at), "lastUpdate": _iso(rec.updated_at), "expression": expression(rec),
            "cerQuestions": [q.model_dump() for q in rec.questions],
            "cerAlternatives": [{"id": a["id"], "label": a["label"], "tradeOff": a["trade_off"]} for a in rec.alternatives]}


def from_tmf921(body: Dict[str, Any]) -> IntentRecord:
    """A TMF921 Intent: an expression to read (JSON-LD), or a description in words."""
    ev = ((body.get("expression") or {}).get("expressionValue")) or {}
    exps: List[Expectation] = []
    for x in ev.get("icm:hasExpectation", []) or []:
        t = x.get("@type")
        kind = x.get("cer:kind")
        target = str(x.get("icm:target") or "").replace("cer:", "")
        if t == "icm:DeliveryExpectation":
            eps = [Endpoint(mention=p.get("cer:node"), port=p.get("cer:port"), vlan=p.get("cer:vlan"), ip=p.get("cer:ip"))
                   for p in (x.get("icm:params") or {}).get("cer:endpoints", [])]
            exps.append(Expectation(kind=Kind(kind or "deliver"), object=ObjectRef(type="slice", endpoints=eps), name=target or None))
            continue
        if t == "icm:ReportingExpectation":
            e = Expectation(kind=Kind.OBSERVE, object=ObjectRef(type="network", mentions=[target] if target else []),
                            action={"op": "report", "metrics": x.get("cer:metrics") or ["status"]})
            if x.get("icm:reportingInterval"):
                e.contexts.append(Context(kind="schedule", params={"seconds": x["icm:reportingInterval"]}))
            exps.append(e)
            continue
        targets = []
        action = dict(x.get("cer:action") or {})
        for c in x.get("log:allOf", []) or []:
            metric = c.get("cer:metric")
            for k, v in c.items():
                if k in QUAN_OPS:
                    op = QUAN_OPS[k]
                    if op in ("minimize", "maximize"):
                        action.update({"op": op, "objective": metric})
                        continue
                    value = [v.get("quan:min"), v.get("quan:max")] if op == "between" else v.get("@value")
                    targets.append(Target(metric=metric, op=op, value=value, unit=v.get("quan:unit")))
        # a property expectation on a delivery's target adds its conditions to the delivery
        host = next((d for d in exps if d.kind == Kind.DELIVER and d.name and d.name == target), None)
        if host is not None and (kind in (None, "deliver")):
            host.targets += targets
            host.contexts += [_context_from_3gpp(c) for c in x.get("icm:context", []) or []]
            continue
        exps.append(Expectation(kind=Kind(kind or "keep"), targets=targets, action=action,
                                object=ObjectRef(type="slice", mentions=[target] if target else []),
                                contexts=[_context_from_3gpp(c) for c in x.get("icm:context", []) or []]))
    rec = IntentRecord(name=body.get("name"), text=body.get("description") or body.get("name"), channel="tmf921", expectations=exps)
    if body.get("id"):
        rec.links["external_id"] = body["id"]
    return rec


def report_tmf921(rec: IntentRecord, base: str = "") -> Dict[str, Any]:
    r = report_3gpp(rec)
    status = r["intentFulfilmentReport"]["intentFulfilmentInfo"]["fulfilmentStatus"]
    return {"id": f"{rec.id}-report-{len(rec.reports)}", "@type": "IntentReport",
            "href": f"{base}/tmf-api/intentManagement/v5/intent/{rec.id}/intentReport/{rec.id}-report-{len(rec.reports)}",
            "creationDate": r["lastUpdatedTime"], "name": f"{rec.name or rec.id} report",
            "intent": {"id": rec.id, "href": f"{base}/tmf-api/intentManagement/v5/intent/{rec.id}"},
            "expression": {"@type": "JsonLdExpression",
                           "expressionValue": {"@context": TIO_CONTEXT, "@type": "icm:IntentReport",
                                               "icm:about": f"cer:{rec.id}", "icm:reportNumber": len(rec.reports),
                                               "icm:intentHandlingState": f"icm:State{status.title().replace('_', '')}",
                                               "cer:fulfilment": r["intentFulfilmentReport"],
                                               **({"cer:feasibility": r["intentFeasibilityCheckReport"]} if "intentFeasibilityCheckReport" in r else {}),
                                               **({"cer:conflicts": r["intentConflictReports"]} if r["intentConflictReports"] else {})}}}


# ── the v1 intent API (14 capability types) ───────────────────────────────────

FEATURE_TYPES = ("sync", "security", "tsn", "beamforming", "multiband", "oran_xhaul", "interference", "telemetry", "resilience")


def from_legacy(intent: Any) -> Optional[Expectation]:
    """A v1 Intent of a device-feature type -> a change expectation the v1 pipeline realizes."""
    itype = getattr(intent.intent_type, "value", intent.intent_type)
    if itype not in FEATURE_TYPES and itype not in ("energy", "modulation", "capacity", "qos"):
        return None
    target = intent.target
    ident = getattr(target, "identifier", "all")
    obj = ObjectRef(type="radio" if getattr(target, "target_type", "") in ("node", "sector") else "network",
                    mentions=[] if ident == "all" else [ident])
    return Expectation(kind=Kind.CHANGE, verb="configure", object=obj, text=intent.raw_input,
                       action={"op": "feature", "legacy_type": itype, "parameters": intent.parameters, "legacy": True})
