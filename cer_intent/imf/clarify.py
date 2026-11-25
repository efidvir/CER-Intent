"""
Questions and answers
=====================
The matcher raises a question for anything it cannot settle from the words,
the network, a profile or the operator's policy: an unknown or ambiguous name,
a missing value, a vague word ("faster"), a VLAN that is taken, a value only the
language model read. Each question offers choices and accepts a typed answer.

Answers are kept on the record ("<expectation id>:<field>" -> value), so the
record can be matched again from the words as read plus the answers given;
nothing is lost when a later answer changes an earlier choice.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from cer_intent.imf.model import Endpoint, Expectation, IntentRecord, Question, Source
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.quantities import find_quantities, mcs_name

PRE_FIELDS = ("endpoint", "endpoints", "object", "addresses", "vlan")     # applied before matching


def key(q: Question) -> str:
    return f"{q.expectation}:{q.field}"


def parse(field: str, raw: Any, net: NetworkModel) -> Tuple[bool, Any, Optional[str]]:
    """A typed or chosen answer -> (ok, value, problem)."""
    if not isinstance(raw, str):
        return True, raw, None
    text = raw.strip()
    if field.startswith("endpoint["):
        r = net.resolve(text, ("site", "radio"))
        return (True, r.id, None) if r.ok else (False, None, f"“{text}” is not a site in the network")
    if field == "endpoints":
        parts = [p for p in re.split(r"\s*(?:,|↔|<->|\band\b|\bto\b)\s*", text) if p]
        ids = [net.resolve(p, ("site", "radio")) for p in parts[:2]]
        if len(ids) == 2 and all(r.ok for r in ids):
            return True, [ids[0].id, ids[1].id], None
        return False, None, "name two sites"
    if field == "object":
        r = net.resolve(text)
        return (True, r.id, None) if r.ok else (False, None, f"“{text}” is not in the network")
    if field in ("bandwidth", "latency", "jitter", "loss", "availability"):
        qs = find_quantities(text)
        q = next((x for x in qs if x.dim in ("rate", "time", "percent", "nines", "number")), None)
        return (True, float(q.value), None) if q else (False, None, "give a number")
    if field == "vlan":
        m = re.search(r"\d{1,4}", text)
        return (True, int(m.group(0)), None) if m else (False, None, "give a VLAN number")
    if field == "addresses":
        ips = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b", text)
        if len(ips) >= 2:
            return True, ips[:2], None
        if re.search(r"l2|ethernet|bridged", text, re.I):
            return True, "L2VPN", None
        return False, None, "give two addresses, or choose Ethernet"
    if field in ("modulation_floor",):
        q = next((x for x in find_quantities(text) if x.dim == "mcs"), None)
        return (True, mcs_name(q.value), None) if q else (False, None, "give an MCS, e.g. MCS4")
    return True, text, None


def apply(rec: IntentRecord, exps: List[Expectation], net: NetworkModel, phase: str) -> None:
    """Apply the record's answers to freshly read expectations. phase: 'pre' (names) or 'post' (values)."""
    by_id = {e.id: e for e in exps}
    for k, value in rec.answers.items():
        eid, _, fld = k.partition(":")
        e = by_id.get(eid)
        if e is None or value is None:
            continue
        pre = fld.startswith(PRE_FIELDS)
        if (phase == "pre") != pre:
            continue
        _apply_one(e, fld, value, net)


def _apply_one(e: Expectation, fld: str, value: Any, net: NetworkModel) -> None:
    prov = e.action.setdefault("provenance", [])
    prov.append({"field": fld, "value": value, "source": Source.ANSWER.value, "why": "the operator's answer"})
    m = re.match(r"endpoint\[(\d)\]", fld)
    if m:
        i = int(m.group(1))
        while len(e.object.endpoints) <= i:
            e.object.endpoints.append(Endpoint())
        ep = e.object.endpoints[i]
        ep.node, ep.source = str(value), Source.ANSWER
        ep.mention = ep.mention or str(value)
        if e.name and str(value) not in e.name:
            e.name = None
        return
    if fld == "endpoints":
        a, b = list(value)[:2]
        e.object.endpoints = [Endpoint(node=a, mention=a, source=Source.ANSWER), Endpoint(node=b, mention=b, source=Source.ANSWER)]
        return
    if fld == "object":
        ids = value if isinstance(value, list) else [value]
        e.object.ids = [str(x) for x in ids]
        e.object.mentions = e.object.mentions or [str(x) for x in ids]
        return
    if fld == "addresses":
        if value == "L2VPN":
            e.set_target("technology", "eq", "L2VPN", None, Source.ANSWER)
        else:
            for ep, ip in zip(e.object.endpoints, list(value)):
                ep.ip = ip
        return
    if fld == "vlan":
        e.set_target("vlan", "eq", int(value), None, Source.ANSWER)
        for ep in e.object.endpoints:
            ep.vlan = int(value)
        if e.action.get("metric") == "vlan":
            e.action["value"] = int(value)
        e.name = None
        return
    if fld == "improve" and isinstance(value, dict):
        e.action = {"op": "set", "metric": value["metric"], "value": value["value"], "provenance": prov}
        unit = {"bandwidth": "Mbps", "latency": "ms", "modulation_floor": "MCS"}.get(value["metric"])
        op = "le" if value["metric"] == "latency" else "ge"
        e.set_target(value["metric"], op, value["value"], unit, Source.ANSWER)
        e.vague = None
        return
    if fld == "targets" and isinstance(value, dict):
        unit = {"availability": "%", "latency": "ms", "modulation_floor": "MCS", "bandwidth": "Mbps"}.get(value["metric"])
        e.set_target(value["metric"], value.get("op", "ge"), value["value"], unit, Source.ANSWER)
        return
    if fld.startswith("confirm:"):
        metric = fld.split(":", 1)[1]
        t = e.target(metric)
        if t is not None:
            if str(value).lower() in ("no", "false", "drop", "0"):
                e.targets.remove(t)
            else:
                t.source = Source.ANSWER
        return
    if fld in ("bandwidth", "latency", "jitter", "loss", "availability", "modulation_floor"):
        unit = {"bandwidth": "Mbps", "latency": "ms", "jitter": "ms", "loss": "%", "availability": "%", "modulation_floor": "MCS"}[fld]
        op = "ge" if fld in ("bandwidth", "availability", "modulation_floor") else "le"
        e.set_target(fld, op, value, unit, Source.ANSWER)
        return


def open_questions(rec: IntentRecord, questions: List[Question]) -> List[Question]:
    """Questions whose answer is not on the record yet, one per field."""
    seen, out = set(), []
    for q in questions:
        k = key(q)
        if k in rec.answers or k in seen:
            continue
        seen.add(k)
        out.append(q)
    return out


def confirm_model_values(exps: List[Expectation]) -> List[Question]:
    """A value only the language model read is confirmed before it changes the network."""
    from cer_intent.imf.model import ACTING_KINDS, Choice
    out = []
    for e in exps:
        if e.kind not in ACTING_KINDS:
            continue
        for t in e.targets:
            if t.source == Source.MODEL:
                out.append(Question(expectation=e.id, field=f"confirm:{t.metric}", reason="confirm",
                                    text=f"Only the language model read “{t.text()}”. Keep it?",
                                    choices=[Choice(label="Keep", value="yes"), Choice(label="Drop", value="no")]))
    return out
