"""
Slice controller pipeline tests: Mapper -> Technology Selector -> Realizer
==========================================================================
The RFC 9543 requests below have the shape OpenSlice and TeraFlowSDN's own
tests use; the L2SM / L3SM payloads are checked against the fields
TeraFlowSDN's L2VPN / L3VPN interfaces read.
"""
from __future__ import annotations

import copy
import ipaddress
import json
from typing import Any, Dict, List

import pytest

from cer_intent.nsc import reset_shared_controller, shared_controller
from cer_intent.nsc.mapper import MappingError, map_request
from cer_intent.nsc.nsc_controller import NetworkSliceController
from cer_intent.nsc.realizer import RealizationError, build_l2sm, build_l3sm, build_rfc9543
from cer_intent.nsc.technology_selector import L2VPN, L3VPN, select_technology


def _sdp(sdp_id: str, node: str, tp: str, ip: str = None, vlan: str = None, prefix: str = None) -> Dict[str, Any]:
    match = []
    if vlan:
        match.append({"type": "ietf-network-slice-service:vlan", "value": [vlan]})
    if prefix:
        match.append({"type": "ietf-network-slice-service:source-ip-prefix", "value": [prefix]})
    sdp = {
        "id": sdp_id,
        "node-id": node,
        "attachment-circuits": {"attachment-circuit": [{"id": "0", "ac-node-id": node, "ac-tp-id": tp}]},
        "service-match-criteria": {"match-criterion": [{
            "index": 1, "match-type": match, "target-connection-group-id": "line1"}]},
    }
    if ip:
        sdp["sdp-ip-address"] = [ip]
    return sdp


def rfc9543(prefixed: bool = False, with_ip: bool = True, vlan: str = "300", technology: str = None) -> Dict[str, Any]:
    slos = [
        {"metric-type": "ietf-network-slice-service:one-way-delay-maximum", "metric-unit": "milliseconds", "bound": 10},
        {"metric-type": "ietf-network-slice-service:one-way-bandwidth", "metric-unit": "Mbps", "bound": 500},
    ]
    service = {
        "id": "slice-a",
        "description": "site A to site B",
        "sdps": {"sdp": [
            _sdp("1", "pe-1", "ge-0/0/1", "10.10.1.1" if with_ip else None, vlan, "172.16.1.0/24" if with_ip else None),
            _sdp("2", "pe-2", "ge-0/0/1", "10.10.2.1" if with_ip else None, vlan),
        ]},
        "connection-groups": {"connection-group": [{
            "id": "line1", "connectivity-type": "point-to-point",
            "connectivity-construct": [
                {"id": 1, "p2p-sender-sdp": "1", "p2p-receiver-sdp": "2",
                 "service-slo-sle-policy": {"slo-policy": {"metric-bound": slos}}},
                {"id": 2, "p2p-sender-sdp": "2", "p2p-receiver-sdp": "1",
                 "service-slo-sle-policy": {"slo-policy": {"metric-bound": [
                     {"metric-type": "ietf-network-slice-service:one-way-delay-maximum",
                      "metric-unit": "milliseconds", "bound": 20},
                     {"metric-type": "ietf-network-slice-service:one-way-bandwidth",
                      "metric-unit": "Mbps", "bound": 1000},
                 ]}}},
            ],
        }]},
    }
    if technology:
        service["realization_technology"] = technology
    key = "ietf-network-slice-service:network-slice-services" if prefixed else "network-slice-services"
    return {key: {"slice-service": [service]}}


# ── Mapper ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prefixed", [False, True])
def test_mapper_reads_endpoints_slos_connectivity_and_acs(prefixed):
    mapped = map_request(rfc9543(prefixed=prefixed))
    assert mapped.slice_id == "slice-a"
    a, b = mapped.endpoints
    assert (a.node_id, a.tp_id, a.ip_address, a.vlan_id) == ("pe-1", "ge-0/0/1", "10.10.1.1", 300)
    assert a.source_prefixes == ["172.16.1.0/24"] and a.prefix_length == 24
    assert a.attachment_circuits[0].tp_id == "ge-0/0/1"
    (group,) = mapped.connection_groups
    assert [(c.sender_sdp, c.receiver_sdp) for c in group.constructs] == [("1", "2"), ("2", "1")]
    # one SLO set for the slice: tightest latency, largest bandwidth
    assert mapped.slos.max_latency_ms == 10 and mapped.slos.bandwidth_mbps == 1000


