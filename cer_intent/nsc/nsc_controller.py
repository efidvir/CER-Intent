"""
Network Slice Controller (NSC) - DMO for the Transport Domain
=============================================================
Takes RFC 9543 slice requests (from OpenSlice or any client) and realizes them
on TeraFlowSDN through its standard interfaces, in the stages the TeraFlowSDN
slice controller uses:

  1. Mapper               nsc/mapper.py               endpoints, SLOs, connectivity, ACs
  2. Technology Selector  nsc/technology_selector.py  L2VPN or L3VPN
  3. Realizer             nsc/realizer.py             L2SM (RFC 8466) / L3SM (RFC 8299)

CER-Intent adds a twin-backed planner check (NDT PCE) between mapping and
selection, an optional selector skill, and radio/ACM decisions that travel as
TeraFlowSDN service settings. It also keeps the slice datastore, SLO/SLE
templates, TVR schedules and subscriptions.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from cer_intent.nsc.ietf_models import (
    SLOSLETemplate,
    ServiceDemarcationPoint,
    ConnectivityConstruct,
    IETFSliceService,
    TVRScheduleItem,
    InstantaneousDeviceEnergy,
    StaticDeviceEnergy,
    IETFTelemetrySubscription,
)
from cer_intent.nsc.mapper import MappingError, map_request
from cer_intent.nsc.pce_planner import NDTPathComputationEngine
from cer_intent.nsc.realizer import Realization, Realizer
from cer_intent.nsc.technology_selector import SelectorSkill, select_technology
from cer_intent.nsc.topology_file import load_topology_file

logger = logging.getLogger("NetworkSliceController")


class NetworkSliceController:
    """
    Domain Management Orchestrator (DMO) for the Transport / xHaul Domain.
    """

    def __init__(self, tfs_client=None, adapter=None, audit_log=None,
                 realization_mode: Optional[str] = None, technology_skill: Optional[SelectorSkill] = None):
        self.tfs_client = tfs_client
        self.adapter = adapter
        self.audit_log = audit_log
        self.realizer = Realizer(tfs_client=tfs_client, mode=realization_mode)
        self.technology_skill = technology_skill
        self.realizations: Dict[str, Realization] = {}
        self.topology_source = "not read yet"

        # Datastores
        self.templates: Dict[str, SLOSLETemplate] = {}
        self.slices: Dict[str, IETFSliceService] = {}
        self.tvr_schedules: Dict[str, TVRScheduleItem] = {}
        self.subscriptions: Dict[str, IETFTelemetrySubscription] = {}

        # Planner
        self.planner = NDTPathComputationEngine(
            topology_provider=self._get_current_topology
        )

        # Initialize standard default templates
        self._init_default_templates()
        self._init_default_energy_records()

    def _get_current_topology(self) -> Dict[str, Any]:
        """
        The planner's topology: TeraFlowSDN when a client is configured, else the
        descriptor file in $CER_INTENT_TOPOLOGY_FILE, else the built-in reference.
        """
        if self.tfs_client:
            try:
                topo = self.tfs_client.fetch_normalized_topology()
                self.topology_source = "TeraFlowSDN"
                return topo
            except Exception as e:
                logger.warning(f"Could not fetch topology from TFS: {e}")
        topo = load_topology_file()
        if topo:
            self.topology_source = topo["source"]
            return topo
        self.topology_source = "reference"
        return self.planner._get_default_6g_topology()

    def _init_default_templates(self):
        """Initializes standard 3GPP/IETF SLO-SLE templates from D3.1."""
        urllc_tpl = SLOSLETemplate(
            id="template-urllc-mission-critical",
            description="URLLC Low-Latency Profile (< 1.5ms, 99.999% availability)",
            slos=[
                {"metric_type": "one-way-delay-maximum", "metric_unit": "milliseconds", "metric_value": 1.5},
                {"metric_type": "jitter-maximum", "metric_unit": "milliseconds", "metric_value": 0.5},
                {"metric_type": "packet-loss-ratio", "metric_unit": "percentage", "metric_value": 0.001},
                {"metric_type": "bandwidth-guaranteed", "metric_unit": "mbps", "metric_value": 500.0},
            ],
            sles=[
                {"expectation_type": "isolation", "expectation_value": "physical-or-dedicated-time-slot", "enforcement_rule": "strict"},
                {"expectation_type": "security", "expectation_value": "macsec-encrypted", "enforcement_rule": "strict"},
                {"expectation_type": "availability", "expectation_value": "99.999%", "enforcement_rule": "strict"},
            ]
        )
        embb_tpl = SLOSLETemplate(
            id="template-embb-high-throughput",
            description="eMBB High-Throughput Profile (>= 2 Gbps, < 15ms latency)",
            slos=[
                {"metric_type": "one-way-delay-maximum", "metric_unit": "milliseconds", "metric_value": 15.0},
                {"metric_type": "bandwidth-guaranteed", "metric_unit": "mbps", "metric_value": 2000.0},
                {"metric_type": "packet-loss-ratio", "metric_unit": "percentage", "metric_value": 0.01},
            ],
            sles=[
                {"expectation_type": "isolation", "expectation_value": "logical-slice", "enforcement_rule": "flexible"},
            ]
        )
        self.templates[urllc_tpl.id] = urllc_tpl
        self.templates[embb_tpl.id] = embb_tpl

    def _init_default_energy_records(self):
        """Populate initial energy records according to D3.1 Section 4.2.5."""
        self.instantaneous_energy_db: Dict[str, InstantaneousDeviceEnergy] = {
            "HL4_5_1_Huawei": InstantaneousDeviceEnergy(
                name="HL4_5_1_Huawei",
                power=403.0,
                energy_mode="basic",
                energy_efficiency=0.000403,
                configuration_summary="PIC_1;PIC_2;NPU_10;PIC_5;MPU_11;PSU_13;PSU_14",
                transceivers_summary="0x100G",
                boards_summary="PIC_1;PIC_2;NPU_10;PIC_5;MPU_11",
                ambient_temperature=24.5,
                cpu_load=4,
                fan_speed=3200,
                traffic_type="IDLE",
                traffic_throughput_gbps=0.0,
                traffic_packet_size_bytes=0,
                power_supplies=[
                    {"name": "PSU_13", "input-current": 3.91, "input-voltage": 54.66, "input-power": 213.72},
                    {"name": "PSU_14", "input-current": 3.46, "input-voltage": 54.72, "input-power": 189.33},
                ],
                boards=[
                    {"name": "PIC_1", "type": "PIC", "power": 62.40},
                    {"name": "PIC_2", "type": "PIC", "power": 62.40},
                    {"name": "NPU_10", "type": "NPU", "power": 243.44},
                    {"name": "MPU_11", "type": "MPU", "power": 35.00},
                ],
                components=[],
                transceivers=[]
            ),
            "ctu-96": InstantaneousDeviceEnergy(
                name="ctu-96",
                power=28.5,
                energy_mode="basic",
                energy_efficiency=0.000014,
                configuration_summary="Ceragon Siklu MH-T261 Node B; mmWave V-band 60GHz",
                transceivers_summary="Integrated 4-sector beamforming RF",
                boards_summary="Baseband-Modem-V1; Sector-Controller",
                ambient_temperature=31.2,
                cpu_load=12,
                fan_speed=0,
                traffic_type="LIVE_FR1_FR2",
                traffic_throughput_gbps=1.45,
                traffic_packet_size_bytes=1280,
                power_supplies=[
                    {"name": "PoE-Injector-01", "input-current": 0.52, "input-voltage": 55.0, "input-power": 28.5}
                ],
                boards=[
                    {"name": "Sector-1-Active", "type": "RF_MODEM", "power": 14.25},
                    {"name": "Sector-2-Redundant", "type": "RF_MODEM", "power": 14.25},
                ],
                components=[],
                transceivers=[{"name": "RF-60G", "type": "V-Band", "power": 6.5}]
            )
        }

        self.static_energy_db: Dict[str, StaticDeviceEnergy] = {
            "HL4_5_1_Huawei": StaticDeviceEnergy(
                name="HL4_5_1_Huawei",
                typical_power=58.71,
                nominal_power=550.0,
                max_power=717.81,
                maximum_traffic_throughput="1Tbps (200Gbps)",
                efficiency=0.00055,
                power_supplies=[{"name": "PSU_13", "type": "PSU"}, {"name": "PSU_14", "type": "PSU"}],
                boards=[
                    {"name": "MPU_11", "type": "MPU", "typical-power": 35.0, "nominal-power": 49.0},
                    {"name": "PIC_1", "type": "PIC", "capacity": "100G", "typical-power": 62.4, "nominal-power": 70.0},
                    {"name": "NPU_10", "type": "NPU", "typical-power": 240.0, "nominal-power": 375.0},
                ],
                transceivers=[{"name": "T100G", "type": "100G", "capacity": "100G", "typical-power": 4.0}]
            ),
            "ctu-96": StaticDeviceEnergy(
                name="ctu-96",
                typical_power=28.5,
                nominal_power=32.0,
                max_power=40.0,
                maximum_traffic_throughput="2.0Gbps",
                efficiency=0.000016,
                power_supplies=[{"name": "PoE-Injector-01", "capacity": 60.0, "typical-power": 28.5, "nominal-power": 32.0}],
                boards=[
                    {"name": "Baseband-01", "type": "BASEBAND", "capacity": 2000.0, "typical-power": 12.0, "nominal-power": 15.0}
                ],
                transceivers=[{"name": "Beamforming-Array", "type": "RF-60G", "capacity": 2000.0, "typical-power": 14.0}]
            )
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Slice pipeline: Mapper -> Planner -> Technology Selector -> Realizer
    # (the same stages as the TeraFlowSDN slice controller, plus the twin-backed
    # planner check that CER-Intent adds between mapping and selection)
    # ─────────────────────────────────────────────────────────────────────────

    def create_or_update_slice_service(self, raw_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Realize one RFC 9543 slice service request.

          1. Mapper               endpoints, SLOs, connectivity, attachment circuits
          2. Planner (NDT PCE)    advisory path and SLO check on the digital twin
          3. Technology Selector  L2VPN or L3VPN, with the reason
          4. Realizer             L2SM (RFC 8466) / L3SM (RFC 8299) to TeraFlowSDN,
                                  radio and ACM decisions as service settings

        A request that cannot be mapped or realized returns {"error": ..., "status": 400}.
        """
        try:
            mapped = map_request(raw_req, self.templates)
        except MappingError as e:
            return {"error": str(e), "status": 400, "stage": "mapper"}

        pce_result = self.planner.compute_constrained_path(
            src_node=mapped.endpoints[0].node_id,
            dst_node=mapped.endpoints[1].node_id,
            max_latency_ms=mapped.slos.max_latency_ms,
            bandwidth_mbps=mapped.slos.bandwidth_mbps,
            isolation_policy=str(mapped.sles.get("isolation", "logical")),
            tvr_schedules=list(self.tvr_schedules.values()),
        )
        computed_path = pce_result.get("computed_path", [ep.node_id for ep in mapped.endpoints])

        choice = select_technology(mapped, skill=self.technology_skill)

        if self.realizer.mode == "tfs-api":
            realization = self.realizer.build(mapped, choice.technology)
            realization.controller_response = self._legacy_tfs_api_dispatch(mapped, choice.technology, computed_path)
            realization.status = "sent" if realization.controller_response.get("ok") else "failed"
        else:
            realization = self.realizer.realize(mapped, choice.technology)
        if realization.status == "failed" and realization.payload == {}:
            return {"error": realization.error, "status": 400, "stage": "realizer"}

        slice_svc = IETFSliceService(
            slice_id=mapped.slice_id,
            description=mapped.description,
            slo_sle_template_ref=mapped.template_ref or "",
            sdps=[
                ServiceDemarcationPoint(ep.sdp_id, ep.node_id, ep.tp_id, ep.ip_address, ep.vlan_id, None)
                for ep in mapped.endpoints
            ],
            connectivity_constructs=[
                ConnectivityConstruct(
                    construct_id=cc.construct_id,
                    connectivity_type=group.connectivity_type,
                    src_sdp_id=cc.sender_sdp or mapped.endpoints[0].sdp_id,
                    dst_sdp_id=cc.receiver_sdp or mapped.endpoints[1].sdp_id,
                )
                for group in mapped.connection_groups for cc in group.constructs
            ],
            status=self._slice_status(realization.status, pce_result.get("feasible", True)),
            computed_path=computed_path,
            realization_technology="L3SM" if choice.technology == "L3VPN" else "L2SM",
            controller_reference="TeraFlowSDN",
        )
        self.slices[mapped.slice_id] = slice_svc
        self.realizations[mapped.slice_id] = realization
        self._notify_subscribers(mapped.slice_id, slice_svc, pce_result)

        return {
            "ietf-network-slice-service:network-slice-services": {
                "slice-service": [slice_svc.to_ietf_dict()]
            },
            "nsc_pipeline": {
                "mapper": {
                    "endpoints": [
                        {"sdp": ep.sdp_id, "node": ep.node_id, "tp": ep.tp_id, "ip": ep.ip_address, "vlan": ep.vlan_id}
                        for ep in mapped.endpoints
                    ],
                    "slos": asdict(mapped.slos),
                    "connectivity": [
                        {"group": g.group_id, "type": g.connectivity_type, "constructs": len(g.constructs)}
                        for g in mapped.connection_groups
                    ],
                    "attachment_circuits": sum(len(ep.attachment_circuits) for ep in mapped.endpoints),
                },
                "planner": pce_result,
                "technology_selector": choice.to_dict(),
                "realizer": realization.to_dict(),
            },
        }

    @staticmethod
    def _slice_status(realization_status: str, feasible: Optional[bool]) -> str:
        if realization_status == "failed":
            return "failed"
        if feasible is False:  # None: the twin could not check the path
            return "degraded"
        return "active" if realization_status == "sent" else "planned"

    def delete_slice_service(self, slice_id: str) -> Optional[Dict[str, Any]]:
        """Withdraw a slice from TeraFlowSDN and the datastore. None if unknown."""
        svc = self.slices.get(slice_id)
        if svc is None:
            return None
        realization = self.realizations.get(slice_id)
        technology = realization.technology if realization else (
            "L3VPN" if svc.realization_technology == "L3SM" else "L2VPN")
        result = self.realizer.withdraw(slice_id, technology)
        if result.get("status") != "failed":
            self.slices.pop(slice_id, None)
            self.realizations.pop(slice_id, None)
        return result

    def _legacy_tfs_api_dispatch(self, mapped, technology: str, computed_path: List[str]) -> Dict[str, Any]:
        """Earlier behaviour (TFS_REALIZATION=tfs-api): a custom slice object via the TFS API."""
        if not self.tfs_client:
            return {"ok": False, "error": "no TeraFlowSDN client configured"}
        try:
            self.tfs_client.create_or_update_slice({
                "slice_id": {"slice_uuid": {"uuid": mapped.slice_id}},
                "slice_endpoint_ids": [
                    {"endpoint_uuid": {"uuid": ep.tp_id}, "device_id": {"device_uuid": {"uuid": ep.node_id}}}
                    for ep in mapped.endpoints
                ],
                "slice_status": {"slice_status": 2},
                "slice_config": {"config_rules": [
                    {"action": 1, "custom": {"resource_key": "/service/realization", "resource_value": technology}},
                    {"action": 1, "custom": {"resource_key": "/service/computed_path", "resource_value": str(computed_path)}},
                ]},
            })
            return {"ok": True}
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"TFS dispatch warning: {e}")
            return {"ok": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # Subscribed Notifications (RFC 8639)
    # ─────────────────────────────────────────────────────────────────────────

    def establish_subscription(self, raw_sub: Dict[str, Any]) -> Dict[str, Any]:
        """Implements /restconf/operations/ietf-subscribed-notifications:establish-subscription"""
        sub_id = f"sub-{uuid.uuid4().hex[:6]}"
        target_slice = raw_req = raw_sub.get("slice_id") or raw_sub.get("target_slice", "all")
        destination = raw_sub.get("notification_destination", "http://localhost:5000/api/v1/telemetry/callbacks")
        period = int(raw_sub.get("period_seconds", 5))

        sub = IETFTelemetrySubscription(
            subscription_id=sub_id,
            slice_id=target_slice,
            notification_destination=destination,
            period_seconds=period
        )
        self.subscriptions[sub_id] = sub
        return {
            "ietf-subscribed-notifications:output": {
                "id": sub_id,
                "status": "subscription-established",
                "target-slice": target_slice,
                "destination": destination,
                "period": period
            }
        }

    def _notify_subscribers(self, slice_id: str, slice_svc: IETFSliceService, pce_result: Dict[str, Any]):
        for sub_id, sub in self.subscriptions.items():
            if sub.slice_id in [slice_id, "all"]:
                event = {
                    "subscription_id": sub_id,
                    "timestamp": time.time(),
                    "slice_id": slice_id,
                    "status": slice_svc.status,
                    "slo_compliance": {
                        "predicted_latency_ms": pce_result.get("total_predicted_latency_ms"),
                        "compliant": pce_result.get("feasible", True)
                    }
                }
                sub.history.append(event)
                sub.last_notified = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # Time-Variant Routing (TVR) Schedules (Section 4.2.4.3)
    # ─────────────────────────────────────────────────────────────────────────

    def add_tvr_schedule(self, schedule_dict: Dict[str, Any]) -> TVRScheduleItem:
        sched_id = schedule_dict.get("schedule_id", f"tvr-{uuid.uuid4().hex[:4]}")
        item = TVRScheduleItem(
            schedule_id=sched_id,
            target_element_id=schedule_dict.get("target_element_id", "link-ctu96-ctu97"),
            element_type=schedule_dict.get("element_type", "link"),
            start_time_iso=schedule_dict.get("start_time_iso", "2026-10-13T14:00:00Z"),
            duration_seconds=int(schedule_dict.get("duration_seconds", 1800)),
            scheduled_state=schedule_dict.get("scheduled_state", "degraded"),
            predicted_capacity_mbps=schedule_dict.get("predicted_capacity_mbps", 450.0),
            predicted_attenuation_db=schedule_dict.get("predicted_attenuation_db", 14.5),
            reason=schedule_dict.get("reason", "heavy-rain-attenuation")
        )
        self.tvr_schedules[sched_id] = item
        return item
