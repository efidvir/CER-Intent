"""The radio emulator answers the Ceragon RESTCONF client the way a MultiHaul TG does."""
from __future__ import annotations

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "emulation"))

from radio_emulator import RadioState, serve  # noqa: E402

from ceragon_tfs_adapter.client import CeragonRestClient  # noqa: E402
from ceragon_tfs_adapter.config import AdapterConfig  # noqa: E402


@pytest.fixture
def radio():
    state = RadioState("radio-a", "MH-T261", "EMU-0001")
    httpd = serve(state, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    client = CeragonRestClient(AdapterConfig(device_ip="127.0.0.1", device_port=port, model_hint=None))
    yield state, client, f"http://127.0.0.1:{port}"
    httpd.shutdown()


def test_detected_and_parsed_as_a_multihaul_tg(radio):
    _, client, _ = radio
    ok, msg = client.test_connection()
    assert ok and client.device_flavor == "terragraph"
    state = client.get_device_state()
    assert (state.model, state.node_name, state.serial_number) == ("MH-T261", "radio-a", "EMU-0001")
    assert [s.index for s in state.sectors] == [1] and state.sectors[0].frequency_mhz == 60480.0
    assert state.active_links[0].speed_tx_mbps == 1800.0


def test_slice_is_staged_then_committed_then_deleted(radio):
    state, client, _ = radio
    client.test_connection()
    ok, _ = client.apply_vlan_slice(vlan_id=300, slice_name="svc-a", endpoints=["eth1", "rf"])
    assert ok and state.running["bridges"] == {}          # staged only
    assert client.commit_candidate()[0] is True
    (bridge,) = state.running["bridges"].values()
    assert [p["interface"] for p in bridge["bridge-port"]] == ["eth1", "rf"]
    assert client.delete_vlan_slice(vlan_id=300)[0] is True
    client.commit_candidate()
    assert state.running["bridges"] == {}


def test_discard_drops_staged_changes(radio):
    state, client, _ = radio
    client.test_connection()
    client.apply_vlan_slice(vlan_id=120, slice_name="x")
    client.discard_candidate()
    client.commit_candidate()
    assert state.running["bridges"] == {}


def test_radio_tuning_reaches_the_sector(radio):
    state, client, _ = radio
    client.test_connection()
    assert client.apply_radio_tuning(frequency_mhz=62640, sector_index=1)[0] is True
    client.commit_candidate()
    assert state.running["sectors"][1]["frequency"] == "62640"


def test_link_conditions_change_what_the_driver_reads(radio):
    _, client, base = radio
    client.test_connection()
    req = urllib.request.Request(f"{base}/emulator/link", data=json.dumps({"speed_mbps": 600, "snr": 9}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert json.loads(resp.read())["speed_mbps"] == 600.0
    link = client.get_device_state().active_links[0]
    assert (link.speed_tx_mbps, link.snr_db) == (600.0, 9.0)