def test_mapper_compact_form_with_template():
    nsc = NetworkSliceController(realization_mode="dry-run")
    mapped = map_request({
        "id": "slice-b",
        "sdps": [{"node_id": "pe-1", "tp_id": "eth1", "vlan_id": 120}, {"node_id": "pe-2", "tp_id": "eth1", "vlan_id": 120}],
        "slo_sle_template_ref": "template-urllc-mission-critical",
        "radio": {"frequency_mhz": 62640},
    }, nsc.templates)
    assert mapped.slos.max_latency_ms == 1.5 and mapped.slos.bandwidth_mbps == 500.0
    assert mapped.sles["isolation"] == "physical-or-dedicated-time-slot"
    assert mapped.extensions == {"radio": {"frequency_mhz": 62640}}
    assert mapped.source_format == "compact"


@pytest.mark.parametrize("request_body,message", [
    ({"id": "x", "sdps": [{"node_id": "pe-1", "tp_id": "eth1"}]}, "two SDPs"),
    ({"id": "x", "sdps": [{"node_id": "pe-1", "tp_id": "eth1"}, {"tp_id": "eth1"}]}, "node-id"),
    ({"sdps": []}, "needs an id"),
])
def test_mapper_rejects_incomplete_requests(request_body, message):
    with pytest.raises(MappingError, match=message):
        map_request(request_body)


# ── Technology Selector ─────────────────────────────────────────────────────────

def test_selector_rules():
    assert select_technology(map_request(rfc9543())).technology == L3VPN
    vlan_only = select_technology(map_request(rfc9543(with_ip=False)))
    assert (vlan_only.technology, vlan_only.decided_by) == (L2VPN, "rule")
    requested = select_technology(map_request(rfc9543(technology="L2SM")))
    assert (requested.technology, requested.decided_by) == (L2VPN, "request")


def test_selector_skill_and_default(monkeypatch):
    mapped = map_request(rfc9543())
    chosen = select_technology(mapped, skill=lambda m: ("L2VPN", "radio hop carries L2 only"))
    assert (chosen.technology, chosen.decided_by, chosen.reason) == (L2VPN, "skill", "radio hop carries L2 only")

    def broken(_):
        raise RuntimeError("model unavailable")
    assert select_technology(mapped, skill=broken).decided_by == "rule"

    neither = map_request(rfc9543(with_ip=False, vlan=None))
    monkeypatch.setenv("NSC_DEFAULT_TECHNOLOGY", "L2VPN")
    assert select_technology(neither).technology == L2VPN
    monkeypatch.delenv("NSC_DEFAULT_TECHNOLOGY")
    assert select_technology(neither).technology == L3VPN


# ── Realizer payloads ───────────────────────────────────────────────────────────

def test_l3sm_has_the_fields_teraflowsdn_reads():
    payload, defaults = build_l3sm(map_request(rfc9543()))
    assert defaults == {"prefix-length": 24}  # SDP 2 gives an address without a prefix
    svc = payload["ietf-l3vpn-svc:l3vpn-svc"]
    assert svc["vpn-services"]["vpn-service"] == [{"vpn-id": "slice-a"}]
    site = svc["sites"]["site"][0]
    assert site["management"]["type"] == "ietf-l3vpn-svc:provider-managed"
    sna = site["site-network-accesses"]["site-network-access"][0]
    assert (sna["site-network-access-id"], sna["device-reference"]) == ("ge-0/0/1", "pe-1")
    assert sna["site-network-access-type"] == "ietf-l3vpn-svc:multipoint"
    assert sna["vpn-attachment"] == {"vpn-id": "slice-a", "site-role": "ietf-l3vpn-svc:hub-role"}
    addresses = sna["ip-connection"]["ipv4"]["addresses"]
    assert addresses["provider-address"] == "10.10.1.1" and addresses["prefix-length"] == 24
    assert sna["service"]["svc-input-bandwidth"] == 1_000_000_000
    qos = sna["service"]["qos"]["qos-profile"]["classes"]["class"][0]
    assert qos["class-id"] == "qos-realtime" and qos["latency"]["latency-boundary"] == 10
    # TeraFlowSDN takes the access VLAN from a static route with a next hop inside the provider range
    route = site["routing-protocols"]["routing-protocol"][0]["static"]["cascaded-lan-prefixes"]["ipv4-lan-prefixes"][0]
    assert route["lan-tag"] == "300" and route["lan"] == "172.16.1.0/24"
    assert ipaddress.ip_address(route["next-hop"]) in ipaddress.ip_network("10.10.1.1/24", strict=False)
    assert svc["sites"]["site"][1]["site-network-accesses"]["site-network-access"][0]["vpn-attachment"]["site-role"] \
        == "ietf-l3vpn-svc:spoke-role"


