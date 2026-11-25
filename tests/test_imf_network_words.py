"""
Understanding from the network at hand: what devices report about themselves (discovery),
the words the network gives its parts (vocabulary), parts described rather than named
(referents), live radio state in answers and checks, and TeraFlowSDN services counted as load.
"""
from __future__ import annotations

import json

from cer_intent.imf import referents
from cer_intent.imf.discovery import Discovery, parse_device
from cer_intent.imf.model import State
from cer_intent.imf.network import NetworkModel
from imf_fakes import build, network_of

HOP = "radio-1|radio-2"


def device(name="radio-1", **live):
    """A device the way TeraFlowSDN returns it, with the views the Ceragon driver reports."""
    rules = {
        "/device/hardware_info": {"node_name": f"{name}-host", "model": "MH-T261", "vendor": "Ceragon", "software_version": "5.1"},
        "/device/capabilities": {"product_line": "MultiHaul TG", "role": "transport_mmwave_vband", "max_throughput_gbps": 1,
                                 "bands": [{"name": "V-band", "freq_min_ghz": 57, "freq_max_ghz": 71}],
                                 "channel_bandwidths_mhz": [2160]},
        "/radio/sector[1]": {"current_modulation": f"MCS-{live.get('mcs', 9)}", "snr_db": live.get("snr", 21.5),
                             "rsl_dbm": -48, "frequency_mhz": 60480, "tx_power_control": "auto"},
        "/interfaces/user-bridge": {"user-bridge": {"bridge": [{"bridge-port": [{"c-vlan": 100}, {"c-vlan": 300}]}]}},
    }
    return {"name": name, "device_type": "packet-radio-router", "device_operational_status": "ENABLED",
            "device_endpoints": [{"name": "eth1"}, {"name": "rf1"}],
            "device_config": {"config_rules": [{"custom": {"resource_key": k, "resource_value": json.dumps(v)}}
                                               for k, v in rules.items()]}}


def test_a_device_says_what_it_is_and_how_its_radio_runs():
    d = parse_device(device(mcs=7, snr=17.0))
    assert (d["hostname"], d["model"], d["family"], d["role"]) == ("radio-1-host", "MH-T261", "MultiHaul TG", "transport_mmwave_vband")
    assert d["bands"] == [{"name": "V-band", "min_ghz": 57, "max_ghz": 71}] and d["max_mbps"] == 1000.0
    assert d["endpoints"] == ["eth1", "rf1"] and d["bridged_vlans"] == [100, 300]
    assert {k: d["live"][k] for k in ("mcs", "snr_db", "rsl_dbm", "freq_mhz", "tx_power_control")} == \
        {"mcs": "MCS7", "snr_db": 17.0, "rsl_dbm": -48, "freq_mhz": 60480, "tx_power_control": "auto"}


def test_details_are_cached_and_radios_read_fresh():
    class Client:
        def __init__(self):
            self.calls = []

        def get_device(self, name, fresh=False):
            self.calls.append((name, fresh))
            if name == "broken":
                raise RuntimeError("timeout")
            return device(name)

    c = Client()
    disc = Discovery(client=lambda: c, ttl_s=60)
    out = disc.details(["radio-1", "region-a", "broken"], radios=["radio-1"])
    assert set(out) == {"radio-1", "region-a"} and "broken" in disc.errors
    assert ("radio-1", True) in c.calls and ("region-a", False) in c.calls
    n = len(c.calls)
    disc.details(["radio-1", "region-a"], radios=["radio-1"])
    assert len(c.calls) == n                                         # within the TTL: no new reads
    disc.details(["radio-1"], radios=["radio-1"], force=True)
    assert len(c.calls) == n + 1


def test_the_network_names_its_parts_in_its_own_words():
    net = NetworkModel.demo()
    phrases = {v["phrase"]: v["id"] for v in net.vocabulary()}
    assert phrases["60 GHz link"] == HOP and phrases["V-band hop"] == HOP and phrases["vlan 100 slice"] == "backhaul-ran"
    assert phrases["hop to edge"] == HOP and phrases["radio-1 to radio-2"] == HOP
    group = net.resolve("MH-T261 radios")
    assert group.status == "group" and [c[0] for c in group.candidates] == ["radio-1", "radio-2"]
    assert net.resolve("the 60 GHz hop").id == HOP


