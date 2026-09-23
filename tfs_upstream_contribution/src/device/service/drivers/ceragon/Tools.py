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
Helper Utilities for Ceragon TeraFlowSDN Driver
===============================================
Functions for extracting TFS endpoints, normalizing configuration rules,
and translating between TFS intents and Ceragon datastore representations.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from device.service.driver_api._Driver import RESOURCE_ENDPOINTS
from .models import CeragonDeviceState

LOGGER = logging.getLogger(__name__)


def extract_endpoints(device_state: CeragonDeviceState) -> List[Tuple[str, str, List[int]]]:
    """
    Extracts TFS-compatible endpoint tuples: (endpoint_uuid, endpoint_type, [sample_types])
    Sample types: 101=BytesIn, 102=BytesOut, 201=PacketsIn, 202=PacketsOut
    """
    endpoints = []
    for iface in device_state.interfaces:
        ep_uuid = iface.name
        ep_type = "copper" if "eth" in iface.name.lower() else "radio"
        sample_types = [101, 102, 201, 202]
        endpoints.append((ep_uuid, ep_type, sample_types))
    return endpoints


def extract_initial_config(device_state: CeragonDeviceState) -> List[Tuple[str, str]]:
    """
    Converts Ceragon device state into TFS initial config rules: List of (resource_key, json_string_val)
    """
    rules: List[Tuple[str, str]] = []

    # 1. Hardware Info
    rules.append(("/device/hardware_info", json.dumps(device_state.hardware_info.to_dict())))

    # 2. Capabilities
    rules.append(("/device/capabilities", json.dumps(device_state.capabilities)))

    # 3. Operating Parameters
    rules.append(("/device/operating_parameters", json.dumps(device_state.operating_parameters.to_dict())))

    # 4. Radio Sectors
    for sector in device_state.radio_sectors:
        rules.append((f"/radio/sector[{sector.sector_id}]", json.dumps(sector.to_dict())))

    # 5. Endpoints
    endpoints_desc = [iface.to_dict() for iface in device_state.interfaces]
    rules.append(("/device/endpoints", json.dumps(endpoints_desc)))

    return rules


def parse_resource_value(val: Any) -> Dict[str, Any]:
    """Safely decodes JSON or returns dictionary."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {"raw_value": val}
    return {"raw_value": val}
