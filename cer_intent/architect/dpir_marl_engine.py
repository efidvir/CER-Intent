"""
Option A: DPIR & MARL Testbed Engine
====================================
Implements the 8 IP-50 + 8 TG Conducted Testbed architecture:
  1. NORMAL_DPIR:
     - 8 sites, 4 MW links, 6 TG links.
     - Flow 1 (W1 -> E1) & Flow 2 (W2 -> E2) routed via DPIR (Deep Predictive Interference-Aware Routing,
       TAU/Ceragon 2025), balancing MW Core vs TG PtMP Hub airtime contention.
  2. DISASTER_4_ISLANDS:
     - At t0, switched PDUs cut CORE and HUB; programmable attenuators go to max attenuation.
     - 4 isolated islands: {W1, W2}, {E1, E2}, {N}, {S}. All inter-site flows severed.
  3. RECOVERED_MARL_3_BRIDGES:
     - Decentralized MARL actors at edge sites (W1, W2, E1, E2, N, S) ignite 3 emergency 60 GHz bridges:
       * Bridge 1: E2 <-> W2 (540m, SNR 11 dB -> 16QAM, 500 Mbps, E2 ignites, angle 34°)
       * Bridge 2: E1 <-> N  (504m, SNR 12 dB -> 64QAM, 1.2 Gbps, E1 ignites, angle 32°)
       * Bridge 3: W1 <-> S  (747m, SNR 5 dB  -> QPSK 1/2, 200 Mbps, W1 ignites, angle 21°)
     - Tree routes re-established: F1 (W1-W2-E2-E1), F2 (W2-E2), svc W1-S, svc W2-E2-E1-N.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOPOLOGY_FILE = Path(__file__).parent.parent.parent / "data" / "option_a_topology.json"


class TestbedPhase(str, Enum):
    NORMAL_DPIR = "normal_dpir"
    DISASTER_4_ISLANDS = "disaster_4_islands"
    RECOVERED_MARL_3_BRIDGES = "recovered_marl_3_bridges"


class OptionATestbedEngine:
    def __init__(self, topo_path: Optional[Path] = None):
        self.topo_path = topo_path or TOPOLOGY_FILE
        self.phase = TestbedPhase.NORMAL_DPIR
        self._load_topology()
        self.history: List[Dict[str, Any]] = []

    def _load_topology(self):
        if self.topo_path.exists():
            with open(self.topo_path, "r", encoding="utf-8") as f:
                self.topology_data = json.load(f)
        else:
            self.topology_data = {"nodes": [], "links": [], "marl_candidate_bridges": []}

    def get_state(self) -> Dict[str, Any]:
        """Return the complete live state of Option A testbed."""
        nodes = []
        links = []

        is_disaster = self.phase in (TestbedPhase.DISASTER_4_ISLANDS, TestbedPhase.RECOVERED_MARL_3_BRIDGES)
        is_recovered = self.phase == TestbedPhase.RECOVERED_MARL_3_BRIDGES

        for n in self.topology_data.get("nodes", []):
            node_copy = dict(n)
            if is_disaster and node_copy["id"] in ("CORE", "HUB"):
                node_copy["status"] = "destroyed"
                node_copy["power"] = "OFF (PDU cut)"
                node_copy["attenuation"] = "MAX (90 dB)"
            else:
                node_copy["status"] = "active"
                node_copy["power"] = "ON"
                node_copy["attenuation"] = "NOMINAL (0 dB)"
            nodes.append(node_copy)

        for l in self.topology_data.get("links", []):
            link_copy = dict(l)
            if is_disaster and (link_copy["source"] in ("CORE", "HUB") or link_copy["target"] in ("CORE", "HUB")):
                link_copy["status"] = "severed"
                link_copy["throughput_mbps"] = 0
                link_copy["loss_pct"] = 100.0
            else:
                link_copy["status"] = "active"
                link_copy["throughput_mbps"] = link_copy.get("capacity_mbps", 1000)
                link_copy["loss_pct"] = 0.0
            links.append(link_copy)

        # Active MARL bridges when recovered
        bridges = []
        for b in self.topology_data.get("marl_candidate_bridges", []):
            b_copy = dict(b)
            if is_recovered:
                b_copy["status"] = "ignited_active"
                # Add to links view
                links.append({
                    "id": b_copy["bridge_id"],
                    "source": b_copy["source"],
                    "target": b_copy["target"],
                    "media": "tg_60ghz_marl_bridge",
                    "capacity_mbps": b_copy["capacity_mbps"],
                    "frequency_band": "60GHz",
                    "current_modulation": b_copy["modulation"],
                    "snr_db": b_copy["snr_db"],
                    "steer_angle_deg": b_copy["steer_angle_deg"],
                    "status": "active_bridge",
                    "latency_ms": 1.2
                })
            else:
                b_copy["status"] = "standby"
            bridges.append(b_copy)

        # Calculate current active flows
        flows = self._compute_flows()

        return {
            "testbed": "Option A — 8 IP-50 + 8 TG",
            "phase": self.phase.value,
            "phase_description": self._get_phase_description(),
            "nodes_count": len(nodes),
            "links_count": len(links),
            "active_islands": self._get_islands(),
            "nodes": nodes,
            "links": links,
            "marl_bridges": bridges,
            "flows": flows,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _compute_flows(self) -> Dict[str, Any]:
        if self.phase == TestbedPhase.NORMAL_DPIR:
            return {
                "F1": {
                    "source": "W1", "destination": "E1",
                    "primary_path": ["W1", "CORE", "E1"],
                    "media": "microwave_ip50",
                    "throughput_gbps": 2.5,
                    "latency_ms": 0.8,
                    "status": "optimal_dpir"
                },
                "F2": {
                    "source": "W2", "destination": "E2",
                    "primary_path": ["W2", "HUB", "E2"],
                    "media": "tg_60ghz_hub",
                    "throughput_gbps": 1.0,
                    "latency_ms": 1.7,
                    "status": "optimal_dpir"
                },
                "svc_W1_S": {"path": ["W1", "HUB", "S"], "status": "active"},
                "svc_W2_N": {"path": ["W2", "HUB", "N"], "status": "active"}
            }
        elif self.phase == TestbedPhase.DISASTER_4_ISLANDS:
            return {
                "F1": {"source": "W1", "destination": "E1", "path": None, "throughput_gbps": 0.0, "status": "severed_core_hub_down"},
                "F2": {"source": "W2", "destination": "E2", "path": None, "throughput_gbps": 0.0, "status": "severed_core_hub_down"},
                "svc_W1_S": {"path": None, "status": "severed"},
                "svc_W2_N": {"path": None, "status": "severed"}
            }
        else: # RECOVERED_MARL_3_BRIDGES
            return {
                "F1": {
                    "source": "W1", "destination": "E1",
                    "path": ["W1", "W2", "E2", "E1"],
                    "hops": ["mw-w2-w1", "bridge-1 (E2<->W2)", "mw-e1-e2"],
                    "throughput_gbps": 0.5,
                    "latency_ms": 2.8,
                    "status": "recovered_marl_tree"
                },
                "F2": {
                    "source": "W2", "destination": "E2",
                    "path": ["W2", "E2"],
                    "hops": ["bridge-1 (E2<->W2)"],
                    "throughput_gbps": 0.5,
                    "latency_ms": 1.2,
                    "status": "recovered_marl_direct"
                },
                "svc_W1_S": {
                    "path": ["W1", "S"],
                    "hops": ["bridge-3 (W1<->S)"],
                    "throughput_mbps": 200,
                    "status": "recovered_marl_direct"
                },
                "svc_W2_N": {
                    "path": ["W2", "E2", "E1", "N"],
                    "hops": ["bridge-1", "mw-e1-e2", "bridge-2 (E1<->N)"],
                    "throughput_mbps": 500,
                    "status": "recovered_marl_tree"
                }
            }

    def _get_islands(self) -> List[List[str]]:
        if self.phase == TestbedPhase.NORMAL_DPIR:
            return [["CORE", "HUB", "W1", "W2", "E1", "E2", "N", "S"]]
        elif self.phase == TestbedPhase.DISASTER_4_ISLANDS:
            return [
                ["W1", "W2"],
                ["E1", "E2"],
                ["N"],
                ["S"]
            ]
        else: # RECOVERED
            return [["W1", "W2", "E2", "E1", "N", "S"]]

    def _get_phase_description(self) -> str:
        if self.phase == TestbedPhase.NORMAL_DPIR:
            return "Normal Operation: DPIR routing flows F1 & F2 across Microwave IP-50 core and Siklu TG Hub."
        elif self.phase == TestbedPhase.DISASTER_4_ISLANDS:
            return "Disaster Event: Switched PDUs cut CORE & HUB power; attenuators at MAX. Network split into 4 isolated islands."
        else:
            return "MARL Recovered: 6 edge agent actors re-steered TG 60GHz beams and ignited 3 emergency bridges."

    def trigger_disaster(self) -> Dict[str, Any]:
        """Trigger disaster event: cuts CORE & HUB power and sets attenuators to max."""
        self.phase = TestbedPhase.DISASTER_4_ISLANDS
        record = {
            "event": "DISASTER_CUT_T0",
            "pdu_cut": ["PDU-CORE", "PDU-HUB"],
            "attenuators_max": ["MW-ATT-1", "MW-ATT-3", "VBAND-ATT-1", "VBAND-ATT-2", "VBAND-ATT-3", "VBAND-ATT-4", "VBAND-ATT-5", "VBAND-ATT-6"],
            "islands": self._get_islands(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.history.append(record)
        logger.warning("[OptionA Engine] DISASTER TRIGGERED! CORE & HUB severed. 4 islands formed.")
        return self.get_state()

    def trigger_marl_recovery(self) -> Dict[str, Any]:
        """Trigger MARL edge actors to ignite 3 bridges and restore spanning tree."""
        self.phase = TestbedPhase.RECOVERED_MARL_3_BRIDGES
        record = {
            "event": "MARL_3_BRIDGES_IGNITED",
            "bridges": [
                {"id": "bridge-1", "link": "E2 <-> W2", "snr": "11 dB", "mod": "16QAM", "angle": "34°"},
                {"id": "bridge-2", "link": "E1 <-> N",  "snr": "12 dB", "mod": "64QAM", "angle": "32°"},
                {"id": "bridge-3", "link": "W1 <-> S",  "snr": "5 dB",  "mod": "QPSK 1/2", "angle": "21°"}
            ],
            "tree_restored": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.history.append(record)
        logger.info("[OptionA Engine] MARL 3-Bridge recovery complete. Spanning tree established.")
        return self.get_state()

    def reset_to_normal(self) -> Dict[str, Any]:
        """Reset testbed to normal DPIR operation."""
        self.phase = TestbedPhase.NORMAL_DPIR
        logger.info("[OptionA Engine] Testbed reset to NORMAL_DPIR.")
        return self.get_state()


# Singleton
_option_a_engine: Optional[OptionATestbedEngine] = None

def get_option_a_engine() -> OptionATestbedEngine:
    global _option_a_engine
    if _option_a_engine is None:
        _option_a_engine = OptionATestbedEngine()
    return _option_a_engine
