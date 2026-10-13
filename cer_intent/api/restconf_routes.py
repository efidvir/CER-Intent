"""
IETF RESTCONF Transport Exposure API (D3.1 Section 3.4.1, 4.2.4 & 4.2.5)
========================================================================
Implements RFC 8040 RESTCONF interface for:
  - IETF RFC 9543: Network Slice Service YANG Model
  - IETF RFC 9291 (L2SM) & RFC 9182 (L3SM) Realizer Payloads
  - RFC 8639 Subscribed Notifications (ietf-subscribed-notifications:establish-subscription)
  - RFC 8345 Topology & IETF TVR (Time-Variant Routing) Schedules
  - Telefónica Transport Energy Models (instantaneous-device-energy-tid & static-device-energy-tid)
  - NDT PCE Path Computation Engine Operation (ietf-pce:compute-path)
"""
import logging
from flask import Blueprint, jsonify, request, current_app, Response

from cer_intent.nsc.nsc_controller import NetworkSliceController
from cer_intent.nsc.ietf_models import SLOSLETemplate, ServiceDemarcationPoint

logger = logging.getLogger("RESTCONF_Transport_API")

restconf_bp = Blueprint("restconf", __name__, url_prefix="/restconf")

# Global singleton instance of NSC (attached to current_app when initialized)
_nsc_instance: NetworkSliceController = None


def get_nsc() -> NetworkSliceController:
    global _nsc_instance
    if _nsc_instance is None:
        tfs_client = current_app.config.get("adapter")
        if hasattr(tfs_client, "tfs_client"):
            tfs_client = tfs_client.tfs_client
        adapter = current_app.config.get("adapter")
        audit_log = current_app.config.get("audit_log")
        _nsc_instance = NetworkSliceController(tfs_client=tfs_client, adapter=adapter, audit_log=audit_log)
    return _nsc_instance


# ─────────────────────────────────────────────────────────────────────────────
# 1. RFC 9543: Network Slice Services (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services", methods=["GET"])
def get_network_slice_services():
    """Retrieve full RFC 9543 Network Slice Services data tree."""
    nsc = get_nsc()
    slices_list = [s.to_ietf_dict() for s in nsc.slices.values()]
    templates_list = [t.to_ietf_dict() for t in nsc.templates.values()]
    return jsonify({
        "ietf-network-slice-service:network-slice-services": {
            "slo-sle-templates": {
                "slo-sle-template": templates_list
            },
            "slice-service": slices_list
        }
    }), 200, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services", methods=["POST"])
def post_network_slice_services():
    """Create a new network slice service or template via root container."""
    nsc = get_nsc()
    body = request.get_json(silent=True) or {}
    
    root_data = body.get("ietf-network-slice-service:network-slice-services", body)
    if "slice-service" in root_data:
        items = root_data["slice-service"]
        if isinstance(items, list) and items:
            res = nsc.create_or_update_slice_service(items[0])
            return jsonify(res), 201, {"Content-Type": "application/yang-data+json"}
    
    res = nsc.create_or_update_slice_service(body)
    return jsonify(res), 201, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slo-sle-templates/slo-sle-template", methods=["GET", "POST"])
def manage_slo_sle_templates():
    """Get or define SLO/SLE templates (RFC 9543 Section 3.1)."""
    nsc = get_nsc()
    if request.method == "GET":
        templates_list = [t.to_ietf_dict() for t in nsc.templates.values()]
        return jsonify({
            "ietf-network-slice-service:slo-sle-template": templates_list
        }), 200, {"Content-Type": "application/yang-data+json"}

    body = request.get_json(silent=True) or {}
    tpl_data = body.get("ietf-network-slice-service:slo-sle-template", body)
    t_id = tpl_data.get("id", f"tpl-{len(nsc.templates)+1}")
    desc = tpl_data.get("description", "Custom SLO-SLE template")
    slos = tpl_data.get("metric-bounds", {}).get("metric-bound", []) or tpl_data.get("slos", [])
    sles = tpl_data.get("service-level-expectations", {}).get("expectation", []) or tpl_data.get("sles", [])

    tpl = SLOSLETemplate(id=t_id, description=desc, slos=slos, sles=sles)
    nsc.templates[t_id] = tpl
    return jsonify({"ietf-network-slice-service:slo-sle-template": [tpl.to_ietf_dict()]}), 201, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slice-service", methods=["GET", "POST"])
def manage_slice_services():
    """List or create active network slice services."""
    nsc = get_nsc()
    if request.method == "GET":
        return jsonify({
            "ietf-network-slice-service:slice-service": [s.to_ietf_dict() for s in nsc.slices.values()]
        }), 200, {"Content-Type": "application/yang-data+json"}

    body = request.get_json(silent=True) or {}
    slice_data = body.get("ietf-network-slice-service:slice-service", body)
    if isinstance(slice_data, list) and slice_data:
        slice_data = slice_data[0]
    res = nsc.create_or_update_slice_service(slice_data)
    return jsonify(res), 201, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slice-service=<slice_id>", methods=["GET", "PUT", "DELETE"])
