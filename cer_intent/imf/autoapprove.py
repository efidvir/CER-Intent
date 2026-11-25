"""
Approving automatically, inside guardrails
==========================================
An intent whose check passed is applied without waiting for a person when every
guardrail below holds. When one does not, it waits for approval and says which.

  enabled       auto-approval is on (operator policy), or an active rule intent
                ("Auto-approve deliveries up to 300 Mbps") covers this intent
  kind          only kinds the policy lists; removals and rules always need a person
  channel/role  who asked, and through which interface
  confirmed     no value only the language model read; no open question
  check         the check passed: no rule holds it or asks for an approver, no conflict
  twin          the twin's NS-3 run passed for this load (a replay for another load does not count)
  size          a delivery up to the size limit; a change up to the size limit and
                at most the allowed increase
  headroom      after it, every hop on the path stays within the policy's share of
                what it carries in design rain
  radios now    no hop on the path runs below its clear-sky modulation right now
  window        inside the auto-approval windows, when the policy sets them
  rate          within the hourly limits, overall and per person
  reversible    every action has an undo

After an automatic approval the intent is watched (watch_s, default 10 min): if
it or any intent that was met before stops being met, it is rolled back.

Policy: data/imf_policy.json, key "auto_approve" (or CER_IMF_AUTO=1 to switch it on
with the defaults); an admin can change it at run time (PUT /api/v2/auto-approve).
Run-time changes are kept in data/imf_auto_policy.json (CER_IMF_AUTO_STATE) and
take precedence over the deployment's settings after a restart; delete that file
to go back to them.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cer_intent.imf.model import ACTING_KINDS, Expectation, IntentRecord, Kind, Source, State
from cer_intent.imf.radio import mcs_index
from cer_intent.imf.timex import window_bounds


@dataclass
class AutoPolicy:
    enabled: bool = False
    kinds: List[str] = field(default_factory=lambda: ["deliver", "change", "lifecycle", "optimise", "keep", "observe"])
    lifecycle_ops: List[str] = field(default_factory=lambda: ["suspend", "resume"])
    max_bandwidth_mbps: float = 200.0
    max_increase_pct: float = 100.0
    max_hop_load_pct: float = 80.0
    require_twin: bool = True
    require_clear_now: bool = True
    channels: List[str] = field(default_factory=lambda: ["text", "chat", "form", "tmf921", "3gpp", "mcp"])
    roles: List[str] = field(default_factory=lambda: ["operator", "approver", "admin"])
    per_hour: int = 10
    per_user_hour: int = 5
    watch_s: int = 600
    windows: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]], env: bool = True) -> "AutoPolicy":
        """The deployment's settings; CER_IMF_AUTO=1 switches it on (only here, at load)."""
        p = cls()
        for k, v in (data or {}).items():
            if hasattr(p, k):
                setattr(p, k, v)
        if env and os.getenv("CER_IMF_AUTO", "").lower() in ("1", "true", "on"):
            p.enabled = True
        return p

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


KINDS = ("deliver", "change", "lifecycle", "optimise", "keep", "observe")
NUMBERS = {"max_bandwidth_mbps": (0, 1e6), "max_increase_pct": (0, 1e4), "max_hop_load_pct": (1, 100),
           "per_hour": (0, 10000), "per_user_hour": (0, 10000), "watch_s": (0, 7 * 86400)}


def validate(changes: Dict[str, Any], roles: Tuple[str, ...]) -> Dict[str, Any]:
    """Settings an admin sends, checked and normalised; ValueError says what is wrong."""
    known = AutoPolicy().to_dict()
    unknown = [k for k in changes if k not in known]
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(unknown)}")
    out: Dict[str, Any] = {}
    for k, v in changes.items():
        if k in ("enabled", "require_twin", "require_clear_now"):
            if not isinstance(v, bool):
                raise ValueError(f"{k} is true or false")
            out[k] = v
        elif k in NUMBERS:
            lo, hi = NUMBERS[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ValueError(f"{k} is a number from {lo:g} to {hi:g}")
            out[k] = int(v) if k in ("per_hour", "per_user_hour", "watch_s") else float(v)
        elif k in ("kinds", "lifecycle_ops", "channels", "roles"):
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ValueError(f"{k} is a list of names")
            allowed = {"kinds": KINDS, "lifecycle_ops": ("suspend", "resume", "delete"), "roles": roles}.get(k)
            bad = [x for x in v if allowed and x not in allowed]
            if bad:
                raise ValueError(f"{k}: {', '.join(bad)} not one of {', '.join(allowed)}")
            out[k] = list(v)
        elif k == "windows":
            if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
                raise ValueError("windows is a list of windows")
            out[k] = v
    return out


def state_path() -> Path:
    from cer_intent.imf.store import ROOT
    return Path(os.getenv("CER_IMF_AUTO_STATE") or str(ROOT / "data" / "imf_auto_policy.json"))


def load_state(path: Optional[Path]) -> Dict[str, Any]:
    """Run-time changes an admin made, kept across restarts."""
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text())
        return data.get("changes", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: Optional[Path], changes: Dict[str, Any], who: str) -> None:
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = load_state(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"changes": {**prev, **changes}, "by": who, "at": time.time()}, indent=1))
    tmp.replace(path)


