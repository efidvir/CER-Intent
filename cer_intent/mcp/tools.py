"""
CER-Intent tools for MCP
========================
Plain functions with typed arguments, so any MCP server can register them:
CER-Intent's own runner (``python -m cer_intent.mcp``), or TeraFlowSDN's MCP
server once the fork is rebased on upstream (call ``register(server)``).

Authority follows the tuple framework: by default the tools only advise
(``CER_INTENT_MCP_MODE=advise``): they map, select and build the request but
change nothing. ``CER_INTENT_MCP_MODE=act`` lets the slice and intent tools
act on TeraFlowSDN. Twin results are always labelled as simulated.

Environment:
  TERAFLOW_URL, TFS_USERNAME, TFS_PASSWORD   TeraFlowSDN (see device/tfs_client.py)
  TFS_REALIZATION                            how slices leave CER-Intent (see nsc/realizer.py)
  CER_INTENT_URL                             running CER-Intent API: submit_intent, and when
                                             CER_INTENT_MCP_PROXY=1 the slice tools use its
                                             RFC 9543 interface (one slice datastore)
  TWIN_URL                                   digital twin service, for run_what_if
"""
# Annotations stay real types (no `from __future__ import annotations`): MCP SDK 1.x
# inspects them with issubclass() when it builds the tool schemas.

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import requests

from cer_intent.nsc import shared_controller
from cer_intent.nsc.mapper import MappingError, map_request
from cer_intent.nsc.realizer import Realizer
from cer_intent.nsc.technology_selector import select_technology


def mcp_mode() -> str:
    return "act" if os.getenv("CER_INTENT_MCP_MODE", "advise").strip().lower() == "act" else "advise"


class _Context:
    """Lazily built clients; tests replace them."""

    def __init__(self) -> None:
        self._tfs = None

    @property
    def tfs(self):
        if self._tfs is None:
            from cer_intent.device.tfs_client import TFSClient
            self._tfs = TFSClient()
        return self._tfs

    @tfs.setter
    def tfs(self, client) -> None:
        self._tfs = client

    @property
    def nsc(self):
        return shared_controller(self.tfs)


CONTEXT = _Context()

RFC9543_PATH = "/restconf/data/ietf-network-slice-service:network-slice-services"


def _api_base() -> str:
    return os.getenv("CER_INTENT_URL", "http://localhost:5000").rstrip("/")


def _proxy() -> bool:
    """Slice tools call the running CER-Intent API instead of an in-process controller."""
    return os.getenv("CER_INTENT_MCP_PROXY", "").strip().lower() in ("1", "true", "yes")


def _http_timeout() -> float:
    return float(os.getenv("CER_INTENT_MCP_HTTP_TIMEOUT", "30"))


# ── Slice controller ───────────────────────────────────────────────────────────

def preview_network_slice(request: Dict[str, Any]) -> Dict[str, Any]:
    """Map an RFC 9543 slice request, choose L2VPN or L3VPN, and build the TeraFlowSDN request without sending it."""
    nsc = CONTEXT.nsc
    try:
        mapped = map_request(request, nsc.templates)
    except MappingError as e:
        return {"error": str(e), "stage": "mapper"}
    choice = select_technology(mapped, skill=nsc.technology_skill)
    realization = Realizer(mode="dry-run").build(mapped, choice.technology)
    return {
        "slice_id": mapped.slice_id,
        "endpoints": [{"node": ep.node_id, "tp": ep.tp_id, "ip": ep.ip_address, "vlan": ep.vlan_id}
                      for ep in mapped.endpoints],
        "slos": mapped.to_dict()["slos"],
        "technology": choice.to_dict(),
        "realization": realization.to_dict(),
    }


