"""
Slice controller view: dashboard support
========================================
Serves the dashboard page ``slice-controller.html``, which shows CER-Intent in
the ETSI chain: OpenSlice -> RFC 9543 -> slice controller (Mapper, Technology
Selector, Realizer) -> L3SM / L2SM -> TeraFlowSDN -> Ceragon driver -> radios.

  GET  /api/v1/etsi/status    realization mode, planner topology, slices,
                              MCP tools and their authority
  POST /api/v1/etsi/what-if   the digital twin's what-if, labelled simulated

Slices themselves are created and deleted on the RFC 9543 interface
(restconf_routes.py); this module only reads the shared controller.
"""
import logging
import os
from typing import Any, Dict, List

import requests
from flask import Blueprint, jsonify, request

from cer_intent.api.restconf_routes import get_nsc
from cer_intent.mcp.tools import TOOLS, mcp_mode, run_what_if
from cer_intent.nsc.realizer import realization_mode

logger = logging.getLogger("ETSI_View")

etsi_bp = Blueprint("etsi", __name__, url_prefix="/api/v1/etsi")


def _slices(nsc) -> List[Dict[str, Any]]:
    out = []
    for sid, svc in nsc.slices.items():
        r = nsc.realizations.get(sid)
        out.append({
            "id": sid,
            "description": svc.description,
            "status": svc.status,
            "technology": r.technology if r else ("L3VPN" if svc.realization_technology == "L3SM" else "L2VPN"),
            "model": svc.realization_technology,
            "mode": r.mode if r else None,
            "realization_status": r.status if r else None,
            "path": list(svc.computed_path),
            "sdps": [{"node": s.node_id, "tp": s.tp_id} for s in svc.sdps],
        })
    return out


@etsi_bp.route("/status", methods=["GET"])
def status():
    nsc = get_nsc()
    topo = nsc._get_current_topology()
    return jsonify({
        "realization": {
            "mode": realization_mode(),
            "controller_configured": nsc.tfs_client is not None,
        },
        "topology": {
            "source": nsc.topology_source,
            "nodes": [{"id": n.get("id"), "type": n.get("type") or n.get("model"), "role": n.get("role")}
                      for n in topo.get("nodes", [])],
            "links": [{"source": l.get("source"), "target": l.get("target"), "type": l.get("type")}
                      for l in topo.get("links", [])],
        },
        "slices": _slices(nsc),
        "mcp": {
            "mode": mcp_mode(),
            "tools": [
                {"name": t.name, "description": t.description,
                 "read_only": t.read_only, "destructive": t.destructive}
                for t in TOOLS
            ],
        },
        "twin": {"configured": bool(os.getenv("TWIN_URL"))},
    })


@etsi_bp.route("/what-if", methods=["POST"])
def what_if():
    scenario = request.get_json(silent=True) or {}
    try:
        result = run_what_if(scenario)
    except (requests.RequestException, ValueError) as exc:
        logger.info("twin what-if unavailable: %s", exc)
        return jsonify({"error": "digital twin not reachable", "insight": "simulated"}), 503
    result["insight"] = "simulated"
    return jsonify(result)