def _row(gid: str, label: str, ok: bool, why: str) -> Dict[str, Any]:
    return {"id": gid, "label": label, "ok": bool(ok), "why": why}


def active_rules(records: List[IntentRecord]) -> List[Tuple[IntentRecord, Expectation]]:
    return [(r, e) for r in records if r.state == State.ACTIVE for e in r.expectations
            if e.kind == Kind.GUARD and e.action.get("rule") == "auto_approve"]


def _rule_covers(rule: Expectation, rec: IntentRecord, net, now: dt.datetime) -> Optional[str]:
    """None when the rule covers this intent, else why not."""
    kinds = rule.action.get("kinds") or ["deliver", "change"]
    for e in rec.expectations:
        if e.kind in ACTING_KINDS and e.kind.value not in kinds:
            return f"the rule covers {', '.join(kinds)}"
    w = rule.context("window")
    if w is not None:
        s, end = window_bounds(w.params, now)
        if s and not (s <= now < (end or s)):
            return "outside the rule's window"
    scope = set(rule.object.ids)
    if scope:
        from cer_intent.imf.check import in_scope, touches
        if not in_scope(scope, touches(rec.expectations, net)):
            return f"the rule covers {', '.join(sorted(scope))}"
    return None


def evaluate(rec: IntentRecord, net, policy: AutoPolicy, records: List[IntentRecord], audit: List[Dict[str, Any]],
             now: Optional[dt.datetime] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    """Whether this checked intent can be applied without a person, and each guardrail with why."""
    now = now or dt.datetime.now()
    rows: List[Dict[str, Any]] = []
    rules = [(r, e) for r, e in active_rules(records) if r.id != rec.id]
    covering = [(r, e) for r, e in rules if _rule_covers(e, rec, net, now) is None]
    rule = covering[0] if covering else None
    limit = policy.max_bandwidth_mbps
    if rule is not None and rule[1].value("bandwidth") is not None:
        limit = float(rule[1].value("bandwidth"))
    on = policy.enabled or rule is not None
    rows.append(_row("enabled", "Auto-approval on", on,
                     f"by the rule {rule[0].name}" if rule else ("by the operator's policy" if policy.enabled else
                                                                  "auto-approval is off and no rule covers this intent")))
    acting = [e for e in rec.expectations if e.kind in ACTING_KINDS or e.kind in (Kind.KEEP, Kind.OBSERVE, Kind.GUARD)]
    kinds = (rule[1].action.get("kinds") if rule else None) or policy.kinds
    bad = [e for e in acting if e.kind.value not in kinds or e.kind == Kind.GUARD or
           (e.kind == Kind.LIFECYCLE and e.action.get("op") not in policy.lifecycle_ops)]
    rows.append(_row("kind", "Kind allowed", not bad,
                     "every expectation is of a kind auto-approval may apply" if not bad else
                     f"{bad[0].kind.value}{' ' + str(bad[0].action.get('op')) if bad[0].action.get('op') else ''} needs a person"))
    rows.append(_row("who", "Who and how", rec.channel in policy.channels and rec.role in policy.roles,
                     f"{rec.owner} ({rec.role}) through {rec.channel}"))
    model_only = [t for e in rec.expectations for t in e.targets if t.source == Source.MODEL]
    rows.append(_row("confirmed", "Every value confirmed", not model_only and not rec.questions,
                     "no value only the language model read" if not model_only else f"{model_only[0].text()} is the model's reading"))
    check = rec.check or {}
    holds = [r for r in check.get("rules", []) if r.get("effect") in ("hold", "approval")]
    conflicts = check.get("conflicts", [])
    rows.append(_row("check", "Check passed", check.get("verdict") == "pass" and not holds and not conflicts,
                     "no rule or conflict stands in the way" if not holds and not conflicts else
                     (holds[0]["why"] if holds else conflicts[0]["why"])))
    changes_network = any((e.kind in (Kind.DELIVER, Kind.CHANGE) and e.target("bandwidth") is not None) or
                          (e.kind == Kind.LIFECYCLE and e.action.get("op") == "resume") for e in rec.expectations)
    twin = check.get("twin") or {}
    if policy.require_twin and changes_network:
        rows.append(_row("twin", "Twin's NS-3 run passed", bool(twin.get("ran")) and twin.get("verdict") == "pass",
                         "passed on the twin" if twin.get("ran") and twin.get("verdict") == "pass" else
                         (twin.get("why") or "the twin did not run")))
    size_why, size_ok = "within the size limit", True
    for e in rec.expectations:
        bw = e.value("bandwidth")
        if e.kind == Kind.DELIVER and bw is not None and float(bw) > limit:
            size_ok, size_why = False, f"{float(bw):g} Mbps is more than the {limit:g} Mbps auto-approval limit"
        if e.kind == Kind.CHANGE and bw is not None:
            before = [v.get("bandwidth") for v in (e.action.get("before") or {}).values() if v.get("bandwidth")]
            if float(bw) > limit:
                size_ok, size_why = False, f"{float(bw):g} Mbps is more than the {limit:g} Mbps auto-approval limit"
            elif before and float(bw) > float(before[0]) * (1 + policy.max_increase_pct / 100.0):
                size_ok, size_why = False, f"{float(before[0]):g} → {float(bw):g} Mbps is more than a {policy.max_increase_pct:g} % increase"
    rows.append(_row("size", "Size", size_ok, size_why))
    head_ok, head_why, fading = True, "every hop keeps its headroom", []
    for sc in check.get("screens", []):
        for h in sc.get("hops", []) or []:
            if not isinstance(h, dict) or "existing_mbps" not in h:
                continue
            cap = float(h.get("rain_capacity_mbps") or 0)
            after = float(h.get("existing_mbps", 0)) + float(h.get("slice_mbps", 0))
            if cap and after > cap * policy.max_hop_load_pct / 100.0 + 1e-9:
                head_ok = False
                head_why = (f"{h['hop']} would carry {after:g} of {cap:g} Mbps in design rain, more than "
                            f"{policy.max_hop_load_pct:g} %")
            if h.get("fading_now"):
                fading.append(f"{h['hop']} runs {h.get('live_mcs')} now")
    if changes_network:
        rows.append(_row("headroom", "Headroom kept", head_ok, head_why))
    if policy.require_clear_now and changes_network:
        rows.append(_row("radios", "Radios at full rate now", not fading,
                         "every hop on the path runs at its clear-sky modulation" if not fading else "; ".join(fading)))
    if policy.windows:
        inside = False
        for w in policy.windows:
            s, end = window_bounds(w, now)
            if s and s <= now < (end or s):
                inside = True
        rows.append(_row("window", "Inside the auto-approval window", inside, "inside" if inside else "outside the window"))
    hour_ago = time.time() - 3600
    recent = [a for a in audit if a.get("event") == "auto-approved" and a.get("t", 0) >= hour_ago]
    mine = [a for a in recent if a.get("owner") == rec.owner]
    rows.append(_row("rate", "Rate", len(recent) < policy.per_hour and len(mine) < policy.per_user_hour,
                     f"{len(recent)} this hour (limit {policy.per_hour}), {len(mine)} by {rec.owner} (limit {policy.per_user_hour})"))
    irreversible = [e for e in rec.expectations if e.kind == Kind.LIFECYCLE and e.action.get("op") == "delete"]
    rows.append(_row("reversible", "Reversible", not irreversible,
                     "every action can be undone" if not irreversible else "a removal cannot be undone automatically"))
    return all(r["ok"] for r in rows), rows


def snapshot_fulfilment(records: List[IntentRecord]) -> Dict[str, bool]:
    """Which live intents were met, from their latest report."""
    out = {}
    for r in records:
        if r.state in (State.ACTIVE, State.DEGRADED) and r.reports:
            out[r.id] = all(x.get("status") != "NOT_FULFILLED" for x in r.reports[-1].get("expectations", {}).values())
    return out


def mcs_drop(live: Optional[str], clear: Optional[str]) -> bool:
    """The radio carries less now than in clear sky (a lower MCS that still carries the cap is no drop)."""
    from cer_intent.imf.radio import capacity_mbps
    return bool(live and clear and (mcs_index(live) or 0) < (mcs_index(clear) or 0)
                and capacity_mbps(live) < capacity_mbps(clear))
