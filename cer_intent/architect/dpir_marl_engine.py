"""
Generic DPIR & MARL Testbed Engine (Option A & Multi-Site Portable)
===================================================================
Implements a topology-driven DPIR (Deep Predictive Interference-Aware Routing)
and decentralized MARL (Multi-Agent Reinforcement Learning) recovery engine.

Designed for full portability across lab installations:
  - Reads any site topology JSON via `TESTBED_TOPOLOGY_FILE` env var or runtime API.
  - Dynamically computes isolated islands using Breadth-First Search (connected components).
  - Dynamically routes end-to-end flows over active links using media-aware Dijkstra shortest-path.
  - Supports full or incremental (per-bridge) MARL link ignition and PDU/attenuator fault injection.
"""
from __future__ import annotations

import heapq
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

DEFAULT_TOPOLOGY_FILE = Path(__file__).parent.parent.parent / "data" / "option_a_topology.json"

DEFAULT_FLOW_SPECS = {
    "F1": {
        "source": "W1",
        "destination": "E1",
        "preferred_media": "microwave",
        "requested_gbps": 2.5,
    },
    "F2": {
        "source": "W2",
        "destination": "E2",
        "preferred_media": "tg_60ghz",
        "requested_gbps": 1.0,
    },
    "svc_W1_S": {
        "source": "W1",
        "destination": "S",
        "preferred_media": "any",
        "requested_mbps": 200,
    },
    "svc_W2_N": {
        "source": "W2",
        "destination": "N",
        "preferred_media": "any",
        "requested_mbps": 500,
    },
}


class TestbedPhase(str, Enum):
    NORMAL_DPIR = "normal_dpir"
    DISASTER_4_ISLANDS = "disaster_4_islands"
    RECOVERED_MARL_3_BRIDGES = "recovered_marl_3_bridges"


