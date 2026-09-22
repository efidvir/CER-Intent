#!/usr/bin/env python3
"""
6G Transport Topology Generator for TeraFlow SDN (TFS)
======================================================
Generates production-grade ETSI TeraFlowSDN (TFS) descriptor JSON files
representing realistic 6G Transport Networks.

Features:
  - Multi-tier 6G O-RAN & Transport Nodal Hierarchy:
      * 6G Core & Edge Data Centers (UPF/CP)
      * Ceragon IP-50FX Aggregation Microwave/mmWave Rings (10-100 Gbps, XPIC, 2048QAM)
      * Ceragon IP-20N Midhaul Nodal Branching Hubs (5-10 Gbps)
      * Ceragon IP-20C & IP-50E E-Band Fronthaul Tail Drops (71-86 GHz, 2.5-20 Gbps)
      * O-RAN Base Station Nodes (O-CU, O-DU, O-RU)
  - Comprehensive 6G Transport Capabilities & Config Rules:
      * Adaptive Coding & Modulation (ACM: QPSK to 4096QAM)
      * Latency SLAs (URLLC <1ms, eMBB <10ms, mMTC <50ms)
      * Precision Clock Sync (IEEE 1588v2 PTP Class C/D, SyncE <130ns accuracy)
      * Physical Protection (1+1 HSB Hot Standby, Space Diversity)
      * Security & Slicing (MACsec, eCPRI/RoE transport, 6G Network Slices)
  - Live Telemetry Engine & Dynamic Telemetry Streamer:
      * Simulates SNR, RSSI, BER, Capacity Utilization, Delay/Jitter, Power consumption, and Rain Fade events.
  - ETSI TeraFlowSDN Descriptor Schema Compliance (contexts, topologies, devices, links, slices, services).

Usage:
  python generate_6g_tfs_topology.py --output data/6g_transport_tfs_descriptors.json
  python generate_6g_tfs_topology.py --live --interval 3
"""

import argparse
import copy
import json
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic UUID Generation helper
# ──────────────────────────────────────────────────────────────────────────────

NAMESPACE_6G = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def make_uuid(name: str) -> str:
    """Generate a deterministic UUID string based on node/link name."""
    return str(uuid.uuid5(NAMESPACE_6G, str(name)))


# ──────────────────────────────────────────────────────────────────────────────
# 6G Hardware Profiles & Capability Schemas
# ──────────────────────────────────────────────────────────────────────────────

