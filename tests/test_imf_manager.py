"""
The intent manager end to end over a fake controller: understand, clarify, check,
negotiate, approve, act, schedule, keep, report, and the standards' shapes.
"""
from __future__ import annotations

import datetime as dt

import pytest

from cer_intent.imf import standards
from cer_intent.imf.llm import RecordedProvider, merge, to_reading
from cer_intent.imf.manager import ImfError
from cer_intent.imf.model import Kind, Source, State
from cer_intent.imf.reader import RuleReader
from imf_fakes import build

L2 = "Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; keep the radio link at MCS4 or better"


def say(m, text, session="t"):
    return m.converse(session, text)


def test_deliver_checked_approved_and_realized_with_its_floor():
    m, nsc, tfs, _ = build()
    r = say(m, L2)
    rec = m.store.get(r["intent"]["id"])
    assert rec.state == State.CHECKED and "Approve to apply" in r["reply"]
    e = rec.expectations[0]
    assert e.name == "slice-region-a-edge-300" and e.value("modulation_floor") == "MCS4"
    assert {p["field"]: p["source"] for p in e.action["provenance"]}["technology"] == "policy"
    r = say(m, "approve")
    assert r["intent"]["state"] == "active"
    assert "slice-region-a-edge-300" in nsc.slices
    assert ("slice-region-a-edge-300", {"acm": {"min_modulation": "MCS4"}}) in [c[1] for c in tfs.calls if c[0] == "update_service_settings"]
    assert m.store.audit_log(rec.id)[-1]["event"] == "applied"


def test_a_missing_site_is_asked_and_the_answer_kept():
    m, nsc, _, _ = build()
    r = say(m, "Connect HQ and edge with 100 Mbps")
    assert r["intent"]["state"] == "clarifying" and "HQ" in r["reply"]
    r = say(m, "region-a")
    rec = m.store.get(r["intent"]["id"])
    assert rec.state == State.CHECKED and rec.name == "slice-region-a-edge-300"
    assert rec.expectations[0].object.endpoints[0].source == Source.ANSWER
    r = say(m, "make it 50 Mbps")
    assert r["how"] == "refine" and m.store.get(rec.id).expectations[0].value("bandwidth") == 50.0


def test_taken_vlans_are_asked_about_and_pending_intents_reserve_theirs():
    m, _, _, _ = build()
    r = say(m, "Connect region-a and edge over VLAN 100 with 50 Mbps")
    assert r["intent"]["questions"][0]["field"] == "vlan"
    first = say(m, "Connect region-a and edge with 100 Mbps", session="a")["intent"]
    second = say(m, "Connect region-a and edge with 100 Mbps", session="b")["intent"]
    vl = lambda rec: rec["expectations"][0]["object"]["endpoints"][0]["vlan"]   # noqa: E731
    assert (vl(first), vl(second)) == (300, 301)


def test_too_much_is_negotiated_and_an_alternative_applied():
    m, nsc, _, _ = build()
    say(m, L2)
    say(m, "approve")
    r = say(m, "Connect region-a and edge with 800 Mbps, gold")
    rec = m.store.get(r["intent"]["id"])
    assert rec.state == State.NEGOTIATING
    alt = rec.alternatives[0]
    assert alt["kind"] == "most_that_fits" and alt["changes"][0]["value"] == 70.0
    r = say(m, "option 1 and apply")
    rec = m.store.get(rec.id)
    assert rec.state == State.ACTIVE
    assert rec.expectations[0].target("bandwidth").source == Source.NEGOTIATED
    assert nsc.requests[rec.expectations[0].name]["slos"]["bandwidth_mbps"] == 70.0


def test_the_twin_decides_when_it_runs_and_finds_the_most_that_fits():
    m, nsc, _, _ = build(twin=True)
    r = say(m, "Connect region-a and edge with 450 Mbps")           # analytic: fits; test twin: 200 + 450 <= 770
    assert r["intent"]["state"] == "checked" and r["intent"]["check"]["twin"]["verdict"] == "pass"
    m.twin.limit = 500.0                                             # the twin now holds at 500 Mbps in all
    r = say(m, "Connect region-a and edge with 450 Mbps", session="x")
    rec = m.store.get(r["intent"]["id"])
    assert rec.state == State.NEGOTIATING and "twin" in rec.check["screens"][0]["why"]
    best = next(a for a in rec.alternatives if a["kind"] == "most_that_fits")
    assert 270.0 <= best["changes"][0]["value"] <= 300.0 and "twin" in best["label"]      # bisection, 10 Mbps steps