def test_l3sm_needs_addresses_and_bandwidth():
    with pytest.raises(RealizationError, match="IP address"):
        build_l3sm(map_request(rfc9543(with_ip=False)))
    no_bw = map_request({"id": "s", "sdps": [{"node_id": "a", "tp_id": "1", "ip_address": "10.0.0.1/30"},
                                             {"node_id": "b", "tp_id": "1", "ip_address": "10.0.0.2/30"}]})
    with pytest.raises(RealizationError, match="bandwidth"):
        build_l3sm(no_bw)


def test_l3sm_records_the_default_latency():
    mapped = map_request({"id": "s", "bandwidth_mbps": 100,
                          "sdps": [{"node_id": "a", "tp_id": "1", "ip_address": "10.0.0.1/30"},
                                   {"node_id": "b", "tp_id": "1", "ip_address": "10.0.0.2/30"}]})
    payload, defaults = build_l3sm(mapped)
    assert defaults == {"latency-boundary": 100.0}


def test_l2sm_has_the_fields_teraflowsdn_reads():
    payload, _ = build_l2sm(map_request(rfc9543(with_ip=False)))
    svc = payload["ietf-l2vpn-svc:l2vpn-svc"]
    assert svc["vpn-services"]["vpn-service"][0]["vpn-svc-type"] == "vpws"
    sna = svc["sites"]["site"][0]["site-network-accesses"]["site-network-access"][0]
    assert sna["bearer"]["bearer-reference"] == "pe-1:ge-0/0/1"
    assert sna["connection"]["tagged-interface"]["dot1q-vlan-tagged"]["cvlan-id"] == 300
    assert sna["service"]["svc-output-bandwidth"] == 1_000_000_000


def test_rfc9543_for_a_teraflowsdn_slice_controller():
    out = build_rfc9543(map_request(rfc9543()))
    svc = out["network-slice-services"]["slice-service"][0]
    sdps = svc["sdps"]["sdp"]
    assert len(sdps) == 2 and all(len(s["attachment-circuits"]["attachment-circuit"]) == 1 for s in sdps)
    assert all(len(s["sdp-ip-address"]) == 1 for s in sdps)
    criterion = sdps[0]["service-match-criteria"]["match-criterion"][0]
    assert criterion["target-connection-group-id"] == "line1"
    assert {"type": "ietf-network-slice-service:vlan", "value": ["300"]} in criterion["match-type"]
    constructs = svc["connection-groups"]["connection-group"][0]["connectivity-construct"]
    bounds = constructs[0]["service-slo-sle-policy"]["slo-policy"]["metric-bound"]
    assert {"metric-type": "ietf-network-slice-service:one-way-bandwidth", "metric-unit": "Mbps", "bound": 500.0} in bounds


# ── Controller end to end, against a fake TeraFlowSDN ──────────────────────────

class FakeTFS:
    def __init__(self, fail: bool = False) -> None:
        self.calls: List[tuple] = []
        self.fail = fail

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if self.fail and name.startswith("create"):
                raise RuntimeError("HTTP 500")
            return {}
        return record

    def names(self) -> List[str]:
        """Calls that change or verify TeraFlowSDN state (the planner's topology reads are left out)."""
        return [c[0] for c in self.calls if c[0] != "fetch_normalized_topology"]