HARDWARE_PROFILES = {
    "IP-50FX": {
        "device_type": "emu-packet-router",
        "description": "Ceragon IP-50FX Disaggregated Aggregation Microwave/mmWave Router",
        "max_capacity_gbps": 10.0,
        "max_channel_mhz": 112,
        "max_modulation": "4096QAM",
        "features": ["ACM", "XPIC", "1+1_HSB", "SyncE", "PTP_IEEE1588v2_ClassC", "MACsec_256", "SRv6"],
        "ports": ["eth-1/100G", "eth-1/10G", "radio-1/1", "radio-1/2", "radio-2/1", "radio-2/2"],
        "role": "transport_agg",
    },
    "IP-20N": {
        "device_type": "emu-packet-router",
        "description": "Ceragon IP-20N Multi-Slot Nodal Midhaul Branching Hub",
        "max_capacity_gbps": 5.0,
        "max_channel_mhz": 112,
        "max_modulation": "2048QAM",
        "features": ["ACM", "XPIC_2+0", "SyncE", "PTP_IEEE1588v2_ClassC", "QoS_StrictPriority"],
        "ports": ["eth-1/10G", "eth-1/1G", "radio-1/1", "radio-1/2"],
        "role": "transport_midhaul",
    },
    "IP-20C": {
        "device_type": "emu-packet-router",
        "description": "Ceragon IP-20C Compact All-Outdoor Fronthaul Tail Node",
        "max_capacity_gbps": 2.5,
        "max_channel_mhz": 56,
        "max_modulation": "2048QAM",
        "features": ["ACM", "eCPRI_Fronthaul", "PTP_IEEE1588v2", "LowLatency_CutThrough"],
        "ports": ["eth-1/10G", "radio-1/1"],
        "role": "transport_fronthaul",
    },
    "IP-50E": {
        "device_type": "emu-packet-router",
        "description": "Ceragon IP-50E E-Band mmWave Ultra-High-Capacity Node (71-86 GHz)",
        "max_capacity_gbps": 20.0,
        "max_channel_mhz": 2000,
        "max_modulation": "512QAM",
        "features": ["ACM", "E-Band_71_86GHz", "100G_Interface", "SyncE", "DeepSleep_EnergySaver"],
        "ports": ["eth-1/100G", "eth-1/10G", "radio-eband-1/1"],
        "role": "transport_mmwave",
    },
    "Core-DC": {
        "device_type": "emu-packet-router",
        "description": "6G Core Data Center & UPF / CP Cloud Node",
        "max_capacity_gbps": 100.0,
        "max_channel_mhz": 0,
        "max_modulation": "N/A",
        "features": ["UPF_Offload", "SRv6", "NetworkSlicing_Core", "MACsec_256"],
        "ports": ["eth-1/100G", "eth-2/100G", "eth-3/100G", "eth-4/100G"],
        "role": "oran_core",
    },
    "O-CU": {
        "device_type": "emu-packet-router",
        "description": "O-RAN Centralized Unit (O-CU) Compute Host",
        "max_capacity_gbps": 25.0,
        "max_channel_mhz": 0,
        "max_modulation": "N/A",
        "features": ["F1_Interface", "E1_Interface", "PTP_Slave", "CU_PDCP_RRC"],
        "ports": ["eth-1/25G", "eth-2/25G"],
        "role": "oran_cu",
    },
    "O-DU": {
        "device_type": "emu-packet-router",
        "description": "O-RAN Distributed Unit (O-DU) Real-time Processing Host",
        "max_capacity_gbps": 25.0,
        "max_channel_mhz": 0,
        "max_modulation": "N/A",
        "features": ["OpenFronthaul_eCPRI", "RLC_MAC_HighPHY", "IEEE1588v2_PTP_ClassD"],
        "ports": ["eth-1/25G", "eth-2/25G", "eth-3/10G"],
        "role": "oran_du",
    },
    "O-RU": {
        "device_type": "emu-packet-router",
        "description": "O-RAN Radio Unit (O-RU) Massive MIMO Remote Head",
        "max_capacity_gbps": 10.0,
        "max_channel_mhz": 400,
        "max_modulation": "256QAM",
        "features": ["LowPHY", "Beamforming_MassiveMIMO", "eCPRI_Target", "SyncE_Slave"],
        "ports": ["eth-1/10G"],
        "role": "oran_ru",
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# 6G Network Slices Definition
# ──────────────────────────────────────────────────────────────────────────────

SLICES_6G = [
    {
        "slice_id": "slice-urllc-6g",
        "name": "6G Ultra-Reliable Low-Latency Communication (URLLC)",
        "type": "URLLC",
        "latency_target_ms": 0.8,
        "availability_target": 99.9999,
        "isolation": "HARD_PHYSICAL",
        "priority": 1,
        "description": "Mission-critical autonomous vehicle & industrial robotics slice",
    },
    {
        "slice_id": "slice-embb-6g",
        "name": "6G Enhanced Mobile Broadband (eMBB) Extreme",
        "type": "eMBB",
        "latency_target_ms": 8.0,
        "availability_target": 99.99,
        "isolation": "SOFT_BANDWIDTH_RESERVATION",
        "priority": 2,
        "description": "Holographic telepresence and immersive XR video stream slice",
    },
    {
        "slice_id": "slice-mmtc-6g",
        "name": "6G Massive Machine-Type Communication (mMTC)",
        "type": "mMTC",
        "latency_target_ms": 45.0,
        "availability_target": 99.9,
        "isolation": "SHARED_BEST_EFFORT",
        "priority": 3,
        "description": "Massive IoT smart-city sensor mesh slice",
    },
    {
        "slice_id": "slice-qkd-6g",
        "name": "6G Quantum-Secured Encrypted Transport Slice",
        "type": "QKD_SECURE",
        "latency_target_ms": 2.0,
        "availability_target": 99.999,
        "isolation": "MACSEC_QKD_ENCRYPTED",
        "priority": 1,
        "description": "Financial & defense quantum key distribution secured transport slice",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Topology Builder Class
# ──────────────────────────────────────────────────────────────────────────────

class Topology6GBuilder:
    """Constructs a complete 6G Transport Topology with TeraFlow SDN descriptors."""

    def __init__(self, context_name: str = "admin", topology_name: str = "admin"):
        self.context_name = context_name
        self.topology_name = topology_name
        self.context_uuid = "43813baf-195e-5da6-af20-b3d0922e71a7"
        self.topology_uuid = "c76135e3-24a8-5e92-9bed-c3c9139359c8"

        self.nodes: List[Dict[str, Any]] = []
        self.links: List[Dict[str, Any]] = []
        self.endpoints_by_device: Dict[str, List[Dict[str, Any]]] = {}
        self.telemetry_state: Dict[str, Any] = {"links": {}, "nodes": {}, "timestamp": ""}

    def add_node(self, node_id: str, name: str, model_key: str, sector: str, x: int, y: int) -> Dict[str, Any]:
        profile = HARDWARE_PROFILES.get(model_key, HARDWARE_PROFILES["IP-50FX"])
        dev_uuid = make_uuid(node_id)

        # Build endpoint descriptors for device ports
        endpoints = []
        for port_name in profile["ports"]:
            ep_uuid = make_uuid(f"{node_id}-{port_name}")
            ep_type = "radio" if "radio" in port_name else "ethernet"
            ep_id_doc = {
                "topology_id": {
                    "context_id": {"context_uuid": {"uuid": self.context_uuid}},
                    "topology_uuid": {"uuid": self.topology_uuid},
                },
                "device_id": {"device_uuid": {"uuid": dev_uuid}},
                "endpoint_uuid": {"uuid": ep_uuid},
            }
            ep_doc = {
                "endpoint_id": ep_id_doc,
                "name": port_name,
                "endpoint_type": ep_type,
                "endpoint_location": {"gps_position": {"latitude": 32.0853, "longitude": 34.7818}},
            }
            endpoints.append(ep_doc)

        self.endpoints_by_device[dev_uuid] = endpoints

        # Build 6G Config Rules
        config_rules = [
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "_connect/address",
                    "resource_value": "127.0.0.1"
                }
            },
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/capabilities",
                    "resource_value": json.dumps({
                        "model": model_key,
                        "description": profile["description"],
                        "max_throughput_gbps": profile["max_capacity_gbps"],
                        "max_channel_mhz": profile["max_channel_mhz"],
                        "max_modulation": profile["max_modulation"],
                        "features": profile["features"],
                        "role": profile["role"],
                        "6g_slices_supported": ["URLLC", "eMBB", "mMTC", "QKD"],
                        "ptp_sync_class": "IEEE1588v2_ClassC" if "ClassC" in str(profile["features"]) else "Standard_PTP",
                    }),
                },
            },
            {
                "action": "CONFIGACTION_SET",
                "custom": {
                    "resource_key": "/device/operating_parameters",
                    "resource_value": json.dumps({
                        "power_mode": "ACTIVE_NORMAL",
                        "tx_power_dbm": 24.0 if "IP-" in model_key else 0.0,
                        "acm_enabled": True,
                        "current_modulation": profile["max_modulation"],
                        "sync_status": "LOCKED_PTP_SYNCE",
                        "temperature_celsius": 42.5,
                    }),
                },
            },
        ]

        dev_id_doc = {"device_uuid": {"uuid": dev_uuid}}

        device_doc = {
            "device_id": dev_id_doc,
            "name": name,
            "device_type": profile["device_type"],
            "device_operational_status": "DEVICEOPERATIONALSTATUS_ENABLED",
            "device_drivers": ["DEVICEDRIVER_UNDEFINED"],
            "device_endpoints": endpoints,
            "device_config": {"config_rules": config_rules},
            "_cer_metadata": {
                "id": node_id,
                "name": name,
                "model": model_key,
                "role": profile["role"],
                "sector": sector,
                "x": x,
                "y": y,
                "max_throughput_gbps": profile["max_capacity_gbps"],
            },
        }

        self.nodes.append(device_doc)
        return device_doc

    def add_link(
        self,
        link_id: str,
        src_node_id: str,
        src_port_index: int,
        dst_node_id: str,
        dst_port_index: int,
        link_type: str,
        capacity_gbps: float,
        distance_km: float,
    ) -> Dict[str, Any]:
        src_uuid = make_uuid(src_node_id)
        dst_uuid = make_uuid(dst_node_id)

        src_eps = self.endpoints_by_device.get(src_uuid, [])
        dst_eps = self.endpoints_by_device.get(dst_uuid, [])

        if not src_eps or not dst_eps:
            raise ValueError(f"Endpoints not found for link {link_id}")

        src_ep = src_eps[min(src_port_index, len(src_eps) - 1)]
        dst_ep = dst_eps[min(dst_port_index, len(dst_eps) - 1)]

        link_uuid = make_uuid(link_id)
        link_id_doc = {"link_uuid": {"uuid": link_uuid}}

        link_doc = {
            "link_id": link_id_doc,
            "name": link_id,
            "link_type": "LINKTYPE_FIBER" if link_type == "fiber" else "LINKTYPE_RADIO",
            "link_endpoint_ids": [
                src_ep["endpoint_id"],
                dst_ep["endpoint_id"],
            ],


            "_cer_metadata": {
                "id": link_id,
                "src": src_node_id,
                "dst": dst_node_id,
                "role": link_type,
                "capacity_gbps": capacity_gbps,
                "distance_km": distance_km,
                "status": "active",
            },
        }

        self.links.append(link_doc)

        self.telemetry_state["links"][link_id] = {
            "snr_db": round(random.uniform(32.0, 42.0), 1),
            "rssi_dbm": round(random.uniform(-45.0, -35.0), 1),
            "ber": 1e-11,
            "capacity_gbps": capacity_gbps,
            "utilized_gbps": round(capacity_gbps * random.uniform(0.15, 0.45), 2),
            "latency_ms": round(0.1 + (distance_km * 0.005), 3),
            "jitter_ms": round(random.uniform(0.01, 0.05), 3),
            "acm_modulation": "2048QAM" if "mw" in link_type else "N/A",
            "rain_fade_active": False,
            "status": "HEALTHY",
        }

        return link_doc

    def build_full_6g_topology(self, num_sectors: int = 4) -> Dict[str, Any]:
        """Constructs a hybrid 6G Ring-and-Tree network topology."""
        self.nodes.clear()
        self.links.clear()

        # 1. Core & Edge Cloud Tier
        self.add_node("oran-core", "6G Core DC & UPF", "Core-DC", "core-0", 500, 150)
        self.add_node("edge-dc-1", "Regional Edge Cloud", "Core-DC", "core-0", 500, 250)

        # 2. IP-50FX Core Aggregation Ring (4 Nodes forming a resilient ring)
        ring_coords = [
            ("mw-agg-1", "Agg Ring Node 1", 380, 320, "core-0"),
            ("mw-agg-2", "Agg Ring Node 2", 620, 320, "core-1"),
            ("mw-agg-3", "Agg Ring Node 3", 620, 520, "core-2"),
            ("mw-agg-4", "Agg Ring Node 4", 380, 520, "core-3"),
        ]
        for nid, name, x, y, sec in ring_coords:
            self.add_node(nid, name, "IP-50FX", sec, x, y)

        # Connect Core DC to Agg Ring
        self.add_link("eth-core-agg1", "oran-core", 0, "mw-agg-1", 0, "ethernet", 100.0, 0.2)
        self.add_link("eth-edgedc-agg2", "edge-dc-1", 0, "mw-agg-2", 0, "ethernet", 100.0, 0.2)

        # Build Microwave Aggregation Ring (10 Gbps XPIC Ring links)
        self.add_link("mw-ring-1-2", "mw-agg-1", 2, "mw-agg-2", 2, "mw", 10.0, 4.5)
        self.add_link("mw-ring-2-3", "mw-agg-2", 3, "mw-agg-3", 2, "mw", 10.0, 4.5)
        self.add_link("mw-ring-3-4", "mw-agg-3", 3, "mw-agg-4", 2, "mw", 10.0, 4.5)
        self.add_link("mw-ring-4-1", "mw-agg-4", 3, "mw-agg-1", 3, "mw", 10.0, 4.5)

        # 3. O-RAN CUs connected to Aggregation Ring
        cu_configs = [
            ("oran-cu1", "O-CU North", "O-CU", "core-0", 380, 240, "mw-agg-1"),
            ("oran-cu2", "O-CU East", "O-CU", "core-1", 700, 320, "mw-agg-2"),
            ("oran-cu3", "O-CU South", "O-CU", "core-2", 620, 600, "mw-agg-3"),
            ("oran-cu4", "O-CU West", "O-CU", "core-3", 300, 520, "mw-agg-4"),
        ]
        for cu_id, name, model, sec, x, y, parent_agg in cu_configs:
            self.add_node(cu_id, name, model, sec, x, y)
            self.add_link(f"eth-{cu_id}", cu_id, 0, parent_agg, 1, "ethernet", 25.0, 0.1)

        # 4. Sectors with Midhaul IP-20N Hubs & O-DUs + IP-20C/IP-50E Tails & O-RUs
        sector_params = [
            ("sector-1", "mw-agg-1", 220, 320, 150, 320),
            ("sector-2", "mw-agg-2", 780, 320, 850, 320),
            ("sector-3", "mw-agg-3", 780, 520, 850, 520),
            ("sector-4", "mw-agg-4", 220, 520, 150, 520),
        ]

        for i, (sec_id, parent_agg, hub_x, hub_y, du_x, du_y) in enumerate(sector_params, start=1):
            hub_id = f"mw-hub-{i}"
            du_id = f"oran-du{i}"

            # IP-20N Midhaul Hub
            self.add_node(hub_id, f"Midhaul Hub {i}", "IP-20N", sec_id, hub_x, hub_y)
            self.add_link(f"mw-branch-{i}", parent_agg, 4, hub_id, 2, "mw", 5.0, 3.2)

            # O-DU Node
            self.add_node(du_id, f"O-DU Node {i}", "O-DU", sec_id, du_x, du_y)
            self.add_link(f"eth-du-{i}", du_id, 0, hub_id, 1, "ethernet", 10.0, 0.1)

            # Fronthaul Drops: IP-20C (Microwave Tail) & IP-50E (E-Band mmWave Tail)
            tail1_id = f"mw-tail-{i}a"
            ru1_id = f"oran-ru-{i}a"

            tail2_id = f"mmw-tail-{i}b"
            ru2_id = f"oran-ru-{i}b"

            # Tail 1: IP-20C
            offset_y1 = hub_y - 60
            self.add_node(tail1_id, f"Fronthaul Tail {i}A", "IP-20C", sec_id, hub_x, offset_y1)
            self.add_node(ru1_id, f"O-RU mmWave {i}A", "O-RU", sec_id, du_x, offset_y1)
            self.add_link(f"mw-tail-link-{i}a", hub_id, 3, tail1_id, 1, "mw", 2.5, 1.2)
            self.add_link(f"eth-ru-link-{i}a", ru1_id, 0, tail1_id, 0, "ethernet", 10.0, 0.1)

            # Tail 2: IP-50E (10 Gbps E-Band mmWave)
            offset_y2 = hub_y + 60
            self.add_node(tail2_id, f"E-Band Tail {i}B", "IP-50E", sec_id, hub_x, offset_y2)
            self.add_node(ru2_id, f"O-RU Sub-6G {i}B", "O-RU", sec_id, du_x, offset_y2)
            self.add_link(f"eband-tail-link-{i}b", hub_id, 0, tail2_id, 2, "mmwave", 20.0, 0.8)
            self.add_link(f"eth-ru-link-{i}b", ru2_id, 0, tail2_id, 1, "ethernet", 10.0, 0.1)

        # Assemble full ETSI TeraFlowSDN Descriptor Object
        ctx_id_doc = {"context_uuid": {"uuid": self.context_uuid}}
        topo_id_doc = {
            "context_id": ctx_id_doc,
            "topology_uuid": {"uuid": self.topology_uuid},
        }

        formatted_slices = []
        for s in SLICES_6G:
            slc_id_doc = {
                "context_id": ctx_id_doc,
                "slice_uuid": {"uuid": make_uuid(s["slice_id"])},
            }
            formatted_slices.append({
                "slice_id": slc_id_doc,
                "name": s["name"],
                "slice_config": {"config_rules": []},
                "slice_endpoint_ids": [],
                "slice_constraints": [],
            })

        service_id_doc = {
            "context_id": ctx_id_doc,
            "service_uuid": {"uuid": make_uuid("service-urllc-fronthaul")},
        }

        formatted_services = [
            {
                "service_id": service_id_doc,
                "name": "6G-URLLC-Fronthaul-Service",
                "service_type": "SERVICETYPE_L2NM",
                "service_status": {"service_analysis_status": "SERVICEANALYSISSTATUS_ACTIVE"},
                "service_endpoint_ids": [
                    self.nodes[0]["device_endpoints"][0]["endpoint_id"],
                    self.nodes[-1]["device_endpoints"][0]["endpoint_id"],
                ],
                "service_config": {"config_rules": []},
            }
        ]

        cer_nodes = [d["_cer_metadata"] for d in self.nodes]
        cer_links = [l["_cer_metadata"] for l in self.links]

        # Clean up internal metadata before saving to protobuf JSON
        for node in self.nodes:
            if "_cer_metadata" in node:
                del node["_cer_metadata"]
        for link in self.links:
            if "_cer_metadata" in link:
                del link["_cer_metadata"]

        descriptor_doc = {
            "contexts": [
                {
                    "context_id": ctx_id_doc,
                    "name": self.context_name,
                    "topology_ids": [topo_id_doc]
                }
            ],
            "topologies": [
                {
                    "topology_id": topo_id_doc,
                    "name": self.topology_name,
                }
            ],
            "devices": self.nodes,
            "links": self.links,
            "slices": formatted_slices,
            "services": formatted_services,
            "_cer_intent_topology": {
                "nodes": cer_nodes,
                "links": cer_links,
            },
        }

        return descriptor_doc


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry Simulator Loop
# ──────────────────────────────────────────────────────────────────────────────

