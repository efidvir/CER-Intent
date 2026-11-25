"""
Auto-approval inside guardrails: what is applied without a person, what waits and why,
rule intents that widen or stop it, the watch that rolls back, and the admin's settings.
"""
from __future__ import annotations

import json

import pytest

from cer_intent.imf.autoapprove import AutoPolicy, validate
from cer_intent.imf.manager import ImfError, IntentManager
from cer_intent.imf.match import Policy
from cer_intent.imf.model import State
from cer_intent.imf.store import IntentStore
from imf_fakes import build, network_of


def auto(**kw) -> Policy:
    return Policy(auto=AutoPolicy(enabled=True, **kw))


def say(m, text, session="t"):
    r = m.converse(session, text)
    return m.store.get(r["intent"]["id"]), r["reply"]


def failing(rec):
    return {g["id"]: g["why"] for g in rec.links.get("guardrails") or [] if not g["ok"]}


def with_live(m, nsc, live):
    """The network the check sees, with the radios' modulation as discovery would read it."""
    def net():
        n = network_of(nsc)
        for k, v in live.items():
            n.nodes[k].live = {**(n.nodes[k].live or {}), "mcs": v}
        return n
    m._network = net


def test_off_by_default_every_intent_waits_for_a_person():
    m, nsc, _, _ = build(twin=True)
    rec, reply = say(m, "Connect region-a and edge with 50 Mbps")
    assert rec.state == State.CHECKED and "Approve to apply" in reply
    assert failing(rec) == {"enabled": "auto-approval is off and no rule covers this intent"}
    assert rec.name not in nsc.slices


def test_a_small_delivery_is_applied_with_every_guardrail_shown_and_watched():
    m, nsc, _, _ = build(twin=True, policy=auto())
    rec, reply = say(m, "Connect region-a and edge with 100 Mbps")
    assert rec.state == State.ACTIVE and rec.name in nsc.slices
    ids = [g["id"] for g in rec.links["guardrails"]]
    assert ids == ["enabled", "kind", "who", "confirmed", "check", "twin", "size", "headroom", "radios", "rate", "reversible"]
    assert all(g["ok"] for g in rec.links["guardrails"])
    assert reply.startswith("Applied automatically (11 guardrails held)") and "rolls back" in reply
    assert rec.approvals[-1]["auto"] and rec.links["auto"]["status"] == "watching"
    assert [a["event"] for a in m.store.audit_log(rec.id)] == ["submitted", "auto-approved", "applied"]


def test_too_big_waits_and_says_which_guardrail():
    m, nsc, _, _ = build(twin=True, policy=auto())
    rec, reply = say(m, "Connect region-a and edge with 300 Mbps")
    assert rec.state == State.CHECKED and rec.name not in nsc.slices
    assert failing(rec) == {"size": "300 Mbps is more than the 200 Mbps auto-approval limit"}
    assert "Needs your approval: 300 Mbps is more than the 200 Mbps auto-approval limit" in reply
    m.approve(rec.id, who="ann", role="operator")
    assert m.store.get(rec.id).state == State.ACTIVE


def test_without_the_twin_nothing_that_adds_load_is_applied():
    m, _, _, _ = build(twin=False, policy=auto())
    rec, _ = say(m, "Connect region-a and edge with 50 Mbps")
    assert rec.state == State.CHECKED and failing(rec) == {"twin": "the twin did not run"}
    m2, _, _, _ = build(twin=False, policy=auto(require_twin=False))
    assert say(m2, "Connect region-a and edge with 50 Mbps")[0].state == State.ACTIVE


def test_headroom_on_every_hop_in_design_rain():
    m, _, _, _ = build(twin=True, policy=auto(max_bandwidth_mbps=1000))
    rec, _ = say(m, "Connect region-a and edge with 450 Mbps")       # 200 + 450 of 770 Mbps in design rain
    assert rec.state == State.CHECKED
    assert failing(rec) == {"headroom": "radio-1|radio-2 would carry 650 of 770 Mbps in design rain, more than 80 %"}