def _with_radio(body: Dict[str, Any]) -> Dict[str, Any]:
    body = copy.deepcopy(body)
    body["network-slice-services"]["slice-service"][0]["radio"] = {"frequency_mhz": 62640}
    body["network-slice-services"]["slice-service"][0]["acm"] = {"min_modulation": "MCS4"}
    return body


def test_controller_realizes_l3vpn_and_sends_radio_settings():
    tfs = FakeTFS()
    nsc = NetworkSliceController(tfs_client=tfs, realization_mode="ietf")
    res = nsc.create_or_update_slice_service(_with_radio(rfc9543()))
    pipeline = res["nsc_pipeline"]
    assert pipeline["technology_selector"]["technology"] == L3VPN
    assert pipeline["realizer"]["status"] == "sent"
    assert tfs.names() == ["create_l3vpn", "update_service_settings"]
    settings_call = next(c for c in tfs.calls if c[0] == "update_service_settings")
    assert settings_call[1] == ("slice-a", {"radio": {"frequency_mhz": 62640}, "acm": {"min_modulation": "MCS4"}})
    assert pipeline["planner"]["feasible"] is None  # endpoints outside the twin topology: not checked
    slice_tree = res["ietf-network-slice-service:network-slice-services"]["slice-service"][0]
    assert slice_tree["id"] == "slice-a"
    assert nsc.slices["slice-a"].status == "active"

    assert nsc.delete_slice_service("slice-a") == {"slice_id": "slice-a", "status": "withdrawn"}
    assert tfs.names()[-1] == "delete_l3vpn" and "slice-a" not in nsc.slices
    assert nsc.delete_slice_service("slice-a") is None


def test_controller_delegates_rfc9543_in_nsc_mode():
    tfs = FakeTFS()
    nsc = NetworkSliceController(tfs_client=tfs, realization_mode="nsc")
    res = nsc.create_or_update_slice_service(_with_radio(rfc9543()))
    assert tfs.names() == ["create_network_slice"]
    assert "network-slice-services" in res["nsc_pipeline"]["realizer"]["payload"]


def test_controller_reports_controller_failures():
    nsc = NetworkSliceController(tfs_client=FakeTFS(fail=True), realization_mode="ietf")
    res = nsc.create_or_update_slice_service(rfc9543())
    assert res["nsc_pipeline"]["realizer"]["status"] == "failed"
    assert nsc.slices["slice-a"].status == "failed"


def test_controller_legacy_tfs_api_mode():
    tfs = FakeTFS()
    nsc = NetworkSliceController(tfs_client=tfs, realization_mode="tfs-api")
    nsc.create_or_update_slice_service(rfc9543())
    assert tfs.names() == ["create_or_update_slice"]


def test_controller_returns_400_for_unmappable_requests():
    res = NetworkSliceController(realization_mode="dry-run").create_or_update_slice_service({"id": "x"})
    assert res["status"] == 400 and res["stage"] == "mapper"


def test_controller_returns_400_when_the_technology_cannot_carry_the_slice():
    res = NetworkSliceController(realization_mode="dry-run").create_or_update_slice_service(
        rfc9543(with_ip=False, technology="L3VPN"))
    assert res["status"] == 400 and res["stage"] == "realizer"


# ── Intent pipeline: slice intents with endpoints go through the controller ────