def update_live_telemetry_step(descriptor_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Generates dynamic live telemetry updates (SNR fluctuations, rain fade, load spikes)."""
    links_metadata = descriptor_doc.get("_cer_intent_topology", {}).get("links", [])
    now_iso = datetime.now(timezone.utc).isoformat()

    telemetry_state = {
        "timestamp": now_iso,
        "links": {},
        "nodes": {},
        "system_health": "OPTIMAL",
        "active_alerts": [],
    }

    # Simulate occasional rain fade on a random microwave link
    rain_fade_target = random.choice([l["id"] for l in links_metadata if l.get("role") == "mw"]) if random.random() < 0.25 else None

    for link in links_metadata:
        lid = link["id"]
        cap = float(link.get("capacity_gbps", 10.0))
        role = link.get("role", "ethernet")

        if lid == rain_fade_target:
            # Rain fade event: SNR drops, modulation downshifts, latency spikes
            snr = round(random.uniform(14.0, 18.0), 1)
            rssi = round(random.uniform(-68.0, -62.0), 1)
            ber = 1e-6
            util = round(cap * random.uniform(0.70, 0.95), 2)
            lat = round(2.5 + random.uniform(0.5, 1.5), 2)
            mod = "16QAM (ACM Downshift)"
            rain_active = True
            telemetry_state["active_alerts"].append({
                "severity": "WARNING",
                "link_id": lid,
                "message": f"Rain fade detected on link {lid}. ACM downshifted to 16QAM.",
            })
        else:
            snr = round(random.uniform(34.0, 44.0), 1) if role == "mw" else 50.0
            rssi = round(random.uniform(-42.0, -32.0), 1) if role == "mw" else -20.0
            ber = 1e-12
            util = round(cap * random.uniform(0.20, 0.55), 2)
            lat = round(0.1 + (float(link.get("distance_km", 1.0)) * 0.005), 3)
            mod = "2048QAM" if role == "mw" else "N/A"
            rain_active = False

        telemetry_state["links"][lid] = {
            "snr_db": snr,
            "rssi_dbm": rssi,
            "ber": ber,
            "capacity_gbps": cap,
            "utilized_gbps": util,
            "utilization_percent": round((util / cap) * 100, 1),
            "latency_ms": lat,
            "jitter_ms": round(random.uniform(0.005, 0.03), 3),
            "acm_modulation": mod,
            "rain_fade_active": rain_active,
            "status": "DEGRADED" if rain_active else "HEALTHY",
        }

    # Simulate node state
    nodes_metadata = descriptor_doc.get("_cer_intent_topology", {}).get("nodes", [])
    for node in nodes_metadata:
        nid = node["id"]
        telemetry_state["nodes"][nid] = {
            "cpu_utilization_percent": round(random.uniform(15.0, 45.0), 1),
            "memory_utilization_percent": round(random.uniform(30.0, 60.0), 1),
            "temperature_celsius": round(random.uniform(38.0, 46.0), 1),
            "power_consumption_watts": round(random.uniform(45.0, 120.0), 1),
            "ptp_sync_lock": True,
            "operational_status": "OPERATIONAL",
        }

    return telemetry_state


# ──────────────────────────────────────────────────────────────────────────────
# CLI Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="6G Transport Topology Generator for TeraFlow SDN (TFS)"
    )
    parser.add_argument(
        "-o", "--output",
        default="data/6g_transport_tfs_descriptors.json",
        help="Target output path for TFS JSON descriptors file",
    )
    parser.add_argument(
        "--sectors",
        type=int,
        default=4,
        help="Number of 6G transport sectors to generate (default: 4)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable continuous live telemetry streaming loop",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Interval in seconds between live telemetry updates (default: 3)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print(" [6G] ETSI TeraFlowSDN (TFS) -- 6G Transport Topology Generator")
    print("=" * 70)

    builder = Topology6GBuilder()
    descriptor_doc = builder.build_full_6g_topology(num_sectors=args.sectors)

    # Ensure output directory exists
    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # Write TFS Descriptor JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(descriptor_doc, f, indent=2)

    num_devices = len(descriptor_doc["devices"])
    num_links = len(descriptor_doc["links"])
    num_slices = len(descriptor_doc["slices"])

    print(f" [+] Created 6G TFS Descriptors at: {args.output}")
    print(f"     |-- Devices: {num_devices} (Core DC, IP-50FX, IP-20N, IP-20C, IP-50E, O-CU/DU/RU)")
    print(f"     |-- Links:   {num_links} (100G Ether, 10G XPIC MW Ring, 20G E-Band mmWave)")
    print(f"     +-- Slices:  {num_slices} (URLLC, eMBB, mMTC, QKD Encrypted)")

    # Also update CER-Intent local topology_state.json for immediate dashboard reflection
    state_file = "data/topology_state.json"
    cer_topo = descriptor_doc["_cer_intent_topology"]
    initial_telemetry = update_live_telemetry_step(descriptor_doc)
    state_doc = {
        "nodes": cer_topo["nodes"],
        "links": cer_topo["links"],
        "telemetry": initial_telemetry,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    if os.path.exists(os.path.dirname(state_file)):
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_doc, f, indent=2)
        print(f" [+] Updated CER-Intent topology state at: {state_file}")

    if args.live:
        print(f"\n [*] Starting Live Telemetry Streamer (Interval: {args.interval}s, Press Ctrl+C to stop)...")
        try:
            step_count = 0
            while True:
                step_count += 1
                telemetry = update_live_telemetry_step(descriptor_doc)
                state_doc["telemetry"] = telemetry
                state_doc["last_updated"] = datetime.now(timezone.utc).isoformat()

                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(state_doc, f, indent=2)

                alerts = telemetry.get("active_alerts", [])
                alert_str = f" [!] Alert: {alerts[0]['message']}" if alerts else " [OK] Status: Normal"
                print(f"   [{datetime.now().strftime('%H:%M:%S')}] Step #{step_count} -- Telemetry updated.{alert_str}")

                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n [!] Live Telemetry Streamer stopped.")

    print("\n Done! File ready to be uploaded to TFS Web UI at http://localhost:8004/")


if __name__ == "__main__":
    main()