class OptionATestbedEngine:
    def __init__(self, topo_path: Optional[Union[str, Path]] = None):
        env_path = os.getenv("TESTBED_TOPOLOGY_FILE") or os.getenv("OPTION_A_TOPOLOGY_FILE")
        self.topo_path = Path(topo_path or env_path or DEFAULT_TOPOLOGY_FILE)
        self.phase = TestbedPhase.NORMAL_DPIR
        self.cut_node_ids: Set[str] = set()
        self.ignited_bridge_ids: Set[str] = set()
        self.history: List[Dict[str, Any]] = []
        self._load_topology()

    def _load_topology(self) -> None:
        if self.topo_path.exists():
            with open(self.topo_path, "r", encoding="utf-8") as f:
                self.topology_data = json.load(f)
        else:
            logger.warning(f"[OptionA Engine] Topology file not found at {self.topo_path}; using empty template.")
            self.topology_data = {"nodes": [], "links": [], "marl_candidate_bridges": [], "flows": {}}

    def load_custom_topology(self, topology_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Load a custom topology JSON payload at runtime (for portable deployment at another site)."""
        self.topology_data = topology_dict
        self.reset_to_normal()
        logger.info(f"[OptionA Engine] Loaded custom topology: {topology_dict.get('name', 'Custom Testbed')}")
        return self.get_state()

    def _default_cut_nodes(self) -> Set[str]:
        """Determine which nodes are cut on disaster based on `pdu_controlled` attribute in topology."""
        pdu_nodes = {
            n["id"]
            for n in self.topology_data.get("nodes", [])
            if n.get("pdu_controlled", False) or n.get("role") in ("core_hub", "tg_ptmp_hub")
        }
        return pdu_nodes or {"CORE", "HUB"}

    def get_state(self) -> Dict[str, Any]:
        """Return the complete live state of the testbed, dynamically computed from topology & active links."""
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []

        is_disaster = self.phase in (
            TestbedPhase.DISASTER_4_ISLANDS,
            TestbedPhase.RECOVERED_MARL_3_BRIDGES,
        ) or bool(self.cut_node_ids)

        active_cut_nodes = self.cut_node_ids if is_disaster else set()

        for n in self.topology_data.get("nodes", []):
            node_copy = dict(n)
            if node_copy["id"] in active_cut_nodes:
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
            if link_copy["source"] in active_cut_nodes or link_copy["target"] in active_cut_nodes:
                link_copy["status"] = "severed"
                link_copy["throughput_mbps"] = 0
                link_copy["loss_pct"] = 100.0
            else:
                link_copy["status"] = "active"
                link_copy["throughput_mbps"] = link_copy.get("capacity_mbps", 1000)
                link_copy["loss_pct"] = 0.0
            links.append(link_copy)

        # Candidate MARL bridges
        bridges: List[Dict[str, Any]] = []
        for b in self.topology_data.get("marl_candidate_bridges", []):
            b_copy = dict(b)
            b_id = b_copy["bridge_id"]
            if b_id in self.ignited_bridge_ids or self.phase == TestbedPhase.RECOVERED_MARL_3_BRIDGES:
                b_copy["status"] = "ignited_active"
                cap_mbps = b_copy.get("capacity_mbps", int(b_copy.get("capacity_gbps", 1.0) * 1000))
                links.append({
                    "id": b_id,
                    "label": f"{b_id} ({b_copy['source']}<->{b_copy['target']})",
                    "source": b_copy["source"],
                    "target": b_copy["target"],
                    "media": "tg_60ghz_marl_bridge",
                    "capacity_mbps": cap_mbps,
                    "throughput_mbps": cap_mbps,
                    "frequency_band": "60GHz",
                    "current_modulation": b_copy.get("modulation", "16QAM"),
                    "snr_db": b_copy.get("snr_db", 15.0),
                    "steer_angle_deg": b_copy.get("steer_angle_deg", 0.0),
                    "status": "active_bridge",
                    "latency_ms": b_copy.get("latency_ms", 1.2),
                    "loss_pct": 0.0,
                })
            else:
                b_copy["status"] = "standby"
            bridges.append(b_copy)

        active_islands = self._compute_islands(nodes, links)
        flows = self._compute_flows(links)

        return {
            "testbed": self.topology_data.get("name", "Option A — 8 IP-50 + 8 TG"),
            "testbed_profile": self.topology_data.get("testbed_profile", "OPTION_A_8_IP50_8_TG"),
            "topology_file": str(self.topo_path),
            "phase": self.phase.value,
            "phase_description": self._get_phase_description(nodes, active_islands, bridges),
            "nodes_count": len(nodes),
            "links_count": len(links),
            "active_islands": active_islands,
            "nodes": nodes,
            "links": links,
            "marl_bridges": bridges,
            "flows": flows,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_islands(
        self, nodes: List[Dict[str, Any]], links: List[Dict[str, Any]]
    ) -> List[List[str]]:
        """Compute connected components (islands) via BFS over active nodes and active links."""
        active_node_ids = [n["id"] for n in nodes if n.get("status") != "destroyed"]
        active_set = set(active_node_ids)

        adj: Dict[str, List[str]] = {nid: [] for nid in active_node_ids}
        for l in links:
            if l.get("status") in ("active", "active_bridge"):
                u, v = l["source"], l["target"]
                if u in active_set and v in active_set:
                    adj[u].append(v)
                    adj[v].append(u)

        visited: Set[str] = set()
        islands: List[List[str]] = []

        for nid in active_node_ids:
            if nid not in visited:
                comp: List[str] = []
                queue = deque([nid])
                visited.add(nid)
                while queue:
                    curr = queue.popleft()
                    comp.append(curr)
                    for nxt in adj.get(curr, []):
                        if nxt not in visited:
                            visited.add(nxt)
                            queue.append(nxt)
                islands.append(comp)

        return islands

    def _find_shortest_path(
        self,
        source: str,
        destination: str,
        links: List[Dict[str, Any]],
        preferred_media: str = "any",
    ) -> Optional[Tuple[List[str], List[Dict[str, Any]]]]:
        """
        Media-aware Dijkstra shortest path over active links.
        In NORMAL_DPIR, links not matching `preferred_media` incur a contention penalty
        so DPIR routes F1 via Microwave Core and F2 via Siklu TG Hub.
        """
        adj: Dict[str, List[Tuple[str, Dict[str, Any], float]]] = {}
        for l in links:
            if l.get("status") not in ("active", "active_bridge"):
                continue
            u, v = l["source"], l["target"]
            base_lat = float(l.get("latency_ms", 1.0))
            media = l.get("media", "")

            # Apply DPIR media preference weight during normal operation
            penalty = 0.0
            if self.phase == TestbedPhase.NORMAL_DPIR and preferred_media not in ("any", "", None):
                if preferred_media not in media:
                    penalty = 10.0

            cost = base_lat + penalty
            adj.setdefault(u, []).append((v, l, cost))
            adj.setdefault(v, []).append((u, l, cost))

        # Dijkstra
        pq: List[Tuple[float, str, List[str], List[Dict[str, Any]]]] = [
            (0.0, source, [source], [])
        ]
        best_cost: Dict[str, float] = {source: 0.0}

        while pq:
            cost, curr, path_nodes, path_links = heapq.heappop(pq)
            if curr == destination:
                return path_nodes, path_links
            if cost > best_cost.get(curr, float("inf")):
                continue
            for nxt, link_obj, edge_cost in adj.get(curr, []):
                new_cost = cost + edge_cost
                if new_cost < best_cost.get(nxt, float("inf")):
                    best_cost[nxt] = new_cost
                    heapq.heappush(
                        pq,
                        (new_cost, nxt, path_nodes + [nxt], path_links + [link_obj]),
                    )

        return None

    def _compute_flows(self, links: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Dynamically compute end-to-end flow routes and capacities over current active links."""
        flow_specs = self.topology_data.get("flows") or DEFAULT_FLOW_SPECS
        results: Dict[str, Any] = {}

        for flow_id, spec in flow_specs.items():
            src = spec["source"]
            dst = spec["destination"]
            pref = spec.get("preferred_media", "any")
            req_gbps = spec.get("requested_gbps")
            req_mbps = spec.get("requested_mbps")

            found = self._find_shortest_path(src, dst, links, preferred_media=pref)
            if not found:
                # Flow severed
                if req_gbps is not None:
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "path": None,
                        "throughput_gbps": 0.0,
                        "status": "severed_core_hub_down" if flow_id in ("F1", "F2") else "severed",
                    }
                else:
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "path": None,
                        "status": "severed",
                    }
                continue

            path_nodes, path_links = found
            total_lat = round(sum(float(l.get("latency_ms", 0.5)) for l in path_links), 2)
            bottleneck_mbps = min(int(l.get("capacity_mbps", 1000)) for l in path_links)
            hop_labels = [l.get("label") or l["id"] for l in path_links]
            uses_bridge = any(l.get("status") == "active_bridge" for l in path_links)

            if self.phase == TestbedPhase.NORMAL_DPIR and not uses_bridge:
                if req_gbps is not None:
                    media_label = "microwave_ip50" if pref == "microwave" else "tg_60ghz_hub"
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "primary_path": path_nodes,
                        "path": path_nodes,
                        "hops": hop_labels,
                        "media": media_label,
                        "throughput_gbps": min(float(req_gbps), bottleneck_mbps / 1000.0),
                        "latency_ms": total_lat,
                        "status": "optimal_dpir",
                    }
                else:
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "path": path_nodes,
                        "hops": hop_labels,
                        "throughput_mbps": min(int(req_mbps or bottleneck_mbps), bottleneck_mbps),
                        "latency_ms": total_lat,
                        "status": "active",
                    }
            else:
                # Recovered / Bridged routing
                rec_status = "recovered_marl_direct" if len(path_links) == 1 else "recovered_marl_tree"
                if req_gbps is not None:
                    achieved_gbps = round(min(float(req_gbps), bottleneck_mbps / 1000.0), 3)
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "path": path_nodes,
                        "hops": hop_labels,
                        "throughput_gbps": achieved_gbps,
                        "latency_ms": total_lat,
                        "status": rec_status,
                    }
                else:
                    achieved_mbps = min(int(req_mbps or bottleneck_mbps), bottleneck_mbps)
                    results[flow_id] = {
                        "source": src,
                        "destination": dst,
                        "path": path_nodes,
                        "hops": hop_labels,
                        "throughput_mbps": achieved_mbps,
                        "latency_ms": total_lat,
                        "status": rec_status,
                    }

        return results

    def _get_phase_description(
        self,
        nodes: List[Dict[str, Any]],
        islands: List[List[str]],
        bridges: List[Dict[str, Any]],
    ) -> str:
        if self.phase == TestbedPhase.NORMAL_DPIR:
            return "Normal Operation: DPIR routing flows F1 & F2 across Microwave IP-50 core and Siklu TG Hub."
        elif self.phase == TestbedPhase.DISASTER_4_ISLANDS:
            cut_str = " & ".join(sorted(self.cut_node_ids)) or "CORE & HUB"
            return (
                f"Disaster Event: Switched PDUs cut {cut_str} power; attenuators at MAX (90 dB). "
                f"Network split into {len(islands)} isolated islands."
            )
        else:
            active_b = sum(1 for b in bridges if b.get("status") == "ignited_active")
            return (
                f"MARL Recovered: Edge agent actors re-steered TG 60GHz beams and ignited "
                f"{active_b} emergency bridges ({len(islands)} connected component)."
            )

    def trigger_disaster(self, cut_nodes: Optional[List[str]] = None) -> Dict[str, Any]:
        """Trigger disaster event: cuts PDU-controlled nodes and sets their link attenuators to max."""
        self.phase = TestbedPhase.DISASTER_4_ISLANDS
        self.cut_node_ids = set(cut_nodes) if cut_nodes else self._default_cut_nodes()
        self.ignited_bridge_ids.clear()

        pdu_cut = [
            n.get("pdu_id", f"PDU-{n['id']}")
            for n in self.topology_data.get("nodes", [])
            if n["id"] in self.cut_node_ids
        ]
        attenuators_max = [
            l["attenuator_id"]
            for l in self.topology_data.get("links", [])
            if (l["source"] in self.cut_node_ids or l["target"] in self.cut_node_ids)
            and l.get("attenuator_id")
        ]

        state = self.get_state()
        record = {
            "event": "DISASTER_CUT_T0",
            "cut_nodes": sorted(self.cut_node_ids),
            "pdu_cut": pdu_cut,
            "attenuators_max": attenuators_max,
            "islands": state["active_islands"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.history.append(record)
        logger.warning(
            f"[OptionA Engine] DISASTER TRIGGERED! Cut nodes: {sorted(self.cut_node_ids)}. "
            f"{len(state['active_islands'])} islands formed."
        )
        return state

    def ignite_bridge(self, bridge_id: str) -> Dict[str, Any]:
        """Ignite a single candidate MARL bridge and dynamically recompute islands and flows."""
        if not self.cut_node_ids and self.phase == TestbedPhase.NORMAL_DPIR:
            self.cut_node_ids = self._default_cut_nodes()
            self.phase = TestbedPhase.DISASTER_4_ISLANDS

        self.ignited_bridge_ids.add(bridge_id)
        all_candidate_ids = {
            b["bridge_id"] for b in self.topology_data.get("marl_candidate_bridges", [])
        }
        if all_candidate_ids and all_candidate_ids.issubset(self.ignited_bridge_ids):
            self.phase = TestbedPhase.RECOVERED_MARL_3_BRIDGES

        return self.get_state()

    def trigger_marl_recovery(self) -> Dict[str, Any]:
        """Trigger MARL edge actors to ignite all candidate bridges and restore spanning tree."""
        if not self.cut_node_ids:
            self.cut_node_ids = self._default_cut_nodes()

        self.phase = TestbedPhase.RECOVERED_MARL_3_BRIDGES
        self.ignited_bridge_ids = {
            b["bridge_id"] for b in self.topology_data.get("marl_candidate_bridges", [])
        }

        state = self.get_state()
        record = {
            "event": "MARL_BRIDGES_IGNITED",
            "bridges": [
                {
                    "id": b["bridge_id"],
                    "link": f"{b['source']} <-> {b['target']}",
                    "snr": f"{b['snr_db']} dB",
                    "mod": b["modulation"],
                    "angle": f"{b['steer_angle_deg']}°",
                }
                for b in self.topology_data.get("marl_candidate_bridges", [])
            ],
            "tree_restored": len(state["active_islands"]) == 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.history.append(record)
        logger.info("[OptionA Engine] MARL recovery complete. Spanning tree established.")
        return state

    def reset_to_normal(self) -> Dict[str, Any]:
        """Reset testbed to normal DPIR operation."""
        self.phase = TestbedPhase.NORMAL_DPIR
        self.cut_node_ids.clear()
        self.ignited_bridge_ids.clear()
        logger.info("[OptionA Engine] Testbed reset to NORMAL_DPIR.")
        return self.get_state()


# Singleton
_option_a_engine: Optional[OptionATestbedEngine] = None


def get_option_a_engine() -> OptionATestbedEngine:
    global _option_a_engine
    if _option_a_engine is None:
        _option_a_engine = OptionATestbedEngine()
    return _option_a_engine
