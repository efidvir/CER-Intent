"""
The rule reader
===============
Reads an operator's words into expectations, deterministically and offline.
It is always on: it reads every request by itself, and checks what a language
model reads (cer_intent/imf/llm.py).

    text ─► clauses ─► kind ─► object, endpoints, targets, contexts, action ─► Reading

Compound requests become several expectations: clauses split on ';', new lines,
sentences and "then"/"also"; a list after a colon ("video 400, ticketing 20
low-latency, staff 50") becomes one expectation per item with the header's
context. "then restore it" is a revert, not a new clause.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cer_intent.imf import lexicon as L
from cer_intent.imf.model import (Context, Endpoint, Expectation, Kind, ObjectRef, Reading, Source, Strictness)
from cer_intent.imf.quantities import Quantity, find_quantities, find_relative, mcs_name
from cer_intent.imf.timex import find_times

# ── clause splitting ──────────────────────────────────────────────────────────
_REVERT = re.compile(r"(?:,?\s*(?:and\s+)?then\s+|,\s*|\s+and\s+)(?:restore|revert|put\s+(?:it|them)\s+back|go\s+back|return\s+(?:it|them)?\s*to\s+normal"
                     r"|resume\s+(?=it\b|them\b)|bring\s+(?=it\s+back|them\s+back)|turn\s+(?=it\s+back\s+on|them\s+back\s+on)"
                     r"|back\s+to\s+(?:normal|before)|undo\s+it|reset\s+(?:it|them))(?:\s+(?:it|them|afterwards?|after(?:wards)?|later))?", re.I)
_SPLIT = re.compile(r"\s*(?:;|\n+|(?<=[a-z0-9)%])\.\s+(?=[A-Z])|,?\s+and\s+then\s+|,\s*then\s+|\.\s*then\s+|\s+also\s+|,\s*also\s+|\s+plus\s+(?=[a-z]+\s)"
                    r"|,\s*(?:and\s+)?(?=(?:keep|hold)\s+(?:the\s+)?(?:radio|link|hop|mcs\s*\d|modulation|it\s+at\s+mcs|at\s+mcs)\b)"
                    r"|\s+and\s+(?=(?:report|alert|notify|send\s+me|tell\s+me|never\s+let|don'?t\s+let|keep\s+(?:it|the))\b))\s*", re.I)
_LIST_HEAD = re.compile(r"^(?P<head>.{0,120}?):\s+(?P<items>.+)$")
_LIST_ITEM = re.compile(r"^\s*(?P<name>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?)\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>mbps|gbps|m|g)?\b(?P<rest>.*)$", re.I)

_NAME = r"[A-Za-z][\w.-]*(?:\s+(?:[A-Za-z](?![\w-])|\d{1,2}(?![\d.\w])))?"
def _ep(n: str, p: str, i: str) -> str:
    return (r"(?:the\s+)?(?P<" + n + r">" + _NAME + r")(?:(?::|\s+port\s+)(?P<" + p + r">(?:eth|ge|xe|et|port|ethernet)[\w/.-]*))?"
            r"(?:\s+(?P<" + i + r">\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?))?")


_PAIRS = [
    re.compile(rf"\bbetween\s+(?:the\s+)?(?:sites?\s+)?{_ep('a', 'pa', 'ia')}\s+and\s+(?:the\s+)?{_ep('b', 'pb', 'ib')}", re.I),
    re.compile(rf"\bfrom\s+(?:the\s+)?(?:site\s+)?{_ep('a', 'pa', 'ia')}\s+to\s+(?:the\s+)?(?:site\s+)?{_ep('b', 'pb', 'ib')}", re.I),
    re.compile(rf"\b(?:connect|link|join)\s+(?:the\s+)?(?:sites?\s+)?{_ep('a', 'pa', 'ia')}\s+(?:and|to|with)\s+(?:the\s+)?{_ep('b', 'pb', 'ib')}", re.I),
    re.compile(rf"{_ep('a', 'pa', 'ia')}\s*(?:↔|<->|<=>|<>|⇄)\s*{_ep('b', 'pb', 'ib')}", re.I),
    re.compile(rf"\b{_ep('a', 'pa', 'ia')}\s+(?:to|and|with)\s+{_ep('b', 'pb', 'ib')}", re.I),
]
_NOT_NAMES = {"the", "a", "an", "and", "to", "with", "site", "sites", "port", "over", "at", "of", "it", "them", "me", "us", "mbps",
              "gbps", "ms", "slice", "service", "vpn", "link", "radio", "hop", "rain", "now", "tonight", "today", "is", "be", "more",
              "less", "much", "up", "down", "back", "normal", "all", "every", "each", "both", "either", "go", "make", "get", "keep",
              "connect", "between", "from", "routed", "bridged", "gold", "silver", "bronze", "platinum", "low", "high", "low-latency",
              "best-effort", "edge-site", "can", "could", "take", "handle", "carry", "add", "region", "this", "that", "what", "how", "i",
              "we", "you", "my", "our", "your", "their", "its", "for", "in", "on", "by", "under", "above", "below", "than", "then",
              "also", "plus", "or", "per", "via", "using", "carrying", "towards", "toward", "into", "onto"}
_SERVICE_NOUN = r"(?:slices?|services?|vpns?|circuits?|connections?|tunnels?)"
_OBJ_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("intent", re.compile(r"\bthe\s+(?P<m>(?:\d+(?:\.\d+)?\s*(?:mbps|gbps)\s+|[\w-]+\s+)?(?:intent|request|order))\b", re.I)),
    ("slice", re.compile(r"\b(?P<m>slice[-_][\w-]+|[\w-]+-slice\b)", re.I)),
    ("slice", re.compile(r"\bslice\s+(?P<m>\d+)\b", re.I)),
    ("service", re.compile(r"\b(?P<m>[\w]+-(?:ran|backhaul|fronthaul|midhaul|svc|service|cctv|video|voice|iot))\b", re.I)),
    ("slice", re.compile(rf"\bthe\s+(?!(?:radio|air|wireless|microwave|hop|new|other|same|existing|current)\b)(?P<m>[\w-]+)\s+{_SERVICE_NOUN}\b", re.I)),
    ("service", re.compile(r"\bthe\s+(?P<m>backhaul|fronthaul|midhaul|ran\s+backhaul)\b", re.I)),
    ("radio", re.compile(r"\b(?P<m>radio[-_ ]?\d+|both\s+radios|the\s+radios|all\s+radios|each\s+radio)\b", re.I)),
    ("hop", re.compile(r"\b(?P<m>(?:the\s+)?(?:\d+\s*ghz\s+)?(?:radio\s+|air\s+|wireless\s+|microwave\s+|mm-?wave\s+|e-?band\s+|v-?band\s+)?"
                       r"(?:hop|link|air\s*link|radio\s+link)s?)\b(?!\s+(?:between|from))", re.I)),
    ("site", re.compile(r"\b(?:site|node)\s+(?P<m>[\w-]+)\b", re.I)),
    ("network", re.compile(r"\b(?P<m>the\s+(?:whole\s+|entire\s+)?network|everywhere|network[- ]wide)\b", re.I)),
]
_ALL = re.compile(r"\b(?:everything|all\s+(?:the\s+)?(?:slices|services|vpns|intents|of\s+them)|every\s+(?:slice|service)|all\s+of\s+them)\b", re.I)
_EXCEPT = re.compile(r"\b(?:except|but|other\s+than|apart\s+from|excluding|besides)\s+(?:for\s+)?(?:the\s+)?(?P<x>[\w-]+(?:\s+(?:and|,)\s*(?:the\s+)?[\w-]+)*)", re.I)
_LIFE_OPS = [("resume", re.compile(r"\b(?:resume|restart|reactivate|re-?enable|unpause|bring\s+back|turn\s+(?:it|them)\s+back\s+on)\b", re.I)),
             ("suspend", re.compile(r"\b(?:suspend|pause|stop|halt|deactivate|disable|turn\s+off|switch\s+off)\b", re.I)),
             ("delete", re.compile(r"\b(?:remove|delete|tear\s+down|terminate|withdraw|cancel|decommission|release|drop|get\s+rid\s+of|clean\s+up)\b", re.I))]
_WEATHER = re.compile(r"\b(?:in|under|during|with|at)\s+(?:a\s+)?(?:(?P<adj>heavy|light|moderate|torrential|the\s+design)\s+)?(?:rain|rainfall|storm|downpour)\b"
                      r"|\b(?P<adj2>heavy|torrential)\s+rain\b|\brain\s+(?:of\s+)?(?P<r>\d+(?:\.\d+)?)\s*mm", re.I)
_COND = re.compile(r"\b(?P<w>when(?:ever)?|if|while|whenever|as\s+long\s+as|once)\s+(?P<body>[^,;]+?)(?=,|;|$|\s+(?:then|and\s+then)\b)", re.I)
_OBS_METRICS = [("lowest_modulation", re.compile(r"\b(?:lowest|minimum|min)\s+(?:modulation|mcs)\b|\bmodulation\b|\bmcs\b|\bacm\s+state\b", re.I)),
                ("throughput", re.compile(r"\bthroughput\b|\btraffic\b|\busage\b", re.I)),
                ("latency", re.compile(r"\blatency\b|\bdelay\b", re.I)),
                ("loss", re.compile(r"\bloss\b|\bdrops?\b", re.I)),
                ("capacity", re.compile(r"\bcapacity\b", re.I)),
                ("utilisation", re.compile(r"\butili[sz]ation\b|\bload\b", re.I)),
                ("availability", re.compile(r"\bavailability\b|\buptime\b|\boutages?\b", re.I)),
                ("energy", re.compile(r"\benergy\b|\bpower\b|\bconsumption\b", re.I)),
                ("status", re.compile(r"\bstatus\b|\bstate\b|\bhealth\b|\bsla\b|\bslos?\b|\bfulfil+ment\b", re.I))]
_ASK_TYPES = [("explain", re.compile(r"^\s*(?:why|explain|how\s+come|what\s+happened)\b", re.I)),
              ("inventory", re.compile(r"\bwhat\s+(?:runs|is\s+running|traffic|services?|slices?)\s+(?:on|over|through|across|use|uses)\b"
                                       r"|\bwhich\s+(?:slices?|services?)\b|\bwhat\s+(?:uses|is\s+on)\b|\bwho\s+uses\b", re.I)),
              ("list", re.compile(r"^\s*(?:show|list|give\s+me)\b|\bwhat\s+(?:intents|rules|policies|slices|services)\s+(?:are|do|exist)\b", re.I)),
              ("capability", re.compile(r"\bwhat\s+can\s+(?:you|i|it)\s+do\b|\bhelp\b|\bwhat\s+do\s+you\s+(?:support|understand)\b", re.I)),
              ("status", re.compile(r"\b(?:status|state|health|ok|okay|up|down|degraded|healthy|fine|doing|working)\b|\bhow\s+is\b", re.I)),
              ("metric", re.compile(r"\bwhat(?:'s|\s+is)\s+the\s+(?:current\s+)?(?:capacity|latency|modulation|throughput|load|utili[sz]ation|headroom)\b", re.I))]
_EXPLORE_TYPES = [("headroom", re.compile(r"\bhow\s+much\s+(?:more|extra|additional|spare|headroom|room)\b|\b(?:max(?:imum)?|most)\s+(?:i|we)\s+can\b"
                                          r"|\bis\s+there\s+(?:room|headroom|capacity)\b|\bheadroom\b|\bhow\s+much\s+(?:can|could)\b", re.I)),
                  ("whatif", re.compile(r"\bwhat\s+(?:if|happens\s+if|would\s+happen)\b|\bsimulate\b", re.I)),
                  ("feasible", re.compile(r"\b(?:can|could|would)\b", re.I))]
_OPT_OBJECTIVES = [("energy", "minimize", re.compile(r"\b(?:energy|power|consumption|green|eco)\b", re.I)),
                   ("latency", "minimize", re.compile(r"\blatency\b|\bdelay\b", re.I)),
                   ("capacity", "maximize", re.compile(r"\bcapacity\b|\bthroughput\b", re.I)),
                   ("utilisation", "balance", re.compile(r"\bbalance\b|\bload\b", re.I))]
_SHED = re.compile(r"\b(?:take|borrow|steal|shed|squeeze|reduce)\s+(?:it\s+|bandwidth\s+|capacity\s+)?(?:from\s+)?(?:the\s+)?(?P<x>best[- ]effort|[\w-]+)\s+(?:first|traffic)\b", re.I)


def _norm(text: str) -> str:
    t = text.replace("≤", "<= ").replace("≥", ">= ").replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"[ \t]+", " ", t)


def split_clauses(text: str) -> List[Tuple[str, int, bool]]:
    """(clause, offset, revert) for each clause; "then restore it" marks the clause before it."""
    out: List[Tuple[str, int, bool]] = []
    pos = 0
    pieces: List[Tuple[str, int]] = []
    for m in _SPLIT.finditer(text):
        pieces.append((text[pos:m.start()], pos))
        pos = m.end()
    pieces.append((text[pos:], pos))
    for piece, off in pieces:
        if not piece.strip():
            continue
        rev = _REVERT.search(piece)
        revert = False
        if rev:
            revert = True
            piece = piece[:rev.start()] + piece[rev.end():]
        stripped = piece.strip(" ,.")
        if re.fullmatch(r"(?:restore|revert|put\s+(?:it|them)\s+back|go\s+back|resume|bring\s+(?:it|them)\s+back|turn\s+(?:it|them)\s+back\s+on)"
                        r"(?:\s+(?:it|them|afterwards?|after|later))?", stripped, re.I):
            if out:
                c, o, _ = out[-1]
                out[-1] = (c, o, True)
            continue
        if stripped:
            out.append((stripped, off + piece.find(stripped), revert))
    return out


def _left(text: str, a: int, n: int = 40) -> str:
    return text[max(0, a - n):a]


def _nearest_metric(text: str, a: int, b: int, candidates: Iterable[str]) -> Optional[str]:
    best, dist = None, 10 ** 6
    for metric in candidates:
        for m in L.METRIC_WORDS[metric].finditer(text):
            d = a - m.end() if m.end() <= a else m.start() - b
            d = abs(d) + (0 if m.end() <= a else 6)   # a word before the number binds a little tighter
            if d < dist:
                best, dist = metric, d
    return best if dist < 45 else None


def _op_for(text: str, a: int, b: int, default: str) -> str:
    left = _left(text, a, 32)
    right = text[b:b + 16]
    if re.search(r"\bbetween\s+[\d.]+\s*\w*\s*$", left, re.I):
        return "between"
    if L.GE_WORDS.search(left) or re.match(r"\s*(?:or\s+(?:more|better|higher|above)|\+|and\s+(?:up|above))", right, re.I):
        return "ge"
    if L.LE_WORDS.search(left) or re.match(r"\s*(?:or\s+(?:less|lower|below|worse|under)|max\b)", right, re.I):
        return "le"
    return default


class RuleReader:
    """Deterministic reader. `names` lists what the network knows (nodes, services, slices, radios)."""

    def __init__(self, names: Optional[Dict[str, List[str]]] = None, now: Optional[dt.datetime] = None):
        self.names = names or {}
        self.now = now

    # ── entry point ───────────────────────────────────────────────────────────
    def read(self, raw: str) -> Reading:
        text = _norm(raw or "").strip()
        reading = Reading(reader="rules")
        if not text:
            reading.notes.append("empty request")
            return reading
        oos = self._out_of_scope(text)
        if oos:
            reading.out_of_scope = oos
            return reading
        for clause, off, revert in split_clauses(text):
            exps = self._read_list(clause, off) or [self._read_clause(clause, off)]
            for e in exps:
                if e is None:
                    continue
                if revert:
                    e.action["revert"] = True
                reading.expectations.append(e)
        self._attach_hints(reading)
        if not reading.expectations:
            reading.notes.append("no expectation recognised")
        return reading

    def _out_of_scope(self, text: str) -> Optional[str]:
        in_scope = re.search(r"\b(?:slice|vpn|radio|hop|mbps|gbps|latency|bandwidth|vlan|mcs|modulation|backhaul|twin|rain)\b", text, re.I)
        for rx, what in L.OUT_OF_SCOPE:
            if rx.search(text) and not in_scope:
                return what
        # nothing about a network at all: no network word and no name the network knows
        if not L.NETWORK_WORDS.search(text) and not any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I)
                                                       for n in self._all_names()):
            return "not about the transport network"
        return None

    # ── a list after a colon: several deliveries sharing the header's context ─
    def _read_list(self, clause: str, off: int) -> Optional[List[Expectation]]:
        m = _LIST_HEAD.match(clause)
        if not m:
            return None
        items = [i for i in re.split(r"\s*,\s*|\s+and\s+(?=[A-Za-z][\w-]*\s+\d)", m.group("items")) if i.strip()]
        parsed = [_LIST_ITEM.match(i) for i in items]
        if len(items) < 2 or not all(parsed):
            return None
        head = m.group("head")
        head_exp = self._read_clause(head, off, allow_empty=True)
        group = re.sub(r"[^a-z0-9]+", "-", re.split(r"[,\s]", head.strip().lower())[0]).strip("-") or "group"
        out: List[Expectation] = []
        base = off + m.start("items")
        cursor = 0
        for raw_item, im in zip(items, parsed):
            ioff = base + m.group("items").find(raw_item, cursor)
            cursor = max(cursor, m.group("items").find(raw_item, cursor) + len(raw_item))
            name = re.sub(r"\s+", "-", im.group("name").lower())
            unit = (im.group("unit") or "").lower()
            value = float(im.group("num")) * (1000.0 if unit in ("gbps", "g") else 1.0)
            e = Expectation(kind=Kind.DELIVER, verb="provide", name=f"{group}-{name}", text=raw_item.strip(), span=[ioff, ioff + len(raw_item)])
            e.set_target("bandwidth", "ge", value, "Mbps", Source.STATED if unit else Source.POLICY,
                         note=None if unit else "unit assumed Mbps", span=[ioff + im.start("num"), ioff + im.end("num")])
            rest = im.group("rest") or ""
            self._profile(rest, e, ioff + im.start("rest"))
            if head_exp is not None:
                e.contexts = [c.model_copy(deep=True) for c in head_exp.contexts]
                if head_exp.object.endpoints:
                    e.object = head_exp.object.model_copy(deep=True)
                self._profile(head, e, off)
            e.object.type = "slice"
            out.append(e)
        return out

    # ── one clause ────────────────────────────────────────────────────────────
    def _kind(self, c: str) -> Tuple[Optional[Kind], Optional[re.Match]]:
        for kind, rx in L.KIND_CUES:
            m = rx.search(c)
            if m:
                if kind == Kind.ASK and re.search(r"^\s*(?:what|how|can|could|is)\b", c, re.I) and L.KIND_CUES[0][1].search(c):
                    return Kind.EXPLORE, m
                return kind, m
        return None, None

    def _read_clause(self, c: str, off: int, allow_empty: bool = False) -> Optional[Expectation]:
        kind, km = self._kind(c)
        times, tspans = find_times(c, self.now)
        cond_spans: List[Tuple[int, int]] = []
        conditions: List[Context] = []
        for cm in _COND.finditer(c):
            body = cm.group("body")
            q = find_quantities(body)
            metric = (_nearest_metric(body, q[0].span[0], q[0].span[1], L.METRIC_WORDS.keys()) if q else None) or \
                ("bandwidth" if any(x.dim == "rate" for x in q) else None)
            rain = re.search(r"\brain\b", body, re.I)
            if q and q[0].dim == "mcs" and kind not in (Kind.ASK,):
                v = q[0]
                low = re.search(r"\b(?:below|under|less\s+than|drops?|falls?|dips?|lower\s+than)\b", body, re.I)
                conditions.append(Context(kind="condition", params={"metric": "lowest_modulation", "op": "lt" if low else "ge",
                                                                    "value": mcs_name(v.value), "unit": "MCS"},
                                          span=[off + cm.start(), off + cm.end()]))
                cond_spans.append(cm.span())
            elif q and (metric or rain) and kind not in (Kind.ASK,):
                v = q[0]
                if rain or v.dim == "rain":
                    conditions.append(Context(kind="weather", params={"rain_mmh": v.value, "op": _op_for(body, v.span[0], v.span[1], "ge")},
                                              span=[off + cm.start(), off + cm.end()]))
                else:
                    conditions.append(Context(kind="condition", params={"metric": metric, "op": _op_for(body, v.span[0], v.span[1], "le"),
                                                                        "value": v.value, "unit": v.unit},
                                              span=[off + cm.start(), off + cm.end()]))
                cond_spans.append(cm.span())
        quants = [q for q in find_quantities(c) if not any(a <= q.span[0] < b for a, b in tspans + cond_spans)]
        endpoints = self._endpoints(c, off)
        obj = self._object(c, off, endpoints)
        vague = L.VAGUE.search(c)
        if kind is None:
            if endpoints and any(q.dim in ("rate",) for q in quants):
                kind = Kind.DELIVER
            elif vague:
                kind = Kind.CHANGE
            elif c.strip().endswith("?"):
                kind = Kind.ASK
            elif obj.mentions and any(q.dim in ("rate", "time", "percent", "mcs", "nines") for q in quants):
                kind = Kind.KEEP if _op_for(c, quants[0].span[0], quants[0].span[1], "eq") in ("ge", "le") else Kind.CHANGE
            elif endpoints:
                kind = Kind.DELIVER
            elif allow_empty:
                kind = Kind.DELIVER
            else:
                return Expectation(kind=Kind.ASK, verb=None, text=c, span=[off, off + len(c)], action={"type": "unknown"},
                                   vague="not understood")
        e = Expectation(kind=kind, verb=(km.group(0).strip().lower() if km else None), object=obj, text=c, span=[off, off + len(c)])
        e.contexts = list(times) + conditions
        for ctx in e.contexts:
            if ctx.span:
                ctx.span = [ctx.span[0] + (off if ctx.kind in ("window", "schedule") else 0), ctx.span[1] + (off if ctx.kind in ("window", "schedule") else 0)]
        w = _WEATHER.search(c)
        if w and not any(x.kind == "weather" for x in e.contexts):
            rain_q = next((q for q in quants if q.dim == "rain"), None)
            params: Dict[str, Any] = {}
            if rain_q:
                params["rain_mmh"] = rain_q.value
                rain_q.used = True
            elif w.group("r"):
                params["rain_mmh"] = float(w.group("r"))
            else:
                adj = (w.group("adj") or w.group("adj2") or "design").lower()
                params["rain"] = adj.replace("the ", "")
            e.contexts.append(Context(kind="weather", params=params, span=[off + w.start(), off + w.end()]))
        for q in quants:
            if q.dim == "rain" and not q.used and not any(x.kind == "weather" for x in e.contexts):
                e.contexts.append(Context(kind="weather", params={"rain_mmh": q.value}, span=[off + q.span[0], off + q.span[1]]))
                q.used = True
        if vague and kind in (Kind.CHANGE, Kind.OPTIMISE, Kind.KEEP):
            e.vague = vague.group(0)
        self._strict(c, e)
        self._profile(c, e, off)
        self._technology(c, e)
        getattr(self, f"_k_{kind.value}")(c, off, e, quants)
        return e

    # ── parts every kind shares ───────────────────────────────────────────────
    def _endpoints(self, c: str, off: int) -> List[Endpoint]:
        found = self._pair(c, off)
        if found:
            return found
        sites = []
        for n in self.names.get("node", []) + self.names.get("radio", []):
            rx = re.compile(r"(?<![\w-])" + re.sub(r"[-_ ]+", r"[-_ ]*", re.escape(n).replace("\\-", "-")) + r"(?![\w-])", re.I)
            for m in rx.finditer(c):
                sites.append((m.start(), m.end(), n))
        sites.sort()
        names = []
        for a, b, n in sites:
            if n not in [x[2] for x in names]:
                names.append((a, b, n))
        if len(names) == 2 and re.search(r"\b(?:to|and|between|from|<->|↔)\b|<->|↔", c[names[0][1]:names[1][0]] or "", re.I):
            return [Endpoint(mention=c[names[0][0]:names[0][1]], span=[off + names[0][0], off + names[0][1]]),
                    Endpoint(mention=c[names[1][0]:names[1][1]], span=[off + names[1][0], off + names[1][1]])]
        return []

    def _pair(self, c: str, off: int) -> List[Endpoint]:
        for rx in _PAIRS:
            for m in rx.finditer(c):
                a, b = m.group("a").strip(), m.group("b").strip()
                if not self._namey(a) or not self._namey(b) or a.lower() == b.lower():
                    continue
                if rx is _PAIRS[-1] and not (self._known(a) and self._known(b)):
                    continue
                return [Endpoint(mention=a, port=m.group("pa"), ip=m.group("ia"), span=[off + m.start("a"), off + m.end("a")]),
                        Endpoint(mention=b, port=m.group("pb"), ip=m.group("ib"), span=[off + m.start("b"), off + m.end("b")])]
        return []

    def _namey(self, s: str) -> bool:
        w = s.lower().strip()
        if w in _NOT_NAMES or re.fullmatch(r"[\d.]+", w):
            return False
        first = w.split()[0]
        if first in _NOT_NAMES and not self._known(s):
            return False
        return bool(re.match(r"[a-z]", w))

    def _known(self, s: str) -> bool:
        key = re.sub(r"[\s_]+", "-", s.lower().strip())
        for names in self.names.values():
            for n in names:
                if key == n.lower() or key.replace("-", "") == n.lower().replace("-", ""):
                    return True
        return False

    def _object(self, c: str, off: int, endpoints: List[Endpoint]) -> ObjectRef:
        if endpoints:
            return ObjectRef(type="slice", endpoints=endpoints)
        obj = ObjectRef(type="network")
        found: List[Tuple[str, str, Tuple[int, int]]] = []
        # names the network knows come first
        for typ, names in self.names.items():
            for n in sorted(names, key=len, reverse=True):
                for m in re.finditer(rf"(?<![\w-]){re.escape(n)}(?![\w-])", c, re.I):
                    if not any(a <= m.start() < b for _, _, (a, b) in found):
                        found.append((typ, n, m.span()))
        for typ, rx in _OBJ_PATTERNS:
            for m in rx.finditer(c):
                span = m.span("m")
                if any(a <= span[0] < b or span[0] <= a < span[1] for _, _, (a, b) in found):
                    continue
                mention = m.group("m").strip()
                if typ == "slice" and mention.lower().split()[0] in ("new", "a", "an", "routed", "bridged", "gold", "silver", "bronze", "l2", "l3", "this", "that"):
                    continue
                found.append((typ, mention, span))
        if found:
            found.sort(key=lambda f: f[2][0])
            obj.type = found[0][0] if found[0][0] != "node" else "site"
            obj.mentions = [f[1] for f in found]
            obj.span = [off + found[0][2][0], off + found[-1][2][1]]
            types = {f[0] for f in found}
            if len(types) > 1:
                obj.selector["types"] = sorted(types)
        if _ALL.search(c):
            obj.selector["all"] = True
            if obj.type == "network":
                obj.type = "slice"
        ex = _EXCEPT.search(c)
        if ex:
            names = [x.strip() for x in re.split(r"\s+and\s+|\s*,\s*", ex.group("x")) if x.strip() and x.strip().lower() != "the"]
            obj.selector["except"] = names
            obj.mentions = [m for m in obj.mentions if m not in names and not any(m.lower() in n.lower() for n in names)]
            obj.selector["all"] = True
            if obj.type in ("network", "service") and re.search(r"slices?|everything", c, re.I):
                obj.type = "slice"
        return obj

    def _strict(self, c: str, e: Expectation) -> None:
        for name, rx in L.STRICT_WORDS:
            if rx.search(c):
                e.strictness = Strictness(name)
                break
        for prio, rx in L.PRIORITY_WORDS:
            if rx.search(c):
                e.priority = prio
                break
        m = re.search(r"\bpriority\s*(?:of\s*|=\s*|level\s*)?(?P<p>\d)\b", c, re.I)
        if m:
            e.priority = int(m.group("p"))

    def _profile(self, c: str, e: Expectation, off: int) -> None:
        for name, rx in L.PROFILE_WORDS:
            m = rx.search(c)
            if m and not (name == "video" and e.kind != Kind.DELIVER) and not (name == "critical" and e.profile):
                if name == "best_effort" and e.kind in (Kind.KEEP,) and _SHED.search(c):
                    continue
                e.profile = name
                e.action.setdefault("profile_span", [off + m.start(), off + m.end()])
                if L.PROFILES[name].get("strictness") == "best_effort":
                    e.strictness = Strictness.BEST_EFFORT
                break

    def _technology(self, c: str, e: Expectation) -> None:
        for tech, rx in L.TECH_WORDS:
            m = rx.search(c)
            if m:
                if tech == "L2VPN" and m.group(0).lower() == "vlan" and e.kind != Kind.DELIVER:
                    continue
                e.set_target("technology", "eq", tech, None, Source.STATED)
                return

    def _targets(self, c: str, off: int, e: Expectation, quants: List[Quantity], rate_metric: str = "bandwidth") -> None:
        for q in quants:
            if q.used:
                continue
            a, b = q.span
            span = [off + a, off + b]
            if q.dim == "rate":
                metric = "headroom" if re.search(r"\bheadroom|spare|reserve\b", c[max(0, a - 30):b + 30], re.I) else rate_metric
                e.set_target(metric, _op_for(c, a, b, "ge"), q.value, "Mbps", span=span)
            elif q.dim == "time":
                metric = _nearest_metric(c, a, b, ("latency", "jitter")) or "latency"
                e.set_target(metric, _op_for(c, a, b, "le"), q.value, "ms", span=span)
            elif q.dim in ("percent", "nines"):
                metric = "availability" if q.dim == "nines" else (
                    _nearest_metric(c, a, b, ("loss", "availability", "headroom", "utilisation")) or ("availability" if q.value >= 90 else "loss"))
                default = "le" if metric in ("loss", "utilisation") else "ge"
                e.set_target(metric, _op_for(c, a, b, default), q.value, "%", span=span)
            elif q.dim == "mcs":
                op = _op_for(c, a, b, "ge")
                e.set_target("modulation_floor", "ge" if op != "le" else "le", mcs_name(q.value), "MCS", span=span)
            elif q.dim == "power":
                e.set_target("tx_power", _op_for(c, a, b, "le"), q.value, "dBm", span=span)
            elif q.dim == "watt":
                e.set_target("energy", _op_for(c, a, b, "le"), q.value, "W", span=span)
            elif q.dim == "vlan":
                for ep in e.object.endpoints:
                    ep.vlan = int(q.value)
                e.set_target("vlan", "eq", int(q.value), None, span=span)
            elif q.dim == "ip":
                ips = [x for x in quants if x.dim == "ip"]
                for ep, ip in zip(e.object.endpoints, ips):
                    ep.ip = ep.ip or ip.meta["ip"]
            elif q.dim == "number":
                left = c[max(0, a - 24):a].lower()
                if re.search(r"latency|delay|jitter", left) and q.value < 1000:
                    metric = "jitter" if "jitter" in left else "latency"
                    e.set_target(metric, _op_for(c, a, b, "le"), q.value, "ms", Source.POLICY, note="unit assumed ms", span=span)
                elif re.search(r"bandwidth|capacity|throughput|rate|speed", left):
                    e.set_target("bandwidth", _op_for(c, a, b, "ge"), q.value, "Mbps", Source.POLICY, note="unit assumed Mbps", span=span)
            q.used = True

    # ── per kind ──────────────────────────────────────────────────────────────
    def _k_deliver(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        if e.object.type == "network":
            e.object.type = "slice"
        self._targets(c, off, e, quants)
        n = re.search(r"\b(?:called|named)\s+(?P<n>[\w-]+)", c, re.I)
        if n:
            e.name = n.group("n")

    def _k_change(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        rel = find_relative(c)
        metric = _nearest_metric(c, 0, len(c), ("latency", "jitter", "loss", "bandwidth")) or "bandwidth"
        vlan = next((q for q in quants if q.dim == "vlan"), None)
        mcs = next((q for q in quants if q.dim == "mcs"), None)
        if vlan is not None and re.search(r"\b(?:move|change|switch|put|migrate)\b", c, re.I):
            e.action = {"op": "set", "metric": "vlan", "value": int(vlan.value)}
            e.set_target("vlan", "eq", int(vlan.value), None, span=[off + vlan.span[0], off + vlan.span[1]])
            vlan.used = True
        elif mcs is not None and re.search(r"\bfloor|modulation|mcs|acm\b", c, re.I):
            e.action = {"op": "set", "metric": "modulation_floor", "value": mcs_name(mcs.value)}
            e.set_target("modulation_floor", "ge", mcs_name(mcs.value), "MCS", span=[off + mcs.span[0], off + mcs.span[1]])
            mcs.used = True
        elif rel is not None:
            unit = rel.unit or ("Mbps" if metric == "bandwidth" else "ms")
            if rel.unit == "ms":
                metric = "latency" if metric not in ("latency", "jitter") else metric
            e.action = {"op": rel.op, "metric": metric, "value": rel.value, "unit": unit if rel.op != "scale" else None,
                        "span": [off + rel.span[0], off + rel.span[1]]}
            for q in quants:
                if rel.span[0] <= q.span[0] < rel.span[1] + 2:
                    q.used = True
        elif re.search(r"\brename\b", c, re.I):
            m = re.search(r"\bto\s+(?P<n>[\w-]+)", c, re.I)
            e.action = {"op": "rename", "value": m.group("n") if m else None}
        elif re.search(r"\b(?:re-?prioriti[sz]e|priority)\b", c, re.I) and e.priority is not None:
            e.action = {"op": "set", "metric": "priority", "value": e.priority}
        elif e.vague:
            e.action = {"op": "improve", "vague": e.vague}
        else:
            e.action = {"op": "set"}
        self._targets(c, off, e, quants)
        if e.action.get("op") == "set" and "metric" not in e.action and e.targets:
            t = e.targets[0]
            e.action.update({"metric": t.metric, "value": t.value, "unit": t.unit})
        if e.object.type == "network" and not e.object.mentions and not e.vague:
            e.object.type = "slice"

    def _k_lifecycle(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        for op, rx in _LIFE_OPS:
            if rx.search(c):
                e.action = {"op": op}
                break
        if e.object.type == "network":
            e.object.type = "slice"
        self._targets(c, off, e, quants)

    def _k_keep(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        self._targets(c, off, e, quants, rate_metric="bandwidth")
        m = re.search(r"\b(?:drop|fall|go|dip|sink)\s+(?:below|under)|\bexceed|\bgo\s+(?:above|over)|\brise\s+above", c, re.I)
        if m and re.search(r"\b(?:never|don'?t|do\s+not|not)\b", c, re.I):
            # "never let X drop below 150" means X >= 150
            for t in e.targets:
                if t.op in ("le", "ge"):
                    t.op = "ge" if re.search(r"drop|fall|dip|sink|below|under", m.group(0), re.I) else "le"
        if e.object.type == "network" and not e.object.mentions:
            e.object.type = "network"

    def _k_optimise(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        for objective, direction, rx in _OPT_OBJECTIVES:
            if rx.search(c):
                e.action = {"op": direction, "objective": objective}
                break
        else:
            e.action = {"op": "optimise", "objective": None}
        self._targets(c, off, e, quants)
        for t in list(e.targets):
            if t.metric == "bandwidth" and t.op in ("le", "lt"):
                e.targets.remove(t)
                e.contexts.append(Context(kind="condition", params={"metric": "traffic", "op": "le", "value": t.value, "unit": "Mbps"},
                                          span=t.span))
        if e.object.type == "network" and re.search(r"\bhop|radio|link\b", c, re.I):
            e.object.type = "hop"

    def _k_guard(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        if re.search(r"\b(?:headroom|spare|reserve|free)\b", c, re.I):
            q = next((x for x in quants if x.dim in ("percent", "rate")), None)
            rule: Dict[str, Any] = {"rule": "headroom"}
            if q:
                rule.update({"value": q.value, "unit": "%" if q.dim == "percent" else "Mbps"})
                e.set_target("headroom", "ge", q.value, "%" if q.dim == "percent" else "Mbps", span=[off + q.span[0], off + q.span[1]])
                q.used = True
            e.action = rule
            if e.object.type == "network":
                e.object.type = "hop"
        elif re.search(r"\bmcs\s*\d|\bmcs\b|modulation|floor", c, re.I):
            q = next((x for x in quants if x.dim == "mcs"), None)
            e.action = {"rule": "floor", "value": mcs_name(q.value) if q else None}
            if q:
                e.set_target("modulation_floor", "ge", mcs_name(q.value), "MCS", span=[off + q.span[0], off + q.span[1]])
                q.used = True
        elif re.search(r"approval", c, re.I):
            e.action = {"rule": "approval"}
        else:
            e.action = {"rule": "freeze"}
        if e.object.type == "network" and e.action.get("rule") == "freeze" and not e.object.mentions:
            e.object.type = "network"

    def _k_observe(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        metrics = [name for name, rx in _OBS_METRICS if rx.search(c)]
        trigger = next((x for x in e.contexts if x.kind in ("condition", "weather")), None)
        if trigger is not None and trigger.kind == "condition" and trigger.params.get("metric"):
            first = trigger.params["metric"]
            metrics = [first] + [m for m in metrics if m != first and (m != "loss" or re.search(r"\bloss\b", c, re.I))]
        e.action = {"op": "report", "metrics": metrics or ["status"]}
        if trigger is not None or re.search(r"\b(?:alert|warn|notify|tell\s+me\s+(?:if|when)|let\s+me\s+know\s+(?:if|when))\b", c, re.I):
            e.action["op"] = "alert"
        if not any(x.kind == "schedule" for x in e.contexts) and e.action["op"] == "report":
            e.action["cadence_default"] = True
        self._targets(c, off, e, quants)

    def _k_explore(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        for name, rx in _EXPLORE_TYPES:
            if rx.search(c):
                e.action = {"question": name}
                break
        self._targets(c, off, e, quants)
        rm = re.search(r"\b(?:remove|delete|lose|drop|without)\s+(?:the\s+)?(?P<x>[\w-]+)", c, re.I)
        if rm and e.action.get("question") == "whatif":
            e.action["remove"] = rm.group("x")
        fail = re.search(r"\b(?P<x>radio[-_ ]?\d|[\w-]+)\s+(?:fails|goes\s+down|is\s+down|dies)\b", c, re.I)
        if fail:
            e.action["failure"] = fail.group("x")

    def _k_ask(self, c: str, off: int, e: Expectation, quants: List[Quantity]) -> None:
        for name, rx in _ASK_TYPES:
            if rx.search(c):
                e.action = {"question": name}
                break
        else:
            e.action = {"question": "status"}
        self._targets(c, off, e, quants)

    def _all_names(self) -> List[str]:
        return [n.lower() for names in self.names.values() for n in names]

    # ── hints that belong to the expectation before them ─────────────────────
    def _attach_hints(self, reading: Reading) -> None:
        keep: List[Expectation] = []
        for e in reading.expectations:
            shed = _SHED.search(e.text or "")
            if shed and keep and keep[-1].kind in (Kind.KEEP, Kind.DELIVER, Kind.CHANGE) and e.kind not in (Kind.LIFECYCLE,):
                keep[-1].action["shed_first"] = shed.group("x").replace(" ", "_").replace("-", "_")
                continue
            floor = e.target("modulation_floor")
            if (e.kind == Kind.KEEP and floor is not None and len(e.targets) == 1 and keep
                    and keep[-1].kind in (Kind.DELIVER, Kind.CHANGE, Kind.OPTIMISE) and e.object.type in ("radio", "hop", "network")
                    and not e.object.ids and all(m.lower() not in self._all_names() for m in e.object.mentions)):
                keep[-1].targets.append(floor)
                keep[-1].action["floor_from"] = e.text
                continue
            if (e.kind in (Kind.KEEP, Kind.OBSERVE) and keep and keep[-1].kind == Kind.DELIVER and not e.object.mentions
                    and not e.object.ids and not e.object.endpoints and re.search(r"\b(?:it|its|this\s+slice|that\s+slice)\b", e.text or "", re.I)):
                e.action["of"] = keep[-1].id
                e.object.type = "slice"
            if e.action.get("type") == "unknown" and keep and re.match(r"^\s*(?:only|but\s+only|just)\b", e.text or "", re.I):
                keep[-1].contexts += e.contexts
                continue
            keep.append(e)
        reading.expectations = keep