def test_slice_intent_with_endpoints_goes_to_the_slice_controller(tmp_path, monkeypatch):
    from cer_intent.intent_schema import Intent
    from cer_intent.translators.slice_translator import SLICE_CONTROLLER_TARGET, SliceTranslator

    intent = Intent(
        intent_type="slice",
        target={"target_type": "node", "identifier": "pe-1"},
        parameters={
            "slice_name": "urllc-a", "slice_type": "URLLC", "vlan_id": 210, "bandwidth_mbps": 200,
            "max_latency_ms": 5, "acm": {"min_modulation": "MCS6"},
            "sdps": [{"node_id": "pe-1", "tp_id": "eth1", "ip_address": "10.1.0.1/30"},
                     {"node_id": "pe-2", "tp_id": "eth1", "ip_address": "10.1.0.2/30"}],
        },
    )
    result = SliceTranslator().translate(intent, [{"id": "pe-1"}])
    (config,) = result.device_configs
    assert (config.device_id, config.config_type) == (SLICE_CONTROLLER_TARGET, "slice_service")
    assert config.parameters["sdps"][0]["vlan_id"] == 210

    from cer_intent.device.adapter import TeraFlowAdapter
    from cer_intent.device.state_store import StateStore

    reset_shared_controller()
    monkeypatch.setenv("TFS_REALIZATION", "ietf")
    adapter = TeraFlowAdapter(StateStore())
    tfs = FakeTFS()
    adapter._tfs_client = tfs  # pylint: disable=protected-access
    outcome = adapter.apply(config, conflict_token="tok-1")
    assert outcome.success is True
    assert outcome.readback_evidence["verified"] is True       # get_service answered
    assert outcome.readback_evidence["technology"] == L3VPN
    assert tfs.names() == ["create_l3vpn", "update_service_settings", "get_service"]
    assert "slice-urllc-a" in shared_controller().slices
    reset_shared_controller()


# ── TFS client: service settings and VPN error lists ───────────────────────────

class FakeResponse:
    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status_code = status
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return copy.deepcopy(self._body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses: Dict[tuple, FakeResponse]) -> None:
        self.responses = responses
        self.sent: List[tuple] = []
        self.headers = {}

    def _answer(self, method, url, **kwargs):
        self.sent.append((method, url, kwargs.get("json")))
        for (m, suffix), resp in self.responses.items():
            if m == method and url.endswith(suffix):
                return resp
        return FakeResponse(404, {"error": "not found"})

    def get(self, url, **kw):
        return self._answer("GET", url, **kw)

    def put(self, url, **kw):
        return self._answer("PUT", url, **kw)

    def request(self, method, url, **kw):
        return self._answer(method, url, **kw)


def test_update_service_settings_merges_and_puts_by_uuid():
    from cer_intent.device.tfs_client import TFSClient

    stored = {"service_id": {"context_id": {"context_uuid": {"uuid": "ctx-uuid"}}, "service_uuid": {"uuid": "svc-uuid"}},
              "service_config": {"config_rules": [{"action": 1, "custom": {
                  "resource_key": "/settings", "resource_value": json.dumps({"address_families": ["IPV4"], "mtu": 1500})}}]}}
    client = TFSClient(base_url="http://tfs.example")
    client._session = FakeSession({  # pylint: disable=protected-access
        ("GET", "/tfs-api/context/admin/service/slice-a"): FakeResponse(200, stored),
        ("PUT", "/tfs-api/context/ctx-uuid/service/svc-uuid"): FakeResponse(200, {"ok": True}),
    })
    client.update_service_settings("slice-a", {"acm": {"min_modulation": "MCS4"}})
    method, url, body = client._session.sent[-1]  # pylint: disable=protected-access
    assert (method, url) == ("PUT", "http://tfs.example/tfs-api/context/ctx-uuid/service/svc-uuid")
    settings = json.loads(body["service_config"]["config_rules"][0]["custom"]["resource_value"])
    assert settings == {"address_families": ["IPV4"], "mtu": 1500, "acm": {"min_modulation": "MCS4"}}


def test_vpn_error_lists_are_raised():
    from cer_intent.device.tfs_client import TFSClient

    client = TFSClient(base_url="http://tfs.example")
    client._session = FakeSession({  # pylint: disable=protected-access
        ("POST", "/vpn-services"): FakeResponse(201, [{"error": "Bearer(x) not found"}]),
    })
    with pytest.raises(RuntimeError, match="Bearer"):
        client.create_l2vpn({"ietf-l2vpn-svc:l2vpn-svc": {}})


# ── RFC 9543 RESTCONF interface ─────────────────────────────────────────────────

