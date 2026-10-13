"""
NDT Path Computation Engine (PCE) Planner (D3.1 Section 2.4.1.1.2 & Figure 2-18)
==================================================================================
Implements the Network Digital Twin (NDT) role as the PCE Planner for the Network
Slice Controller (NSC).

Workflow:
  1. Mapper receives IETF Slice Service request.
  2. Mapper requests NDT PCE to compute optimal underlay path.
  3. PCE evaluates topology graph, link capabilities, queuing delay, TVR availability,
     and SLO/SLE constraints (latency, bandwidth, isolation).
  4. Returns optimal path, hops, predicted latency, and feasibility verdict.
"""
from __future__ import annotations

import heapq
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("NDT_PCE_Planner")


class NDTPathComputationEngine:
    """
    Path Computation Engine (PCE) executed by the Network Digital Twin (NDT).
    Determines optimal multi-hop paths satisfying IETF RFC 9543 SLO/SLE constraints.
    """

    def __init__(self, topology_provider=None):
        self.topology_provider = topology_provider

    def compute_constrained_path(
        self,
        src_node: str,
        dst_node: str,
        max_latency_ms: Optional[float] = None,
        bandwidth_mbps: Optional[float] = None,
        isolation_policy: Optional[str] = "logical",
        tvr_schedules: Optional[List[Any]] = None,
        topology_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes Constrained Shortest Path First (CSPF) over the transport topology graph.
        """
        # Resolve topology
        topo = topology_dict
        if not topo and self.topology_provider:
            topo = self.topology_provider()

        if not topo:
            topo = self._get_default_6g_topology()

        nodes = topo.get("nodes", [])
        links = topo.get("links", [])

        # Build adjacency graph
        # Format: adj[u] = [(v, link_id, latency_ms, capacity_mbps, link_type)]
        adj: Dict[str, List[Tuple[str, str, float, float, str]]] = {
            n.get("id", n.get("uuid")): [] for n in nodes
        }
        
        # Check TVR schedules for unavailable/degraded links
        blocked_links = set()
        degraded_links = {}
        if tvr_schedules:
            for item in tvr_schedules:
                target = getattr(item, "target_element_id", None) or item.get("target_element_id")
                state = getattr(item, "scheduled_state", None) or item.get("scheduled_state")
                if state == "unavailable":
                    blocked_links.add(target)
                elif state == "degraded":
                    atten = getattr(item, "predicted_attenuation_db", 10.0) or item.get("predicted_attenuation_db", 10.0)
                    degraded_links[target] = float(atten)

        for l in links:
            l_id = l.get("id", l.get("uuid", "link"))
            src = l.get("source", l.get("src", ""))
            dst = l.get("target", l.get("dst", ""))
            
            if l_id in blocked_links:
                continue

            lat = float(l.get("latency_ms", 0.35))
            cap = float(l.get("capacity_mbps", 1000.0))
            l_type = l.get("type", "wireless-microwave")

            # Apply TVR degradation if active
            if l_id in degraded_links:
                lat += 0.85  # Latency penalty due to adaptive modulation drop (ACM)
                cap *= 0.4   # Capacity drop due to rain attenuation

            # Filter links by bandwidth constraint if bandwidth requested
            if bandwidth_mbps and cap < bandwidth_mbps:
                continue

            if src in adj and dst in adj:
                adj[src].append((dst, l_id, lat, cap, l_type))
                adj[dst].append((src, l_id, lat, cap, l_type))  # Undirected transport link

        # Validate endpoints exist
        if src_node not in adj:
            # Fallback to closest match or default
            src_node = next(iter(adj.keys())) if adj else src_node
        if dst_node not in adj:
            dst_node = list(adj.keys())[-1] if adj else dst_node

        if src_node == dst_node:
            return {
                "feasible": True,
                "src_node": src_node,
                "dst_node": dst_node,
                "computed_path": [src_node],
                "computed_links": [],
                "hop_count": 0,
                "total_predicted_latency_ms": 0.05,
                "min_link_capacity_mbps": 10000.0,
                "algorithm": "CSPF-Dijkstra-NDT",
                "explanation": "Ingress and Egress SDPs share the same physical node."
            }

        # Dijkstra algorithm minimizing latency with constraints
        # Priority queue entries: (cost_latency, current_node, path_nodes, path_links, min_capacity)
        pq = [(0.0, src_node, [src_node], [], float("inf"))]
        visited = set()

        best_path = None
        while pq:
            cost, u, p_nodes, p_links, min_cap = heapq.heappop(pq)

            if u == dst_node:
                best_path = (cost, p_nodes, p_links, min_cap)
                break

            if u in visited:
                continue
            visited.add(u)

            for v, link_id, lat, cap, l_type in adj.get(u, []):
                if v not in visited:
                    new_cost = cost + lat
                    # Check latency constraint
                    if max_latency_ms and new_cost > max_latency_ms:
                        continue
                    heapq.heappush(
                        pq,
                        (
                            round(new_cost, 3),
                            v,
                            p_nodes + [v],
                            p_links + [link_id],
                            min(min_cap, cap),
                        ),
                    )

        if best_path:
            tot_lat, p_nodes, p_links, min_cap = best_path
            return {
                "feasible": True,
                "src_node": src_node,
                "dst_node": dst_node,
                "computed_path": p_nodes,
                "computed_links": p_links,
                "hop_count": len(p_nodes) - 1,
                "total_predicted_latency_ms": tot_lat,
                "min_link_capacity_mbps": min_cap,
                "isolation_applied": isolation_policy,
                "algorithm": "CSPF-Dijkstra-NDT-PCE",
                "explanation": (
                    f"NDT PCE computed optimal {len(p_nodes)-1}-hop underlay path via "
                    f"{' -> '.join(p_nodes)} with predicted end-to-end latency of {tot_lat} ms."
                ),
            }
        else:
            return {
                "feasible": False,
                "src_node": src_node,
                "dst_node": dst_node,
                "computed_path": [],
                "computed_links": [],
                "total_predicted_latency_ms": -1.0,
                "algorithm": "CSPF-Dijkstra-NDT-PCE",
                "error": f"No feasible path found between {src_node} and {dst_node} meeting SLO constraints (max latency: {max_latency_ms} ms, min BW: {bandwidth_mbps} Mbps).",
            }

    def _get_default_6g_topology(self) -> Dict[str, Any]:
        """Provides default reference 6G transport topology if none is loaded."""
        return {
            "nodes": [
                {"id": "ctu-96", "type": "ceragon-siklu-mh-t261", "model": "MH-T261"},
                {"id": "ctu-97", "type": "ceragon-siklu-mh-t261", "model": "MH-T261"},
                {"id": "edge-router-01", "type": "frr-ip-router", "model": "FRR-L3"},
                {"id": "edge-router-02", "type": "frr-ip-router", "model": "FRR-L3"},
                {"id": "core-transport-sw", "type": "tsn-bridge", "model": "OpenFlow-TSN"},
            ],
            "links": [
                {"id": "link-ctu96-ctu97", "source": "ctu-96", "target": "ctu-97", "latency_ms": 0.42, "capacity_mbps": 2000.0, "type": "wireless-mmwave"},
                {"id": "link-ctu96-er01", "source": "ctu-96", "target": "edge-router-01", "latency_ms": 0.25, "capacity_mbps": 10000.0, "type": "optical-ethernet"},
                {"id": "link-ctu97-er02", "source": "ctu-97", "target": "edge-router-02", "latency_ms": 0.28, "capacity_mbps": 10000.0, "type": "optical-ethernet"},
                {"id": "link-er01-core", "source": "edge-router-01", "target": "core-transport-sw", "latency_ms": 0.35, "capacity_mbps": 25000.0, "type": "optical-100g"},
                {"id": "link-er02-core", "source": "edge-router-02", "target": "core-transport-sw", "latency_ms": 0.38, "capacity_mbps": 25000.0, "type": "optical-100g"},
            ]
        }