def test_radios_below_their_clear_sky_rate_now_hold_it_until_they_recover():
    m, nsc, _, _ = build(twin=True, policy=auto())
    live = {"radio-1": "MCS6", "radio-2": "MCS6"}
    with_live(m, nsc, live)
    rec, _ = say(m, "Connect region-a and edge with 50 Mbps")
    assert rec.state == State.CHECKED and failing(rec) == {"radios": "radio-1|radio-2 runs MCS6 now"}
    live.clear()
    assert m.recheck(rec.id).state == State.ACTIVE


def test_hourly_limit_per_person():
    m, _, _, _ = build(twin=True, policy=auto(per_user_hour=1))
    first, _ = say(m, "Connect region-a and edge with 20 Mbps", "a")
    second, _ = say(m, "Connect region-a and edge with 20 Mbps", "b")
    assert first.state == State.ACTIVE and second.state == State.CHECKED
    assert failing(second) == {"rate": "1 this hour (limit 10), 1 by operator (limit 1)"}


def test_a_removal_always_needs_a_person_and_a_suspend_does_not():
    m, nsc, _, _ = build(twin=True, policy=auto())
    rec, _ = say(m, "Remove the slice on VLAN 100")
    assert rec.state == State.CHECKED and set(failing(rec)) == {"kind", "reversible"}
    rec, reply = say(m, "Suspend backhaul-ran", "s")
    assert rec.state == State.COMPLETED and "backhaul-ran" not in nsc.slices and reply.startswith("Applied automatically")


def test_a_rule_intent_turns_it_on_for_what_it_covers():
    m, nsc, _, _ = build(twin=True)
    rule, reply = say(m, "Auto-approve deliveries up to 300 Mbps", "r")
    assert rule.state == State.CHECKED and "Approve to apply" in reply          # a rule binds everyone: a person sets it
    with pytest.raises(ImfError):
        m.approve(rule.id, who="op", role="operator")
    m.approve(rule.id, who="ann", role="approver")
    rec, _ = say(m, "Connect region-a and edge with 250 Mbps", "a")
    assert rec.state == State.ACTIVE
    assert rec.links["guardrails"][0]["why"] == f"by the rule {rule.name}"
    m2, _, _, _ = build(twin=True)
    rule2, _ = say(m2, "Auto-approve deliveries up to 300 Mbps", "r")
    m2.approve(rule2.id, who="ann", role="approver")
    rec, _ = say(m2, "Connect region-a and edge with 320 Mbps", "b")
    assert rec.state == State.CHECKED and failing(rec) == {"size": "320 Mbps is more than the 300 Mbps auto-approval limit"}


def test_a_never_rule_stops_it_for_what_it_names():
    m, _, _, _ = build(twin=True, policy=auto())
    rule, _ = say(m, "Never auto-approve deliveries", "r")
    assert rule.expectations[0].action == {"rule": "approval", "no_auto": True, "kinds": ["deliver"]}
    m.approve(rule.id, who="ann", role="admin")
    rec, reply = say(m, "Connect region-a and edge with 50 Mbps", "a")
    assert rec.state == State.CHECKED and failing(rec) == {"check": f"{rule.name} asks a person to approve this"}
    assert say(m, "Suspend backhaul-ran", "s")[0].state == State.COMPLETED        # not a delivery: still automatic


@pytest.mark.parametrize("text,kinds,ids", [
    ("No changes during business hours without approval", None, []),
    ("Don't approve changes automatically", None, []),
    ("Stop auto-approving slices on radio-1", None, ["radio-1"]),
    ("No auto-approval for suspensions", ["lifecycle"], []),
])
def test_restrictions_read_broadly_unless_they_name_a_kind(text, kinds, ids):
    m, _, _, _ = build(twin=True, policy=auto())
    e = say(m, text, "r")[0].expectations[0]
    assert e.action.get("rule") == "approval" and e.action.get("kinds") == kinds and e.object.ids == ids