def test_restconf_slice_interface(monkeypatch):
    from flask import Flask
    from cer_intent.api import restconf_routes

    monkeypatch.setenv("TFS_REALIZATION", "dry-run")
    reset_shared_controller()
    monkeypatch.setattr(restconf_routes, "_nsc_instance", None)
    app = Flask(__name__)
    app.config["adapter"] = None
    app.register_blueprint(restconf_routes.restconf_bp)
    client = app.test_client()
    base = "/restconf/data/ietf-network-slice-service:network-slice-services"

    bad = client.post(base, json={"network-slice-services": {"slice-service": [{"id": "x", "sdps": {"sdp": []}}]}})
    assert bad.status_code == 400 and "two SDPs" in bad.get_json()["error"]

    good = client.post(base, json=rfc9543())
    assert good.status_code == 201
    body = good.get_json()
    assert body["nsc_pipeline"]["realizer"]["status"] == "built"
    assert body["nsc_pipeline"]["realizer"]["model"] == "L3SM (RFC 8299)"

    assert client.get(f"{base}/slice-service=slice-a").status_code == 200
    assert client.delete(f"{base}/slice-service=slice-a").status_code == 204
    assert client.delete(f"{base}/slice-service=slice-a").status_code == 404
    reset_shared_controller()


# ── one modulation floor per radio hop ─────────────────────────────────────────

def _hop_slice(sid: str, vlan: int, floor: str = None) -> Dict[str, Any]:
    svc = {"id": sid, "bandwidth_mbps": 100, "realization_technology": "L2VPN",
           "sdps": [{"id": "1", "node_id": "region-a", "tp_id": "eth1", "vlan_id": vlan},
                    {"id": "2", "node_id": "edge", "tp_id": "eth1", "vlan_id": vlan}]}
    if floor:
        svc["acm"] = {"min_modulation": floor}
    return svc


def test_radios_carry_the_highest_floor_asked_and_drop_back_when_slices_leave(monkeypatch):
    from cer_intent.nsc.nsc_controller import floor_rank

    assert floor_rank("MCS6") > floor_rank("MCS4") > 0 and floor_rank("256QAM") > floor_rank("16-QAM") > floor_rank("qpsk")
    tfs = FakeTFS()
    nsc = NetworkSliceController(tfs_client=tfs, realization_mode="ietf")
    monkeypatch.setattr(nsc.planner, "compute_constrained_path",
                        lambda **kw: {"computed_path": ["region-a", "radio-1", "radio-2", "edge"], "feasible": True})
    monkeypatch.setenv("CER_ACM_BASELINE_FLOOR", "MCS1")

    def settings_since(n):
        return [(c[1][0], c[1][1]["acm"]["min_modulation"]) for c in tfs.calls[n:] if c[0] == "update_service_settings"]

    nsc.create_or_update_slice_service(_hop_slice("a", 300, "MCS4"))
    nsc.create_or_update_slice_service(_hop_slice("plain", 320))
    n = len(tfs.calls)
    res = nsc.create_or_update_slice_service(_hop_slice("b", 310, "MCS6"))
    assert settings_since(n) == [("b", "MCS6"), ("a", "MCS6")]          # a carries the hop's floor; plain carries none
    assert res["hop_floor"]["updated"] == ["a"]

    n = len(tfs.calls)
    res = nsc.create_or_update_slice_service(_hop_slice("c", 330, "MCS2"))
    assert settings_since(n) == [("c", "MCS6")] and res["hop_floor"]["requested"] == "MCS2"
    assert nsc.requests["c"]["acm"] == {"min_modulation": "MCS2"}          # what c asked is kept

    n = len(tfs.calls)
    res = nsc.delete_slice_service("b")
    assert sorted(settings_since(n)) == [("a", "MCS4"), ("c", "MCS4")]   # back to the highest that remains
    n = len(tfs.calls)
    nsc.delete_slice_service("a")
    assert settings_since(n) == [("c", "MCS2")]

    n = len(tfs.calls)
    res = nsc.delete_slice_service("c")                                   # the last floor hands back the baseline
    assert settings_since(n) == [("c", "MCS1")] and res["hop_floor"]["applied"] == "MCS1"
    assert [c[0] for c in tfs.calls[n:]][-1] == "delete_l2vpn"
    assert nsc.hop_floors == {}
