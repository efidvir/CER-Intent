"""
Descriptions that point at parts of the network
===============================================
An operator often describes rather than names: "the slice on VLAN 100", "the
busiest hop", "slices over radio-1", "all the routed slices", "the degraded
ones", "my last slice", "the 60 GHz link", "the radio at edge". Each pattern
here is answered from the network as it is now (cer_intent/imf/network.py) and
the intent store, and says why it picked what it picked.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from cer_intent.imf.radio import mcs_index


@dataclass
class Referent:
    type: str                          # slice, hop, radio, site, intent
    ids: List[str]
    why: str
    span: Tuple[int, int] = (0, 0)
    group: bool = False                # a set ("all the routed slices") rather than one thing

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "ids": self.ids, "why": self.why, "span": list(self.span), "group": self.group}


_SLICE = r"(?:slices?|services?|vpns?|circuits?|ones?)"
_VLAN = [re.compile(rf"\b{_SLICE}\s+(?:on|with|using|over|in|carrying)\s+vlan\s*(?P<v>\d{{1,4}})\b", re.I),
         re.compile(rf"\bvlan\s*(?P<v>\d{{1,4}})(?:'s)?\s+{_SLICE}\b", re.I),
         re.compile(r"\b(?:the\s+)?(?:one|slice|service)\s+(?:on|with)\s+vlan\s*(?P<v>\d{1,4})\b", re.I),
         re.compile(r"^(?:\s*\w+){0,3}?\s+vlan\s*(?P<v>\d{1,4})\b(?!\s*(?:with|for|and|between|from|to)\b)", re.I)]
_IP = re.compile(r"\b(?P<ip>\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)\b")
_RATE = re.compile(rf"\bthe\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<u>mbps|gbps|mbit/s|m|g)\s+{_SLICE}\b", re.I)
_TECH = re.compile(rf"\b(?:all\s+)?(?:the\s+|my\s+)?(?P<t>l2|l3|layer[- ]?2|layer[- ]?3|routed|ethernet|bridged|l2vpn|l3vpn)\s+{_SLICE}\b", re.I)
_STATE = re.compile(r"\b(?:the\s+|all\s+(?:the\s+)?)?(?P<s>degraded|suspended|failing|held|active|paused|scheduled|waiting)\s+"
                    r"(?P<what>slices|intents|ones|services|objectives)\b", re.I)
_PATH = re.compile(rf"\b(?:{_SLICE}|traffic|everything|anything|whatever|what|all\s+that)\s+(?:that\s+)?"
                   r"(?:(?:runs?|goes?|uses?|rides?|travels?|is|are)\s+)?"
                   r"(?:on|over|through|across|using|uses?|via|crossing|cross(?:es)?|riding)\s+(?:the\s+)?(?P<x>[\w.-]+(?:\s+(?:hop|link|radio|site))?)", re.I)
_SUPER_HOP = re.compile(r"\bthe\s+(?P<s>busiest|most\s+loaded|fullest|most\s+used|least\s+loaded|emptiest|quietest|least\s+used|"
                        r"weakest|most\s+faded|fading|worst)\s+(?P<what>hop|link|radio\s+link|radio)\b", re.I)
_SUPER_SLICE = re.compile(rf"\bthe\s+(?P<s>biggest|largest|smallest|newest|latest|most\s+recent|oldest|first|last)\s+{_SLICE}\b", re.I)
_MINE = re.compile(r"\b(?:my\s+(?P<a>last|latest|previous|newest|most\s+recent|first)\s+(?P<w>slice|intent|request|change)"
                   r"|the\s+(?P<w2>slice|one|intent)\s+(?:i|we)\s+(?:just\s+)?(?:made|created|asked\s+for|set\s+up|requested|added))\b", re.I)
_ADJ = re.compile(r"\bthe\s+(?P<what>hop|link|radio\s+link|radio|radios)\s+(?:to|at|near|next\s+to|towards|toward|from|by|serving|facing|in)"
                  r"\s+(?:the\s+)?(?P<site>[\w-]+(?:\s+[a-z](?![\w-]))?)", re.I)
_BAND = re.compile(r"\bthe\s+(?P<band>\d{2,3}(?:\.\d+)?\s*ghz|[vewd]-?band)\s+(?P<what>hops?|links?|radios?|radio\s+links?)\b", re.I)


def _slices_with(net, pred: Callable[[Any], bool]) -> List[str]:
    return [s.id for s in net.slices.values() if pred(s)]


def find(text: str, net, records: Optional[List[Any]] = None, owner: Optional[str] = None) -> List[Referent]:
    """Every description in the text that points at something in the network, with why."""
    out: List[Referent] = []
    t = text or ""
    for rx in _VLAN:
        for m in rx.finditer(t):
            v = int(m.group("v"))
            ids = _slices_with(net, lambda s: v in s.vlans())
            if ids:
                out.append(Referent("slice", ids, f"VLAN {v} is used by {', '.join(ids)}", m.span()))
        if out:
            break
    for m in _IP.finditer(t):
        try:
            want = ipaddress.ip_network(m.group("ip"), strict=False)
        except ValueError:
            continue
        ids = []
        for s in net.slices.values():
            for e in s.endpoints:
                ip = e.get("ip")
                if not ip:
                    continue
                try:
                    if ipaddress.ip_interface(ip).ip in want or ipaddress.ip_interface(ip).network.overlaps(want):
                        ids.append(s.id)
                except ValueError:
                    pass
        if ids:
            out.append(Referent("slice", sorted(set(ids)), f"{m.group('ip')} is on {', '.join(sorted(set(ids)))}", m.span()))
    for m in _RATE.finditer(t):
        v = float(m.group("n")) * (1000.0 if m.group("u").lower() in ("gbps", "g") else 1.0)
        ids = _slices_with(net, lambda s: s.bandwidth_mbps is not None and abs(float(s.bandwidth_mbps) - v) < 0.5)
        if ids:
            out.append(Referent("slice", ids, f"{', '.join(ids)} carr{'ies' if len(ids) == 1 else 'y'} {v:g} Mbps", m.span()))
    for m in _TECH.finditer(t):
        tech = "L3VPN" if re.search(r"l3|3|routed", m.group("t"), re.I) else "L2VPN"
        ids = _slices_with(net, lambda s: (s.technology or "").upper().replace("L3SM", "L3VPN").replace("L2SM", "L2VPN").startswith(tech)
                           or (tech == "L3VPN" and "L3" in str(s.technology or "").upper())
                           or (tech == "L2VPN" and "L2" in str(s.technology or "").upper()))
        out.append(Referent("slice", ids, f"{'routed (L3VPN)' if tech == 'L3VPN' else 'Ethernet (L2VPN)'} slices: "
                                          f"{', '.join(ids) or 'none'}", m.span(), group=True))
    if records is not None:
        for m in _STATE.finditer(t):
            state = {"paused": "suspended", "failing": "degraded", "waiting": "checked"}.get(m.group("s").lower(), m.group("s").lower())
            recs = [r for r in records if r.state.value == state]
            if m.group("what").lower() in ("slices", "services", "ones"):
                ids = sorted({sid for r in recs for sid in (r.links.get("slices") or []) + list((r.links.get("suspended") or {}).keys())})
                out.append(Referent("slice", ids, f"{state} intents' slices: {', '.join(ids) or 'none'}", m.span(), group=True))
            else:
                ids = [r.id for r in recs]
                out.append(Referent("intent", ids, f"{state} intents: {', '.join(r.name or r.id for r in recs) or 'none'}",
                                    m.span(), group=True))
        for m in _MINE.finditer(t):
            mine = [r for r in records if (owner is None or r.owner == owner) and (r.links.get("slices") or r.acts())]
            mine.sort(key=lambda r: r.created_at)
            if not mine:
                continue
            pick = mine[0] if (m.group("a") or "").lower() == "first" else mine[-1]
            slices = pick.links.get("slices") or [e.name for e in pick.expectations if e.name]
            if slices:
                out.append(Referent("slice", slices[:1], f"your {'first' if pick is mine[0] and len(mine) > 1 and (m.group('a') or '').lower() == 'first' else 'latest'} "
                                                          f"slice: {slices[0]} ({pick.name})", m.span()))
            else:
                out.append(Referent("intent", [pick.id], f"your latest intent: {pick.name}", m.span()))
    for m in _PATH.finditer(t):
        x = m.group("x")
        r = net.resolve(x, ("radio", "site", "hop"))
        if not r.ok and r.status != "group":
            continue
        targets = [r.id] if r.ok else [c[0] for c in r.candidates]
        ids = []
        for tgt in targets:
            if "|" in str(tgt):
                a, _, b = tgt.partition("|")
                ids += [s.id for s in net.slices.values() if a in s.path and b in s.path]
            else:
                ids += [s.id for s in net.slices.values() if tgt in s.path or tgt in s.nodes()]
        ids = sorted(set(ids))
        out.append(Referent("slice", ids, f"slices over {', '.join(map(str, targets))}: {', '.join(ids) or 'none'}", m.span(), group=True))
    for m in _SUPER_HOP.finditer(t):
        hops = net.radio_hops()
        if not hops:
            continue
        s = m.group("s").lower()
        if s in ("weakest", "most faded", "fading", "worst"):
            scored = [(mcs_index(net.live_mcs(h)) if net.live_mcs(h) else 99, h) for h in hops]
            scored.sort(key=lambda x: x[0])
            h = scored[0][1]
            why = f"{h.name} runs at {net.live_mcs(h)} now" if net.live_mcs(h) else f"{h.name} (no radio reported its modulation)"
        else:
            rev = s in ("busiest", "most loaded", "fullest", "most used")
            h = sorted(hops, key=lambda x: net.load(x) / max(1.0, x.capacity(0)), reverse=rev)[0]
            why = f"{h.name} carries {net.load(h):g} of {h.capacity(0):g} Mbps"
        out.append(Referent("hop", [h.name], why, m.span()))
    for m in _SUPER_SLICE.finditer(t):
        sl = list(net.slices.values())
        if not sl:
            continue
        s = m.group("s").lower()
        if s in ("biggest", "largest", "smallest"):
            pick = sorted(sl, key=lambda x: x.bandwidth_mbps or 0, reverse=s != "smallest")[0]
            why = f"{pick.id} carries {pick.bandwidth_mbps or 0:g} Mbps"
        else:
            order = {sid: i for i, sid in enumerate(net.slices)}
            pick = sorted(sl, key=lambda x: order[x.id], reverse=s not in ("oldest", "first"))[0]
            why = f"{pick.id} is the {s} slice"
        out.append(Referent("slice", [pick.id], why, m.span()))
    for m in _ADJ.finditer(t):
        site = net.resolve(m.group("site"), ("site",))
        if not site.ok:
            continue
        what = m.group("what").lower()
        if what.startswith("radio") and "link" not in what:
            ids = [n for n in net.neighbours(site.id) if n in net.nodes and net.nodes[n].radio]
            if ids:
                out.append(Referent("radio", ids, f"{', '.join(ids)} {'is' if len(ids) == 1 else 'are'} next to {site.id}", m.span(),
                                    group=what.endswith("s")))
        else:
            hops = [h for h in net.radio_hops() if site.id in net._ends_through(h)]
            if hops:
                out.append(Referent("hop", [hops[0].name], f"{hops[0].name} is the radio hop on the way to {site.id}", m.span()))
    for m in _BAND.finditer(t):
        band = m.group("band").lower().replace(" ", "")
        ghz = re.match(r"(\d+(?:\.\d+)?)ghz", band)
        radios = []
        for n in net.nodes.values():
            if not n.radio:
                continue
            for b in n.bands:
                if ghz and b.get("min_ghz") and b.get("max_ghz") and float(b["min_ghz"]) <= float(ghz.group(1)) <= float(b["max_ghz"]):
                    radios.append(n.id)
                elif not ghz and str(b.get("name", "")).lower().replace("-", "") == band.replace("-", ""):
                    radios.append(n.id)
        radios = sorted(set(radios))
        if not radios:
            continue
        if m.group("what").lower().startswith("radio") and "link" not in m.group("what").lower():
            out.append(Referent("radio", radios, f"{', '.join(radios)} work in {m.group('band')}", m.span(), group=True))
        else:
            hops = [h.name for h in net.radio_hops() if h.a in radios and h.b in radios]
            if hops:
                out.append(Referent("hop", hops, f"{', '.join(hops)}: both radios work in {m.group('band')}", m.span(),
                                    group=m.group("what").lower().endswith("s")))
    return out
