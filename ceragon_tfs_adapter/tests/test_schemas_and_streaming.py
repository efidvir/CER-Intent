"""
Tests for Complete YANG Schema Closure, Bidirectional Control (12 Domains),
and Real-Time Telemetry/Event Streaming across the Ceragon Portfolio.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple
import pytest

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.driver import TFSCeragonDriver
from ceragon_tfs_adapter.mapper import CeragonTFSMapper
from ceragon_tfs_adapter.schemas import (
    get_schema_content,
    get_schema_metadata,
    get_schemas_for_family,
    list_schemas,
    validate_schema_closure,
)


# ── 1. YANG Schema Bundle & Closure Verification ─────────────────────────────

def test_yang_schema_closure_and_completeness():
    ok, report = validate_schema_closure()
    assert ok is True, f"YANG closure failed: {report}"
    assert report["missing_dependencies"] == {}
    assert report["unbalanced_modules"] == []
    assert report["total_schemas"] == 84
    assert report["total_rpcs"] >= 15
    assert report["total_notifications"] >= 3


@pytest.mark.parametrize(
    "module_name,expected_scope",
    [
        ("radio-bridge-tg-radio-common", "siklu_tg"),
        ("radio-bridge-tg-radio-dn", "siklu_tg"),
        ("radio-bridge-tg-user-bridge", "siklu_tg"),
        ("radio-bridge-tg-bond", "siklu_tg"),
        ("radio-bridge-tg-pm", "siklu_tg"),
        ("radio-bridge-tg-events", "siklu_tg"),
        ("ietf-snmp-common", "standard"),
        ("ietf-snmp-usm", "standard"),
        ("ietf-snmp-vacm", "standard"),
        ("radio-bridge-eh-radio", "siklu_eh"),
        ("ceragon-common-types", "ceraos"),
        ("ceragon-radio-link", "ceraos"),
        ("ceragon-qos", "ceraos"),
        ("ceragon-protection", "ceraos"),
        ("ceragon-slice", "ceraos"),
        ("ceragon-multiband", "ceraos"),
        ("ceragon-sync", "ceraos"),
        ("ceragon-macsec", "ceraos"),
        ("ceragon-oran-xhaul", "ceraos"),
        ("ceragon-pm-telemetry", "ceraos"),
        ("ietf-microwave-radio-link", "ceraos"),
        ("ietf-interfaces", "standard"),
        ("ietf-hardware", "standard"),
        ("ietf-system", "standard"),
        ("ieee802-dot1q-sched", "standard"),
        ("ieee802-dot1ae-macsec", "standard"),
        ("ietf-ptp", "standard"),
    ],
)
def test_portfolio_yang_modules_present_and_parsed(module_name: str, expected_scope: str):
    content = get_schema_content(module_name)
    assert content is not None and len(content) > 100
    meta = get_schema_metadata(module_name)
    assert meta is not None
    assert meta["name"] == module_name
    assert meta["family_scope"] == expected_scope


def test_family_schema_filtering():
    tg_mods = get_schemas_for_family("siklu_tg")
    eh_mods = get_schemas_for_family("siklu_eh")
    cera_mods = get_schemas_for_family("ceraos")

    assert "radio-bridge-tg-radio-common" in tg_mods
    assert "radio-bridge-eh-radio" in eh_mods
    assert "ceragon-radio-link" in cera_mods
    assert "ietf-microwave-radio-link" in cera_mods


# ── 2. Bidirectional Control Across All 12 Domains & All 3 API Flavors ───────

class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, url: str = "https://10.0.0.1/restconf"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.url = url
        self.text = json.dumps(self._payload) if self._payload != "" else ""

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _MockRestSession:
    """Captures every GET/POST/PATCH/PUT/DELETE sent by CeragonRestClient."""

    def __init__(self, datastore_payload: Dict[str, Any]):
        self.datastore = datastore_payload
        self.calls: List[Tuple[str, str, Any]] = []
        self.auth = None
        self.headers: Dict[str, str] = {}
        self.verify = False

    def get(self, url: str, timeout: int = 10) -> _FakeResponse:
        self.calls.append(("GET", url, None))
        return _FakeResponse(200, {"ietf-restconf:data": self.datastore}, url=url)

    def patch(self, url: str, json: Any = None, timeout: int = 10) -> _FakeResponse:
        self.calls.append(("PATCH", url, json))
        return _FakeResponse(204, "", url=url)

    def put(self, url: str, json: Any = None, timeout: int = 10) -> _FakeResponse:
        self.calls.append(("PUT", url, json))
        return _FakeResponse(204, "", url=url)

    def delete(self, url: str, timeout: int = 10) -> _FakeResponse:
        self.calls.append(("DELETE", url, None))
        return _FakeResponse(204, "", url=url)

    def post(self, url: str, json: Any = None, timeout: int = 10) -> _FakeResponse:
        self.calls.append(("POST", url, json))
        if "get-events" in url:
            return _FakeResponse(200, {
                "radio-bridge-tg-events:output": {
                    "events": [
                        {
                            "index": 0,
                            "event": "2026-10-28 12:00:00.100, 201,SYSTEM, LOCAL,  RADIO,   Link peer-dn-1 state is Connected",
                        }
                    ]
                }
            }, url=url)
        if "get-pm-items" in url:
            return _FakeResponse(200, {
                "radio-bridge-tg-pm:output": {
                    "pm-items": [{"item-type": "rf", "names": [{"id": 0, "name": "peer-dn-1"}]}]
                }
            }, url=url)
        if "get-pm-item-info" in url:
            return _FakeResponse(200, {
                "radio-bridge-tg-pm:output": {
                    "pm-info-periods": [{
                        "index": 0,
                        "validity": True,
                        "completion-percentage": "100.00",
                        "scalar": [{"scalar-name": "rssi", "min": "-45.000", "max": "-40.000", "avg": "-42.000"}],
                    }]
                }
            }, url=url)
        if "get-pm-bins" in url:
            return _FakeResponse(200, {
                "ceragon-pm-telemetry:output": {
                    "bins": [{"bin-index": 0, "rsl-avg-dbm": -38.5, "tsl-avg-dbm": 18.0, "errored-seconds": 0}]
                }
            }, url=url)
        if "get-schema" in url:
            return _FakeResponse(200, {
                "ietf-netconf-monitoring:output": {"data": "module mock { namespace 'urn:mock'; prefix m; }"}
            }, url=url)
        return _FakeResponse(204, "", url=url)


def _make_ceraos_driver(model: str = "IP-50FX") -> Tuple[TFSCeragonDriver, _MockRestSession]:
    cfg = AdapterConfig(device_ip="10.20.30.40", model_hint=model)
    drv = TFSCeragonDriver(cfg)
    mock_sess = _MockRestSession({
        "ietf-system:system": {"hostname": f"node-{model.lower()}"},
        "ietf-hardware:hardware": {
            "component": [{
                "name": "chassis",
                "class": "iana-hardware:chassis",
                "model-name": model,
                "serial-num": f"SN-{model}-001",
                "hardware-rev": "2.0",
                "software-rev": "CeraOS-13.2",
            }]
        },
        "ietf-interfaces:interfaces": {
            "interface": [{
                "name": "eth-1/10G",
                "type": "iana-if-type:ethernetCsmacd",
                "speed": 10_000_000_000,
                "enabled": True,
                "oper-status": "up",
                "statistics": {"in-octets": 1250000, "out-octets": 2500000, "in-errors": 0, "out-errors": 0},
            }]
        },
        "ceragon-radio-link:radio-link-cfg": {
            "carrier": [{
                "id": 1,
                "admin-status": "up",
                "tx-frequency-mhz": 18000.0,
                "tx-power-dbm": 18.0,
                "xpic-enabled": True,
                "rsl-dbm": -39.5,
                "tsl-dbm": 18.0,
                "snr-db": 34.2,
                "current-modulation": "qam-4096",
                "current-capacity-mbps": 1850.0,
                "modem-temperature": 46,
                "rf-temperature": 42,
            }]
        },
    })
    drv.client._session = mock_sess
    drv.client._datastore_url = "https://10.20.30.40/restconf/data"
    drv.client._device_flavor = "ceraos"
    drv.sync_to_tfs = lambda *a, **kw: {"status": "mock_synced"}  # type: ignore[assignment]
    return drv, mock_sess


def _make_tg_driver(model: str = "MH-N366") -> Tuple[TFSCeragonDriver, _MockRestSession]:
    cfg = AdapterConfig(device_ip="192.168.1.225", model_hint=model)
    drv = TFSCeragonDriver(cfg)
    mock_sess = _MockRestSession({
        "radio-bridge-tg-system:system": {
            "name": "dn-pop-1",
            "state": {"product": model, "uptime": "00012:04:10:00"},
        },
        "radio-bridge-tg-inventory:inventory": {
            "component": [{
                "physical-class": "chassis",
                "model-name": model,
                "serial-num": f"SN-{model}-99",
                "hardware-rev": "B1",
                "software-rev": "3.4.0",
            }]
        },
        "radio-bridge-tg-interfaces:interfaces": {
            "interface": [{
                "ifIndex": 1,
                "name": "eth1",
                "ifDescr": "eth1 10G RJ45",
                "ifSpeed": 10_000_000_000,
                "admin-status": "up",
                "oper-status": "up",
                "ifInOctets": 987654,
                "ifOutOctets": 456789,
            }]
        },
        "radio-bridge-tg-radio-common:radio-common": {
            "node-config": {"operation-mode": "BU", "tx-power-control": "auto"},
            "sectors-config": {
                "sector": [{
                    "index": 1,
                    "admin-status": "up",
                    "state": {
                        "frequency": "60480",
                        "antenna-mode": "massive2",
                        "mac-addr": "00:11:22:33:44:55",
                        "temperatures": {"modem-temperature": 51, "rf": [{"index": 1, "rf-temperature": 48}]},
                    },
                }]
            },
            "links": {
                "active": [{
                    "remote-assigned-name": "peer-tu-1",
                    "actual-local-sector-index": 1,
                    "actual-remote-sector-index": 1,
                    "rssi": -44,
                    "snr": 24.5,
                    "mcs-tx": 12,
                    "mcs-rx": 12,
                    "speed-tx": 3800,
                    "speed-rx": 3800,
                    "beam-azimuth-tx": 15,
                    "beam-elevation-tx": -2,
                    "tx-ok": 50000,
                    "rx-ok": 49990,
                }]
            },
        },
    })
    drv.client._session = mock_sess
    drv.client._datastore_url = "https://192.168.1.225/restconf/ds/ietf-datastores:candidate"
    drv.client._device_flavor = "terragraph"
    drv.sync_to_tfs = lambda *a, **kw: {"status": "mock_synced"}  # type: ignore[assignment]
    return drv, mock_sess


def test_ceraos_all_control_domains_and_delete():
    drv, sess = _make_ceraos_driver("IP-50FX")
    resources = [
        ("/interface[name=IP-50FX]/slice", {"vlan_id": 250, "slice_name": "urllc-slice", "bandwidth_mbps": 1500, "s_vlan_id": 10}),
        ("/interface[name=IP-50FX]/radio", {"frequency_mhz": 18500.0, "tx_power_dbm": 20.0, "mrmc_script_id": 4501, "channel_bandwidth_mhz": 80.0}),
        ("/interface[name=IP-50FX]/acm", {"min_modulation": "qpsk", "max_modulation": "qam-4096", "adaptive_enabled": True}),
        ("/interface[name=IP-50FX]/qos", {"cir_mbps": 1000, "pir_mbps": 2000}),
        ("/interface[name=IP-50FX]/tsn", {"cycle_time_us": 500, "preemption_8021qbu": True}),
        ("/interface[name=IP-50FX]/multiband", {"bond_name": "mb-1", "member_interfaces": ["rf-eband-1", "rf-mw-1"]}),
        ("/interface[name=IP-50FX]/protection", {"protection_mode": "1+1_HSB", "group_id": 1, "trigger_switchover": True}),
        ("/interface[name=IP-50FX]/sync", {"sync_mode": "ptp", "ptp_profile": "itu-g8275-1", "domain_number": 24}),
        ("/interface[name=IP-50FX]/security", {"enabled": True, "cipher_suite": "gcm-aes-256"}),
        ("/interface[name=IP-50FX]/oran_xhaul", {"enabled": True, "iq_compression": "bfp-9bit", "delay_budget_us": 75}),
        ("/interface[name=IP-50FX]/energy", {"mode": "green-atpc", "target_rsl_dbm": -40.0, "sleep_secondary_carriers": True}),
    ]
    res = drv.set_config(resources)
    assert all(ok for _, ok, _ in res), f"Unexpected failure in CeraOS set_config: {res}"

    # Verify DeleteConfig removes the slice
    del_res = drv.delete_config([("/interface[name=IP-50FX]/slice", {"vlan_id": 250, "slice_name": "urllc-slice"})])
    assert del_res[0][1] is True
    assert any(method == "DELETE" and "ceragon-slice:slice-config/slice=urllc-slice" in url for method, url, _ in sess.calls)


def test_terragraph_all_supported_domains_and_two_phase_commit():
    drv, sess = _make_tg_driver("MH-N366")
    resources = [
        ("/interface[name=MH-N366]/slice", {"vlan_id": 120, "slice_name": "tg-slice-120", "endpoints": ["eth1", "rf"]}),
        ("/interface[name=MH-N366]/radio", {"frequency_mhz": 62640.0, "tx_power_dbm": 22.0, "admin_status": "up"}),
        ("/interface[name=MH-N366]/beamforming", {"sector_index": 1, "trigger_topo_scan": True}),
        ("/interface[name=MH-N366]/protection", {"protection_mode": "active-backup", "group_id": 1}),
        ("/interface[name=MH-N366]/sync", {"sync_mode": "ptp"}),
    ]
    res = drv.set_config(resources, auto_commit=True)
    assert all(ok for _, ok, _ in res), f"Unexpected failure in TG set_config: {res}"
    # Verify two-phase candidate commit RPC was invoked
    assert any(method == "POST" and "ietf-netconf:commit" in url for method, url, _ in sess.calls)
    # Verify start-topo-scan RPC was invoked for beamforming
    assert any(method == "POST" and "radio-bridge-tg-radio-dn:start-topo-scan" in url for method, url, _ in sess.calls)
    # Verify real user-bridge path was patched for VLAN slice
    assert any(method == "PATCH" and "radio-bridge-tg-user-bridge:user-bridge/bridge=" in url for method, url, _ in sess.calls)
    # Verify TG active-backup bond was patched for protection
    assert any(method == "PATCH" and "radio-bridge-tg-bond:bonds/bond=bond-1" in url for method, url, _ in sess.calls)


# ── 3. Bidirectional Telemetry, PM Intervals & Event Streaming ───────────────

def test_telemetry_and_event_streaming_both_ways():
    drv, _ = _make_tg_driver("MH-N366")
    sample = drv.client.fetch_pm_telemetry(period_type="quarter")
    d = sample.to_dict()

    assert d["model"] == "MH-N366"
    assert d["api_flavor"] == "siklu_tg"
    assert d["rsl_dbm"] == -44.0
    assert d["snr_db"] == 24.5
    assert d["modulation"] == "MCS-12"
    assert d["air_capacity_mbps"] == 3800.0
    assert d["in_octets_total"] == 987654
    assert len(d["active_links"]) == 1
    assert d["active_links"][0]["remote_assigned_name"] == "peer-tu-1"
    assert len(d["pm_intervals"]) == 1
    assert len(d["recent_events"]) == 1
    assert d["recent_events"][0]["subsystem"] == "RADIO"

    # Mapper converts sample into TFS northbound config rules
    tfs_rules = CeragonTFSMapper.to_tfs_telemetry_rules(sample)
    keys = [r["custom"]["resource_key"] for r in tfs_rules]
    assert "/device/pm_telemetry" in keys
    assert "/device/events" in keys

    # GetConfig retrieves live telemetry, events, and YANG schema content
    cfg_items = dict(drv.get_config(["/device/pm_telemetry", "/device/events", "/yang/ceragon-radio-link"]))
    assert cfg_items["/device/pm_telemetry"]["rsl_dbm"] == -44.0
    assert len(cfg_items["/device/events"]) == 1
    assert "module mock" in cfg_items["/yang/ceragon-radio-link"]

    # SubscribeState & UnsubscribeState lifecycle
    sub_res = drv.subscribe_state([("/device/pm_telemetry", 60.0, 0.5)])
    assert sub_res[0][1] is True
    unsub_res = drv.unsubscribe_state([("/device/pm_telemetry", 60.0, 0.5)])
    assert unsub_res[0][1] is True