def create_network_slice(request: Dict[str, Any]) -> Dict[str, Any]:
    """Create an RFC 9543 network slice on the transport network (acts only when CER_INTENT_MCP_MODE=act)."""
    if mcp_mode() != "act":
        return {"mode": "advise", "applied": False, "note": "set CER_INTENT_MCP_MODE=act to apply",
                "preview": preview_network_slice(request)}
    if _proxy():
        resp = requests.post(f"{_api_base()}{RFC9543_PATH}", json=request, timeout=_http_timeout())
        result = resp.json()
    else:
        result = CONTEXT.nsc.create_or_update_slice_service(request)
    if "nsc_pipeline" not in result:
        return {"mode": "act", "applied": False, **result}
    return {"mode": "act", "applied": result["nsc_pipeline"]["realizer"]["status"] == "sent",
            "pipeline": result["nsc_pipeline"]}


def list_network_slices() -> Dict[str, Any]:
    """List the slices the slice controller holds, with status and realization technology."""
    if _proxy():
        resp = requests.get(f"{_api_base()}{RFC9543_PATH}", timeout=_http_timeout())
        resp.raise_for_status()
        tree = resp.json().get("ietf-network-slice-service:network-slice-services", {})
        return {"slices": [
            {"id": s.get("id"), "status": s.get("status"),
             "technology": (s.get("custom-topology") or {}).get("realization-technology"),
             "endpoints": [f"{sdp.get('node-id')}:{(sdp.get('service-match-criteria') or {}).get('match-criterion', [{}])[0].get('value')}"
                           for sdp in (s.get("sdps") or {}).get("sdp", [])]}
            for s in tree.get("slice-service", [])
        ]}
    nsc = CONTEXT.nsc
    return {"slices": [
        {"id": s.slice_id, "status": s.status, "technology": s.realization_technology,
         "endpoints": [f"{sdp.node_id}:{sdp.tp_id}" for sdp in s.sdps]}
        for s in nsc.slices.values()
    ]}


def get_network_slice(slice_id: str) -> Dict[str, Any]:
    """One slice as an RFC 9543 slice-service, plus how it was realized."""
    if _proxy():
        resp = requests.get(f"{_api_base()}{RFC9543_PATH}/slice-service={slice_id}", timeout=_http_timeout())
        if resp.status_code == 404:
            return {"error": f"slice '{slice_id}' not found"}
        resp.raise_for_status()
        items = resp.json().get("ietf-network-slice-service:slice-service", [])
        return {"slice-service": items[0] if items else None, "realization": None}
    nsc = CONTEXT.nsc
    svc = nsc.slices.get(slice_id)
    if svc is None:
        return {"error": f"slice '{slice_id}' not found"}
    realization = nsc.realizations.get(slice_id)
    return {"slice-service": svc.to_ietf_dict(), "realization": realization.to_dict() if realization else None}


def delete_network_slice(slice_id: str) -> Dict[str, Any]:
    """Withdraw a slice from TeraFlowSDN (acts only when CER_INTENT_MCP_MODE=act)."""
    if mcp_mode() != "act":
        return {"mode": "advise", "applied": False, "note": f"would withdraw slice '{slice_id}'"}
    if _proxy():
        resp = requests.delete(f"{_api_base()}{RFC9543_PATH}/slice-service={slice_id}", timeout=_http_timeout())
        if resp.status_code == 404:
            return {"mode": "act", "applied": False, "error": f"slice '{slice_id}' not found"}
        return {"mode": "act", "applied": resp.status_code == 204, "slice_id": slice_id,
                "http_status": resp.status_code}
    result = CONTEXT.nsc.delete_slice_service(slice_id)
    if result is None:
        return {"mode": "act", "applied": False, "error": f"slice '{slice_id}' not found"}
    return {"mode": "act", "applied": result.get("status") == "withdrawn", **result}


# ── Network state ──────────────────────────────────────────────────────────────

def get_transport_topology() -> Dict[str, Any]:
    """Transport topology from TeraFlowSDN as RFC 8345 (ietf-network)."""
    return CONTEXT.tfs.get_rfc8345_networks()


