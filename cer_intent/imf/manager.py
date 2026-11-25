"""
The intent manager
==================
One pipeline for every way an operator expresses an intent:

  capture      text (studio, chat, MCP), a form, TMF921 v5, 3GPP TS 28.312, v1
  understand   the rule reader, and a language model when configured (cross-checked)
  match        names -> network objects; profile and policy defaults; relative -> absolute
  clarify      questions with choices; answers are kept and re-applied
  check        guard rules, conflicts with other intents, the analytic radio
               screen and the twin's NS-3 pre-flight
  negotiate    alternatives when the network cannot do what was asked
  approve/act  roles and approvals; actions through the slice controller and
               TeraFlowSDN; windows scheduled and reverted; rollback on failure
  keep/report  standing objectives watched; 28.312 / TMF921 reports

The manager keeps no state of its own beyond the intent store: the network is
read fresh (NetworkModel) for each step.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cer_intent.imf import clarify
from cer_intent.imf.actions import Actuator, radio_state
from cer_intent.imf.answers import answer_ask, answer_explore
from cer_intent.imf.check import TwinClient, active_guards, check_record
from cer_intent.imf.llm import Provider, merge, provider_from_env
from cer_intent.imf.match import Matcher, Policy
from cer_intent.imf.model import (ACTING_KINDS, STANDING_KINDS, Expectation, IntentRecord, Kind, Question,
                                  Source, State)
from cer_intent.imf.negotiate import alternatives, apply_alternative
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.radio import capacity_mbps, mcs_index
from cer_intent.imf.reader import RuleReader
from cer_intent.imf.store import IntentStore
from cer_intent.imf.timex import find_times, window_bounds

logger = logging.getLogger("CER-Intent.imf")

OPEN_STATES = (State.DRAFT, State.CLARIFYING, State.CHECKED, State.NEGOTIATING, State.HELD)
LIVE_STATES = (State.ACTIVE, State.DEGRADED, State.SCHEDULED, State.SUSPENDED)
YES = re.compile(r"^\s*(?:yes|yep|yeah|ok(?:ay)?|sure|approve[ds]?|go(?:\s+ahead)?|apply(?:\s+it)?|do\s+it|confirm(?:ed)?|proceed|ship\s+it)\b[\s.!]*$", re.I)
NO = re.compile(r"^\s*(?:no|nope|cancel|stop|abort|forget\s+it|never\s*mind|discard|drop\s+it|withdraw(?:\s+it)?)\b[\s.!]*$", re.I)
OPTION = re.compile(r"^\s*(?:option|alternative|choice|take|go\s+with|use)?\s*(?:#|no\.?\s*)?(?P<n>\d|one|two|three|four|five|first|second|third|fourth|fifth|last)\b(?:\s+(?:one|option))?[\s.!]*(?P<go>(?:and\s+)?(?:apply|approve|go|do\s+it))?[\s.!]*$", re.I)
REFINE = re.compile(r"^\s*(?:make\s+it|change\s+it\s+to|instead|actually|rather|no,?\s+make\s+it|set\s+it\s+to|but|and|only|also\s+make\s+it|with)\b", re.I)
WORDS = {"one": 1, "first": 1, "two": 2, "second": 2, "three": 3, "third": 3, "four": 4, "fourth": 4, "five": 5, "fifth": 5}


class ImfError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class IntentManager:
    def __init__(self, store: Optional[IntentStore] = None, network: Optional[Callable[[], NetworkModel]] = None,
                 nsc: Optional[Callable[[], Any]] = None, twin: Optional[TwinClient] = None, llm: Optional[Provider] = None,
                 policy: Optional[Policy] = None, clock: Optional[Callable[[], dt.datetime]] = None,
                 legacy: Optional[Callable[[str], Dict[str, Any]]] = None, use_llm_env: bool = True):
        self.store = store or IntentStore()
        self._network = network or NetworkModel.demo
        self.actuator = Actuator(nsc or _default_nsc)
        self.actuator._suspended_lookup = self._suspended_request
        self.twin = twin
        self.llm = llm if llm is not None else (provider_from_env() if use_llm_env else None)
        self.policy = policy or Policy.load()
        self.clock = clock or dt.datetime.now
        self.legacy = legacy
        self.lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.events: List[Dict[str, Any]] = []

    # ── the network, with the store's intents ────────────────────────────────
    def network(self) -> NetworkModel:
        net = self._network()
        try:
            from cer_intent.intent_parser import register_network_names
            register_network_names(net.nodes)
        except Exception:  # pylint: disable=broad-except
            pass
        net.intents = []
        for r in self.store.all():
            if r.state in (State.WITHDRAWN, State.REJECTED):
                continue
            keeps: Dict[str, List[float]] = {}
            if r.state in (State.ACTIVE, State.DEGRADED):
                for e in r.expectations:
                    if e.kind == Kind.KEEP and e.value("bandwidth") is not None:
                        for sid in e.object.ids:
                            keeps.setdefault(sid, []).append(float(e.value("bandwidth")))
            net.intents.append({"id": r.id, "name": r.name, "text": r.text, "slices": r.links.get("slices", []),
                                "priority": max([e.priority for e in r.expectations if e.priority] or [5]),
                                "state": r.state.value, "keeps": keeps})
        return net

    # ── capture ──────────────────────────────────────────────────────────────
    def submit(self, text: Optional[str] = None, record: Optional[IntentRecord] = None, channel: str = "text",
               who: str = "operator", role: str = "operator", session: Optional[str] = None,
               check: bool = True, approve: bool = False) -> IntentRecord:
        with self.lock:
            net = self.network()
            if record is None:
                if not text or not text.strip():
                    raise ImfError("empty intent")
                record = IntentRecord(text=text.strip(), channel=channel)
                self._understand(record, net)
            else:
                record.channel = record.channel or channel
                record.base = [e.model_dump() for e in record.expectations]
                record.readings = {"reader": record.channel, "rules": None, "model": None}
            record.owner, record.role, record.session = who, role, session
            if not record.name:
                record.name = self._name(record)
                record.readings["auto_name"] = True
            record.touch("submitted", who=who, role=role, channel=record.channel)
            self.store.audit("submitted", record.id, who, role, channel=record.channel, text=record.text)
            self._evaluate(record, net, run_check=check)
            self.store.put(record)
            if approve and record.state == State.CHECKED:
                return self.approve(record.id, who=who, role=role)
            return record

    def _understand(self, rec: IntentRecord, net: NetworkModel) -> None:
        now = self.clock()
        rules = RuleReader(net.names(), now).read(rec.text or "")
        model = None
        error = None
        if self.llm is not None:
            try:
                model = self.llm.read(rec.text or "", net.names())
            except Exception as exc:  # pylint: disable=broad-except
                error = f"{self.llm.name}: {exc.__class__.__name__}"
        reading, info = merge(rules, model)
        if error:
            info["model_error"] = error
        legacy = self._legacy_feature(rec.text or "", reading)
        if legacy is not None:
            reading.expectations = [legacy]
            reading.out_of_scope = None
            info["reader"] = "rules (v1 feature)"
        rec.out_of_scope = reading.out_of_scope
        rec.readings = info
        rec.readings["notes"] = reading.notes
        rec.base = [e.model_dump() for e in reading.expectations]

    def _legacy_feature(self, text: str, reading) -> Optional[Expectation]:
        """Device features the v1 pipeline realizes (timing, MACsec, TSN, beams, ...)."""
        unread = not reading.expectations or all(e.kind == Kind.ASK and e.action.get("type") == "unknown" for e in reading.expectations)
        if not unread and not reading.out_of_scope:
            return None
        try:
            from cer_intent.intent_parser import RuleParser, IntentParser
            from cer_intent.imf.standards import FEATURE_TYPES, from_legacy
            data = RuleParser().parse_text(text)
            if data.get("intent_type") not in FEATURE_TYPES:
                return None
            intent = IntentParser.__new__(IntentParser)._build_intent(data, raw_input=text, source="imf")
            return from_legacy(intent)
        except Exception:  # pylint: disable=broad-except
            return None

    def _name(self, rec: IntentRecord) -> str:
        base = next((d.get("name") for d in rec.base if d.get("name")), None)
        if not base:
            words = re.findall(r"[a-z0-9]+", (rec.text or "intent").lower())[:5]
            base = "-".join(words) or "intent"
        name, k = base, 2
        taken = {r.name for r in self.store.all()}
        while name in taken:
            name, k = f"{base}-{k}", k + 1
        return name

    # ── match, clarify, check, negotiate, answer ─────────────────────────────
    def _evaluate(self, rec: IntentRecord, net: NetworkModel, run_check: bool = True, use_twin: bool = True) -> None:
        net.reserved = {}
        for other in self.store.all(states=[*OPEN_STATES, State.SCHEDULED]):
            if other.id == rec.id:
                continue
            for e in other.expectations:
                if e.kind == Kind.DELIVER and e.name and e.name not in net.slices:
                    net.reserved[e.name] = {"intent": other.name or other.id, "nodes": [x.node for x in e.object.endpoints if x.node],
                                            "vlans": sorted({int(x.vlan) for x in e.object.endpoints if x.vlan is not None})}
        exps = [Expectation.model_validate(d) for d in rec.base]
        rec.expectations = exps
        clarify.apply(rec, exps, net, "pre")
        questions = Matcher(net, self.policy).match(rec)
        clarify.apply(rec, exps, net, "post")
        for alt in rec.links.get("accepted", []):
            apply_alternative(rec, alt, stable=True)
        questions += clarify.confirm_model_values(rec.expectations)
        unknown = [e for e in rec.expectations if e.kind == Kind.ASK and e.action.get("type") == "unknown"]
        rec.questions = clarify.open_questions(rec, questions)
        if rec.out_of_scope:
            rec.state = State.REJECTED
            rec.answer = {"text": f"That is outside what CER-Intent manages here ({rec.out_of_scope}). "
                                  "I handle slices, radio hops, their objectives, rules, reports and what-ifs.", "insight": "none"}
            rec.touch("rejected", reason=rec.out_of_scope)
            return
        if unknown and len(unknown) == len(rec.expectations):
            rec.state = State.CLARIFYING
            rec.questions = [Question(field="rephrase", reason="unknown", free=True,
                                      text="I could not read that as a request about this network. Can you say what should happen, "
                                           "to which slice, radio or sites?")]
            rec.touch("not understood")
            return
        named = next((e.name for e in rec.expectations if e.kind == Kind.DELIVER and e.name), None)
        if named and rec.readings.get("auto_name") and named != rec.name and \
                named not in {r.name for r in self.store.all() if r.id != rec.id}:
            rec.name = named
        if rec.questions:
            rec.state = State.CLARIFYING
            rec.touch("questions", questions=[q.text for q in rec.questions])
            return
        answers = []
        for e in rec.expectations:
            if e.kind == Kind.EXPLORE:
                answers.append(answer_explore(e, net, self.twin if use_twin else None))
            elif e.kind == Kind.ASK and e.action.get("type") != "unknown":
                answers.append(answer_ask(e, net, self.store.all()))
        if answers:
            rec.answer = answers[0] if len(answers) == 1 else {"text": " ".join(a.get("text", "") for a in answers), "parts": answers}
        nothing = [e.action["nothing"] for e in rec.expectations if e.action.get("nothing")]
        if not any(e.kind in ACTING_KINDS or e.kind in STANDING_KINDS for e in rec.expectations) or (
                nothing and len(nothing) == len([e for e in rec.expectations if e.kind in ACTING_KINDS])
                and not any(e.kind in STANDING_KINDS for e in rec.expectations)):
            rec.state = State.ANSWERED
            if nothing and not answers:
                rec.answer = {"text": "Nothing to do: " + "; ".join(nothing) + ".", "insight": "state"}
            rec.touch("answered")
            return
        if not run_check:
            rec.state = State.DRAFT
            return
        others = self.store.all()
        result = check_record(rec, net, active_guards(others), others, self.twin if use_twin else None, self.clock())
        rec.check = result
        rec.alternatives = []
        if result["verdict"] == "held":
            rec.state = State.HELD
        elif result["verdict"] == "fail":
            rec.alternatives = alternatives(rec, net, result, self.twin if use_twin else None)
            rec.state = State.NEGOTIATING if rec.alternatives else State.HELD
        else:
            rec.state = State.CHECKED
        rec.touch("checked", verdict=result["verdict"], twin=(result.get("twin") or {}).get("verdict"))

    def answer(self, rid: str, question: str, value: Any, who: str = "operator", role: str = "operator") -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            q = next((x for x in rec.questions if x.id == question or clarify.key(x) == question or x.field == question), None)
            if q is None:
                raise ImfError("no such open question", 404)
            if q.field == "rephrase":
                rec.text = str(value)
                net = self.network()
                rec.answers = {}
                self._understand(rec, net)
                self._evaluate(rec, net)
                self.store.put(rec)
                return rec
            net = self.network()
            ok, parsed, problem = clarify.parse(q.field if not q.field.startswith("confirm:") else "confirm", value, net)
            if not ok:
                raise ImfError(problem or "could not use that answer")
            rec.answers[clarify.key(q)] = parsed
            rec.touch("answered", question=q.text, value=parsed, who=who)
            self.store.audit("answer", rec.id, who, role, question=q.field, value=parsed)
            self._evaluate(rec, net)
            self.store.put(rec)
            return rec

    def accept(self, rid: str, alt: Any, who: str = "operator", role: str = "operator", approve: bool = False) -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            chosen = None
            for a in rec.alternatives:
                if str(alt) in (a["id"], str(a["n"])) or alt == a["n"]:
                    chosen = a
            if chosen is None:
                raise ImfError("no such alternative", 404)
            rec.links.setdefault("accepted", []).append(chosen)
            rec.touch("alternative accepted", label=chosen["label"], who=who)
            self.store.audit("alternative", rec.id, who, role, label=chosen["label"])
            self._evaluate(rec, self.network())
            self.store.put(rec)
            if approve and rec.state == State.CHECKED:
                return self.approve(rec.id, who=who, role=role)
            return rec

    def recheck(self, rid: str) -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            if rec.state not in OPEN_STATES:
                raise ImfError(f"the intent is {rec.state.value}", 409)
            self._evaluate(rec, self.network())
            self.store.put(rec)
            return rec

    # ── approve and act ──────────────────────────────────────────────────────
    def approve(self, rid: str, who: str = "operator", role: str = "operator") -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            if rec.state != State.CHECKED:
                raise ImfError(f"the intent is {rec.state.value}; only a checked intent can be approved", 409)
            if role not in self.policy.act_roles:
                raise ImfError(f"the {role} role cannot approve changes", 403)
            needs = [r for r in (rec.check or {}).get("rules", []) if r["effect"] == "approval"]
            big = self.policy.require_approval_above_mbps
            if big is not None and any((e.value("bandwidth") or 0) > big for e in rec.expectations if e.kind in ACTING_KINDS):
                needs.append({"why": f"more than {big:g} Mbps needs an approver"})
            if any(e.kind == Kind.GUARD for e in rec.expectations):
                needs.append({"why": "a rule binds every other intent: an approver sets it"})
            if needs and role not in self.policy.approval_roles:
                raise ImfError(needs[0]["why"] + f" (you act as {role})", 403)
            if (rec.check or {}).get("at", 0) < time.time() - 120:
                self._evaluate(rec, self.network())
                if rec.state != State.CHECKED:
                    self.store.put(rec)
                    raise ImfError("the network changed since the check; see the new result", 409)
            rec.approvals.append({"t": time.time(), "who": who, "role": role})
            self.store.audit("approved", rec.id, who, role)
            rec.touch("approved", who=who, role=role)
            if self._windowed(rec):
                rec.state = State.SCHEDULED
                rec.links["schedule"] = self._schedule(rec)
                rec.touch("scheduled", **rec.links["schedule"])
                self.store.put(rec)
                self.tick()
                return self._get(rid)
            self._act(rec)
            self.store.put(rec)
            return rec

    def _windowed(self, rec: IntentRecord) -> bool:
        for e in rec.expectations:
            if e.kind in (Kind.DELIVER, Kind.CHANGE, Kind.OPTIMISE) and e.context("window"):
                return True
        return False

    def _schedule(self, rec: IntentRecord) -> Dict[str, Any]:
        now = self.clock()
        out = {}
        for e in rec.expectations:
            w = e.context("window")
            if w and e.kind in (Kind.DELIVER, Kind.CHANGE, Kind.OPTIMISE):
                start, end = window_bounds(w.params, now)
                out[e.id] = {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
                             "once": bool(w.params.get("once") or w.params.get("date") or not (w.params.get("label") or w.params.get("days"))),
                             "started": False}
        return out

    def _act(self, rec: IntentRecord, only: Optional[List[str]] = None, net: Optional[NetworkModel] = None) -> bool:
        net = net or self.network()
        done: List[Dict[str, Any]] = []
        ok = True
        for e in rec.expectations:
            if only is not None and e.id not in only:
                continue
            acts: List[Dict[str, Any]] = []
            if e.kind == Kind.DELIVER:
                acts = [self.actuator.deliver(e, rec)]
            elif e.kind == Kind.CHANGE and e.action.get("legacy"):
                acts = [self._legacy_act(e, rec)]
            elif e.kind == Kind.CHANGE:
                acts = self.actuator.change(e, rec)
            elif e.kind == Kind.LIFECYCLE:
                acts = self.actuator.lifecycle(e, rec)
            elif e.kind == Kind.OPTIMISE and e.action.get("objective") == "energy":
                acts = self.actuator.energy(e, rec, True, net)
            for a in acts:
                a["expectation"] = e.id
            rec.actions += acts
            done += acts
            if any(not a.get("ok") for a in acts):
                ok = False
                break
        if not ok:
            self._rollback(rec, done)
            rec.state = State.FAILED
            err = next((a.get("error") for a in done if not a.get("ok")), "an action failed")
            rec.answer = {"text": f"Not applied: {err}. Everything done before it was undone.", "insight": "state"}
            rec.touch("failed", error=err)
            self.store.audit("failed", rec.id, error=err)
            return False
        only_lifecycle = all(e.kind in (Kind.LIFECYCLE,) for e in rec.expectations if e.kind in ACTING_KINDS) and \
            not any(e.kind in STANDING_KINDS for e in rec.expectations)
        rec.state = State.COMPLETED if only_lifecycle else State.ACTIVE
        rec.touch("applied", actions=len(done))
        self.store.audit("applied", rec.id, actions=[{k: a.get(k) for k in ("op", "slice", "hop", "ok")} for a in done])
        self._report(rec, self.network())
        return True

    def _legacy_act(self, e: Expectation, rec: IntentRecord) -> Dict[str, Any]:
        if self.legacy is None:
            return {"t": time.time(), "op": "feature", "ok": False, "error": "the v1 pipeline is not connected"}
        res = self.legacy(rec.text or e.text or "")
        ok = isinstance(res, dict) and not res.get("error")
        return {"t": time.time(), "op": "feature", "legacy_type": e.action.get("legacy_type"), "ok": ok,
                "v1": {k: res.get(k) for k in ("intent_id", "status", "error") if isinstance(res, dict) and k in res},
                **({} if ok else {"error": res.get("error") if isinstance(res, dict) else "v1 refused"})}

    def _rollback(self, rec: IntentRecord, done: List[Dict[str, Any]]) -> None:
        for a in reversed(done):
            if not a.get("ok"):
                continue
            undo = a.get("undo") or {}
            try:
                if undo.get("op") == "remove":
                    rec.actions.append({**self.actuator.remove(undo["slice"]), "rollback": True})
                    if undo["slice"] in rec.links.get("slices", []):
                        rec.links["slices"].remove(undo["slice"])
                elif undo.get("op") == "change":
                    e = Expectation(kind=Kind.CHANGE, object={"type": "slice", "ids": [undo["slice"]]},
                                    action={"before": {undo["slice"]: undo["set"]}})
                    rec.actions += [{**x, "rollback": True} for x in self.actuator.change(e, rec, revert=True)]
                elif undo.get("op") == "resume":
                    e = Expectation(kind=Kind.LIFECYCLE, object={"type": "slice", "ids": [undo["slice"]]}, action={"op": "resume"})
                    rec.actions += [{**x, "rollback": True} for x in self.actuator.lifecycle(e, rec)]
            except Exception as exc:  # pylint: disable=broad-except
                rec.actions.append({"t": time.time(), "op": "rollback", "ok": False, "error": str(exc)})

    def _suspended_request(self, sid: str) -> Optional[Dict[str, Any]]:
        for r in self.store.all():
            req = (r.links.get("suspended") or {}).get(sid)
            if req:
                (r.links.get("suspended") or {}).pop(sid, None)
                self.store.put(r)
                return req
        return None

    # ── withdraw, suspend, resume ────────────────────────────────────────────
    def withdraw(self, rid: str, who: str = "operator", role: str = "operator") -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            if role not in self.policy.act_roles:
                raise ImfError(f"the {role} role cannot withdraw intents", 403)
            if rec.state in (State.ACTIVE, State.DEGRADED, State.SCHEDULED, State.SUSPENDED):
                self._undo_all(rec)
            rec.state = State.WITHDRAWN
            rec.touch("withdrawn", who=who)
            self.store.audit("withdrawn", rec.id, who, role)
            self.store.put(rec)
            return rec

    def _undo_all(self, rec: IntentRecord) -> None:
        net = self.network()
        for e in rec.expectations:
            if e.kind == Kind.DELIVER and e.name and e.name in (rec.links.get("slices") or []):
                rec.actions.append({**self.actuator.remove(e.name), "expectation": e.id, "withdraw": True})
                rec.links["slices"].remove(e.name)
            elif e.kind == Kind.CHANGE and not e.action.get("legacy") and e.action.get("before") and \
                    any(a.get("expectation") == e.id and a.get("ok") and a.get("op") == "change" for a in rec.actions):
                rec.actions += [{**a, "withdraw": True} for a in self.actuator.change(e, rec, revert=True)]
            elif e.kind == Kind.OPTIMISE and any(a.get("expectation") == e.id and a.get("op") == "energy-on" for a in rec.actions):
                rec.actions += self.actuator.energy(e, rec, False, net)

    def suspend(self, rid: str, who: str = "operator", role: str = "operator") -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            if rec.state not in (State.ACTIVE, State.DEGRADED):
                raise ImfError(f"the intent is {rec.state.value}", 409)
            for sid in list(rec.links.get("slices") or []):
                e = Expectation(kind=Kind.LIFECYCLE, object={"type": "slice", "ids": [sid]}, action={"op": "suspend"})
                rec.actions += self.actuator.lifecycle(e, rec)
            rec.state = State.SUSPENDED
            rec.touch("suspended", who=who)
            self.store.audit("suspended", rec.id, who, role)
            self.store.put(rec)
            return rec

    def resume(self, rid: str, who: str = "operator", role: str = "operator") -> IntentRecord:
        with self.lock:
            rec = self._get(rid)
            if rec.state != State.SUSPENDED:
                raise ImfError(f"the intent is {rec.state.value}", 409)
            for sid in list((rec.links.get("suspended") or {}).keys()):
                e = Expectation(kind=Kind.LIFECYCLE, object={"type": "slice", "ids": [sid]}, action={"op": "resume"})
                rec.actions += self.actuator.lifecycle(e, rec)
            rec.state = State.ACTIVE
            rec.touch("resumed", who=who)
            self.store.audit("resumed", rec.id, who, role)
            self.store.put(rec)
            return rec

    # ── conversation ─────────────────────────────────────────────────────────
    def converse(self, session: str, text: str, who: str = "operator", role: str = "operator") -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            raise ImfError("say something")
        with self.lock:
            last = next(iter(sorted(self.store.all(session=session), key=lambda r: r.updated_at, reverse=True)), None)
            open_last = last if last is not None and last.state in OPEN_STATES else None
            if open_last is not None:
                if YES.match(text) and open_last.state == State.CHECKED:
                    rec = self.approve(open_last.id, who=who, role=role)
                    return self._said(rec, "approve")
                if NO.match(text):
                    rec = self.withdraw(open_last.id, who=who, role=role)
                    return self._said(rec, "cancel", "Cancelled; nothing was changed.")
                m = OPTION.match(text)
                if m and open_last.state == State.NEGOTIATING and open_last.alternatives:
                    n = m.group("n").lower()
                    k = len(open_last.alternatives) if n == "last" else int(n) if n.isdigit() else WORDS.get(n, 0)
                    rec = self.accept(open_last.id, k, who=who, role=role, approve=bool(m.group("go")))
                    return self._said(rec, "option")
                if open_last.state == State.CLARIFYING and open_last.questions:
                    q = open_last.questions[0]
                    if q.field == "rephrase":
                        rec = self.answer(open_last.id, q.id, text, who=who, role=role)
                        return self._said(rec, "rephrase")
                    choice = self._match_choice(q, text)
                    if choice is not None:
                        rec = self.answer(open_last.id, q.id, choice, who=who, role=role)
                        return self._said(rec, "answer")
                    ok, _, _ = clarify.parse(q.field, text, self.network())
                    if ok and not REFINE.match(text) and len(text.split()) <= 6:
                        rec = self.answer(open_last.id, q.id, text, who=who, role=role)
                        return self._said(rec, "answer")
                if REFINE.match(text) or len(text.split()) <= 4 and re.search(r"\d\s*(?:mbps|gbps|mbit|ms\b|%|mcs|mm/h)", text, re.I):
                    rec = self._refine(open_last, text, who, role)
                    if rec is not None:
                        return self._said(rec, "refine")
            if open_last is not None and open_last.state == State.NEGOTIATING and YES.match(text):
                return self._said(open_last, "which", "Which option? " + " ".join(f"{a['n']}) {a['label']}." for a in open_last.alternatives))
            if open_last is not None and open_last.state in (State.CLARIFYING, State.HELD) and (YES.match(text) or OPTION.match(text)):
                return self._said(open_last, "pending", describe(open_last))
            if last is not None and last.state in LIVE_STATES and NO.match(text):
                rec = self.withdraw(last.id, who=who, role=role)
                return self._said(rec, "cancel", f"Withdrawn: {rec.name}. What it changed was put back.")
            if YES.match(text) or NO.match(text) or OPTION.match(text):
                return {"reply": "Nothing is waiting for an answer. Tell me what the network should do.", "how": "idle", "intent": None}
            text2 = self._pronouns(text, last)
            rec = self.submit(text2, channel="chat", who=who, role=role, session=session)
            if text2 != text:
                rec.readings["context"] = f"“it” read as {', '.join((last.links.get('slices') or [last.name])[:2])}"
                self.store.put(rec)
            return self._said(rec, "new")

    def _match_choice(self, q: Question, text: str) -> Any:
        t = text.strip().lower().rstrip(".!")
        m = OPTION.match(text)
        if m and q.choices:
            n = m.group("n").lower()
            k = len(q.choices) if n == "last" else int(n) if n.isdigit() else WORDS.get(n, 0)
            if 1 <= k <= len(q.choices):
                return q.choices[k - 1].value
        for c in q.choices:
            if t == str(c.label).lower() or t == str(c.value).lower():
                return c.value
        return None

    def _refine(self, rec: IntentRecord, text: str, who: str, role: str) -> Optional[IntentRecord]:
        """'make it 600', 'only at night', 'with 5 ms': change the open intent instead of starting a new one."""
        if not rec.base:
            return None
        net = self.network()
        reading = RuleReader(net.names(), self.clock()).read(re.sub(REFINE, "", text, count=1).strip() or text)
        target_d = next((d for d in rec.base if d.get("kind") in ("deliver", "change", "keep", "optimise")), rec.base[0])
        e = Expectation.model_validate(target_d)
        changed = False
        times, _ = find_times(text, self.clock())
        if times:
            e.contexts = [c for c in e.contexts if c.kind not in ("window", "schedule")] + list(times)
            changed = True
        for x in reading.expectations:
            for t in x.targets:
                if t.metric == "technology" and t.source != Source.STATED:
                    continue
                e.set_target(t.metric, t.op, t.value, t.unit, Source.STATED, span=None)
                if e.kind == Kind.CHANGE and e.action.get("metric") == t.metric:
                    e.action.update({"op": "set", "value": t.value})
                changed = True
            if x.profile:
                e.profile = x.profile
                changed = True
        if not changed:
            from cer_intent.imf.quantities import find_quantities
            q = next((q for q in find_quantities(text) if q.dim in ("rate", "number")), None)
            if q is not None and e.target("bandwidth") is not None:
                e.set_target("bandwidth", "ge", float(q.value), "Mbps", Source.STATED)
                changed = True
        if not changed:
            return None
        rec.base = [e.model_dump() if d is target_d else d for d in rec.base]
        rec.text = f"{rec.text} — {text}"
        rec.touch("refined", text=text, who=who)
        self.store.audit("refined", rec.id, who, role, text=text)
        self._evaluate(rec, net)
        self.store.put(rec)
        return rec

    def _pronouns(self, text: str, last: Optional[IntentRecord]) -> str:
        if last is None or not re.search(r"\b(?:it|that\s+slice|this\s+slice|the\s+same\s+slice|them)\b", text, re.I):
            return text
        reading = RuleReader(self.network().names(), self.clock()).read(text)
        if any(e.object.ids or e.object.mentions or e.object.endpoints or e.object.selector for e in reading.expectations):
            return text
        slices = last.links.get("slices") or [e.name for e in last.expectations if e.kind == Kind.DELIVER and e.name] or \
            [i for e in last.expectations for i in e.object.ids]
        if not slices:
            return text
        return re.sub(r"\b(?:that\s+slice|this\s+slice|the\s+same\s+slice|it|them)\b", slices[0], text, count=1, flags=re.I)

    def _said(self, rec: IntentRecord, how: str, reply: Optional[str] = None) -> Dict[str, Any]:
        return {"reply": reply or describe(rec), "how": how, "intent": rec.model_dump(mode="json")}

    # ── schedules, objectives, reports ───────────────────────────────────────
    def tick(self, now: Optional[dt.datetime] = None) -> List[Dict[str, Any]]:
        now = now or self.clock()
        events: List[Dict[str, Any]] = []
        with self.lock:
            for rec in self.store.all(states=[State.SCHEDULED, State.ACTIVE, State.DEGRADED]):
                sched = rec.links.get("schedule") or {}
                for eid, w in sched.items():
                    start = dt.datetime.fromisoformat(w["start"]) if w.get("start") else None
                    end = dt.datetime.fromisoformat(w["end"]) if w.get("end") else None
                    if not w.get("started") and start and start <= now and (end is None or now < end):
                        ok = self._act(rec, only=[eid])
                        w["started"] = ok
                        events.append({"intent": rec.id, "event": "window started" if ok else "window failed", "expectation": eid})
                        if ok:
                            rec.state = State.ACTIVE
                    elif w.get("started") and end and now >= end:
                        self._end_window(rec, eid)
                        w["started"] = False
                        events.append({"intent": rec.id, "event": "window ended", "expectation": eid})
                        if w.get("once"):
                            w["done"] = True
                        else:
                            e = next(x for x in rec.expectations if x.id == eid)
                            s2, e2 = window_bounds(e.context("window").params, now + dt.timedelta(minutes=1))
                            w.update({"start": s2.isoformat() if s2 else None, "end": e2.isoformat() if e2 else None})
                if sched and all(w.get("done") for w in sched.values()):
                    rec.state = State.COMPLETED
                    rec.touch("completed")
                elif sched and not any(w.get("started") for w in sched.values()) and rec.state == State.ACTIVE and \
                        not any(e.kind in STANDING_KINDS for e in rec.expectations):
                    rec.state = State.SCHEDULED
                if rec.state in (State.ACTIVE, State.DEGRADED):
                    events += self._watch(rec, now)
                self.store.put(rec)
        self.events = (self.events + events)[-200:]
        return events

    def _end_window(self, rec: IntentRecord, eid: str) -> None:
        e = next((x for x in rec.expectations if x.id == eid), None)
        if e is None:
            return
        net = self.network()
        if e.kind == Kind.DELIVER and e.name in (rec.links.get("slices") or []):
            rec.actions.append({**self.actuator.remove(e.name), "expectation": eid, "window": "end"})
            rec.links["slices"].remove(e.name)
        elif e.kind == Kind.CHANGE:
            rec.actions += [{**a, "window": "end"} for a in self.actuator.change(e, rec, revert=True)]
        elif e.kind == Kind.OPTIMISE:
            rec.actions += [{**a, "window": "end"} for a in self.actuator.energy(e, rec, False, net)]
        rec.touch("window ended", expectation=eid)

    def _watch(self, rec: IntentRecord, now: dt.datetime) -> List[Dict[str, Any]]:
        """Standing objectives and reports at their cadence."""
        events = []
        last = rec.links.get("watched_at", 0)
        every = min([int(c.params.get("seconds") or self.policy.keep_check_every_s)
                     for e in rec.expectations for c in e.contexts if c.kind == "schedule"] or [self.policy.keep_check_every_s])
        if time.time() - last < every and rec.links.get("watched_at") is not None:
            return events
        rec.links["watched_at"] = time.time()
        net = self.network()
        report = self._report(rec, net)
        met = all(x.get("status") != "NOT_FULFILLED" for x in report["expectations"].values())
        if not met and rec.state == State.ACTIVE:
            rec.state = State.DEGRADED
            rec.touch("degraded", why=report.get("why"))
            events.append({"intent": rec.id, "event": "degraded", "why": report.get("why")})
            fixes = self._remedy(rec, report, net)
            events += fixes
            if fixes:
                again = self._report(rec, self.network())
                if all(x.get("status") != "NOT_FULFILLED" for x in again["expectations"].values()):
                    rec.state = State.ACTIVE
                    rec.touch("restored", by=[f.get("suspended") for f in fixes])
                    events.append({"intent": rec.id, "event": "restored", "why": "after shedding best effort"})
        elif met and rec.state == State.DEGRADED:
            rec.state = State.ACTIVE
            rec.touch("restored")
            events.append({"intent": rec.id, "event": "restored"})
        for e in rec.expectations:
            if e.kind == Kind.OBSERVE and e.action.get("op") == "alert":
                fired = report["expectations"].get(e.id, {}).get("alert")
                if fired:
                    events.append({"intent": rec.id, "event": "alert", "why": fired})
        return events

    def _remedy(self, rec: IntentRecord, report: Dict[str, Any], net: NetworkModel) -> List[Dict[str, Any]]:
        """A keep objective with 'take it from best effort first': suspend best-effort slices on the hop."""
        events = []
        for e in rec.expectations:
            if e.kind != Kind.KEEP or not e.action.get("shed_first"):
                continue
            if report["expectations"].get(e.id, {}).get("status") != "NOT_FULFILLED":
                continue
            victims = []
            for other in self.store.all(states=[State.ACTIVE, State.DEGRADED]):
                if other.id == rec.id:
                    continue
                if any(x.kind == Kind.DELIVER and x.strictness.value == "best_effort" for x in other.expectations):
                    victims.append(other)
            for v in victims:
                self.suspend(v.id, who=f"intent {rec.name}", role="operator")
                events.append({"intent": rec.id, "event": "shed", "suspended": v.id,
                               "why": f"{rec.name} keeps its objective by suspending best-effort {v.name}"})
                rec.touch("shed", suspended=v.name)
        return events

    def report(self, rid: str) -> Dict[str, Any]:
        with self.lock:
            rec = self._get(rid)
            if rec.state in LIVE_STATES:
                self._report(rec, self.network())
                self.store.put(rec)
            from cer_intent.imf.standards import report_3gpp
            return report_3gpp(rec)

    def _report(self, rec: IntentRecord, net: NetworkModel) -> Dict[str, Any]:
        radios = [n.id for n in net.nodes.values() if n.radio]
        nsc = None
        try:
            nsc = self.actuator.nsc
        except Exception:  # pylint: disable=broad-except
            pass
        live = radio_state(getattr(nsc, "tfs_client", None), radios) if nsc is not None else {}
        out: Dict[str, Any] = {"t": time.time(), "state": rec.state.value, "radios": live, "expectations": {}}
        whys = []
        for e in rec.expectations:
            r: Dict[str, Any] = {"status": "FULFILLED", "targets": {}}
            if e.kind == Kind.DELIVER:
                s = net.slices.get(e.name or "")
                if s is None and e.name in (rec.links.get("slices") or []):
                    r["status"] = "NOT_FULFILLED"
                    whys.append(f"{e.name} is not in the slice controller")
                if s is not None:
                    served, short = self._served(s.id, net, live)
                    for t in e.targets:
                        if t.metric == "bandwidth":
                            ok = served + 1e-6 >= float(t.value)
                            r["targets"]["bandwidth"] = {"achieved": round(served, 1), "status": "FULFILLED" if ok else "NOT_FULFILLED"}
                            if not ok:
                                r["status"] = "NOT_FULFILLED"
                                whys.append(short)
                        elif t.metric == "modulation_floor":
                            r["targets"]["modulation_floor"] = {"achieved": s.hop_floor or s.acm_floor, "status": "FULFILLED"}
            elif e.kind == Kind.KEEP:
                for sid in e.object.ids:
                    s = net.slices.get(sid)
                    if s is None:
                        continue
                    served, short = self._served(sid, net, live)
                    bw = e.value("bandwidth")
                    if bw is not None:
                        ok = served + 1e-6 >= float(bw)
                        r["targets"]["bandwidth"] = {"achieved": round(served, 1), "status": "FULFILLED" if ok else "NOT_FULFILLED"}
                        if not ok:
                            r["status"] = "NOT_FULFILLED"
                            whys.append(short)
                    floor = e.value("modulation_floor")
                    if floor:
                        lowest = min((mcs_index(live.get(x, {}).get("mcs")) or 99 for x in s.path if x in live), default=None)
                        if lowest is not None and lowest != 99:
                            ok = lowest >= (mcs_index(floor) or 0)
                            r["targets"]["modulation_floor"] = {"achieved": f"MCS{lowest}", "status": "FULFILLED" if ok else "NOT_FULFILLED"}
                            if not ok:
                                r["status"] = "NOT_FULFILLED"
                                whys.append(f"{sid}'s hop runs at MCS{lowest}, below {floor}")
            elif e.kind == Kind.OBSERVE:
                vals = {}
                for hop in net.radio_hops():
                    mcs = [live.get(x, {}).get("mcs") for x in (hop.a, hop.b) if live.get(x, {}).get("mcs")]
                    lowest = min(mcs, key=lambda m: mcs_index(m) or 0) if mcs else hop.mcs(0)
                    vals[hop.name] = {"lowest_modulation": lowest, "capacity_mbps": capacity_mbps(lowest) if lowest else None,
                                      "load_mbps": net.load(hop), "source": "radios" if mcs else "model (clear sky)"}
                r["values"] = vals
                cond = next((c for c in e.contexts if c.kind == "condition"), None)
                if cond and e.action.get("op") == "alert":
                    metric, value = cond.params.get("metric"), cond.params.get("value")
                    for hop, v in vals.items():
                        if metric in ("lowest_modulation", "modulation_floor", "mcs") or e.target("modulation_floor"):
                            thr = mcs_index(value) if value is not None else mcs_index(e.value("modulation_floor"))
                            cur = mcs_index(v["lowest_modulation"])
                            if thr and cur and cur < thr:
                                r["alert"] = f"{hop} runs at {v['lowest_modulation']}"
                fl = e.target("modulation_floor")
                if fl is not None and e.action.get("op") == "alert":
                    for hop, v in vals.items():
                        cur = mcs_index(v["lowest_modulation"])
                        if cur and cur < (mcs_index(fl.value) or 0):
                            r["alert"] = f"{hop} runs at {v['lowest_modulation']}, below {fl.value}"
            out["expectations"][e.id] = r
        out["why"] = "; ".join(w for w in whys if w)
        rec.reports.append(out)
        rec.reports = rec.reports[-50:]
        return out

    def _served(self, sid: str, net: NetworkModel, live: Dict[str, Dict[str, Any]]) -> Tuple[float, str]:
        """
        What a slice gets when the hop runs at the radios' current MCS. The radios queue every
        slice in one class (as the twin models them), so a hop that falls short shares what it
        carries in proportion to what each slice asks.
        """
        s = net.slices.get(sid)
        if s is None:
            return 0.0, f"{sid} is gone"
        worst = s.bandwidth_mbps or 0.0
        why = ""
        for hop in net.hops(s.path):
            mcs = [live.get(x, {}).get("mcs") for x in (hop.a, hop.b) if live.get(x, {}).get("mcs")]
            if not mcs:
                continue
            lowest = min(mcs, key=lambda m: mcs_index(m) or 0)
            cap = min(hop.port_mbps, capacity_mbps(lowest))
            demand = net.load(hop)
            mine = s.bandwidth_mbps or 0.0
            got = mine if demand <= cap else cap * mine / demand
            if got < worst:
                worst = got
                why = f"{hop.name} runs at {lowest} ({cap:g} Mbps) for {demand:g} Mbps asked: {sid} gets {got:.0f}"
        return worst, why

    def _rank(self, sid: str, net: NetworkModel) -> float:
        for i in net.intents:
            if sid in (i.get("slices") or []):
                return float(i.get("priority") or 5)
        return 5.0

    # ── background loop ──────────────────────────────────────────────────────
    def start(self, every_s: float = 10.0) -> None:
        if self._thread is not None:
            return

        def loop():
            while not self._stop.wait(every_s):
                try:
                    self.tick()
                except Exception:  # pylint: disable=broad-except
                    logger.exception("intent manager tick failed")
        self._thread = threading.Thread(target=loop, name="imf-tick", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _get(self, rid: str) -> IntentRecord:
        rec = self.store.get(rid)
        if rec is None:
            raise ImfError("intent not found", 404)
        return rec


def _default_nsc():
    try:
        from cer_intent.api.restconf_routes import get_nsc
        return get_nsc()
    except Exception:  # pylint: disable=broad-except
        from cer_intent.nsc import shared_controller
        return shared_controller()


# ── what to say back ───────────────────────────────────────────────────────────

def describe(rec: IntentRecord) -> str:
    read = "; ".join(e.summary() for e in rec.expectations) or (rec.text or "")
    s = rec.state
    if s == State.REJECTED:
        return (rec.answer or {}).get("text", "Outside what I manage.")
    if s == State.CLARIFYING:
        q = rec.questions[0]
        choices = ", ".join(f"{i}) {c.label}" for i, c in enumerate(q.choices, 1))
        lead = f"I read: {read}. " if rec.expectations and q.field != "rephrase" else ""
        return f"{lead}{q.text}" + (f" {choices}" if choices else "")
    if s == State.ANSWERED:
        return (rec.answer or {}).get("text", "Done.")
    check = rec.check or {}
    twin = check.get("twin") or {}
    basis = ("the twin's NS-3 run: " + str(twin.get("verdict"))) if twin.get("ran") else "the analytic radio screen"
    if s == State.CHECKED:
        why = next((x.get("why") for x in check.get("screens", []) if x.get("why")), None) or \
            next((h.get("why") for x in check.get("screens", []) for h in x.get("hops", []) if isinstance(h, dict) and h.get("why")), "no objection")
        rules = [r["why"] for r in check.get("rules", []) if r["effect"] in ("approval", "floor", "headroom")]
        conflicts = [c["why"] for c in check.get("conflicts", []) if c.get("severity") == "warn"]
        extra = (" " + " ".join(rules + conflicts)) if rules or conflicts else ""
        return f"I read: {read}. Checked on {basis}: {why}.{extra} Approve to apply."
    if s == State.NEGOTIATING:
        why = "; ".join(x.get("why") for x in check.get("screens", []) if x.get("ok") is False) or \
              "; ".join(c["why"] for c in check.get("conflicts", []))
        opts = " ".join(f"{a['n']}) {a['label']}." for a in rec.alternatives)
        return f"Not as asked: {why}. Options: {opts} Say the option number."
    if s == State.HELD:
        why = "; ".join([r["why"] for r in check.get("rules", []) if r["effect"] == "hold"] +
                        [x.get("why") for x in check.get("screens", []) if x.get("ok") is False] +
                        [c["why"] for c in check.get("conflicts", []) if c.get("severity") == "block"])
        hint = " Ask how much fits, or try less." if any(x.get("ok") is False for x in check.get("screens", [])) else ""
        return f"Held: {why or 'a rule or a failed check'}.{hint}"
    if s == State.SCHEDULED:
        sched = rec.links.get("schedule") or {}
        when = ", ".join(f"{w.get('start', '')[:16].replace('T', ' ')} – {(w.get('end') or '')[11:16]}" for w in sched.values())
        return f"Scheduled: {read}. Acts at {when}" + (", then puts things back." if any(e.action.get("revert") for e in rec.expectations) else ".")
    if s in (State.ACTIVE, State.COMPLETED):
        acts = [a for a in rec.actions if a.get("ok") and not a.get("rollback")]
        watch = "; ".join(e.summary() for e in rec.expectations if e.kind in (Kind.KEEP, Kind.GUARD, Kind.OBSERVE))
        if not acts:
            return f"Active: {watch or read}."
        what = ", ".join(f"{a['op']} {a.get('slice') or a.get('hop') or ''}".strip() for a in acts[-4:])
        return f"Done: {what}." + (f" Watching: {watch}." if watch else "")
    if s == State.DEGRADED:
        last = rec.reports[-1] if rec.reports else {}
        return f"Degraded: {last.get('why') or 'an objective is not met'}."
    if s == State.FAILED:
        return (rec.answer or {}).get("text", "Failed.")
    if s == State.WITHDRAWN:
        return "Withdrawn."
    if s == State.SUSPENDED:
        return "Suspended; resume to bring it back."
    return f"{s.value}: {read}"