def test_a_failed_action_is_rolled_back():
    m, nsc, tfs, _ = build(fail_on="update_service_settings")
    say(m, L2)                                       # the floor travels as service settings, which fail
    r = say(m, "approve")
    assert m.store.get(r["intent"]["id"]).state == State.FAILED and "slice-region-a-edge-300" not in nsc.slices
    m, nsc, tfs, _ = build(fail_on="update_service_constraints")
    r = say(m, "Connect region-a and edge with 100 Mbps; double the backhaul")
    assert [e["kind"] for e in r["intent"]["expectations"]] == ["deliver", "change"]
    r = say(m, "approve")
    rec = m.store.get(r["intent"]["id"])
    assert rec.state == State.FAILED and "undone" in r["reply"]
    assert "slice-region-a-edge-300" not in nsc.slices                  # the delivery made first was removed
    assert any(a.get("rollback") and a["op"] == "remove" for a in rec.actions)


def test_a_window_acts_at_its_start_and_reverts_at_its_end():
    m, nsc, _, now = build()
    r = say(m, "Double the backhaul tonight 20:00-23:00, then restore it")
    assert r["intent"]["state"] == "checked"
    r = say(m, "approve")
    rid = r["intent"]["id"]
    assert m.store.get(rid).state == State.SCHEDULED
    m.tick(dt.datetime(2026, 11, 25, 20, 1))
    assert nsc.requests["backhaul-ran"]["slos"]["bandwidth_mbps"] == 400.0 and m.store.get(rid).state == State.ACTIVE
    m.tick(dt.datetime(2026, 11, 25, 23, 1))
    assert nsc.requests["backhaul-ran"]["slos"]["bandwidth_mbps"] == 200.0
    assert m.store.get(rid).state == State.COMPLETED


def test_a_keep_objective_sheds_best_effort_when_the_radios_fade():
    m, nsc, tfs, _ = build()
    for text in ("Connect region-a and edge with 300 Mbps", "A best-effort slice from region-a to edge for 100 Mbps",
                 "Never let the backhaul drop below 150 Mbps; take it from best effort first"):
        r = say(m, text, session=text[:8])
        assert r["intent"]["state"] == "checked", r["reply"]
        say(m, "approve", session=text[:8])
    tfs.mcs.update({"radio-1": 3, "radio-2": 3})                     # 385 Mbps for 600 asked
    events = m.tick()
    kinds = [e["event"] for e in events]
    assert "shed" in kinds and "restored" in kinds
    be = next(r for r in m.store.all() if any(e.strictness.value == "best_effort" for e in r.expectations))
    assert be.state == State.SUSPENDED and be.links["suspended"]


def test_rules_hold_changes_and_need_an_approver():
    m, _, _, now = build()
    r = say(m, "No changes during business hours without approval", session="g")
    with pytest.raises(ImfError):
        m.approve(r["intent"]["id"], role="operator")                # a rule binds everyone: an approver sets it
    m.approve(r["intent"]["id"], role="approver")
    r = say(m, "Connect region-a and edge with 100 Mbps")
    assert any(x["effect"] == "approval" for x in r["intent"]["check"]["rules"])
    with pytest.raises(ImfError) as e:
        m.approve(r["intent"]["id"], role="operator")
    assert e.value.status == 403
    assert m.approve(r["intent"]["id"], role="approver").state == State.ACTIVE
    r = say(m, "Freeze all changes this weekend", session="f")
    m.approve(r["intent"]["id"], role="admin")
    now["t"] = dt.datetime(2026, 11, 28, 11, 0)                      # Saturday
    r = say(m, "Connect region-a and edge with 50 Mbps", session="w")
    assert r["intent"]["state"] == "held" and "frozen" in r["reply"]


def test_viewers_read_and_explore_but_do_not_act():
    m, _, _, _ = build()
    r = m.converse("v", "How much more can the hop carry in heavy rain?", role="viewer")
    assert r["intent"]["state"] == "answered" and "Mbps more fits" in r["reply"]
    r = m.converse("v", "Connect region-a and edge with 100 Mbps", role="viewer")
    with pytest.raises(ImfError):
        m.approve(r["intent"]["id"], role="viewer")


def test_questions_whatifs_and_explanations():
    m, _, _, _ = build()
    assert "backhaul-ran" in say(m, "What runs over radio-1?")["reply"]
    assert "lose their only path" in say(m, "What if radio-1 fails?")["reply"]
    assert "Without backhaul-ran" in say(m, "What happens if we remove the backhaul?")["reply"]
    r = say(m, "Could I add 200 Mbps between region-a and edge in heavy rain?")
    assert r["intent"]["state"] == "answered" and r["reply"].startswith("Yes")
    assert say(m, "Configure BGP on the core routers")["intent"]["state"] == "rejected"
    assert "Nothing is waiting" in say(m, "approve", session="empty")["reply"]


