"""
Numbers with units, as operators write them
===========================================
"500 Mbps", "0.5 Gbps", "half a gig", "five nines", "under 5 ms", "MCS4 or better",
"256-QAM", "60 mm/h", "by 20 %", "double", "to 600"... Each found quantity keeps
its character span so the studio can underline where a value came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
            "sixty": 60, "hundred": 100, "a hundred": 100, "a few": 3, "a couple of": 2, "half a": 0.5, "a": 1, "an": 1}
NINES = {"two": 99.0, "three": 99.9, "four": 99.99, "five": 99.999, "six": 99.9999}

NUM = r"(?P<num>\d+(?:[.,]\d+)?)"
UNIT_PATTERNS: List[Tuple[str, str, float, str]] = [
    # (dimension, unit regex, factor to the canonical unit, canonical unit)
    ("rate", r"t(?:bps|bit/?s|b/s)", 1_000_000.0, "Mbps"),
    ("rate", r"g(?:bps|bit/?s|b/s|ig(?:abits?)?(?:/s| per second)?|igs?)\b", 1000.0, "Mbps"),
    ("rate", r"m(?:bps|bit/?s|b/s|egabits?(?:/s| per second)?|egs?)\b", 1.0, "Mbps"),
    ("rate", r"k(?:bps|bit/?s|b/s|ilobits?(?:/s| per second)?)\b", 0.001, "Mbps"),
    ("rain", r"mm\s*/\s*h(?:r|our)?\b|mm\s+per\s+hour|millimet(?:er|re)s?\s+(?:per|an|a)\s+hour", 1.0, "mm/h"),
    ("time", r"(?:µs|us|microseconds?|micro-seconds?)\b", 0.001, "ms"),
    ("time", r"(?:ms|msec|millis(?:econds?)?|milliseconds?)\b", 1.0, "ms"),
    ("percent", r"(?:%|percent|per\s*cent|pct)", 1.0, "%"),
    ("power", r"dbm\b", 1.0, "dBm"),
    ("db", r"db\b", 1.0, "dB"),
    ("watt", r"kw\b|kilowatts?\b", 1000.0, "W"),
    ("watt", r"w\b|watts?\b", 1.0, "W"),
    ("distance", r"km\b|kilomet(?:er|re)s?\b", 1000.0, "m"),
    ("distance", r"m\b|met(?:er|re)s?\b", 1.0, "m"),
    ("duration", r"(?:hours?|hrs?|h)\b", 3600.0, "s"),
    ("duration", r"(?:minutes?|mins?)\b", 60.0, "s"),
    ("duration", r"(?:seconds?|secs?|s)\b", 1.0, "s"),
    ("duration", r"(?:days?)\b", 86400.0, "s"),
]
_UNIT_RE = [(dim, re.compile(NUM + r"\s*(?:-\s*)?(?P<unit>" + pat + r")", re.I), f, cu) for dim, pat, f, cu in UNIT_PATTERNS]
_MCS_RE = re.compile(r"\b(?:mcs\s*-?\s*(?P<mcs>\d{1,2})|(?P<qam>\d{2,4})\s*-?\s*qam|(?P<psk>qpsk|8psk|bpsk))\b", re.I)
_NINES_RE = re.compile(r"\b(?P<n>two|three|four|five|six)\s+nines\b", re.I)
_HALF_GIG = re.compile(r"\bhalf\s+a\s+gig(?:abit)?\b", re.I)
_BARE_NUM = re.compile(r"(?<![\w.:/-])(?P<num>\d+(?:\.\d+)?)(?![\w.:%/-])")
_VLAN_RE = re.compile(r"\bvlan(?:\s*id)?\s*[:#]?\s*(?P<v>\d{1,4})\b", re.I)
_IP_RE = re.compile(r"\b(?P<ip>\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)\b")
QAM_TO_MCS = {"bpsk": 1, "qpsk": 2, "8psk": 3, "16": 4, "32": 5, "64": 6, "128": 7, "256": 8, "512": 9, "1024": 10, "2048": 11, "4096": 12}


@dataclass
class Quantity:
    dim: str                    # rate, time, percent, rain, power, db, watt, distance, duration, mcs, nines, vlan, ip, number
    value: float
    unit: Optional[str]
    span: Tuple[int, int]
    raw: str
    used: bool = False
    meta: dict = field(default_factory=dict)


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def find_quantities(text: str) -> List[Quantity]:
    """Every number with a unit, MCS/QAM, nines, VLAN and IP; then bare numbers not covered."""
    out: List[Quantity] = []
    taken: List[Tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    def add(q: Quantity) -> None:
        out.append(q)
        taken.append(q.span)

    for m in _IP_RE.finditer(text):
        add(Quantity("ip", 0.0, None, m.span(), m.group("ip"), meta={"ip": m.group("ip")}))
    for m in _VLAN_RE.finditer(text):
        if free(*m.span()):
            add(Quantity("vlan", float(m.group("v")), None, m.span(), m.group(0)))
    for m in _NINES_RE.finditer(text):
        add(Quantity("nines", NINES[m.group("n").lower()], "%", m.span(), m.group(0)))
    for m in _HALF_GIG.finditer(text):
        add(Quantity("rate", 500.0, "Mbps", m.span(), m.group(0)))
    for m in _MCS_RE.finditer(text):
        if not free(*m.span()):
            continue
        if m.group("mcs"):
            idx = int(m.group("mcs"))
        elif m.group("qam"):
            idx = QAM_TO_MCS.get(m.group("qam"), 0)
        else:
            idx = QAM_TO_MCS.get(m.group("psk").lower(), 2)
        add(Quantity("mcs", float(idx), "MCS", m.span(), m.group(0)))
    for dim, rx, factor, cu in _UNIT_RE:
        for m in rx.finditer(text):
            a, b = m.span()
            if not free(a, b):
                continue
            # a time of day such as "20:00" or a range such as "18-23h" is not a duration
            pre = text[max(0, a - 1):a]
            if dim == "duration" and (pre == ":" or re.match(r"\d{1,2}:\d{2}", text[a:b])):
                continue
            if dim == "distance" and re.search(r"\b(?:ms|mm)\b", m.group("unit"), re.I):
                continue
            add(Quantity(dim, _f(m.group("num")) * factor, cu, (a, b), m.group(0)))
    for m in _BARE_NUM.finditer(text):
        a, b = m.span()
        if free(a, b) and not re.match(r"\d{1,2}:\d{2}", text[a:a + 5]):
            # skip clock times (handled by the time reader) and digits inside names like radio-1
            prev = text[max(0, a - 1):a]
            if prev in ("-", "_") or (a >= 1 and text[a - 1].isalpha()):
                continue
            out.append(Quantity("number", _f(m.group("num")), None, (a, b), m.group(0)))
    out.sort(key=lambda q: q.span[0])
    return out


# ── relative changes ─────────────────────────────────────────────────────────
_SCALE_WORDS = [(re.compile(r"\b(?:double|twice|2x|x2|two\s+times)\b", re.I), 2.0),
                (re.compile(r"\b(?:triple|three\s+times|3x|x3)\b", re.I), 3.0),
                (re.compile(r"\b(?:quadruple|four\s+times|4x)\b", re.I), 4.0),
                (re.compile(r"\b(?:halve|half|cut\s+in\s+half)\b", re.I), 0.5)]
_UP = re.compile(r"\b(?:increase|raise|boost|bump|grow|expand|up|upgrade|add|more|extend|higher)\b", re.I)
_DOWN = re.compile(r"\b(?:decrease|reduce|lower|cut|shrink|drop|less|downgrade|trim|lessen)\b", re.I)
_BY = re.compile(r"\bby\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|mbps|gbps|ms)?", re.I)
_TO = re.compile(r"\bto\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|mbps|gbps|ms|mcs\s*\d+)?", re.I)
_PLUS = re.compile(r"(?P<sign>[+-])\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>mbps|gbps|%)", re.I)
_MAKE_IT = re.compile(r"\bmake\s+(?:it|[\w-]+)\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>mbps|gbps|ms|%)?", re.I)
_ADD = re.compile(r"\b(?:add|another|extra|additional|plus)\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>mbps|gbps|mbit/s)\b", re.I)
_PCT_MORE = re.compile(r"\b(?P<num>\d+(?:\.\d+)?)\s*(?:%|percent)\s+(?P<dir>more|less|extra|fewer)\b", re.I)


@dataclass
class Relative:
    op: str            # scale, add, set
    value: float
    unit: Optional[str]
    span: Tuple[int, int]


def find_relative(text: str) -> Optional[Relative]:
    for rx, factor in _SCALE_WORDS:
        m = rx.search(text)
        if m:
            return Relative("scale", factor, None, m.span())
    m = _PCT_MORE.search(text)
    if m:
        v = _f(m.group("num"))
        return Relative("scale", 1 + (v / 100.0) * (-1 if m.group("dir").lower() in ("less", "fewer") else 1), None, m.span())
    m = _ADD.search(text)
    if m:
        v = _f(m.group("num")) * (1000.0 if m.group("unit").lower() == "gbps" else 1.0)
        return Relative("add", v, "Mbps", m.span())
    m = _PLUS.search(text)
    if m:
        v = _f(m.group("num")) * (1000.0 if m.group("unit").lower() == "gbps" else 1.0)
        if m.group("unit") == "%":
            return Relative("scale", 1 + (v / 100.0) * (1 if m.group("sign") == "+" else -1), None, m.span())
        return Relative("add", v if m.group("sign") == "+" else -v, "Mbps", m.span())
    m = _BY.search(text)
    if m:
        unit = (m.group("unit") or "").lower()
        v = _f(m.group("num"))
        down = bool(_DOWN.search(text[:m.start()])) and not bool(_UP.search(text[:m.start()]))
        if unit in ("%", "percent"):
            return Relative("scale", 1 + (v / 100.0) * (-1 if down else 1), None, m.span())
        v = v * (1000.0 if unit == "gbps" else 1.0)
        return Relative("add", -v if down else v, "ms" if unit == "ms" else "Mbps", m.span())
    m = _MAKE_IT.search(text) or _TO.search(text)
    if m and (m.group("unit") or _UP.search(text) or _DOWN.search(text) or text.lower().startswith(("make", "set", "change", "take"))):
        unit = (m.group("unit") or "").lower()
        v = _f(m.group("num")) * (1000.0 if unit == "gbps" else 1.0)
        return Relative("set", v, {"ms": "ms", "%": "%", "percent": "%"}.get(unit, "Mbps" if unit in ("mbps", "gbps", "") else unit),
                        m.span())
    return None


def mcs_name(idx: float) -> str:
    return f"MCS{int(idx)}"


def mcs_index(name: object) -> Optional[int]:
    if name is None:
        return None
    if isinstance(name, (int, float)):
        return int(name)
    m = re.search(r"(\d+)", str(name))
    if str(name).upper().startswith("MCS") and m:
        return int(m.group(1))
    s = str(name).lower().replace("-", "").replace(" ", "")
    for k, v in QAM_TO_MCS.items():
        if s == k or s == f"{k}qam":
            return v
    return int(m.group(1)) if m else None
