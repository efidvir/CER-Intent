"""
The network the intent manager matches words against
=====================================================
Built from what CER-Intent already reads (cer_intent/flow/routes.snapshot():
the TeraFlowSDN topology and services, the slice controller's slices and the
requests they were made from), the twin's site plan, the intent store and an
optional alias file. Nothing here is specific to a lab: names, aliases, radio
hops, loads and free VLANs all come from those sources.

It answers:
  names()           what the reader should recognise, by type
  resolve(mention)  a mention -> one network object, or candidates to ask about
  path(a, b)        nodes between two sites; hops(path) the radio hops on it
  load(hop)         what the slices on a hop ask for in total
  free_vlan(...)    the lowest free VLAN in the operator's pool
"""
from __future__ import annotations

import difflib
import json
import os
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cer_intent.imf.radio import Hop

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = {"design_rain_mmh": 60.0, "hop_distance_m": 250.0, "r001_mmh": 42.0, "freq_ghz": 60.48,
                "clear_sky_snr_db": 15.85, "links": {}}
RADIO_WORDS = ("wireless", "radio", "microwave", "mmwave", "mm-wave", "ceragon")


def norm(s: str) -> str:
    return re.sub(r"[\s_]+", "-", str(s or "").strip().lower()).strip("-")


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def tokens(s: str) -> List[str]:
    stop = {"the", "a", "an", "of", "slice", "service", "vpn", "in", "before", "demo", "to", "and", "for", "my", "our"}
    return [t for t in re.findall(r"[a-z0-9]+", str(s or "").lower()) if t not in stop]


@dataclass
class Node:
    id: str
    uuid: Optional[str] = None
    type: Optional[str] = None
    radio: bool = False
    model: Optional[str] = None
    status: Optional[str] = None
    endpoints: List[str] = field(default_factory=list)
    # what the device reports about itself (cer_intent/imf/discovery.py)
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    family: Optional[str] = None
    role: Optional[str] = None
    features: List[str] = field(default_factory=list)
    bands: List[Dict[str, Any]] = field(default_factory=list)
    max_mbps: Optional[float] = None
    live: Dict[str, Any] = field(default_factory=dict)       # mcs, snr_db, rsl_dbm, speed_mbps, freq_mhz, tx_power_control

    def band_words(self) -> List[str]:
        words = []
        for b in self.bands:
            if b.get("name"):
                words.append(str(b["name"]))
            lo, hi = b.get("min_ghz"), b.get("max_ghz")
            if lo and hi:
                words.append(f"{round((float(lo) + float(hi)) / 2 / 10) * 10:g} GHz")
        if self.live.get("freq_mhz"):
            f = float(self.live["freq_mhz"]) / 1000.0
            words += [f"{f:g} GHz", f"{round(f):g} GHz"]
        return list(dict.fromkeys(words))

    def access_port(self) -> Optional[str]:
        for e in self.endpoints:
            if not str(e).startswith(("rf-", "rf_", "radio")):
                return e
        return None


@dataclass
class Link:
    id: str
    a: str
    b: str
    radio: bool = False
    a_ep: Optional[str] = None
    b_ep: Optional[str] = None


@dataclass
class SliceInfo:
    id: str
    status: Optional[str] = None
    technology: Optional[str] = None
    path: List[str] = field(default_factory=list)
    endpoints: List[Dict[str, Any]] = field(default_factory=list)
    bandwidth_mbps: Optional[float] = None
    max_latency_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    availability_pct: Optional[float] = None
    acm_floor: Optional[str] = None
    hop_floor: Optional[str] = None
    description: Optional[str] = None
    intent: Optional[str] = None             # the intent record that made it, when known
    source: str = "slice controller"         # or "TeraFlowSDN": a service CER-Intent did not make
    technology_label: Optional[str] = None

    def vlans(self) -> List[int]:
        return sorted({int(e["vlan"]) for e in self.endpoints if e.get("vlan") not in (None, "")})

    def nodes(self) -> List[str]:
        return [e.get("node") for e in self.endpoints if e.get("node")]