def test_withdrawing_puts_things_back():
    m, nsc, _, _ = build()
    say(m, L2)
    rid = say(m, "approve")["intent"]["id"]
    assert "slice-region-a-edge-300" in nsc.slices
    r = say(m, "cancel")
    assert r["how"] == "cancel" and m.store.get(rid).state == State.WITHDRAWN
    assert "slice-region-a-edge-300" not in nsc.slices


def test_reports_follow_the_radios():
    m, _, tfs, _ = build()
    say(m, L2)
    rid = say(m, "approve")["intent"]["id"]
    rep = m.report(rid)
    assert rep["intentFulfilmentReport"]["intentFulfilmentInfo"]["fulfilmentStatus"] == "FULFILLED"
    tfs.mcs.update({"radio-1": 4, "radio-2": 4})                     # 462 Mbps for 700 asked
    m.tick()
    rep = m.report(rid)
    assert rep["intentFulfilmentReport"]["intentFulfilmentInfo"]["notFulfilledState"] == "DEGRADED"
    got = rep["intentFulfilmentReport"]["expectationFulfilmentResults"][0]["targetFulfilmentResults"]
    assert any(t["targetName"] == "oneWayBandwidth" and t["targetAchievedValue"] == 330.0 for t in got)


def test_tmf921_and_3gpp_round_trip():
    m, nsc, _, _ = build()
    rec = m.submit(L2)
    tmf = standards.to_tmf921(rec)
    assert tmf["lifecycleStatus"] == "pending" and tmf["expression"]["@type"] == "JsonLdExpression"
    back = m.submit(record=standards.from_tmf921(tmf), channel="tmf921")
    e = back.expectations[0]
    assert (e.kind, e.value("bandwidth"), e.value("modulation_floor")) == (Kind.DELIVER, 500.0, "MCS4")
    g = standards.to_3gpp(rec)
    assert g["intentExpectations"][0]["expectationVerb"] == "DELIVER"
    assert {"targetName": "oneWayBandwidth", "targetCondition": "IS_EQUAL_TO_OR_GREATER_THAN", "targetValueRange": 500.0,
            "targetUnit": "Mbps", "cerSource": "stated"} in g["intentExpectations"][0]["expectationTargets"]
    back = standards.from_3gpp({"Intent": g})
    assert back.expectations[0].value("latency") == 10.0
    report = standards.report_3gpp(rec)
    assert report["intentFeasibilityCheckReport"]["feasibilityCheckResult"] == "FEASIBLE"


def test_a_model_reading_fills_what_the_rules_missed_and_is_confirmed():
    text = "Spin up something snappy for the cameras between the two sites, about a quarter gig"
    model = {"expectations": [{"kind": "deliver", "object": {"type": "slice", "endpoints": [{"mention": "region-a"}, {"mention": "edge"}]},
                               "targets": [{"metric": "bandwidth", "op": "ge", "value": 250, "unit": "Mbps"},
                                           {"metric": "latency", "op": "le", "value": 10, "unit": "ms"}]}], "_model": "fixture"}
    m, _, _, _ = build()
    m.llm = RecordedProvider(data={text: model})
    rec = m.submit(text)
    assert rec.readings["reader"] in ("model", "rules+model")
    if rec.readings["reader"] == "model":
        assert rec.state == State.CLARIFYING and rec.questions[0].field.startswith("confirm:")
    # agreement when both read the same thing
    rules = RuleReader({}).read("Connect region-a and edge with 300 Mbps")
    same = to_reading({"expectations": [e.model_dump() for e in rules.expectations]}, "fixture")
    _, info = merge(rules, same)
    assert info["agreement"] == 1.0 and info["reader"] == "rules+model"


def test_device_features_go_to_the_v1_pipeline():
    m, _, _, _ = build()
    calls = []
    m.legacy = lambda text: calls.append(text) or {"intent_id": "v1-1", "status": "applied"}
    r = say(m, "Enable PTP G.8275.1 timing on radio-2")
    rec = m.store.get(r["intent"]["id"])
    assert rec.expectations[0].action["legacy_type"] == "sync" and rec.state == State.CHECKED
    say(m, "approve")
    assert calls == ["Enable PTP G.8275.1 timing on radio-2"] and m.store.get(rec.id).state == State.ACTIVE
