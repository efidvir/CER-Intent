"""
Network Slice Controller (NSC) - DMO for Transport Domain (D3.1 Section 2.4.1.1)
================================================================================
Implements the 5 functional blocks defined in D3.1 Figure 2-17:
  1. NBI Processor (Translator): CRUD for IETF RFC 9543 Slice Services & Templates
  2. Mapper: Enriches slice requests with topology and triggers the Planner
  3. Planner (NDT PCE): Path Computation Engine powered by the Network Digital Twin
  4. Realizer: Translates slice into IETF L2SM (RFC 9291) and L3SM (RFC 9182) for TFS
  5. Slice Datastore: Central persistent state of active transport slices & TVR schedules
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, List, Optional, Any

from cer_intent.nsc.ietf_models import (
    SLOSLETemplate,
    ServiceDemarcationPoint,
    ConnectivityConstruct,
    IETFSliceService,
    generate_ietf_l2sm_payload,
    generate_ietf_l3sm_payload,
    TVRScheduleItem,
    InstantaneousDeviceEnergy,
    StaticDeviceEnergy,
    IETFTelemetrySubscription,
)
from cer_intent.nsc.pce_planner import NDTPathComputationEngine

logger = logging.getLogger("NetworkSliceController")


class NetworkSliceController:
    """
    Domain Management Orchestrator (DMO) for the Transport / xHaul Domain.
    """

    def __init__(self, tfs_client=None, adapter=None, audit_log=None):
        self.tfs_client = tfs_client
        self.adapter = adapter
        self.audit_log = audit_log

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
        """Fetch live topology from TFS client if available, or return fallback."""
        if self.tfs_client:
            try:
                return self.tfs_client.fetch_normalized_topology()
            except Exception as e:
                logger.warning(f"Could not fetch topology from TFS: {e}")
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
    # Functional Block 1 & 2: NBI Processor & Mapper
    # ─────────────────────────────────────────────────────────────────────────

    def create_or_update_slice_service(self, raw_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the 7-step Transport Service Creation Workflow (D3.1 Figure 2-18):
          1. Ingest slice request
          2. NBI Processor normalizes to IETF Slice
          3. Mapper extracts endpoints & constraints
          4. Mapper triggers Planner (NDT PCE)
          5. Planner computes optimal underlay path
          6. Realizer converts to L2SM (RFC 9291) or L3SM (RFC 9182)
          7. Dispatches to TFS / transport infrastructure
        """
        # Step 1 & 2: NBI Processor parsing
        slice_id = raw_req.get("id") or raw_req.get("slice_id") or f"slice-{uuid.uuid4().hex[:6]}"
        desc = raw_req.get("description", f"IETF Network Slice {slice_id}")
        tpl_ref = raw_req.get("slo_sle_template_ref") or raw_req.get("slo-sle-policy", {}).get("slo-sle-template", "template-urllc-mission-critical")
        
        sdps_raw = raw_req.get("sdps", {}).get("sdp", []) or raw_req.get("sdps", [])
        sdp_objects = []
        for s in sdps_raw:
            sdp_objects.append(ServiceDemarcationPoint(
                sdp_id=s.get("id") or s.get("sdp_id", f"sdp-{uuid.uuid4().hex[:4]}"),
                node_id=s.get("node_id") or s.get("node-id", "ctu-96"),
                tp_id=s.get("tp_id") or s.get("tp-id", "eth0"),
                ip_address=s.get("ip_address"),
                vlan_id=s.get("vlan_id"),
                dscp_code=s.get("dscp_code", 46)
            ))

        # Default SDPs if omitted (ctu-96 to edge-router-02)
        if len(sdp_objects) < 2:
            sdp_objects = [
                ServiceDemarcationPoint("sdp-ingress", "ctu-96", "eth0", "192.168.1.225", 100, 46),
                ServiceDemarcationPoint("sdp-egress", "edge-router-02", "eth1", "10.100.2.1", 100, 46)
            ]

        # Step 3: Mapper extracts parameters & constraints
        template = self.templates.get(tpl_ref)
        max_lat = None
        min_bw = None
        isolation = "logical"
        if template:
            for slo in template.slos:
                if "delay" in slo.get("metric_type", ""):
                    max_lat = slo.get("metric_value")
                elif "bandwidth" in slo.get("metric_type", ""):
                    min_bw = slo.get("metric_value")
            for sle in template.sles:
                if sle.get("expectation_type") == "isolation":
                    isolation = sle.get("expectation_value")

        # Step 4 & 5: Planner (NDT PCE) computes optimal underlay path
        src_node = sdp_objects[0].node_id
        dst_node = sdp_objects[1].node_id
        
        # Pull active TVR schedules to ensure path avoids degraded/unavailable links
        active_tvr = list(self.tvr_schedules.values())
        
        pce_result = self.planner.compute_constrained_path(
            src_node=src_node,
            dst_node=dst_node,
            max_latency_ms=max_lat,
            bandwidth_mbps=min_bw,
            isolation_policy=isolation,
            tvr_schedules=active_tvr
        )

        computed_path = pce_result.get("computed_path", [src_node, dst_node])
        is_feasible = pce_result.get("feasible", True)

        # Step 6: Realizer selection (L2SM or L3SM)
        requested_tech = raw_req.get("realization_technology", "L2SM").upper()
        if "L3" in requested_tech or "IP" in requested_tech:
            realization_tech = "L3SM"
            controller_payload = generate_ietf_l3sm_payload(
                slice_service=IETFSliceService(
                    slice_id=slice_id,
                    description=desc,
                    slo_sle_template_ref=tpl_ref,
                    sdps=sdp_objects,
                    computed_path=computed_path
                ),
                dscp=sdp_objects[0].dscp_code or 46
            )
        else:
            realization_tech = "L2SM"
            controller_payload = generate_ietf_l2sm_payload(
                slice_service=IETFSliceService(
                    slice_id=slice_id,
                    description=desc,
                    slo_sle_template_ref=tpl_ref,
                    sdps=sdp_objects,
                    computed_path=computed_path
                ),
                dscp=sdp_objects[0].dscp_code or 46
            )

        # Assemble RFC 9543 Slice Service
        slice_svc = IETFSliceService(
            slice_id=slice_id,
            description=desc,
            slo_sle_template_ref=tpl_ref,
            sdps=sdp_objects,
            connectivity_constructs=[
                ConnectivityConstruct(
                    construct_id=f"cc-{slice_id}-1",
                    connectivity_type="point-to-point",
                    src_sdp_id=sdp_objects[0].sdp_id,
                    dst_sdp_id=sdp_objects[1].sdp_id
                )
            ],
            status="active" if is_feasible else "degraded",
            computed_path=computed_path,
            realization_technology=realization_tech,
            controller_reference="TeraFlowSDN"
        )
        self.slices[slice_id] = slice_svc

        # Step 7: Southbound Controller dispatch to TFS (if connected)
        tfs_dispatch_status = "STAGED_LOCAL"
        if self.tfs_client:
            try:
                # TFS slice handler invocation
                tfs_resp = self.tfs_client.create_or_update_slice({
                    "slice_id": {"slice_uuid": {"uuid": slice_id}},
                    "slice_endpoint_ids": [
                        {"endpoint_uuid": {"uuid": sdp.tp_id}, "device_id": {"device_uuid": {"uuid": sdp.node_id}}}
                        for sdp in sdp_objects
                    ],
                    "slice_status": {"slice_status": 2},  # SLICESTATUS_ACTIVE
                    "slice_config": {
                        "config_rules": [
                            {"action": 1, "custom": {"resource_key": "/service/realization", "resource_value": realization_tech}},
                            {"action": 1, "custom": {"resource_key": "/service/computed_path", "resource_value": str(computed_path)}},
                        ]
                    }
                })
                tfs_dispatch_status = "COMMITTED_TO_TFS"
            except Exception as e:
                logger.warning(f"TFS dispatch warning: {e}")
                tfs_dispatch_status = f"LOCAL_EMULATED (TFS: {e})"

        # Trigger Subscribed Notifications if any subscribers are registered for this slice
        self._notify_subscribers(slice_id, slice_svc, pce_result)

        return {
            "ietf-network-slice-service:network-slice-services": {
                "slice-service": [slice_svc.to_ietf_dict()]
            },
            "nsc_workflow": {
                "step_1_idmo_request": "RECEIVED",
                "step_2_ietf_slice_normalized": True,
                "step_3_mapper_extracted": {
                    "template": tpl_ref,
                    "max_latency_slo_ms": max_lat,
                    "isolation_sle": isolation
                },
                "step_4_5_planner_pce": pce_result,
                "step_6_realizer_technology": realization_tech,
                "step_7_controller_payload": controller_payload,
                "controller_status": tfs_dispatch_status
            }
        }

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
