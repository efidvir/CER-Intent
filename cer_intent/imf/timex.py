"""
Times as operators write them
=============================
"tonight 20:00-23:00", "Saturday 18-23", "from 8pm to 11pm", "business hours",
"at night", "for 3 hours", "until Friday", "every hour", "daily at 08:00".

Returns window contexts ({start, end, days, date, once, label}) and schedule
contexts ({every, seconds, at}); named windows come from operator policy
(lexicon.WINDOWS) and are marked as such.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from cer_intent.imf.lexicon import DAYS, WINDOWS
from cer_intent.imf.model import Context, Source

_CLOCK = r"(?:(?P<h{n}>\d{{1,2}})(?::(?P<m{n}>\d{{2}}))?\s*(?P<ap{n}>am|pm|a\.m\.|p\.m\.|h)?|(?P<w{n}>noon|midnight))"
_RANGE = re.compile(r"\b(?:from\s+|between\s+)?" + _CLOCK.format(n=1) + r"\s*(?:-|–|—|to|until|till|and)\s*" + _CLOCK.format(n=2) + r"\b", re.I)
_UNIT_NEXT = r"(?![.,]\d)(?!\s*(?:[kmgt]?bps|[kmg]bit|mbit|gbit|ms|%|percent|mm|db|dbm|w\b|hz|ghz|mhz|g\b|m\b|mcs|qam|x\b))"
_AT = re.compile(r"\b(?:at|from|after|before|until|till)\s+" + _CLOCK.format(n=1) + r"\b" + _UNIT_NEXT, re.I)
_DUR = re.compile(r"\bfor\s+(?:the\s+next\s+)?(?P<n>\d+(?:\.\d+)?|an?|one|two|three|four|five|six|twelve)\s*(?P<u>minutes?|mins?|hours?|hrs?|h|days?)\b", re.I)
_UNTIL_DAY = re.compile(r"\buntil\s+(?P<d>monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight)\b", re.I)
_EVERY = re.compile(r"\b(?:every\s+(?P<n>\d+)?\s*(?P<u>minutes?|mins?|hours?|hrs?|days?|weeks?|day|hour|week|morning|evening|night)"
                    r"|(?P<adv>hourly|daily|weekly|nightly))\b(?:\s+at\s+(?P<at>\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?", re.I)
_WORD_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "twelve": 12}


def _clock(m: re.Match, n: int, hint_pm: bool = False) -> Optional[str]:
    w = m.group(f"w{n}")
    if w:
        return "12:00" if w.lower() == "noon" else "00:00"
    h = m.group(f"h{n}")
    if h is None:
        return None
    hh, mm = int(h), int(m.group(f"m{n}") or 0)
    ap = (m.group(f"ap{n}") or "").lower().replace(".", "")
    if ap == "pm" and hh < 12:
        hh += 12
    elif ap == "am" and hh == 12:
        hh = 0
    elif not ap and hint_pm and hh < 12:
        hh += 12
    if hh > 24 or mm > 59:
        return None
    return f"{hh % 24:02d}:{mm:02d}"


def _next_day(now: dt.datetime, day: str) -> dt.date:
    order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    delta = (order.index(day) - now.weekday()) % 7
    return (now + dt.timedelta(days=delta)).date()


def find_times(text: str, now: Optional[dt.datetime] = None) -> Tuple[List[Context], List[Tuple[int, int]]]:
    """Window and schedule contexts in the text, and the spans they cover."""
    now = now or dt.datetime.now()
    low = text.lower()
    contexts: List[Context] = []
    spans: List[Tuple[int, int]] = []
    window: Dict[str, Any] = {}
    wspan: List[int] = []

    def mark(a: int, b: int) -> None:
        spans.append((a, b))
        wspan.extend([a, b])

    # named windows (policy)
    for name, w in sorted(WINDOWS.items(), key=lambda kv: -len(kv[0])):
        i = low.find(name)
        if i >= 0 and not any(a <= i < b for a, b in spans):
            window.update({k: v for k, v in w.items()})
            window["label"] = name
            window["named"] = True
            mark(i, i + len(name))
            if w.get("once") and not w.get("days"):        # "tonight": today; "this weekend": the next Saturday and Sunday
                window["date"] = now.date().isoformat()
            break
    # explicit clock ranges, e.g. 20:00-23:00, 18-23, from 8pm to 11pm
    for m in _RANGE.finditer(text):
        a, b = m.span()
        raw = m.group(0)
        if not re.search(r"\d", raw):
            continue
        # a bare "300 and 310" or "500-800" is not a time range: hours must be <= 24 and need a cue
        h1, h2 = m.group("h1"), m.group("h2")
        if h1 and h2 and (int(h1) > 24 or int(h2) > 24):
            continue
        cue = bool(re.search(r":|am|pm|h\b|noon|midnight", raw, re.I)) or bool(
            re.search(r"\b(?:from|between)\s*$", text[:a], re.I) and re.search(
                r"\b(?:tonight|today|tomorrow|evening|morning|night|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|weekday)\b",
                low)) or bool(re.search(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tonight|today|tomorrow)\s*,?\s*$", text[:a], re.I))
        if not cue:
            continue
        evening = bool(re.search(r"tonight|evening|night|pm", low))
        clock1 = m.group("m1") is not None or (h1 or "").startswith("0")      # "22:00", "02:00": a 24-hour clock
        clock2 = m.group("m2") is not None or (h2 or "").startswith("0")
        start = _clock(m, 1, hint_pm=not clock1 and evening and int(h1 or 0) < 12 and int(h1 or 0) >= 5)
        end = _clock(m, 2, hint_pm=not clock2 and evening and int(h2 or 0) <= 12 and (start or "00") >= "12")
        if start and end:
            window.update({"start": start, "end": end})
            mark(a, b)
            break
    # days
    for word, d in DAYS.items():
        for m in re.finditer(rf"\b{word}s?\b", low):
            if any(x <= m.start() < y for x, y in spans):
                continue
            plural = m.group(0).endswith("s") and not word.endswith("s")
            every = bool(re.search(r"\bevery\s*$", low[:m.start()])) or plural
            window.setdefault("days", [])
            if d not in window["days"]:
                window["days"].append(d)
            if not every:
                window["date"] = _next_day(now, d).isoformat()
                window["once"] = True
            mark(*m.span())
    for word, delta in (("today", 0), ("tomorrow", 1)):
        i = low.find(word)
        if i >= 0 and not any(a <= i < b for a, b in spans):
            window["date"] = (now.date() + dt.timedelta(days=delta)).isoformat()
            window["once"] = True
            mark(i, i + len(word))
    # a single time: "at 20:00", "from 8pm"
    if "start" not in window:
        m = _AT.search(text)
        if m and re.search(r"\d|noon|midnight", m.group(0)):
            t = _clock(m, 1, hint_pm=bool(re.search(r"tonight|evening", low)))
            if t:
                key = "end" if m.group(0).lower().startswith(("until", "till", "before")) else "start"
                window[key] = t
                mark(*m.span())
    # durations: "for 3 hours"
    m = _DUR.search(text)
    if m:
        n = m.group("n").lower()
        n = _WORD_N.get(n, None) if not re.match(r"\d", n) else float(n)
        unit = m.group("u").lower()
        secs = float(n or 1) * (60 if unit.startswith("m") else 86400 if unit.startswith("d") else 3600)
        window["duration_s"] = secs
        if "start" not in window:
            window["start"] = "now"
        mark(*m.span())
    m = _UNTIL_DAY.search(text)
    if m:
        d = m.group("d").lower()
        target = now.date() + dt.timedelta(days=1) if d == "tomorrow" else (now.date() if d == "tonight" else _next_day(now, DAYS[d]))
        window["until"] = target.isoformat()
        window.setdefault("start", "now")
        mark(*m.span())
    if window:
        named = window.pop("named", False)
        contexts.append(Context(kind="window", params=window, span=[min(wspan), max(wspan)] if wspan else None,
                                source=Source.POLICY if named and "start" in WINDOWS.get(window.get("label", ""), {}) else Source.STATED,
                                note=f"named window '{window['label']}' (operator policy)" if named else None))
    # recurrence: "every hour", "hourly", "daily at 08:00"
    m = _EVERY.search(text)
    if m:
        if m.group("adv"):
            adv = m.group("adv").lower()
            every, secs = {"hourly": ("1h", 3600), "daily": ("1d", 86400), "weekly": ("7d", 604800), "nightly": ("1d", 86400)}[adv]
        else:
            n = int(m.group("n") or 1)
            u = m.group("u").lower()
            unit_s = 60 if u.startswith("min") else 3600 if u.startswith(("hour", "hr")) else 604800 if u.startswith("week") else 86400
            every, secs = f"{n}{u[0] if not u.startswith('min') else 'm'}", n * unit_s
        params: Dict[str, Any] = {"every": every, "seconds": secs}
        if m.group("at"):
            params["at"] = m.group("at")
        contexts.append(Context(kind="schedule", params=params, span=list(m.span())))
        spans.append(m.span())
    return contexts, spans


def window_bounds(params: Dict[str, Any], now: Optional[dt.datetime] = None) -> Tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """The next concrete start and end of a window, for the scheduler."""
    now = now or dt.datetime.now()
    date = dt.date.fromisoformat(params["date"]) if params.get("date") else now.date()
    start_s, end_s = params.get("start"), params.get("end")
    if start_s in (None, "now"):
        start = now
    else:
        h, m = map(int, start_s.split(":"))
        start = dt.datetime.combine(date, dt.time(h, m))
        days = params.get("days")
        if days and not params.get("date"):
            order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            for k in range(8):
                cand = start + dt.timedelta(days=k)
                if order[cand.weekday()] in days and (cand > now or (end_s and _end_after(cand, end_s) > now)):
                    start = cand
                    break
        elif start + dt.timedelta(hours=12) < now and not params.get("date"):
            start += dt.timedelta(days=1)
    end: Optional[dt.datetime] = None
    if end_s and start_s not in (None, "now") and not params.get("date") and not params.get("days"):
        prev = start - dt.timedelta(days=1)          # a window over midnight that began yesterday
        if prev <= now < _end_after(prev, end_s):
            return prev, _end_after(prev, end_s)
    if params.get("duration_s"):
        end = start + dt.timedelta(seconds=float(params["duration_s"]))
    elif end_s:
        end = _end_after(start, end_s)
    elif params.get("until"):
        end = dt.datetime.combine(dt.date.fromisoformat(params["until"]), dt.time(23, 59))
    return start, end


def _end_after(start: dt.datetime, end_s: str) -> dt.datetime:
    h, m = map(int, end_s.split(":"))
    end = dt.datetime.combine(start.date(), dt.time(h % 24, m))
    if end <= start:
        end += dt.timedelta(days=1)
    return end
