"""Reading words into expectations: kinds, objects, values, times, conditions and scope."""
from __future__ import annotations

import datetime as dt

import pytest

from cer_intent.imf.model import Kind
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.reader import RuleReader, split_clauses
from cer_intent.imf.timex import find_times, window_bounds

NOW = dt.datetime(2026, 11, 25, 10, 0)          # a Wednesday


@pytest.fixture(scope="module")
def reader():
    return RuleReader(NetworkModel.demo().names(), NOW)


def one(reader, text):
    r = reader.read(text)
    assert len(r.expectations) == 1, [e.summary() for e in r.expectations]
    return r.expectations[0]


def test_a_delivery_with_its_floor_in_the_same_sentence(reader):
    e = one(reader, "I need 120 Mbps between region-a and edge, keep MCS5 or better")
    assert e.kind == Kind.DELIVER
    assert [x.mention for x in e.object.endpoints] == ["region-a", "edge"]
    assert (e.value("bandwidth"), e.value("modulation_floor")) == (120.0, "MCS5")


def test_names_are_matched_however_they_are_written(reader):
    e = one(reader, "Build a slice Region A to the edge carrying 300 mbps")
    assert [x.mention.lower() for x in e.object.endpoints] == ["region a", "edge"]


def test_relative_changes(reader):
    assert one(reader, "Add 50 Mbps to the backhaul").action["op"] == "add"
    e = one(reader, "Give the backhaul 50% more")
    assert e.kind == Kind.CHANGE and e.action["op"] == "scale" and e.action["value"] == pytest.approx(1.5)
    e = one(reader, "Double the backhaul tonight 20:00-23:00, then restore it")
    assert e.action["revert"] and e.context("window").params["start"] == "20:00"


def test_units_after_at_are_not_times(reader):
    e = one(reader, "Link edge to region-a at 0.2 Gbps, keep MCS5 or better")
    assert e.value("bandwidth") == 200.0 and e.context("window") is None


def test_twenty_four_hour_ranges_cross_midnight():
    ctx, _ = find_times("Suspend the backhaul tonight 22:00-02:00", NOW)
    w = ctx[0].params
    assert (w["start"], w["end"]) == ("22:00", "02:00")
    start, end = window_bounds(w, NOW)
    assert end - start == dt.timedelta(hours=4)
    # at 03:00 a nightly window that began yesterday is still open
    s, e = window_bounds({"start": "22:00", "end": "06:00"}, dt.datetime(2026, 11, 25, 3, 0))
    assert s == dt.datetime(2026, 11, 24, 22, 0) and e == dt.datetime(2026, 11, 25, 6, 0)


def test_a_list_after_a_colon_becomes_one_delivery_each(reader):
    r = reader.read("Stadium event Saturday 18:00-23:00: north 400 Mbps, south 300 Mbps, press 100 Mbps")
    assert [e.value("bandwidth") for e in r.expectations] == [400.0, 300.0, 100.0]
    assert all(e.context("window").params["days"] == ["sat"] for e in r.expectations)


def test_conditions_and_alerts(reader):
    e = one(reader, "Notify me if latency on the backhaul goes above 8 ms")
    c = e.context("condition").params
    assert (e.kind, c["metric"], c["op"], c["value"]) == (Kind.OBSERVE, "latency", "ge", 8.0)
    e = one(reader, "Alert me when the radio link drops below MCS6")
    assert e.context("condition").params == {"metric": "lowest_modulation", "op": "lt", "value": "MCS6", "unit": "MCS"}
    assert e.action["metrics"][0] == "lowest_modulation"


def test_rules(reader):
    assert one(reader, "Never let any hop go below MCS4").action == {"rule": "floor", "value": "MCS4"}
    assert one(reader, "Freeze all changes this weekend").action["rule"] == "freeze"
    assert one(reader, "Always keep 20% headroom on the radio link").action["rule"] == "headroom"


def test_it_after_a_delivery_is_that_delivery(reader):
    r = reader.read("Give region-a to edge 200 Mbps and never let it fall below 150 Mbps")
    d, k = r.expectations
    assert (d.kind, k.kind) == (Kind.DELIVER, Kind.KEEP) and k.action["of"] == d.id


def test_scope(reader):
    assert reader.read("Configure BGP on the core routers").out_of_scope
    assert reader.read("Book a meeting room for 3pm").out_of_scope
    assert reader.read("Tell me when it starts raining more than 30 mm/h").out_of_scope is None
    assert reader.read("What can you do?").out_of_scope is None


def test_clauses():
    assert [c for c, _, _ in split_clauses("Connect a and b with 300 Mbps and report its throughput every hour")] == \
        ["Connect a and b with 300 Mbps", "report its throughput every hour"]
    assert split_clauses("Suspend the backhaul tonight, then resume it") == [("Suspend the backhaul tonight", 0, True)]
