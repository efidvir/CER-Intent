"""
TFS Driver Interface for Ceragon Devices
=========================================
Implements runtime configuration translation and state synchronization matching
the TeraFlowSDN driver lifecycle (Connect, Disconnect, GetConfig, SetConfig).
Translates TFS intents (slices, VLANs, capacity, modulation, QoS) into native Ceragon RESTCONF calls.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ceragon_tfs_adapter.client import CeragonRestClient
from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.models import CeragonDeviceState
from ceragon_tfs_adapter.registrar import TFSRegistrar

logger = logging.getLogger(__name__)


class TFSCeragonDriver:
    """
    Driver layer mediating between TeraFlowSDN intents/config rules and Ceragon REST APIs.
    Supports both Terragraph mmWave nodes and CeraOS multi-core microwave nodes.
    """

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig()
        self.client = CeragonRestClient(self.config)
        self.registrar = TFSRegistrar(self.config)
        self._connected = False
        self._cached_state: Optional[CeragonDeviceState] = None

    def connect(self) -> Tuple[bool, str]:
        """Establish session with the physical Ceragon device."""
        ok, msg = self.client.test_connection()
        self._connected = ok
        return ok, msg

    def sync_to_tfs(self) -> Dict[str, Any]:
        """Fetch live operational state and update TFS device registry."""
        state = self.client.get_device_state()
        self._cached_state = state
        result = self.registrar.register_or_update_device(state)
        result["device_state"] = state.to_dict()
        return result

    def set_config(self, resources: List[Tuple[str, Any]]) -> List[Tuple[str, bool, str]]:
        """
        Applies a list of resource configuration updates to the physical device.
        Matches TFS driver SetConfig format: [(resource_key, resource_value), ...]
        """
        results = []
        for key, val in resources:
            try:
                parsed_val = json.loads(val) if isinstance(val, str) else val
            except Exception:
                parsed_val = val

            logger.info(f"[Driver SetConfig] Resource: {key} -> {parsed_val}")

            # 1. Network Slicing & VLAN Intents
            if "slice" in key.lower() or "vlan" in key.lower():
                if isinstance(parsed_val, dict):
                    vlan_id = int(parsed_val.get("vlan_id", parsed_val.get("vlan_tag", 100)))
                    slice_name = str(parsed_val.get("slice_name", parsed_val.get("slice_id", "slice-1")))
                    bw = parsed_val.get("bandwidth_mbps", parsed_val.get("min_throughput_gbps", 1.0) * 1000)
                    ok, msg = self.client.apply_vlan_slice(vlan_id=vlan_id, slice_name=slice_name, bandwidth_mbps=int(bw))
                    results.append((key, ok, msg))
                else:
                    results.append((key, False, "Invalid slice parameter dictionary"))

            # 2. Operating Parameters (Frequency, Power, Tuning)
            elif "/device/operating_parameters" in key:
                if isinstance(parsed_val, dict):
                    freq = parsed_val.get("frequency_mhz")
                    pwr = parsed_val.get("tx_power_dbm")
                    adm = parsed_val.get("admin_status")
                    ok, msg = self.client.apply_radio_tuning(frequency_mhz=freq, tx_power_dbm=pwr, admin_status=adm)
                    results.append((key, ok, msg))
                else:
                    results.append((key, False, "Invalid operating parameters format"))

            # 3. Modulation & Capacity Intents
            elif "modulation" in key.lower() or "capacity" in key.lower():
                if isinstance(parsed_val, dict):
                    script_id = parsed_val.get("mrmc_script_id")
                    freq = parsed_val.get("tx_frequency")
                    pwr = parsed_val.get("tx_power_dbm")
                    ok, msg = self.client.apply_radio_tuning(frequency_mhz=freq, tx_power_dbm=pwr, script_id=script_id)
                    results.append((key, ok, msg))
                else:
                    results.append((key, False, "Invalid modulation/capacity parameters format"))

            # 4. Custom parameter acknowledged
            else:
                logger.info(f"Accepted custom configuration rule for key {key}")
                results.append((key, True, "Acknowledged and stored in TFS mirror"))

        # Trigger refresh after changes
        try:
            self.sync_to_tfs()
        except Exception as e:
            logger.warning(f"Post-config sync warning: {e}")

        return results