@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slice-service={<slice_id>}", methods=["GET", "PUT", "DELETE"])
def slice_service_instance(slice_id: str):
    """Retrieve, update or delete a specific slice service by ID."""
    nsc = get_nsc()
    slice_id = slice_id.strip("{}")
    
    if request.method == "GET":
        svc = nsc.slices.get(slice_id)
        if not svc:
            return jsonify({"error": f"Slice '{slice_id}' not found"}), 404
        return jsonify({
            "ietf-network-slice-service:slice-service": [svc.to_ietf_dict()]
        }), 200, {"Content-Type": "application/yang-data+json"}

    if request.method == "DELETE":
        if slice_id in nsc.slices:
            del nsc.slices[slice_id]
            return Response(status=204)
        return jsonify({"error": f"Slice '{slice_id}' not found"}), 404

    # PUT
    body = request.get_json(silent=True) or {}
    body["id"] = slice_id
    res = nsc.create_or_update_slice_service(body)
    return jsonify(res), 200, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slice-service=<slice_id>/sdps", methods=["GET", "POST"])
@restconf_bp.route("/data/ietf-network-slice-service:network-slice-services/slice-service={<slice_id>}/sdps", methods=["GET", "POST"])
def slice_service_sdps(slice_id: str):
    """Manage Service Demarcation Points (SDPs) for a specific slice."""
    nsc = get_nsc()
    slice_id = slice_id.strip("{}")
    svc = nsc.slices.get(slice_id)
    if not svc:
        return jsonify({"error": f"Slice '{slice_id}' not found"}), 404

    if request.method == "GET":
        return jsonify({
            "ietf-network-slice-service:sdps": {
                "sdp": [sdp.to_ietf_dict() for sdp in svc.sdps]
            }
        }), 200, {"Content-Type": "application/yang-data+json"}

    body = request.get_json(silent=True) or {}
    sdp_data = body.get("sdp", body)
    new_sdp = ServiceDemarcationPoint(
        sdp_id=sdp_data.get("id", f"sdp-{len(svc.sdps)+1}"),
        node_id=sdp_data.get("node-id", "ctu-96"),
        tp_id=sdp_data.get("tp-id", "eth0"),
        ip_address=sdp_data.get("ip_address"),
        vlan_id=sdp_data.get("vlan_id")
    )
    svc.sdps.append(new_sdp)
    return jsonify({"sdp": new_sdp.to_ietf_dict()}), 201, {"Content-Type": "application/yang-data+json"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. RFC 8639: Subscribed Notifications Operation
# ─────────────────────────────────────────────────────────────────────────────

@restconf_bp.route("/operations/ietf-subscribed-notifications:establish-subscription", methods=["POST"])
def establish_subscription():
    """RFC 8639 establishment of telemetry notification subscription."""
    nsc = get_nsc()
    body = request.get_json(silent=True) or {}
    input_data = body.get("ietf-subscribed-notifications:input", body)
    res = nsc.establish_subscription(input_data)
    return jsonify(res), 200, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-subscribed-notifications:subscriptions", methods=["GET"])
def get_subscriptions():
    """List active subscriptions and notification history."""
    nsc = get_nsc()
    subs_list = [
        {
            "id": s.subscription_id,
            "target-slice": s.slice_id,
            "destination": s.notification_destination,
            "period-sec": s.period_seconds,
            "active": s.active,
            "last-notified": s.last_notified,
            "events-count": len(s.history),
            "recent-events": s.history[-5:]
        }
        for s in nsc.subscriptions.values()
    ]
    return jsonify({"ietf-subscribed-notifications:subscriptions": subs_list}), 200


# ─────────────────────────────────────────────────────────────────────────────
# 3. IETF RFC 8345 Topology & TVR (Time-Variant Routing) (Section 4.2.4)
# ─────────────────────────────────────────────────────────────────────────────

@restconf_bp.route("/data/ietf-network:networks", methods=["GET"])
def get_rfc8345_networks():
    """Exposes network topology formatted in IETF RFC 8345."""
    nsc = get_nsc()
    topo = nsc._get_current_topology()
    
    rfc_nodes = []
    for n in topo.get("nodes", []):
        rfc_nodes.append({
            "node-id": n.get("id", n.get("uuid", "node")),
            "ietf-network-topology:termination-point": [
                {"tp-id": "eth0"}, {"tp-id": "rf0"}
            ]
        })

    rfc_links = []
    for l in topo.get("links", []):
        rfc_links.append({
            "link-id": l.get("id", l.get("uuid", "link")),
            "source": {"source-node": l.get("source", l.get("src", "")), "source-tp": "eth0"},
            "destination": {"dest-node": l.get("target", l.get("dst", "")), "dest-tp": "eth0"},
            "custom-parameters": {
                "latency-ms": l.get("latency_ms", 0.35),
                "capacity-mbps": l.get("capacity_mbps", 1000.0)
            }
        })

    return jsonify({
        "ietf-network:networks": {
            "network": [
                {
                    "network-id": "unity6g-transport-topology",
                    "network-types": {"ietf-network-topology:network-topology": {}},
                    "node": rfc_nodes,
                    "ietf-network-topology:link": rfc_links
                }
            ]
        }
    }), 200, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/ietf-tvr-topology:tvr-schedules", methods=["GET", "POST"])
def manage_tvr_schedules():
    """IETF TVR scheduled topological states (Section 4.2.4.3)."""
    nsc = get_nsc()
    if request.method == "GET":
        schedules = [
            {
                "schedule-id": s.schedule_id,
                "target-element-id": s.target_element_id,
                "element-type": s.element_type,
                "start-time-iso": s.start_time_iso,
                "duration-seconds": s.duration_seconds,
                "scheduled-state": s.scheduled_state,
                "predicted-capacity-mbps": s.predicted_capacity_mbps,
                "predicted-attenuation-db": s.predicted_attenuation_db,
                "reason": s.reason
            }
            for s in nsc.tvr_schedules.values()
        ]
        return jsonify({"ietf-tvr-topology:tvr-schedules": {"schedule": schedules}}), 200, {"Content-Type": "application/yang-data+json"}

    body = request.get_json(silent=True) or {}
    item = nsc.add_tvr_schedule(body)
    return jsonify({
        "status": "scheduled",
        "schedule_id": item.schedule_id,
        "target": item.target_element_id,
        "scheduled_state": item.scheduled_state
    }), 201, {"Content-Type": "application/yang-data+json"}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Telefónica Transport Energy YANG Models (Section 4.2.5, pp. 104-107)
# ─────────────────────────────────────────────────────────────────────────────

@restconf_bp.route("/data/instantaneous-device-energy-tid:device", methods=["GET"])
@restconf_bp.route("/data/instantaneous-device-energy-tid:device=<device_name>", methods=["GET"])
@restconf_bp.route("/data/instantaneous-device-energy-tid:device={<device_name>}", methods=["GET"])
def get_instantaneous_energy(device_name: str = None):
    """Returns instantaneous device energy records (Figure 4-12 & 4-13)."""
    nsc = get_nsc()
    if device_name:
        d_name = device_name.strip("{}")
        rec = nsc.instantaneous_energy_db.get(d_name)
        if not rec:
            return jsonify({"error": f"Device energy record '{d_name}' not found"}), 404
        return jsonify(rec.to_yang_dict()), 200, {"Content-Type": "application/yang-data+json"}
    
    # Return all devices
    all_devs = [rec.to_yang_dict()["instantaneous-device-energy-tid:device"] for rec in nsc.instantaneous_energy_db.values()]
    return jsonify({"instantaneous-device-energy-tid:devices": {"device": all_devs}}), 200, {"Content-Type": "application/yang-data+json"}


@restconf_bp.route("/data/static-device-energy-tid:device", methods=["GET"])
@restconf_bp.route("/data/static-device-energy-tid:device=<device_name>", methods=["GET"])
@restconf_bp.route("/data/static-device-energy-tid:device={<device_name>}", methods=["GET"])
def get_static_energy(device_name: str = None):
    """Returns static device energy records (Figure 4-14 & 4-15)."""
    nsc = get_nsc()
    if device_name:
        d_name = device_name.strip("{}")
        rec = nsc.static_energy_db.get(d_name)
        if not rec:
            return jsonify({"error": f"Static device energy record '{d_name}' not found"}), 404
        return jsonify(rec.to_yang_dict()), 200, {"Content-Type": "application/yang-data+json"}

    all_devs = [rec.to_yang_dict()["static-device-energy-tid:device"] for rec in nsc.static_energy_db.values()]
    return jsonify({"static-device-energy-tid:devices": {"device": all_devs}}), 200, {"Content-Type": "application/yang-data+json"}


# ─────────────────────────────────────────────────────────────────────────────
# 5. NDT Path Computation Engine (PCE) Operation (Section 2.4.1.1.2 & 2.4.1.1.4)
# ─────────────────────────────────────────────────────────────────────────────

@restconf_bp.route("/operations/ietf-pce:compute-path", methods=["POST"])
def compute_path_operation():
    """
    NDT PCE Path Computation Engine operation.
    Computes optimal path satisfying latency, bandwidth, and TVR constraints.
    """
    nsc = get_nsc()
    body = request.get_json(silent=True) or {}
    input_data = body.get("ietf-pce:input", body)
    
    src = input_data.get("source_node", "ctu-96")
    dst = input_data.get("dest_node", "edge-router-02")
    max_lat = input_data.get("max_latency_ms")
    min_bw = input_data.get("min_bandwidth_mbps")
    isolation = input_data.get("isolation_policy", "logical")

    result = nsc.planner.compute_constrained_path(
        src_node=src,
        dst_node=dst,
        max_latency_ms=max_lat,
        bandwidth_mbps=min_bw,
        isolation_policy=isolation,
        tvr_schedules=list(nsc.tvr_schedules.values())
    )
    return jsonify({"ietf-pce:output": result}), 200, {"Content-Type": "application/yang-data+json"}
