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
RFC 8040 RESTCONF Candidate Datastore Payload Templates
=======================================================
Generates structured JSON payloads for mutating candidate datastores
across Ceragon MultiHaul TG (Clixon), EtherHaul, and CeraOS devices.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def build_radio_tuning_payload(
    frequency_mhz: Optional[float] = None,
    channel_id: Optional[int] = None,
    tx_power_dbm: Optional[float] = None,
    atpc_enabled: Optional[bool] = None,
    min_mcs_floor: Optional[str] = None,
    antenna_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates candidate payload for radio sector tuning."""
    radio_cfg: Dict[str, Any] = {}

    if frequency_mhz is not None:
        radio_cfg["frequency-mhz"] = frequency_mhz
    if channel_id is not None:
        radio_cfg["channel-id"] = channel_id
    if tx_power_dbm is not None:
        radio_cfg["tx-power-dbm"] = tx_power_dbm
    if atpc_enabled is not None:
        radio_cfg["atpc"] = "enabled" if atpc_enabled else "disabled"
    if min_mcs_floor is not None:
        radio_cfg["acm-min-floor"] = min_mcs_floor
    if antenna_profile is not None:
        radio_cfg["antenna-profile"] = antenna_profile

    return {"radio-bridge-tg:radio": radio_cfg}


def build_vlan_slice_payload(
    vlan_id: int,
    slice_name: str,
    bandwidth_mbps: int = 1000,
    sub_interface_id: int = 1,
    priority: int = 5,
) -> Dict[str, Any]:
    """Generates candidate payload for 802.1Q transport slice provisioning."""
    return {
        "ietf-interfaces:interfaces": {
            "interface": [
                {
                    "name": f"eth1.{vlan_id}",
                    "type": "iana-if-type:l2vlan",
                    "description": f"TFS Transport Slice: {slice_name}",
                    "enabled": True,
                    "ietf-interfaces:sub-interfaces": {
                        "sub-interface": [
                            {
                                "index": sub_interface_id,
                                "vlan-id": vlan_id,
                                "bandwidth-limit-mbps": bandwidth_mbps,
                                "qos-priority": priority,
                            }
                        ]
                    },
                }
            ]
        }
    }


def build_acm_floor_hardening_payload(
    min_modulation: str = "64QAM",
    target_snr_threshold_db: float = 18.0,
) -> Dict[str, Any]:
    """Generates candidate payload for rain-fade modulation protection."""
    return {
        "radio-bridge-tg-acm:acm-configuration": {
            "enabled": True,
            "min-modulation-floor": min_modulation,
            "adaptive-power-boost": True,
            "snr-hysteresis-db": target_snr_threshold_db,
        }
    }
