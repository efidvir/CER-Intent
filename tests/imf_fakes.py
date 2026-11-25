"""A slice controller over a fake TeraFlowSDN, and the network the intent manager reads from it."""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from cer_intent.imf.manager import IntentManager
from cer_intent.imf.match import Policy
from cer_intent.imf.network import NetworkModel, SliceInfo
from cer_intent.imf.store import IntentStore
from cer_intent.nsc.nsc_controller import NetworkSliceController

PATH = ["region-a", "radio-1", "radio-2", "edge"]
BACKHAUL = {"id": "backhaul-ran", "description": "RAN backhaul", "bandwidth_mbps": 200, "realization_technology": "L2VPN",
            "sdps": [{"id": "1", "node_id": "region-a", "tp_id": "eth1", "vlan_id": 100},
                     {"id": "2", "node_id": "edge", "tp_id": "eth1", "vlan_id": 100}]}


class FakeTFS:
    """Records every call; get_device answers with the radios' current modulation."""

    def __init__(self, fail_on: Optional[str] = None):
        self.calls: List[tuple] = []
        self.fail_on = fail_on
        self.mcs: Dict[str, int] = {}

    def get_device(self, name, fresh=False):
        self.calls.append(("get_device", (name,), {}))
        if name in self.mcs:
            return {"device_config": {"config_rules": [{"custom": {"resource_key": "/radio/sector[1]",
                                                                  "resource_value": {"current_modulation": f"MCS-{self.mcs[name]}"}}}]}}
        return {}

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if self.fail_on and name == self.fail_on:
                raise RuntimeError("HTTP 500 from the controller")
            return {}
        return record

    def names(self) -> List[str]:
        return [c[0] for c in self.calls if c[0] not in ("fetch_normalized_topology", "get_device")]


class Twin:
    """A twin that passes or fails by total load on the hop (stands in for the NS-3 pre-flight)."""

    def __init__(self, nsc, limit_mbps: float = 770.0):
        self.nsc, self.limit, self.calls, self.last_error = nsc, limit_mbps, [], None

    def preflight(self, candidate, plan=None, exclude=None, overrides=None):
        self.calls.append({"candidate": candidate, "exclude": exclude, "overrides": overrides})
        load = 0.0
        for sid, req in self.nsc.requests.items():
            if sid == candidate.get("slice_id") or sid in (exclude or []):
                continue
            bw = (overrides or {}).get(sid, {}).get("bandwidth_mbps", req["slos"].get("bandwidth_mbps") or 0)
            load += float(bw)
        total = load + float(candidate.get("bandwidth_mbps") or 0)
        ok = total <= self.limit
        return {"verdict": "pass" if ok else "fail", "insight": "simulated", "engine": {"engine": "test twin"},
                "checks": [{"id": "bandwidth", "label": "Slice bandwidth", "target": f"{candidate.get('bandwidth_mbps')} Mbps",
                            "value": f"{candidate.get('bandwidth_mbps') if ok else 0} Mbps", "ok": ok}],
                "network": {"path": PATH, "existing_services": []}, "scenarios": {"after": {"hops": []}}}


def network_of(nsc) -> NetworkModel:
    net = NetworkModel.demo(with_slice=False)
    for sid, svc in nsc.slices.items():
        req = nsc.requests[sid]
        net.slices[sid] = SliceInfo(
            id=sid, status=svc.status, path=list(svc.computed_path),
            endpoints=[{"node": e["node_id"], "port": e["tp_id"], "vlan": e.get("vlan_id"), "ip": e.get("ip_address")}
                       for e in req["endpoints"]],
            bandwidth_mbps=req["slos"].get("bandwidth_mbps"), max_latency_ms=req["slos"].get("max_latency_ms"),
            acm_floor=(req.get("acm") or {}).get("min_modulation"), hop_floor=nsc.hop_floors.get(sid),
            description=req["service"].get("description"))
    return net


def build(twin: bool = False, fail_on: Optional[str] = None, clock: Optional[dt.datetime] = None,
          policy: Optional[Policy] = None, with_backhaul: bool = True):
    tfs = FakeTFS(fail_on=fail_on)
    nsc = NetworkSliceController(tfs_client=tfs, realization_mode="ietf")
    nsc.planner.compute_constrained_path = lambda **kw: {"computed_path": list(PATH), "feasible": True}
    if with_backhaul:
        nsc.create_or_update_slice_service(dict(BACKHAUL))
    now = {"t": clock or dt.datetime(2026, 11, 25, 10, 0)}
    m = IntentManager(store=IntentStore(":memory:"), network=lambda: network_of(nsc), nsc=lambda: nsc,
                      twin=Twin(nsc) if twin else None, use_llm_env=False, clock=lambda: now["t"],
                      policy=policy or Policy())
    return m, nsc, tfs, now