def test_the_watch_rolls_back_when_its_objective_breaks():
    m, nsc, tfs, _ = build(twin=True, policy=auto())
    rec, _ = say(m, "Connect region-a and edge with 100 Mbps; keep the radio link at MCS4 or better")
    assert m.tick() == [] and m.store.get(rec.id).state == State.ACTIVE
    tfs.mcs.update({"radio-1": 3, "radio-2": 3})                                # read back through the controller
    events = m.tick()
    rec = m.store.get(rec.id)
    assert "auto rollback" in [e["event"] for e in events]
    assert rec.state == State.FAILED and rec.name not in nsc.slices and rec.links["auto"]["status"] == "rolled back"
    assert rec.answer["text"].startswith("Rolled back automatically within its watch window")
    assert m.store.audit_log(rec.id)[-1]["event"] == "auto-rolled-back"


def test_a_resume_is_screened_and_rolled_back_if_it_starves_what_was_met():
    m, nsc, tfs, _ = build(twin=True, policy=auto(max_bandwidth_mbps=1000, max_hop_load_pct=100))
    a, _ = say(m, "Connect region-a and edge with 300 Mbps", "a")
    a.links["auto"]["status"] = "passed"
    m.store.put(a)
    s, _ = say(m, "Suspend backhaul-ran", "s")
    s.links["auto"]["status"] = "passed"
    m.store.put(s)
    res, _ = say(m, "Resume backhaul-ran", "r")                                 # named though suspended
    assert res.state == State.COMPLETED and "backhaul-ran" in nsc.slices
    assert [x["slice"] for x in res.check["screens"]] == ["backhaul-ran"] and res.check["twin"]["verdict"] == "pass"
    assert res.links["auto"]["baseline"] == {a.id: True}
    tfs.mcs.update({"radio-1": 4, "radio-2": 4})                                # 462 Mbps for 500 asked
    events = m.tick()
    assert {"intent": res.id, "event": "auto rollback"}.items() <= next(e for e in events if e["event"] == "auto rollback").items()
    assert m.store.get(res.id).state == State.FAILED and "backhaul-ran" not in nsc.slices


def test_the_watch_ends():
    m, _, _, _ = build(twin=True, policy=auto(watch_s=0))
    rec, _ = say(m, "Connect region-a and edge with 100 Mbps")
    assert m.tick() == [{"intent": rec.id, "event": "auto watch passed"}]
    assert m.store.get(rec.id).links["auto"]["status"] == "passed" and m.tick() == []


def test_only_an_admin_changes_it_and_the_change_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("CER_IMF_AUTO", "1")                                     # the deployment switches it on
    state = tmp_path / "imf_auto_policy.json"
    m = IntentManager(store=IntentStore(":memory:"), use_llm_env=False, policy=Policy(), auto_state=state)
    assert m.policy.auto.enabled
    with pytest.raises(ImfError) as e:
        m.set_auto_policy({"enabled": False}, "op", "operator")
    assert e.value.status == 403
    for bad in ({"colour": "red"}, {"max_hop_load_pct": 150}, {"roles": ["root"]}, {"enabled": "no"}):
        with pytest.raises(ImfError):
            m.set_auto_policy(bad, "ann", "admin")
    out = m.set_auto_policy({"enabled": False, "max_bandwidth_mbps": 150}, "ann", "admin")
    assert out["enabled"] is False and out["max_bandwidth_mbps"] == 150.0
    assert json.loads(state.read_text())["changes"] == {"enabled": False, "max_bandwidth_mbps": 150.0}
    again = IntentManager(store=IntentStore(":memory:"), use_llm_env=False, policy=Policy(), auto_state=state)
    assert again.policy.auto.enabled is False and again.policy.auto.max_bandwidth_mbps == 150.0   # after a restart


def test_validate_normalises_numbers():
    assert validate({"per_hour": 3.0, "max_bandwidth_mbps": 100}, ("operator",)) == {"per_hour": 3, "max_bandwidth_mbps": 100.0}
