"""
Matching a reading to the network, and filling what the operator left out
=========================================================================
Words become network objects (sites, radios, hops, slices, services, other
intents); values the operator did not give come from a service profile or the
operator's policy; relative requests ("double it", "+100 Mbps") become absolute
values from what the slice has now. Anything that cannot be settled this way
becomes a question (cer_intent/imf/clarify.py asks it).

Every filled value is recorded in the expectation's provenance list with the
reason, so the studio and the report show why a value is there.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cer_intent.imf import lexicon as L
from cer_intent.imf.model import (Choice, Context, Endpoint, Expectation, IntentRecord, Kind, Question,
                                  Source, Strictness)
from cer_intent.imf.network import NetworkModel, norm

ROOT = Path(__file__).resolve().parents[2]
PROFILE_OPS = {"latency": ("le", "ms"), "jitter": ("le", "ms"), "loss": ("le", "%"), "availability": ("ge", "%"),
               "bandwidth": ("ge", "Mbps")}


@dataclass
class Policy:
    """Operator defaults. data/imf_policy.json (or CER_IMF_POLICY) overrides any of them."""
    vlan_pool: Tuple[int, int] = (300, 3999)
    report_every_s: int = 900
    keep_check_every_s: int = 30
    bandwidth_choices: Tuple[int, ...] = (50, 100, 200, 500)
    default_profile: Optional[str] = None
    require_approval_above_mbps: Optional[float] = None
    approval_roles: Tuple[str, ...] = ("approver", "admin")
    act_roles: Tuple[str, ...] = ("operator", "approver", "admin")
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=lambda: dict(L.PROFILES))
    auto: Any = None                       # AutoPolicy (cer_intent/imf/autoapprove.py)

    def __post_init__(self):
        if self.auto is None:
            from cer_intent.imf.autoapprove import AutoPolicy
            self.auto = AutoPolicy.from_dict(None)

    @classmethod
    def load(cls) -> "Policy":
        from cer_intent.imf.autoapprove import AutoPolicy
        p = Policy()
        path = os.getenv("CER_IMF_POLICY") or str(ROOT / "data" / "imf_policy.json")
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            return p
        for k, v in data.items():
            if k == "profiles" and isinstance(v, dict):
                p.profiles.update(v)
            elif k == "auto_approve" and isinstance(v, dict):
                p.auto = AutoPolicy.from_dict(v)
            elif hasattr(p, k) and not k.startswith("_"):
                setattr(p, k, tuple(v) if isinstance(getattr(p, k), tuple) else v)
        return p


def note(e: Expectation, fld: str, value: Any, source: Source, why: str) -> None:
    e.action.setdefault("provenance", []).append({"field": fld, "value": value, "source": source.value, "why": why})


class Matcher:
    def __init__(self, net: NetworkModel, policy: Optional[Policy] = None, records: Optional[List[Any]] = None,
                 owner: Optional[str] = None):
        self.net = net
        self.policy = policy or Policy.load()
        self.net.vlan_pool = tuple(self.policy.vlan_pool)
        self.records = records
        self.owner = owner

    # ── entry point ──────────────────────────────────────────────────────────
    def match(self, rec: IntentRecord) -> List[Question]:
        questions: List[Question] = []
        taken_ids: List[str] = []
        for e in rec.expectations:
            if e.kind == Kind.ASK and e.action.get("type") == "unknown":
                continue
            questions += self._object(e)
            if e.kind == Kind.DELIVER:
                questions += self._deliver(e, taken_ids)
            elif e.kind == Kind.CHANGE and e.action.get("legacy"):
                pass                                  # a device feature: the v1 pipeline reads its own parameters
            elif e.kind == Kind.CHANGE:
                questions += self._change(e)
            elif e.kind == Kind.LIFECYCLE:
                done = {"suspend": "suspended", "resume": "resumed", "delete": "removed"}.get(e.action.get("op"), "changed")
                questions += self._needs_ids(e, f"Which slice should be {done}?")
            elif e.kind == Kind.KEEP:
                questions += self._keep(e)
            elif e.kind == Kind.OPTIMISE:
                self._optimise(e)
            elif e.kind == Kind.OBSERVE:
                self._observe(e)
            self._profile(e)
        by_id = {e.id: e for e in rec.expectations}
        for e in rec.expectations:            # "... and never let it fall below 150 Mbps": "it" is the delivery
            ref = by_id.get(e.action.get("of") or "")
            if ref is not None and ref.name and not e.object.ids:
                e.object.ids = [ref.name]
                note(e, "object", ref.name, Source.RESOLVED, "“it”: the slice this request delivers")
        return questions

    # ── objects ──────────────────────────────────────────────────────────────
    def _object(self, e: Expectation) -> List[Question]:
        qs: List[Question] = []
        obj = e.object
        if obj.endpoints:
            for i, ep in enumerate(obj.endpoints):
                if ep.node:
                    continue
                res = self.net.resolve(ep.mention or "", ("site", "radio"))
                if res.ok:
                    ep.node = res.id
                    if res.status != "exact":
                        ep.source = Source.RESOLVED
                        note(e, f"endpoint[{i}]", res.id, Source.RESOLVED, f"“{ep.mention}” matched {res.id} ({res.status})")
                else:
                    choices = [Choice(label=c[0], value=c[0]) for c in res.candidates] or \
                              [Choice(label=s, value=s) for s in self.net.sites()]
                    qs.append(Question(expectation=e.id, field=f"endpoint[{i}]", reason="ambiguous" if res.candidates else "unknown",
                                       text=f"Which site is “{ep.mention}”?", choices=choices))
            return qs
        types = {"slice": ("slice", "service", "intent"), "service": ("slice", "service", "intent"),
                 "intent": ("intent", "slice"), "radio": ("radio",), "hop": ("hop",), "site": ("site", "radio"),
                 "node": ("site", "radio"), "link": ("hop",)}.get(obj.type, ("slice", "service", "site", "radio", "intent"))
        ids: List[str] = []
        # descriptions answered from the network: "the slice on VLAN 100", "the busiest hop", "slices over radio-1"
        if e.kind != Kind.DELIVER:
            from cer_intent.imf import referents
            found = referents.find(e.text or "", self.net, self.records, self.owner)
            if e.kind == Kind.GUARD:
                # a rule binds what is named, now and later: "slices over radio-1" means radio-1
                found = [r for r in found if r.type not in ("slice", "intent")]
            if found:
                want = {"hop": "hop", "radio": "radio", "slice": "slice", "intent": "intent"}
                for r in found:
                    ids += r.ids
                    note(e, "object", r.ids, Source.RESOLVED, r.why)
                obj.type = want.get(found[0].type, obj.type) if obj.type in ("network", "slice", "service", "hop", "radio", "site") else obj.type
                obj.ids = list(dict.fromkeys(ids))
                obj.selector["described"] = [r.why for r in found]
                if not obj.ids and any(r.group for r in found):
                    e.action["nothing"] = "; ".join(r.why for r in found)
                return qs
        for mention in obj.mentions:
            low = mention.lower()
            if obj.type == "radio" and re.search(r"both|the\s+radios|all|each", low):
                ids += [n.id for n in self.net.nodes.values() if n.radio]
                continue
            if obj.type in ("hop", "link") or re.search(r"\b(?:hop|link)s?\b", low):
                hops = self.net.radio_hops()
                if len(hops) == 1:
                    ids.append(hops[0].name)
                    note(e, "object", hops[0].name, Source.RESOLVED, "the network's only radio hop")
                elif hops:
                    qs.append(Question(expectation=e.id, field="object", reason="ambiguous", text="Which radio hop?",
                                       choices=[Choice(label=h.name.replace("|", " – "), value=h.name) for h in hops]))
                continue
            if obj.type == "network":
                continue
            res = self.net.resolve(mention, tuple(t for t in types if t != "intent") or types)
            if not res.ok and "intent" in types and res.status == "unknown":
                res = self.net.resolve(mention, ("intent",))
            if res.status == "group":
                ids += [c[0] for c in res.candidates]
                note(e, "object", [c[0] for c in res.candidates], Source.RESOLVED, f"“{mention}”: every one the network reports")
                continue
            if res.ok:
                ids.append(res.id)
                if res.type == "site" and obj.type in ("slice", "service"):
                    obj.type = "site"
                if res.status != "exact":
                    note(e, "object", res.id, Source.RESOLVED, f"“{mention}” matched {res.id} ({res.status})")
            elif e.kind not in (Kind.ASK, Kind.EXPLORE):
                choices = [Choice(label=c[0], value=c[0]) for c in res.candidates] or \
                          [Choice(label=x, value=x) for x in self.net.suggest(types)]
                qs.append(Question(expectation=e.id, field="object", reason="ambiguous" if res.candidates else "unknown",
                                   text=f"Which {obj.type} is “{mention}”?", choices=choices))
        sel = obj.selector
        if sel.get("all") and obj.type in ("slice", "service", "network"):
            ids = list(self.net.slices)
        if sel.get("except"):
            drop = set()
            for x in sel["except"]:
                r = self.net.resolve(x, ("slice", "service", "intent"))
                drop.add(r.id if r.ok else x)
            ids = [i for i in ids if i not in drop]
            note(e, "object", ids, Source.RESOLVED, f"all slices except {', '.join(sorted(drop))}")
        if sel.get("name_contains"):
            ids = [i for i in self.net.slices if sel["name_contains"].lower() in i.lower()]
        obj.ids = list(dict.fromkeys(ids))
        # two sites named in a delivery are its endpoints
        if e.kind == Kind.DELIVER and not obj.endpoints:
            sites = [i for i in obj.ids if i in self.net.nodes]
            if len(sites) >= 2:
                obj.endpoints = [Endpoint(node=sites[0], mention=sites[0]), Endpoint(node=sites[1], mention=sites[1])]
                obj.ids, obj.type = [], "slice"
            elif len(sites) == 1:
                obj.endpoints = [Endpoint(node=sites[0], mention=sites[0])]
                obj.ids, obj.type = [], "slice"
        return qs

    def _needs_ids(self, e: Expectation, text: str) -> List[Question]:
        if e.object.ids:
            return []
        if e.object.selector.get("all"):
            e.action["nothing"] = f"no slice matches: {e.object.label()}"
            return []
        slices = list(self.net.slices)
        if not slices:
            return [Question(expectation=e.id, field="object", reason="missing", text="There are no slices to act on.", free=False)]
        return [Question(expectation=e.id, field="object", reason="missing", text=text,
                         choices=[Choice(label=s, value=s) for s in slices[:8]])]

    # ── deliver ──────────────────────────────────────────────────────────────
    def _deliver(self, e: Expectation, taken: List[str]) -> List[Question]:
        qs: List[Question] = []
        eps = e.object.endpoints
        sites = self.net.sites()
        if len(eps) == 1 and eps[0].node:
            others = [s for s in sites if s != eps[0].node]
            if len(others) == 1:
                eps.append(Endpoint(node=others[0], mention=others[0], source=Source.RESOLVED))
                note(e, "endpoint[1]", others[0], Source.RESOLVED, "the only other site")
            else:
                qs.append(Question(expectation=e.id, field="endpoint[1]", reason="missing",
                                   text=f"Between {eps[0].node} and which site?",
                                   choices=[Choice(label=s, value=s) for s in others]))
        elif not eps:
            if len(sites) == 2:
                e.object.endpoints = [Endpoint(node=sites[0], mention=sites[0], source=Source.RESOLVED),
                                      Endpoint(node=sites[1], mention=sites[1], source=Source.RESOLVED)]
                note(e, "endpoints", sites, Source.RESOLVED, "the network has two sites")
                eps = e.object.endpoints
            else:
                pairs = [(a, b) for i, a in enumerate(sites) for b in sites[i + 1:]]
                qs.append(Question(expectation=e.id, field="endpoints", reason="missing", text="Between which two sites?",
                                   choices=[Choice(label=f"{a} ↔ {b}", value=[a, b]) for a, b in pairs[:6]]))
        if len(eps) == 2 and eps[0].node and eps[0].node == eps[1].node:
            qs.append(Question(expectation=e.id, field="endpoint[1]", reason="ambiguous",
                               text=f"Both ends are {eps[0].node}. Which site is the other end?",
                               choices=[Choice(label=s, value=s) for s in sites if s != eps[0].node]))
        # ports
        for i, ep in enumerate(eps):
            if ep.node and not ep.port:
                p = self.net.port(ep.node)
                if p:
                    ep.port = p
                    note(e, f"endpoint[{i}].port", p, Source.POLICY, "the site's access port")
        # technology
        tech = e.target("technology")
        has_ip = any(ep.ip for ep in eps)
        if tech is None:
            value = "L3VPN" if has_ip else "L2VPN"
            e.set_target("technology", "eq", value, None, Source.POLICY,
                         note="addresses given: routed" if has_ip else "no addresses: Ethernet")
            note(e, "technology", value, Source.POLICY, "addresses given: routed (L3VPN)" if has_ip else "no addresses given: Ethernet (L2VPN)")
        elif tech.value == "L3VPN" and not has_ip and len(eps) == 2:
            qs.append(Question(expectation=e.id, field="addresses", reason="missing",
                               text="A routed slice needs an address at each end (for example 192.0.2.1/30 and 198.51.100.1/30).",
                               choices=[Choice(label="Use Ethernet (L2VPN) instead", value="L2VPN")]))
        # VLAN
        nodes = [ep.node for ep in eps if ep.node]
        vlan = e.value("vlan") or next((ep.vlan for ep in eps if ep.vlan), None)
        is_l2 = (e.value("technology") or "L2VPN") == "L2VPN"
        if vlan is not None:
            owner = self.net.vlan_owner(int(vlan), nodes)
            if owner and owner != e.name:
                free = self.net.free_vlan(nodes)
                qs.append(Question(expectation=e.id, field="vlan", reason="conflict", default=free,
                                   text=f"VLAN {vlan} already carries {owner} at these sites.",
                                   choices=[Choice(label=f"Use VLAN {free}", value=free)] if free else []))
        elif is_l2 and nodes:
            free = self.net.free_vlan(nodes)
            if free is not None:
                vlan = free
                e.set_target("vlan", "eq", free, None, Source.POLICY, note="next free VLAN in the pool")
                note(e, "vlan", free, Source.POLICY, f"lowest free VLAN in the pool {self.policy.vlan_pool[0]}–{self.policy.vlan_pool[1]}")
        for ep in eps:
            if vlan is not None and ep.vlan is None:
                ep.vlan = int(vlan)
        # bandwidth
        if e.target("bandwidth") is None:
            prof = self.policy.profiles.get(e.profile or "", {})
            if prof.get("bandwidth"):
                e.set_target("bandwidth", "ge", float(prof["bandwidth"]), "Mbps", Source.PROFILE)
            else:
                head = self._headroom(nodes)
                hint = f" Up to {head:g} Mbps fits in design rain." if head is not None else ""
                qs.append(Question(expectation=e.id, field="bandwidth", reason="missing",
                                   text=f"How much bandwidth should it carry?{hint}",
                                   choices=[Choice(label=f"{b} Mbps", value=b) for b in self.policy.bandwidth_choices
                                            if head is None or b <= head]))
        # the slice id, once both ends are known
        if not e.name and len(nodes) == 2:
            base = "slice-" + "-".join(norm(n) for n in nodes) + (f"-{vlan}" if vlan else "-l3" if not is_l2 else "")
            name, k = base, 2
            while name in self.net.slices or name in taken or name in self.net.reserved:
                name, k = f"{base}-{k}", k + 1
            e.name = name
            note(e, "name", name, Source.POLICY, "sites and VLAN")
        if e.name:
            taken.append(e.name)
        return qs

    def _headroom(self, nodes: List[str]) -> Optional[float]:
        if len(nodes) < 2:
            return None
        hops = self.net.hops(self.net.path(nodes[0], nodes[1]))
        if not hops:
            return None
        return max(0.0, min(h.capacity(h.design_rain_mmh) - self.net.load(h) for h in hops))

    # ── change ───────────────────────────────────────────────────────────────
    def _change(self, e: Expectation) -> List[Question]:
        qs = self._needs_ids(e, "Which slice should change?")
        if qs:
            return qs
        op, metric = e.action.get("op"), e.action.get("metric")
        if op == "improve":
            sid = e.object.ids[0]
            s = self.net.slices.get(sid)
            cur_bw = s.bandwidth_mbps if s else None
            cur_lat = s.max_latency_ms if s else None
            choices = []
            if cur_bw:
                choices.append(Choice(label=f"More bandwidth: {cur_bw:g} → {cur_bw * 1.5:g} Mbps", value={"metric": "bandwidth", "value": cur_bw * 1.5}))
                choices.append(Choice(label=f"Double it: {cur_bw * 2:g} Mbps", value={"metric": "bandwidth", "value": cur_bw * 2}))
            choices.append(Choice(label=f"Lower latency: ≤ {max(1.0, (cur_lat or 10) / 2):g} ms",
                                  value={"metric": "latency", "value": max(1.0, (cur_lat or 10) / 2)}))
            choices.append(Choice(label="Hold a higher modulation in rain (MCS6)", value={"metric": "modulation_floor", "value": "MCS6"}))
            return [Question(expectation=e.id, field="improve", reason="vague",
                             text=f"“{e.vague}” can mean several things for {sid}. Which one?", choices=choices)]
        if op in ("scale", "add", "set") and metric in ("bandwidth", "latency", "jitter", "loss"):
            for sid in e.object.ids:
                s = self.net.slices.get(sid)
                field_name = {"bandwidth": "bandwidth_mbps", "latency": "max_latency_ms", "loss": "loss_pct"}.get(metric)
                cur = getattr(s, field_name, None) if s and field_name else None
                value = e.action.get("value")
                if op == "set":
                    new = float(value)
                elif cur is None:
                    qs.append(Question(expectation=e.id, field=metric, reason="missing",
                                       text=f"{sid} has no {metric} on record. What value should it have?"))
                    continue
                else:
                    new = cur * float(value) if op == "scale" else cur + float(value)
                    if metric != "bandwidth" and op == "add" and e.action.get("unit") == "%":
                        new = cur * (1 + float(value) / 100.0)
                ge = metric == "bandwidth"
                e.set_target(metric, "ge" if ge else "le", round(new, 3), {"bandwidth": "Mbps", "loss": "%"}.get(metric, "ms"),
                             Source.RESOLVED if op != "set" else Source.STATED,
                             note=f"{cur:g} → {new:g}" if cur is not None else None)
                if cur is not None:
                    e.action.setdefault("before", {})[sid] = {metric: cur}
                    note(e, metric, round(new, 3), Source.RESOLVED, f"{sid} has {cur:g} now; {op} {value}")
                break
        if metric == "vlan" and e.action.get("value") is not None:
            sid = e.object.ids[0]
            s = self.net.slices.get(sid)
            owner = self.net.vlan_owner(int(e.action["value"]), s.nodes() if s else [])
            if owner and owner != sid:
                free = self.net.free_vlan(s.nodes() if s else [])
                qs.append(Question(expectation=e.id, field="vlan", reason="conflict", default=free,
                                   text=f"VLAN {e.action['value']} already carries {owner}.",
                                   choices=[Choice(label=f"Use VLAN {free}", value=free)] if free else []))
        return qs

    # ── standing objectives ──────────────────────────────────────────────────
    def _keep(self, e: Expectation) -> List[Question]:
        if e.targets:
            return []
        sid = e.object.ids[0] if e.object.ids else None
        s = self.net.slices.get(sid or "")
        if s:
            if s.bandwidth_mbps:
                e.set_target("bandwidth", "ge", s.bandwidth_mbps, "Mbps", Source.RESOLVED, note="as delivered")
            if s.max_latency_ms:
                e.set_target("latency", "le", s.max_latency_ms, "ms", Source.RESOLVED, note="as delivered")
            note(e, "targets", [t.text() for t in e.targets], Source.RESOLVED, f"{sid}'s objectives as delivered")
            return []
        return [Question(expectation=e.id, field="targets", reason="vague" if e.vague else "missing",
                         text="What should hold?",
                         choices=[Choice(label="Availability ≥ 99.99 %", value={"metric": "availability", "op": "ge", "value": 99.99}),
                                  Choice(label="Latency ≤ 10 ms", value={"metric": "latency", "op": "le", "value": 10}),
                                  Choice(label="Lowest modulation ≥ MCS4", value={"metric": "modulation_floor", "op": "ge", "value": "MCS4"})])]

    def _optimise(self, e: Expectation) -> None:
        if not e.object.ids and e.object.type in ("hop", "network"):
            e.object.ids = [h.name for h in self.net.radio_hops()]
            e.object.type = "hop"
            note(e, "object", e.object.ids, Source.RESOLVED, "every radio hop")

    def _observe(self, e: Expectation) -> None:
        if e.action.get("op") == "report" and not e.context("schedule"):
            e.contexts.append(Context(kind="schedule", params={"every": f"{self.policy.report_every_s // 60} min",
                                                              "seconds": self.policy.report_every_s}, source=Source.POLICY))
            note(e, "cadence", self.policy.report_every_s, Source.POLICY, "the operator's report cadence")

    def _profile(self, e: Expectation) -> None:
        name = e.profile or (self.policy.default_profile if e.kind == Kind.DELIVER else None)
        prof = self.policy.profiles.get(name or "")
        if not prof or e.kind not in (Kind.DELIVER, Kind.CHANGE, Kind.KEEP):
            return
        for metric, (op, unit) in PROFILE_OPS.items():
            if metric in prof and e.target(metric) is None:
                e.set_target(metric, op, float(prof[metric]), unit, Source.PROFILE, note=f"{prof.get('label', name)} profile")
        if e.priority is None and prof.get("priority") is not None:
            e.priority = int(prof["priority"])
        if prof.get("strictness") == "best_effort":
            e.strictness = Strictness.BEST_EFFORT
        if not e.profile:
            e.profile = name