@dataclass
class Resolution:
    mention: str
    status: str                       # exact, alias, fuzzy, ambiguous, unknown
    id: Optional[str] = None
    type: Optional[str] = None
    score: float = 0.0
    candidates: List[Tuple[str, str, float]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("exact", "alias", "fuzzy") and self.id is not None


class NetworkModel:
    def __init__(self, nodes: Iterable[Node] = (), links: Iterable[Link] = (), slices: Iterable[SliceInfo] = (),
                 services: Iterable[Dict[str, Any]] = (), intents: Iterable[Dict[str, Any]] = (),
                 plan: Optional[Dict[str, Any]] = None, aliases: Optional[Dict[str, str]] = None,
                 vlan_pool: Tuple[int, int] = (300, 3999), source: str = "snapshot"):
        self.nodes: Dict[str, Node] = {n.id: n for n in nodes}
        self.links: List[Link] = list(links)
        self.slices: Dict[str, SliceInfo] = {s.id: s for s in slices}
        self.services: List[Dict[str, Any]] = list(services)
        self.intents: List[Dict[str, Any]] = list(intents)
        self.plan = {**DEFAULT_PLAN, **(plan or {})}
        self.aliases = {norm(k): v for k, v in (aliases or {}).items()}
        self.vlan_pool = vlan_pool
        self.source = source
        self.reserved: Dict[str, Dict[str, Any]] = {}       # intents not applied yet: name -> {"vlans", "nodes", "intent"}
        self.suspended: Dict[str, SliceInfo] = {}           # slices a suspend put aside: named, but carrying no load
        by_uuid = {n.uuid: n.id for n in self.nodes.values() if n.uuid}
        for lk in self.links:          # links may name devices by uuid
            lk.a, lk.b = by_uuid.get(lk.a, lk.a), by_uuid.get(lk.b, lk.b)
            if not lk.radio and lk.a in self.nodes and lk.b in self.nodes:
                lk.radio = self.nodes[lk.a].radio and self.nodes[lk.b].radio

    # ── construction ─────────────────────────────────────────────────────────
    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any], intents: Iterable[Dict[str, Any]] = (),
                      plan: Optional[Dict[str, Any]] = None) -> "NetworkModel":
        topo = snap.get("topology") or {}
        nodes = [Node(id=n["id"], uuid=n.get("uuid"), type=n.get("type"), status=n.get("status"),
                      radio=bool(n.get("radio")) or any(w in str(n.get("type") or "").lower() for w in RADIO_WORDS),
                      model=n.get("model"), endpoints=[e for e in n.get("endpoints") or [] if e])
                 for n in topo.get("nodes", [])]
        links = [Link(id=l.get("id"), a=l.get("a"), b=l.get("b"), radio=bool(l.get("radio")),
                      a_ep=l.get("a_ep"), b_ep=l.get("b_ep")) for l in topo.get("links", [])]
        slices = [SliceInfo(**{k: s.get(k) for k in SliceInfo.__dataclass_fields__ if k in s}) for s in snap.get("slices", [])]
        for s, raw in zip(slices, snap.get("slices", [])):
            s.endpoints = raw.get("endpoints") or []
            s.path = raw.get("path") or []
        net = cls(nodes, links, slices, snap.get("services", []), intents, plan or load_plan(), load_aliases(), source="live")
        # services in TeraFlowSDN that the slice controller did not make still use the hops
        by_uuid = {n.uuid: n.id for n in net.nodes.values() if n.uuid}
        for svc in snap.get("services", []):
            name = svc.get("name")
            if not name or name in net.slices or "ACTIVE" not in str(svc.get("status") or ""):
                continue
            ends = [by_uuid.get(e, e) for e in svc.get("endpoints") or []]
            vlans, ips, ports = svc.get("vlans") or {}, svc.get("ips") or {}, svc.get("ports") or []
            eps = [{"node": e, "port": ports[i] if i < len(ports) else None, "vlan": vlans.get(e), "ip": ips.get(e)}
                   for i, e in enumerate(ends)]
            net.slices[name] = SliceInfo(id=name, status="active", technology=svc.get("type"), endpoints=eps,
                                         path=net.path(ends[0], ends[-1]) if len(ends) >= 2 else [],
                                         bandwidth_mbps=svc.get("capacity_mbps"), max_latency_ms=svc.get("latency_ms"),
                                         description=f"TeraFlowSDN service {name}", source="TeraFlowSDN")
        return net

    def enrich(self, details: Dict[str, Dict[str, Any]]) -> "NetworkModel":
        """Add what each device reports about itself (discovery.parse_device) to the model."""
        for name, d in details.items():
            n = self.nodes.get(name)
            if n is None:
                continue
            n.hostname = d.get("hostname") or n.hostname
            n.model = d.get("model") or n.model
            n.vendor = d.get("vendor") or n.vendor
            n.family = d.get("family") or n.family
            n.role = d.get("role") or n.role
            n.features = d.get("features") or n.features
            n.bands = d.get("bands") or n.bands
            n.max_mbps = d.get("max_mbps") or n.max_mbps
            n.live = d.get("live") or n.live
            if d.get("endpoints"):
                n.endpoints = [e for e in d["endpoints"] if e]
            if n.bands and not n.radio:
                n.radio = True
        for lk in self.links:
            if not lk.radio and lk.a in self.nodes and lk.b in self.nodes:
                lk.radio = self.nodes[lk.a].radio and self.nodes[lk.b].radio
        return self

    @classmethod
    def demo(cls, with_slice: bool = True) -> "NetworkModel":
        """The end-to-end flow's network (emulation/flow): two sites over one 60 GHz hop, one slice in service."""
        flow = ROOT / "emulation" / "flow"
        topo = json.loads((flow / "topology.json").read_text())
        nodes = []
        for d in topo["devices"]:
            radio = "DEVICEDRIVER_CERAGON" in (d.get("device_drivers") or []) or any(
                w in str(d.get("device_type", "")).lower() for w in RADIO_WORDS)
            nodes.append(Node(id=d["name"], uuid=d["device_id"]["device_uuid"]["uuid"], type=d.get("device_type"),
                              radio=radio, endpoints=["eth1"] + (["rf-sector-1"] if radio else ["int"]),
                              hostname=d["name"], model="MH-T261" if radio else None, family="MultiHaul TG" if radio else None,
                              role="transport_mmwave_vband" if radio else "datacenter",
                              bands=[{"name": "V-band", "min_ghz": 57.0, "max_ghz": 71.0}] if radio else [],
                              max_mbps=1000.0 if radio else None,
                              live={"freq_mhz": 60480.0} if radio else {}))
        links = []
        for lk in topo["links"]:
            a, b = lk["link_endpoint_ids"][:2]
            ea, eb = a["endpoint_uuid"]["uuid"], b["endpoint_uuid"]["uuid"]
            links.append(Link(id=lk["name"], a=a["device_id"]["device_uuid"]["uuid"], b=b["device_id"]["device_uuid"]["uuid"],
                              radio=ea.startswith("rf-") or eb.startswith("rf-"), a_ep=ea, b_ep=eb))
        slices = []
        if with_slice:
            slices.append(SliceInfo(id="backhaul-ran", status="active", technology="L2VPN",
                                    path=["region-a", "radio-1", "radio-2", "edge"],
                                    endpoints=[{"node": "region-a", "port": "eth1", "vlan": 100},
                                               {"node": "edge", "port": "eth1", "vlan": 100}],
                                    bandwidth_mbps=200.0, description="RAN backhaul, in service before the demo"))
        plan = json.loads((flow / "site_plan.json").read_text()) if (flow / "site_plan.json").exists() else {}
        return cls(nodes, links, slices, plan=plan, aliases=load_aliases(), source="demo")

    # ── what the reader should recognise ─────────────────────────────────────
    def names(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {"node": [], "radio": [], "slice": [], "service": [], "intent": []}
        for n in self.nodes.values():
            out["radio" if n.radio else "node"].append(n.id)
        out["slice"] = list(self.slices) + [x for x in self.suspended if x not in self.slices]
        known = set(self.slices) | set(self.suspended)
        out["service"] = [s.get("name") for s in self.services if s.get("name") and s.get("name") not in known]
        out["intent"] = [i.get("name") for i in self.intents if i.get("name")]
        for v in self.vocabulary():
            if v["phrase"].lower() != str(v["id"]).lower() and len(v["phrase"]) >= 3:
                out.setdefault({"site": "node"}.get(v["type"], v["type"]), []).append(v["phrase"])
        return {k: sorted(set(v), key=len, reverse=True) for k, v in out.items() if v}

    # ── words the network gives its parts ────────────────────────────────────
    def vocabulary(self) -> List[Dict[str, Any]]:
        """Phrases that mean a part of this network, each with the part and where the phrase comes from."""
        out: List[Dict[str, Any]] = []

        def add(phrase, ident, typ, why):
            if phrase and str(phrase).strip():
                out.append({"phrase": str(phrase).strip(), "id": ident, "type": typ, "why": why})
        radios = [n for n in self.nodes.values() if n.radio]
        for n in self.nodes.values():
            t = "radio" if n.radio else "site"
            if n.hostname and n.hostname.lower() != n.id.lower():
                add(n.hostname, n.id, t, "the device's host name")
            short = re.sub(r"^(?:[a-z]+-)+(?=[a-z]+-?\d+$)", "", n.id.lower())
            if short != n.id.lower() and len(short) >= 4:
                add(short, n.id, t, "the end of its name")
        for group, key, why in (("model", "model", "the radios' model"), ("family", "family", "the radios' product family")):
            vals = {getattr(n, key) for n in radios if getattr(n, key)}
            for v in vals:
                ids = [n.id for n in radios if getattr(n, key) == v]
                add(f"{v} radios" if len(ids) > 1 else v, ids if len(ids) > 1 else ids[0], "radio", why)
        for hop in self.radio_hops():
            a, b = self.nodes.get(hop.a), self.nodes.get(hop.b)
            add(f"{hop.a} {hop.b} hop", hop.name, "hop", "its two radios")
            add(f"{hop.a} to {hop.b}", hop.name, "hop", "its two radios")
            words = list(dict.fromkeys((a.band_words() if a else []) + (b.band_words() if b else [])))
            for w in words:
                same = [h for h in self.radio_hops() if w in ((self.nodes[h.a].band_words() if h.a in self.nodes else []))]
                if len(same) == 1:
                    for noun in ("hop", "link", "radio link"):
                        add(f"{w} {noun}", hop.name, "hop", f"the radios report {w}")
            ends = self._ends_through(hop)
            for site in ends:
                add(f"hop to {site}", hop.name, "hop", f"the radio hop on the way to {site}")
                add(f"{site} hop", hop.name, "hop", f"the radio hop on the way to {site}")
            if len(ends) == 2:
                add(f"{ends[0]} {ends[1]} link", hop.name, "hop", "the radio hop between the two sites")
        for s in self.slices.values():
            for v in s.vlans():
                add(f"vlan {v} slice", s.id, "slice", f"{s.id} uses VLAN {v}")
            if s.description and s.source == "slice controller":
                add(s.description.split(",")[0], s.id, "slice", "its description")
        for k, v in self.aliases.items():
            hit = next((e for e in self._entities() if e[0] == v), None)
            if hit:
                add(k, v, hit[1], "the operator's alias")
        return out

    def _ends_through(self, hop: Hop) -> List[str]:
        """The sites on either side of a radio hop (following links away from it)."""
        ends = []
        for start, other in ((hop.a, hop.b), (hop.b, hop.a)):
            seen, frontier = {other, start}, [start]
            found = None
            while frontier and found is None:
                nxt = []
                for x in frontier:
                    for nb in self.neighbours(x):
                        if nb in seen:
                            continue
                        seen.add(nb)
                        if nb in self.nodes and not self.nodes[nb].radio:
                            found = nb
                            break
                        nxt.append(nb)
                    if found:
                        break
                frontier = nxt
            if found:
                ends.append(found)
        return ends

    def live_mcs(self, hop: Hop) -> Optional[str]:
        """The lower of the two radios' current modulation, when the radios reported it."""
        from cer_intent.imf.radio import mcs_index
        vals = [self.nodes[x].live.get("mcs") for x in (hop.a, hop.b) if x in self.nodes and self.nodes[x].live.get("mcs")]
        return min(vals, key=lambda m: mcs_index(m) or 0) if vals else None

    def sites(self) -> List[str]:
        return [n.id for n in self.nodes.values() if not n.radio]

    # ── mention -> object ────────────────────────────────────────────────────
    def _entities(self, types: Optional[Iterable[str]] = None) -> List[Tuple[str, str, List[str]]]:
        want = set(types or ("site", "radio", "slice", "service", "intent", "hop"))
        out: List[Tuple[str, str, List[str]]] = []
        for n in self.nodes.values():
            t = "radio" if n.radio else "site"
            if t in want:
                out.append((n.id, t, [n.id] + ([n.hostname] if n.hostname else [])))
        if "slice" in want or "service" in want:
            for s in self.slices.values():
                out.append((s.id, "slice", [s.id] + ([s.description] if s.description else [])))
            for s in self.suspended.values():
                if s.id not in self.slices:
                    out.append((s.id, "slice", [s.id] + ([s.description] if s.description else [])))
            for svc in self.services:
                name = svc.get("name")
                if name and name not in self.slices:
                    out.append((name, "service", [name]))
        if "intent" in want:
            for i in self.intents:
                if i.get("name"):
                    out.append((i["name"], "intent", [i["name"]] + ([i.get("text")] if i.get("text") else [])))
        if "hop" in want:
            for h in self.radio_hops():
                out.append((h.name, "hop", [h.name, f"{h.a} {h.b}", f"{h.a} to {h.b}"]))
        return out

    def resolve(self, mention: str, types: Optional[Iterable[str]] = None) -> Resolution:
        hit = self._vocab_hit(mention, types)
        if hit is not None:
            return hit
        m = re.sub(r"^(?:the|a|an|our|my)\s+", "", str(mention or "").strip(), flags=re.I)
        m = re.sub(r"^(?:site|node|slice|service|radio\s+site)\s+(?=\S)", "", m, flags=re.I)
        m = re.sub(r"\s+(?:site|node)$", "", m, flags=re.I)
        if not m:
            return Resolution(mention=mention, status="unknown")
        key = norm(m)
        ents = self._entities(types)
        # 1. exact name (case, spaces and separators ignored)
        exact = [(i, t) for i, t, _ in ents if norm(i) == key or squash(i) == squash(m)]
        if len(exact) == 1:
            return Resolution(mention, "exact", exact[0][0], exact[0][1], 1.0)
        if len(exact) > 1:
            return Resolution(mention, "ambiguous", candidates=[(i, t, 1.0) for i, t in exact])
        # 2. the operator's alias file
        if key in self.aliases:
            target = self.aliases[key]
            hit = next(((i, t) for i, t, _ in ents if i == target), None)
            if hit:
                return Resolution(mention, "alias", hit[0], hit[1], 0.97)
        # 3. words: every word of the mention appears in the name or description
        mt = tokens(m)
        scored: List[Tuple[str, str, float]] = []
        for i, t, texts in ents:
            best = 0.0
            for txt in texts:
                tt = tokens(txt)
                if mt and tt and set(mt) <= set(tt):
                    best = max(best, 0.9 - 0.02 * (len(set(tt)) - len(set(mt))))
                r = difflib.SequenceMatcher(None, squash(m), squash(txt)).ratio()
                if len(squash(m)) >= 3:
                    best = max(best, r * 0.95)
            if best >= 0.72:
                scored.append((i, t, round(best, 3)))
        scored.sort(key=lambda x: -x[2])
        if not scored:
            return Resolution(mention, "unknown")
        if len(scored) > 1 and scored[0][2] - scored[1][2] < 0.06:
            return Resolution(mention, "ambiguous", candidates=scored[:4])
        top = scored[0]
        return Resolution(mention, "fuzzy", top[0], top[1], top[2], candidates=scored[:4])

    def _vocab_hit(self, mention: str, types: Optional[Iterable[str]] = None) -> Optional[Resolution]:
        key = squash(re.sub(r"^(?:the|a|an|our|my|both|all)\s+", "", str(mention or "").strip(), flags=re.I))
        if not key:
            return None
        want = set(types) if types else None
        hits = [v for v in self.vocabulary() if squash(v["phrase"]) == key and (want is None or v["type"] in want
                                                                                   or (v["type"] == "slice" and "service" in want))]
        ids = {json.dumps(v["id"]) for v in hits}
        if len(ids) == 1:
            v = hits[0]
            if isinstance(v["id"], list):          # a group: "the MH-T261 radios"
                return Resolution(mention, "group", candidates=[(i, v["type"], 0.95) for i in v["id"]])
            return Resolution(mention, "alias", v["id"], v["type"], 0.96, candidates=[(v["id"], v["type"], 0.96)])
        return None

    def suggest(self, types: Iterable[str], limit: int = 6) -> List[str]:
        return [i for i, _, _ in self._entities(types)][:limit]

    # ── graph ────────────────────────────────────────────────────────────────
    def neighbours(self, node: str) -> List[str]:
        out = []
        for lk in self.links:
            if lk.a == node:
                out.append(lk.b)
            elif lk.b == node:
                out.append(lk.a)
        return out

    def path(self, a: str, b: str) -> List[str]:
        if a not in self.nodes or b not in self.nodes:
            return []
        prev: Dict[str, Optional[str]] = {a: None}
        q = deque([a])
        while q:
            cur = q.popleft()
            if cur == b:
                break
            for nb in self.neighbours(cur):
                if nb not in prev:
                    prev[nb] = cur
                    q.append(nb)
        if b not in prev:
            return []
        out, cur = [], b
        while cur is not None:
            out.append(cur)
            cur = prev[cur]
        return out[::-1]

    def hop(self, a: str, b: str) -> Hop:
        key, rkey = f"{a}|{b}", f"{b}|{a}"
        link_plan = (self.plan.get("links") or {}).get(key) or (self.plan.get("links") or {}).get(rkey) or {}
        return Hop(a=a, b=b, distance_m=float(link_plan.get("distance_m", self.plan.get("hop_distance_m", 250.0))),
                   freq_ghz=float(link_plan.get("freq_ghz", self.plan.get("freq_ghz", 60.48))),
                   vertical=str(link_plan.get("polarisation", self.plan.get("polarisation", "H"))).upper().startswith("V"),
                   clear_sky_snr_db=float(link_plan.get("clear_sky_snr_db", self.plan.get("clear_sky_snr_db", 15.85))),
                   reference_m=float(self.plan.get("reference_m", self.plan.get("hop_distance_m", 250.0))),
                   r001_mmh=float(link_plan.get("r001_mmh", self.plan.get("r001_mmh", 42.0))),
                   design_rain_mmh=float(self.plan.get("design_rain_mmh", 60.0)),
                   acm_margin_db=float(link_plan.get("acm_margin_db", self.plan.get("acm_margin_db", 1.0))))

    def radio_hops(self) -> List[Hop]:
        return [self.hop(lk.a, lk.b) for lk in self.links if lk.radio]

    def hops(self, path: List[str]) -> List[Hop]:
        out = []
        for x, y in zip(path, path[1:]):
            lk = next((l for l in self.links if {l.a, l.b} == {x, y}), None)
            if lk is not None and lk.radio:
                out.append(self.hop(x, y))
        return out

    def slices_on(self, hop: Hop) -> List[SliceInfo]:
        return [s for s in self.slices.values() if hop.a in s.path and hop.b in s.path]

    def load(self, hop: Hop, exclude: Iterable[str] = ()) -> float:
        skip = set(exclude)
        return float(sum(s.bandwidth_mbps or 0.0 for s in self.slices_on(hop) if s.id not in skip))

    def hop_floor(self, hop: Hop, exclude: Iterable[str] = ()) -> Optional[str]:
        from cer_intent.nsc.nsc_controller import floor_rank
        skip = set(exclude)
        floors = [s.acm_floor for s in self.slices_on(hop) if s.acm_floor and s.id not in skip]
        return max(floors, key=floor_rank) if floors else None

    # ── addressing ───────────────────────────────────────────────────────────
    def used_vlans(self, nodes: Iterable[str] = ()) -> List[int]:
        want = set(nodes)
        used = set()
        for s in self.slices.values():
            for e in s.endpoints:
                if e.get("vlan") not in (None, "") and (not want or e.get("node") in want):
                    used.add(int(e["vlan"]))
        return sorted(used)

    def free_vlan(self, nodes: Iterable[str] = ()) -> Optional[int]:
        nodes = list(nodes)
        used = set(self.used_vlans(nodes))
        for r in self.reserved.values():
            if not nodes or set(r.get("nodes") or []) & set(nodes):
                used |= set(r.get("vlans") or [])
        lo, hi = self.vlan_pool
        for v in range(lo, hi + 1):
            if v not in used:
                return v
        return None

    def vlan_owner(self, vlan: int, nodes: Iterable[str] = ()) -> Optional[str]:
        want = set(nodes)
        for name, r in self.reserved.items():
            if int(vlan) in (r.get("vlans") or []) and (not want or set(r.get("nodes") or []) & want):
                return f"{name} (intent {r.get('intent')}, not applied yet)"
        for s in self.slices.values():
            for e in s.endpoints:
                if e.get("vlan") not in (None, "") and int(e["vlan"]) == int(vlan) and (not want or e.get("node") in want):
                    return s.id
        return None

    def port(self, node: str) -> Optional[str]:
        n = self.nodes.get(node)
        return n.access_port() if n else None

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "nodes": [asdict(n) for n in self.nodes.values()],
                "live": {h.name: self.live_mcs(h) for h in self.radio_hops()},
                "links": [asdict(l) for l in self.links], "slices": [asdict(s) for s in self.slices.values()],
                "hops": [{"hop": h.name, "distance_m": h.distance_m, "load_mbps": self.load(h),
                          "floor": self.hop_floor(h), "slices": [s.id for s in self.slices_on(h)]} for h in self.radio_hops()],
                "plan": self.plan}


def load_plan() -> Dict[str, Any]:
    """The twin's site plan: CER_SITE_PLAN, else the flow's, else defaults."""
    for p in (os.getenv("CER_SITE_PLAN"), str(ROOT / "emulation" / "flow" / "site_plan.json")):
        if p and Path(p).exists():
            try:
                return {**DEFAULT_PLAN, **json.loads(Path(p).read_text())}
            except (OSError, ValueError):
                pass
    return dict(DEFAULT_PLAN)


def load_aliases() -> Dict[str, str]:
    """Operator aliases ("headquarters" -> "region-a"): CER_IMF_ALIASES or data/imf_aliases.json."""
    p = os.getenv("CER_IMF_ALIASES") or str(ROOT / "data" / "imf_aliases.json")
    try:
        data = json.loads(Path(p).read_text())
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}