def get_radio_link(device: str) -> Dict[str, Any]:
    """RFC 8561 view of a radio's carriers, as the Ceragon driver reports it to TeraFlowSDN."""
    dev = CONTEXT.tfs.get_device(device)
    for rule in dev.get("device_config", {}).get("config_rules", []):
        custom = rule.get("custom") or {}
        if custom.get("resource_key") == "/microwave-radio-link":
            value = custom.get("resource_value")
            return json.loads(value) if isinstance(value, str) else value
    return {"error": f"device '{device}' has no /microwave-radio-link view (not a Ceragon radio, or not yet discovered)"}


# ── Intents and the twin ───────────────────────────────────────────────────────

def submit_intent(text: str) -> Dict[str, Any]:
    """Send a free-text intent to CER-Intent, which parses, checks and applies it (acts only in act mode)."""
    if mcp_mode() != "act":
        return {"mode": "advise", "applied": False, "note": "set CER_INTENT_MCP_MODE=act to submit", "intent": text}
    resp = requests.post(f"{_api_base()}/api/v1/intent", json={"intent": text, "source": "mcp"}, timeout=_http_timeout())
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:500]}
    return {"mode": "act", "http_status": resp.status_code, **(body if isinstance(body, dict) else {"result": body})}


def run_what_if(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Run a what-if scenario on the digital twin. The answer is simulated, never a measurement."""
    base = os.getenv("TWIN_URL", "http://localhost:9100").rstrip("/")
    resp = requests.post(f"{base}/what-if", json=scenario, timeout=_http_timeout())
    resp.raise_for_status()
    body = resp.json()
    body.setdefault("insight", "simulated")
    return body


# ── The intent manager (API v2): records, questions, alternatives, approval ────

def _v2(method: str, path: str, body: Optional[Dict[str, Any]] = None, acting: bool = False) -> Dict[str, Any]:
    """Call CER-Intent's /api/v2. In advise mode the agent acts as a viewer: it can read, ask and explore, never approve."""
    role = "operator" if (acting and mcp_mode() == "act") else "viewer"
    headers = {"X-User": os.getenv("CER_INTENT_MCP_USER", "mcp-agent"), "X-Role": role}
    resp = requests.request(method, f"{_api_base()}{path}", json=body, headers=headers, timeout=_http_timeout())
    try:
        out = resp.json()
    except ValueError:
        out = {"raw": resp.text[:500]}
    if not isinstance(out, dict):
        out = {"result": out}
    out.setdefault("http_status", resp.status_code)
    out["mode"] = mcp_mode()
    return out


def _brief(rec: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("id", "name", "state", "reply", "questions", "alternatives", "answer", "check", "links", "http_status", "mode", "error")
    return {k: rec.get(k) for k in keep if k in rec}


def intent_converse(text: str, session: str = "mcp") -> Dict[str, Any]:
    """Talk to the intent manager as an operator would: a request, an answer to its question, 'option 2', 'approve'."""
    return _v2("POST", "/api/v2/converse", {"session": session, "text": text}, acting=True)


def intent_submit(text: str) -> Dict[str, Any]:
    """Submit an intent in words; returns how it was read, any questions, the check and alternatives. Nothing changes until approval."""
    return _brief(_v2("POST", "/api/v2/intents", {"text": text, "channel": "mcp"}, acting=True))


def intent_get(intent_id: str) -> Dict[str, Any]:
    """An intent record: expectations with where each value came from, state, check, actions, reports."""
    return _v2("GET", f"/api/v2/intents/{intent_id}")


def intent_answer(intent_id: str, question: str, value: str) -> Dict[str, Any]:
    """Answer one of an intent's open questions (by question id or field)."""
    return _brief(_v2("POST", f"/api/v2/intents/{intent_id}/answers", {"question": question, "value": value}, acting=True))


def intent_accept_alternative(intent_id: str, alternative: str) -> Dict[str, Any]:
    """Accept one of the alternatives offered for an intent the network cannot meet as asked (id or number)."""
    return _brief(_v2("POST", f"/api/v2/intents/{intent_id}/alternatives/{alternative}/accept", {}, acting=True))


def intent_approve(intent_id: str) -> Dict[str, Any]:
    """Approve a checked intent so it is applied (act mode only; rules may require a human approver)."""
    if mcp_mode() != "act":
        return {"mode": "advise", "applied": False, "note": "set CER_INTENT_MCP_MODE=act to approve", "intent_id": intent_id}
    return _brief(_v2("POST", f"/api/v2/intents/{intent_id}/approve", {}, acting=True))


def intent_withdraw(intent_id: str) -> Dict[str, Any]:
    """Withdraw an intent; what it changed in the network is put back (act mode only)."""
    if mcp_mode() != "act":
        return {"mode": "advise", "applied": False, "note": "set CER_INTENT_MCP_MODE=act to withdraw", "intent_id": intent_id}
    return _brief(_v2("DELETE", f"/api/v2/intents/{intent_id}", acting=True))


def intent_report(intent_id: str) -> Dict[str, Any]:
    """The 3GPP TS 28.312 intent report: fulfilment per expectation and target, feasibility, conflicts."""
    return _v2("GET", f"/api/v2/intents/{intent_id}/report")


def explore_network(question: str) -> Dict[str, Any]:
    """Ask a question or a what-if ('how much more can the hop carry in heavy rain?'); answered from the twin, nothing changes."""
    out = _v2("POST", "/api/v2/intents", {"text": question, "channel": "mcp"})
    return {"answer": (out.get("answer") or {}).get("text") or out.get("reply"), "state": out.get("state"),
            "insight": (out.get("answer") or {}).get("insight"), "data": (out.get("answer") or {}).get("data"),
            "http_status": out.get("http_status"), "mode": out.get("mode")}


# ── Registry ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolSpec:
    fn: Callable[..., Dict[str, Any]]
    read_only: bool
    destructive: bool = False

    @property
    def name(self) -> str:
        return self.fn.__name__

    @property
    def description(self) -> str:
        return (self.fn.__doc__ or "").strip().splitlines()[0]


TOOLS: List[ToolSpec] = [
    ToolSpec(preview_network_slice, read_only=True),
    ToolSpec(create_network_slice, read_only=False),
    ToolSpec(list_network_slices, read_only=True),
    ToolSpec(get_network_slice, read_only=True),
    ToolSpec(delete_network_slice, read_only=False, destructive=True),
    ToolSpec(get_transport_topology, read_only=True),
    ToolSpec(get_radio_link, read_only=True),
    ToolSpec(submit_intent, read_only=False),
    ToolSpec(run_what_if, read_only=True),
    ToolSpec(intent_converse, read_only=False),
    ToolSpec(intent_submit, read_only=False),
    ToolSpec(intent_get, read_only=True),
    ToolSpec(intent_answer, read_only=False),
    ToolSpec(intent_accept_alternative, read_only=False),
    ToolSpec(intent_approve, read_only=False),
    ToolSpec(intent_withdraw, read_only=False, destructive=True),
    ToolSpec(intent_report, read_only=True),
    ToolSpec(explore_network, read_only=True),
]


def register(server: Any, prefix: str = "") -> List[str]:
    """
    Register every tool on an MCP server object that has ``add_tool`` (the MCP
    Python SDK's FastMCP / MCPServer). Returns the registered names.
    """
    names = []
    for spec in TOOLS:
        name = f"{prefix}{spec.name}"
        kwargs: Dict[str, Any] = {"name": name, "description": spec.description}
        annotations = _annotations(spec)
        if annotations is not None:
            kwargs["annotations"] = annotations
        try:
            server.add_tool(spec.fn, **kwargs)
        except TypeError:  # older SDKs without annotations
            kwargs.pop("annotations", None)
            server.add_tool(spec.fn, **kwargs)
        names.append(name)
    return names


def _annotations(spec: ToolSpec) -> Optional[Any]:
    try:
        from mcp.types import ToolAnnotations
    except ImportError:
        return None
    return ToolAnnotations(readOnlyHint=spec.read_only, destructiveHint=spec.destructive,
                           openWorldHint=spec.fn in (submit_intent, run_what_if, intent_converse, intent_submit, explore_network))