def test_parts_described_rather_than_named():
    net = NetworkModel.demo()

    def ids(text):
        return [(r.type, r.ids) for r in referents.find(text, net)]

    assert ids("what is on the slice on VLAN 100") == [("slice", ["backhaul-ran"])]
    assert ids("the 200 Mbps slice") == [("slice", ["backhaul-ran"])]
    assert ids("what runs over radio-1") == [("slice", ["backhaul-ran"])]
    assert ids("the busiest hop") == [("hop", [HOP])]
    assert ids("the radio at edge") == [("radio", ["radio-2"])]
    assert ids("the 60 GHz link") == [("hop", [HOP])]
    assert ids("the V-band radios") == [("radio", ["radio-1", "radio-2"])]


def test_the_weakest_hop_is_the_one_running_lowest_now():
    net = NetworkModel.demo()
    net.nodes["radio-2"].live = {"mcs": "MCS5"}
    found = referents.find("the weakest hop", net)
    assert found[0].ids == [HOP] and "MCS5" in found[0].why


def test_my_last_slice_and_degraded_intents_come_from_the_records():
    m, nsc, _, _ = build(twin=True)
    r = m.converse("a", "Connect region-a and edge with 50 Mbps")
    m.approve(r["intent"]["id"], who="operator", role="operator")
    rec = m.store.get(r["intent"]["id"])
    found = referents.find("my last slice", m.network(), m.store.all(), "operator")
    assert found and found[0].ids == [rec.name]
    rec.state = State.DEGRADED
    m.store.put(rec)
    assert referents.find("the degraded intents", m.network(), m.store.all())[0].ids == [rec.id]


def test_a_change_to_a_described_slice():
    m, _, _, _ = build()
    r = m.converse("t", "Give the VLAN 100 slice 50% more")
    e = m.store.get(r["intent"]["id"]).expectations[0]
    assert e.object.ids == ["backhaul-ran"] and e.value("bandwidth") == 300.0
    assert e.object.selector["described"] == ["VLAN 100 is used by backhaul-ran"]


def test_answers_carry_the_radios_live_state():
    m, nsc, _, _ = build()

    def net():
        n = network_of(nsc)
        n.nodes["radio-2"].live = {"mcs": "MCS8", "snr_db": 19.5, "rsl_dbm": -50, "freq_mhz": 60480}
        return n
    m._network = net
    r = m.converse("t", "What is the radio at edge doing?")
    assert "radio-2" in r["reply"] and "MCS8" in r["reply"] and "19.5 dB" in r["reply"]


def test_teraflowsdn_services_cer_intent_did_not_make_count_as_load():
    snap = {"topology": {"nodes": [{"id": "region-a"}, {"id": "radio-1", "radio": True}, {"id": "radio-2", "radio": True},
                                   {"id": "edge"}],
                         "links": [{"id": "l1", "a": "region-a", "b": "radio-1"}, {"id": "l2", "a": "radio-1", "b": "radio-2", "radio": True},
                                   {"id": "l3", "a": "radio-2", "b": "edge"}]},
            "slices": [],
            "services": [{"name": "legacy-l2", "status": "SERVICESTATUS_ACTIVE", "type": "L2NM", "endpoints": ["region-a", "edge"],
                          "capacity_mbps": 150, "vlans": {"region-a": 210, "edge": 210}, "ports": ["eth2", "eth2"]}]}
    net = NetworkModel.from_snapshot(snap)
    s = net.slices["legacy-l2"]
    assert s.source == "TeraFlowSDN" and s.path == ["region-a", "radio-1", "radio-2", "edge"] and s.vlans() == [210]
    assert net.load(net.hop("radio-1", "radio-2")) == 150.0
    assert [r.ids for r in referents.find("the slice on VLAN 210", net)] == [["legacy-l2"]]
