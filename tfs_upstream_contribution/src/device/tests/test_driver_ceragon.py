# Copyright 2026 Ceragon Networks Ltd. & ETSI TeraFlowSDN Authors
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit Tests for Ceragon Wireless Transport Driver
=================================================
Validates the driver lifecycle, candidate datastore mutations,
endpoint discovery, and YANG schema compliance for ETSI TeraFlowSDN.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from requests import Response

from device.service.driver_api._Driver import RESOURCE_ENDPOINTS
from device.service.drivers.ceragon.CeragonDriver import CeragonDriver
from device.service.drivers.ceragon.schemas import get_all_schemas, list_available_schemas


@pytest.fixture
def mock_ceragon_driver():
    """Returns a CeragonDriver instance with default settings."""
    return CeragonDriver(
        address="192.168.1.225",
        port=80,
        username="admin",
        password="admin",
        timeout=5,
    )


def test_driver_initialization(mock_ceragon_driver):
    assert mock_ceragon_driver.name == "ceragon"
    assert mock_ceragon_driver.address == "192.168.1.225"
    assert mock_ceragon_driver.port == 80
    assert mock_ceragon_driver.settings.get("username") == "admin"


def test_driver_connect_success(mock_ceragon_driver):
    mock_resp = Response()
    mock_resp.status_code = 200

    with patch.object(mock_ceragon_driver._client.session, "get", return_value=mock_resp):
        ok = mock_ceragon_driver.Connect()
        assert ok is True
        # Re-connect should be idempotent
        assert mock_ceragon_driver.Connect() is True


def test_driver_connect_failure(mock_ceragon_driver):
    mock_resp = Response()
    mock_resp.status_code = 401

    with patch.object(mock_ceragon_driver._client.session, "get", return_value=mock_resp):
        ok = mock_ceragon_driver.Connect()
        assert ok is False


def test_driver_get_initial_config(mock_ceragon_driver):
    initial_config = mock_ceragon_driver.GetInitialConfig()
    assert isinstance(initial_config, list)
    assert len(initial_config) >= 4

    config_dict = dict(initial_config)
    assert RESOURCE_ENDPOINTS in config_dict

    endpoints = config_dict[RESOURCE_ENDPOINTS]
    assert len(endpoints) == 3
    ep_names = [ep[0] for ep in endpoints]
    assert "ctu-96:eth1" in ep_names
    assert "ctu-96:rf-sector-1" in ep_names
    assert "ctu-96:Host" in ep_names

    # Check hardware info
    assert "/device/hardware_info" in config_dict
    hw = json.loads(config_dict["/device/hardware_info"])
    assert hw["vendor"] == "Ceragon"
    assert hw["model"] == "MH-T261"
    assert hw["serial_number"] == "AE09100255"

    # Check operating parameters
    assert "/device/operating_parameters" in config_dict
    op = json.loads(config_dict["/device/operating_parameters"])
    assert op["frequency_ghz"] == 60.48
    assert op["channel_id"] == 2


def test_driver_get_config(mock_ceragon_driver):
    # Query specific keys
    res = mock_ceragon_driver.GetConfig(["/device/operating_parameters", "/device/capabilities"])
    res_dict = dict(res)

    assert "/device/operating_parameters" in res_dict
    op = json.loads(res_dict["/device/operating_parameters"])
    assert op["tx_power_control"] == "auto"
    assert op["modem_temperature_c"] == 61

    assert "/device/capabilities" in res_dict
    caps = json.loads(res_dict["/device/capabilities"])
    assert caps["beamforming"] is True
    assert caps["yang_schemas_bundled"] == 51


def test_driver_set_config_radio_tuning(mock_ceragon_driver):
    patch_resp = Response()
    patch_resp.status_code = 200
    commit_resp = Response()
    commit_resp.status_code = 200

    with patch.object(mock_ceragon_driver._client.session, "patch", return_value=patch_resp), \
         patch.object(mock_ceragon_driver._client.session, "post", return_value=commit_resp):

        rules = [
            (
                "/radio/tuning",
                {
                    "frequency_mhz": 60480.0,
                    "channel_id": 2,
                    "tx_power_dbm": 20.0,
                    "atpc_enabled": True,
                },
            )
        ]
        results = mock_ceragon_driver.SetConfig(rules)
        assert len(results) == 1
        assert results[0] is True


def test_driver_set_config_vlan_slice(mock_ceragon_driver):
    patch_resp = Response()
    patch_resp.status_code = 204
    commit_resp = Response()
    commit_resp.status_code = 200

    with patch.object(mock_ceragon_driver._client.session, "patch", return_value=patch_resp), \
         patch.object(mock_ceragon_driver._client.session, "post", return_value=commit_resp):

        rules = [
            (
                "/slice[slice-uran-6g]",
                {
                    "slice_name": "slice-uran-6g",
                    "vlan_id": 200,
                    "bandwidth_mbps": 1000,
                },
            )
        ]
        results = mock_ceragon_driver.SetConfig(rules)
        assert len(results) == 1
        assert results[0] is True


def test_driver_set_config_acm_rain_floor(mock_ceragon_driver):
    patch_resp = Response()
    patch_resp.status_code = 200
    commit_resp = Response()
    commit_resp.status_code = 200

    with patch.object(mock_ceragon_driver._client.session, "patch", return_value=patch_resp), \
         patch.object(mock_ceragon_driver._client.session, "post", return_value=commit_resp):

        rules = [
            (
                "/modulation/acm_floor",
                {
                    "min_modulation": "64QAM",
                },
            )
        ]
        results = mock_ceragon_driver.SetConfig(rules)
        assert len(results) == 1
        assert results[0] is True


def test_driver_disconnect(mock_ceragon_driver):
    mock_ceragon_driver.Connect()
    ok = mock_ceragon_driver.Disconnect()
    assert ok is True


def test_yang_schemas_completeness():
    schemas = list_available_schemas()
    assert len(schemas) == 51
    assert "radio-bridge-tg" in schemas
    assert "ietf-interfaces" in schemas
    assert "ietf-datastores" in schemas
    assert "radio-bridge-tg-acm" in schemas

    all_content = get_all_schemas()
    assert len(all_content) == 51
    for name, content in all_content.items():
        assert len(content) > 0
        assert f"module {name}" in content or "submodule" in content or "module" in content
