"""
The intent record
=================
Every request, whatever channel it arrives on (text, form, catalogue template,
TMF921, 3GPP TS 28.312, an OpenSlice order or an agent over MCP), becomes one
IntentRecord: a set of expectations.

An expectation says
  * what it applies to          object      a service, slice, radio hop, radio, site, ...
  * the values it asks for      targets     metric, condition, value, unit
  * when and where it holds     contexts    time windows, schedules, weather, conditions
  * how strict it is            strictness  must, prefer, best effort; and a priority

That is the structure of 3GPP TS 28.312 (IntentExpectation with expectationObject,
expectationTargets and expectationContexts) and of the TM Forum intent common
model, so TMF921 and 28.312 requests map onto it directly (cer_intent/imf/standards.py).

Every value records where it came from: stated by the operator, resolved
against the network, taken from a service profile or an operator policy,
agreed in a negotiation, or read by the language model. The studio shows it.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Kind(str, Enum):
    DELIVER = "deliver"        # create connectivity: a slice, a VPN, a service
    CHANGE = "change"          # modify something that exists
    LIFECYCLE = "lifecycle"    # suspend, resume, remove
    KEEP = "keep"              # a standing objective: keep a KPI within bounds
    OPTIMISE = "optimise"      # minimise or maximise something under constraints
    GUARD = "guard"            # a rule every other intent must respect
    OBSERVE = "observe"        # report or alert
    EXPLORE = "explore"        # what-if, headroom: answered on the twin, nothing changes
    ASK = "ask"                # a question about the network or a decision


KIND_LABEL = {
    Kind.DELIVER: "deliver", Kind.CHANGE: "change", Kind.LIFECYCLE: "lifecycle", Kind.KEEP: "keep",
    Kind.OPTIMISE: "optimise", Kind.GUARD: "guard", Kind.OBSERVE: "observe", Kind.EXPLORE: "explore", Kind.ASK: "ask",
}
ACTING_KINDS = {Kind.DELIVER, Kind.CHANGE, Kind.LIFECYCLE, Kind.OPTIMISE}      # change the network when approved
STANDING_KINDS = {Kind.KEEP, Kind.GUARD, Kind.OBSERVE}                          # stay active and are watched


class Source(str, Enum):
    STATED = "stated"          # the operator said it
    RESOLVED = "resolved"      # matched against the network (a name, a path, a service)
    PROFILE = "profile"        # from a service profile (gold, URLLC, ...)
    POLICY = "policy"          # an operator default or rule
    NEGOTIATED = "negotiated"  # an alternative the operator accepted
    MODEL = "model"            # read by the language model and not confirmed by the rules
    ANSWER = "answer"          # the operator's answer to a question


class Strictness(str, Enum):
    MUST = "must"
    PREFER = "prefer"
    BEST_EFFORT = "best_effort"


class State(str, Enum):
    DRAFT = "draft"                    # understood, not checked
    CLARIFYING = "clarifying"          # waiting for answers
    CHECKED = "checked"                # feasibility known, waiting for approval
    NEGOTIATING = "negotiating"        # infeasible as asked; alternatives offered
    HELD = "held"                      # blocked by a rule or a failed check
    SCHEDULED = "scheduled"            # approved, acts at a later time
    ACTIVE = "active"                  # realized or standing, and being watched
    DEGRADED = "degraded"              # active, an expectation not met
    SUSPENDED = "suspended"
    ANSWERED = "answered"              # a question or a what-if: done
    WITHDRAWN = "withdrawn"
    COMPLETED = "completed"            # a time-bound intent that ended
    FAILED = "failed"
    REJECTED = "rejected"              # out of scope


METRICS: Dict[str, Dict[str, Any]] = {
    # metric: unit, kind of value, the direction that is "better"
    "bandwidth": {"unit": "Mbps", "better": "higher"},
    "latency": {"unit": "ms", "better": "lower"},
    "jitter": {"unit": "ms", "better": "lower"},
    "loss": {"unit": "%", "better": "lower"},
    "availability": {"unit": "%", "better": "higher"},
    "modulation_floor": {"unit": "MCS", "better": "higher"},
    "headroom": {"unit": "%", "better": "higher"},
    "throughput": {"unit": "Mbps", "better": "higher"},
    "capacity": {"unit": "Mbps", "better": "higher"},
    "energy": {"unit": "W", "better": "lower"},
    "tx_power": {"unit": "dBm", "better": "lower"},
    "priority": {"unit": None, "better": "higher"},
    "vlan": {"unit": None},
    "technology": {"unit": None},
    "lowest_modulation": {"unit": "MCS", "better": "higher"},
    "utilisation": {"unit": "%", "better": "lower"},
}
OPS = ("ge", "le", "gt", "lt", "eq", "between", "minimize", "maximize", "set", "scale", "add")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


class Target(BaseModel):
    metric: str
    op: str = "eq"
    value: Any = None
    unit: Optional[str] = None
    source: Source = Source.STATED
    span: Optional[List[int]] = None
    note: Optional[str] = None

    def text(self) -> str:
        sym = {"ge": "≥", "le": "≤", "gt": ">", "lt": "<", "eq": "=", "set": "→", "add": "+"}.get(self.op, self.op)
        if self.op == "between" and isinstance(self.value, (list, tuple)):
            return f"{self.metric} {self.value[0]}–{self.value[1]} {self.unit or ''}".strip()
        if self.op == "scale":
            return f"{self.metric} ×{self.value:g}"
        if self.op in ("minimize", "maximize"):
            return f"{self.op} {self.metric}"
        v = self.value if not isinstance(self.value, float) else f"{self.value:g}"
        return f"{self.metric} {sym} {v}{(' ' + self.unit) if self.unit and self.unit != 'MCS' else ''}".strip()


class Context(BaseModel):
    kind: str                      # window, schedule, weather, condition, region
    params: Dict[str, Any] = Field(default_factory=dict)
    source: Source = Source.STATED
    span: Optional[List[int]] = None
    note: Optional[str] = None

    def text(self) -> str:
        p = self.params
        if self.kind == "window":
            days = p.get("days")
            if p.get("duration_s") and p.get("start") in (None, "now"):
                h = float(p["duration_s"]) / 3600.0
                return f"now · for {h:g} h" if h >= 1 else f"now · for {float(p['duration_s']) / 60:g} min"
            if p.get("until") and p.get("start") in (None, "now"):
                return f"now · until {p['until']}"
            d = f"{p['label']} · " if p.get("label") else ""
            when = f"{p.get('start', '')}–{p.get('end', '')}".strip("–")
            return f"{d}{when}{(' · ' + ','.join(days)) if days and not p.get('label') else ''}".strip(" ·")
        if self.kind == "schedule":
            return f"every {p.get('every')}" + (f" at {p['at']}" if p.get("at") else "")
        if self.kind == "weather":
            return f"rain {p.get('rain_mmh')} mm/h" if p.get("rain_mmh") is not None else "in rain"
        if self.kind == "condition":
            sym = {"ge": "≥", "le": "≤", "gt": ">", "lt": "<", "eq": "="}.get(p.get("op"), p.get("op") or "")
            v = p.get("value")
            v = f"{v:g}" if isinstance(v, float) else v
            unit = "" if str(v).upper().startswith("MCS") else (p.get("unit") or "")
            return f"when {p.get('metric')} {sym} {v} {unit}".strip()
        return f"{self.kind} {p}"


class Endpoint(BaseModel):
    node: Optional[str] = None
    mention: Optional[str] = None
    port: Optional[str] = None
    vlan: Optional[int] = None
    ip: Optional[str] = None
    source: Source = Source.STATED
    span: Optional[List[int]] = None


class ObjectRef(BaseModel):
    type: str = "network"          # slice, service, hop, radio, site, link, intent, traffic_class, network
    mentions: List[str] = Field(default_factory=list)
    ids: List[str] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)
    selector: Dict[str, Any] = Field(default_factory=dict)    # {"all": True, "except": [...], "name_contains": "stadium"}
    source: Source = Source.STATED
    span: Optional[List[int]] = None

    def label(self) -> str:
        if self.endpoints:
            return " ↔ ".join(e.node or e.mention or "?" for e in self.endpoints)
        if self.ids:
            return ", ".join(self.ids)
        if self.selector.get("all"):
            ex = self.selector.get("except") or []
            return f"all {self.type}s" + (f" except {', '.join(ex)}" if ex else "")
        if self.mentions:
            return ", ".join(self.mentions)
        return self.type


class Expectation(BaseModel):
    id: str = Field(default_factory=lambda: new_id("e-"))
    kind: Kind
    verb: Optional[str] = None
    object: ObjectRef = Field(default_factory=ObjectRef)
    targets: List[Target] = Field(default_factory=list)
    contexts: List[Context] = Field(default_factory=list)
    strictness: Strictness = Strictness.MUST
    priority: Optional[int] = None
    profile: Optional[str] = None
    action: Dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = None
    text: Optional[str] = None
    span: Optional[List[int]] = None
    vague: Optional[str] = None             # a vague word the operator used ("faster")

    def target(self, metric: str) -> Optional[Target]:
        return next((t for t in self.targets if t.metric == metric), None)

    def value(self, metric: str, default: Any = None) -> Any:
        t = self.target(metric)
        return t.value if t is not None and t.value is not None else default

    def set_target(self, metric: str, op: str, value: Any, unit: Optional[str] = None,
                   source: Source = Source.STATED, note: Optional[str] = None, span: Optional[List[int]] = None) -> Target:
        t = self.target(metric)
        if t is None:
            t = Target(metric=metric, op=op, value=value, unit=unit, source=source, note=note, span=span)
            self.targets.append(t)
        else:
            t.op, t.value, t.unit, t.source, t.note = op, value, unit or t.unit, source, note
            if span is not None:
                t.span = span
        return t

    def context(self, kind: str) -> Optional[Context]:
        return next((c for c in self.contexts if c.kind == kind), None)

    def summary(self) -> str:
        bits = [KIND_LABEL[self.kind]]
        if self.action.get("op"):
            bits.append(str(self.action["op"]))
        bits.append(self.object.label())
        bits += [t.text() for t in self.targets]
        bits += [c.text() for c in self.contexts]
        return " · ".join(b for b in bits if b)


class Choice(BaseModel):
    label: str
    value: Any


class Question(BaseModel):
    id: str = Field(default_factory=lambda: new_id("q-"))
    expectation: Optional[str] = None
    field: str                         # endpoint, bandwidth, object, metric, addresses, ...
    text: str
    choices: List[Choice] = Field(default_factory=list)
    free: bool = True                  # a typed answer is accepted
    reason: str = "missing"            # missing, ambiguous, vague, confirm
    default: Any = None


class IntentRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("int-"))
    name: Optional[str] = None
    text: Optional[str] = None
    channel: str = "text"               # text, form, tmf921, 3gpp, openslice, mcp, v1, template
    owner: str = "operator"
    role: str = "operator"
    session: Optional[str] = None
    expectations: List[Expectation] = Field(default_factory=list)
    state: State = State.DRAFT
    out_of_scope: Optional[str] = None
    questions: List[Question] = Field(default_factory=list)
    readings: Dict[str, Any] = Field(default_factory=dict)      # how it was read: rules, model, agreement
    check: Optional[Dict[str, Any]] = None                      # feasibility, conflicts, rules, availability
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    answer: Optional[Dict[str, Any]] = None                     # for ask / explore
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    reports: List[Dict[str, Any]] = Field(default_factory=list)
    approvals: List[Dict[str, Any]] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    links: Dict[str, Any] = Field(default_factory=dict)         # slice ids, legacy intent id, schedule ids
    answers: Dict[str, Any] = Field(default_factory=dict)       # "<expectation id>:<field>" -> the operator's answer
    base: List[Dict[str, Any]] = Field(default_factory=list)    # the expectations as read, before matching
    risk: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def touch(self, event: str, **detail: Any) -> None:
        self.updated_at = time.time()
        self.history.append({"t": self.updated_at, "event": event, **detail})

    def kinds(self) -> List[str]:
        return [e.kind.value for e in self.expectations]

    def summary(self) -> str:
        return " | ".join(e.summary() for e in self.expectations) or (self.out_of_scope or "")

    def acts(self) -> bool:
        return any(e.kind in ACTING_KINDS for e in self.expectations)

    def standing(self) -> bool:
        return any(e.kind in STANDING_KINDS for e in self.expectations)


# ── what a reader (the rules or a language model) returns ────────────────────

class Reading(BaseModel):
    """One reading of an operator's words: the expectations, before matching to the network."""
    expectations: List[Expectation] = Field(default_factory=list)
    out_of_scope: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
    reader: str = "rules"


def reading_schema() -> Dict[str, Any]:
    """JSON schema a language model is held to."""
    return Reading.model_json_schema()
