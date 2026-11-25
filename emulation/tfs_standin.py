"""
TeraFlowSDN stand-in for the end-to-end flow
============================================
TeraFlowSDN itself runs as Kubernetes microservices. To show the whole flow on
a laptop (or in a browser), this stand-in answers the parts of TeraFlowSDN's
northbound interface that CER-Intent and the digital twin call, and drives the
Ceragon radios with the TeraFlowSDN fork's own code:

  IETF L2VPN / L3VPN NBI  POST   /restconf/data/ietf-l2vpn-svc:l2vpn-svc/vpn-services     (RFC 8466)
                          POST   /restconf/data/ietf-l3vpn-svc:l3vpn-svc/vpn-services     (RFC 8299)
                          DELETE .../vpn-services/vpn-service=<id>
  RFC 8345                GET    /restconf/data/ietf-network:networks/
  TFS-API                 GET    /tfs-api/contexts, /tfs-api/context/<ctx>/topology_details/<topo>,
                                 /tfs-api/devices, /tfs-api/device/<id>, /tfs-api/links,
                                 /tfs-api/context/<ctx>/services
                          GET/PUT/DELETE /tfs-api/context/<ctx>/service/<id>

A VPN request becomes a TeraFlowSDN service (L2NM or L3NM) whose path is the
shortest device path between its two sites. On every Ceragon radio of that path
the fork's Ceragon service handler composes the config rules
(service_handlers/ceragon_transport/ConfigRules.py) and the fork's CeragonDriver
applies them over RESTCONF, one commit per request. A service update (new
"/settings", e.g. the ACM floor) re-applies them; a delete tears them down.
Devices that are neither Ceragon radios nor plain sites are listed with the
rules TeraFlowSDN would give their drivers and marked as not applied here.

Stand-in diagnostics (not part of TeraFlowSDN):
  GET /standin/wire?since=<seq>   every request it served and every southbound exchange
  GET /standin/state              devices, services and the path of each service
  X-Flow-Quiet: 1                 request header: serve without logging (status polling)

    python emulation/tfs_standin.py --descriptors emulation/flow/topology.json \\
        --fork-src ../teraflowsdn/src --port 8088
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
import threading
import time
import types
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request

LOG = logging.getLogger("tfs-standin")

L2VPN_PATH = "/restconf/data/ietf-l2vpn-svc:l2vpn-svc"
L3VPN_PATH = "/restconf/data/ietf-l3vpn-svc:l3vpn-svc"
NETWORKS_PATH = "/restconf/data/ietf-network:networks"
CERAGON = "DEVICEDRIVER_CERAGON"
# Device subtrees read back live through the driver when a radio is read, by API flavour
READBACK_SUBTREES = {
    "siklu_tg": ("radio-bridge-tg-user-bridge:user-bridge", "radio-bridge-tg-radio-common:radio-common"),
    "ceraos": ("ceragon-slice:slice-config",),
}
NO_DRIVER = ("DEVICEDRIVER_UNDEFINED",)
UA = "TeraFlowSDN stand-in (Ceragon driver)"
_QUIET = threading.local()      # set while serving a request sent with X-Flow-Quiet: 1


# ── The fork's code ──────────────────────────────────────────────────────────

def load_fork(fork_src: str) -> Tuple[type, types.ModuleType]:
    """
    CeragonDriver and the Ceragon handler's ConfigRules from a TeraFlowSDN fork
    checkout, without the rest of TeraFlowSDN: the drivers and service_handlers
    package __init__ files import every driver and handler, and the config-rule
    factory needs only one enum from the generated protobuf code.
    """
    import importlib.util
    fork_src = os.path.abspath(fork_src)
    if fork_src not in sys.path:
        sys.path.insert(0, fork_src)
    for name, rel in (("device.service.drivers", "device/service/drivers"),
                      ("service.service.service_handlers", "service/service/service_handlers")):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [os.path.join(fork_src, rel)]
            sys.modules[name] = pkg
    if "common.proto.context_pb2" not in sys.modules:
        pb2 = types.ModuleType("common.proto.context_pb2")
        pb2.ConfigActionEnum = types.SimpleNamespace(CONFIGACTION_UNDEFINED=0, CONFIGACTION_SET=1, CONFIGACTION_DELETE=2)
        sys.modules["common.proto.context_pb2"] = pb2
    from device.service.drivers.ceragon.CeragonDriver import CeragonDriver  # noqa: E402
    path = os.path.join(fork_src, "service/service/service_handlers/ceragon_transport/ConfigRules.py")
    spec = importlib.util.spec_from_file_location("ceragon_transport_config_rules", path)
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    return CeragonDriver, rules


# ── Wire log ─────────────────────────────────────────────────────────────────

class Wire:
    """Requests served and southbound exchanges, in order."""

    def __init__(self, keep: int = 2000) -> None:
        self.lock = threading.Lock()
        self.items: "collections.deque[Dict[str, Any]]" = collections.deque(maxlen=keep)
        self.seq = 0

    def add(self, **entry: Any) -> None:
        with self.lock:
            self.seq += 1
            entry["seq"] = self.seq
            entry.setdefault("t", time.time())
            self.items.append(entry)

    def since(self, seq: int) -> List[Dict[str, Any]]:
        with self.lock:
            return [e for e in self.items if e["seq"] > seq]


def _short(body: Any, limit: int = 6000) -> Any:
    """Bodies as JSON where they are JSON, trimmed for the log."""
    if body is None or body == b"" or body == "":
        return None
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return body[:limit]
    text = json.dumps(body)
    return body if len(text) <= limit else text[:limit] + "…"


def tap_requests(wire: Wire, src: str, dst_of: Callable[[str], str]) -> None:
    """Record every HTTP exchange made with the requests library in this process."""
    import requests

    if getattr(requests.Session.request, "_standin_tap", False):
        return
    original = requests.Session.request

    def request_(self, method, url, *args, **kwargs):  # noqa: ANN001
        if self.headers.get("User-Agent") != UA or getattr(_QUIET, "on", False):
            return original(self, method, url, *args, **kwargs)   # someone else's session, or a quiet read
        t0 = time.time()
        body = kwargs.get("json")
        if body is None:
            body = kwargs.get("data")
        try:
            resp = original(self, method, url, *args, **kwargs)
        except Exception as exc:
            wire.add(src=src, dst=dst_of(url), method=method.upper(), url=url, status=None, t=t0,
                     ms=round((time.time() - t0) * 1000, 1), req=_short(body), res=str(exc), dir="south")
            raise
        wire.add(src=src, dst=dst_of(url), method=method.upper(), url=url, status=resp.status_code, t=t0,
                 ms=round((time.time() - t0) * 1000, 1), req=_short(body), res=_short(resp.content), dir="south")
        return resp

    request_._standin_tap = True
    requests.Session.request = request_


# ── TeraFlowSDN objects ──────────────────────────────────────────────────────

def _uuid(kind: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tfs/{kind}/{name}"))


def _rules_of(device: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for rule in device.get("device_config", {}).get("config_rules", []):
        custom = rule.get("custom") or {}
        out[custom.get("resource_key")] = custom.get("resource_value")
    return out


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _rule(key: str, value: Any, action: str = "CONFIGACTION_SET") -> Dict[str, Any]:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True)
    return {"action": action, "custom": {"resource_key": key, "resource_value": value}}


def _endpoint_id(device: str, endpoint: str, ctx: str = "admin") -> Dict[str, Any]:
    return {"device_id": {"device_uuid": {"uuid": device}}, "endpoint_uuid": {"uuid": endpoint},
            "topology_id": {"context_id": {"context_uuid": {"uuid": ctx}}, "topology_uuid": {"uuid": ctx}}}


class StandIn:
    def __init__(self, descriptors: Dict[str, Any], driver_cls: type, rules: types.ModuleType, wire: Wire) -> None:
        self.wire, self.driver_cls, self.rules = wire, driver_cls, rules
        self.lock = threading.RLock()
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.links: Dict[str, Dict[str, Any]] = {}
        self.drivers: Dict[str, Any] = {}
        self.services: Dict[str, Dict[str, Any]] = {}
        self.paths: Dict[str, List[Tuple[str, List[str]]]] = {}
        self.applied: Dict[str, Dict[str, Any]] = {}
        # rules the services configured on each device, as TeraFlowSDN's Context keeps them
        self.service_rules: Dict[str, "collections.OrderedDict[str, Any]"] = collections.defaultdict(collections.OrderedDict)
        self.capacity_gbps: Dict[Tuple[str, str], float] = {}
        self.addresses: Dict[str, str] = {}          # "address:port" -> device, for the wire log
        for dev in descriptors.get("devices", []):
            self.add_device(dev)
        for link in descriptors.get("links", []):
            self.add_link(link)

    # devices and links ------------------------------------------------------
    def add_device(self, dev: Dict[str, Any]) -> Dict[str, Any]:
        dev = json.loads(json.dumps(dev))
        uid = dev["device_id"]["device_uuid"]["uuid"]
        dev.setdefault("name", uid)
        rules = _rules_of(dev)
        drivers = dev.get("device_drivers", [])
        self.addresses[f"{rules.get('_connect/address')}:{rules.get('_connect/port')}"] = uid
        if CERAGON in drivers:
            settings = _json(rules.get("_connect/settings")) or {}
            driver = self.driver_cls(str(rules.get("_connect/address")), int(rules.get("_connect/port") or 80), **settings)
            session = getattr(getattr(driver, "_client", None), "_session", None)
            if session is not None:                     # the driver's requests announce TeraFlowSDN
                session.headers["User-Agent"] = UA
            ok = driver.Connect()
            dev["device_operational_status"] = "DEVICEOPERATIONALSTATUS_ENABLED" if ok else "DEVICEOPERATIONALSTATUS_DISABLED"
            if ok:
                self.drivers[uid] = driver
                eps = []
                for key, value in driver.GetConfig(["/endpoints"]):
                    if isinstance(value, dict) and value.get("uuid"):
                        eps.append({"endpoint_id": _endpoint_id(uid, value["uuid"]), "name": value.get("name", value["uuid"]),
                                    "endpoint_type": value.get("type", ""),
                                    "kpi_sample_types": sorted((value.get("sample_types") or {}).keys())})
                dev["device_endpoints"] = eps
                initial = [r for r in dev["device_config"]["config_rules"]
                           if (r.get("custom") or {}).get("resource_key", "").startswith("_connect/")]
                for key, value in driver.GetInitialConfig():
                    initial.append(_rule(key, value))
                dev["device_config"]["config_rules"] = initial
        else:
            settings = _json(rules.get("_connect/settings")) or {}
            eps = dev.get("device_endpoints") or [
                {"endpoint_id": _endpoint_id(uid, e["uuid"]), "name": e["uuid"], "endpoint_type": e.get("type", "")}
                for e in settings.get("endpoints", [])]
            dev["device_endpoints"] = eps
            dev["device_operational_status"] = "DEVICEOPERATIONALSTATUS_ENABLED"
        with self.lock:
            self.devices[uid] = dev
        if uid in self.drivers:
            self._read_capacity(uid, self.drivers[uid])
        return dev

    def add_link(self, link: Dict[str, Any]) -> None:
        lid = link["link_id"]["link_uuid"]["uuid"]
        link = json.loads(json.dumps(link))
        link.setdefault("name", lid)
        with self.lock:
            self.links[lid] = link
            # endpoints the links name but the descriptors did not list (e.g. router ports)
            for ep in link.get("link_endpoint_ids", []):
                dev = self.devices.get(ep["device_id"]["device_uuid"]["uuid"])
                name = ep["endpoint_uuid"]["uuid"]
                if dev is not None and name not in {e["name"] for e in dev.get("device_endpoints", [])}:
                    dev.setdefault("device_endpoints", []).append(
                        {"endpoint_id": _endpoint_id(dev["name"], name), "name": name, "endpoint_type": ""})

    def adjacency(self) -> Dict[str, List[Tuple[str, str, str]]]:
        adj: Dict[str, List[Tuple[str, str, str]]] = collections.defaultdict(list)
        for link in self.links.values():
            eps = link.get("link_endpoint_ids", [])
            if len(eps) < 2:
                continue
            a, b = eps[0], eps[1]
            da, ea = a["device_id"]["device_uuid"]["uuid"], a["endpoint_uuid"]["uuid"]
            db, eb = b["device_id"]["device_uuid"]["uuid"], b["endpoint_uuid"]["uuid"]
            adj[da].append((db, ea, eb))
            adj[db].append((da, eb, ea))
        return adj

    def compute_path(self, src: str, src_ep: str, dst: str, dst_ep: str) -> List[Tuple[str, List[str]]]:
        """Shortest device path as [(device, [endpoints used on it])], like a service connection's hops."""
        adj = self.adjacency()
        prev: Dict[str, Tuple[str, str, str]] = {}
        queue, seen = collections.deque([src]), {src}
        while queue:
            node = queue.popleft()
            if node == dst:
                break
            for nxt, out_ep, in_ep in sorted(adj.get(node, [])):
                if nxt not in seen:
                    seen.add(nxt)
                    prev[nxt] = (node, out_ep, in_ep)
                    queue.append(nxt)
        if dst not in seen:
            raise ValueError(f"no path between {src} and {dst}")
        hops = []                                   # (from, out endpoint, to, in endpoint), src -> dst
        node = dst
        while node != src:
            p, out_ep, in_ep = prev[node]
            hops.append((p, out_ep, node, in_ep))
            node = p
        hops.reverse()
        eps: "collections.OrderedDict[str, List[str]]" = collections.OrderedDict()
        eps[src] = [src_ep]
        for p, out_ep, node, in_ep in hops:
            if out_ep not in eps[p]:
                eps[p].append(out_ep)
            eps.setdefault(node, []).append(in_ep)
        if dst_ep not in eps[dst]:
            eps[dst].append(dst_ep)
        return list(eps.items())

    # services ---------------------------------------------------------------
    def find_service(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if key in self.services:
                return self.services[key]
            for svc in self.services.values():
                if svc.get("name") == key:
                    return svc
        return None

    def _service_settings(self, svc: Dict[str, Any]) -> Dict[str, Any]:
        for rule in svc.get("service_config", {}).get("config_rules", []):
            custom = rule.get("custom") or {}
            if custom.get("resource_key") == "/settings":
                return _json(custom.get("resource_value")) or {}
        return {}

    def _access_points(self, svc: Dict[str, Any]) -> List[Dict[str, Any]]:
        found = []
        for rule in svc.get("service_config", {}).get("config_rules", []):
            custom = rule.get("custom") or {}
            key = custom.get("resource_key", "")
            if key.startswith("/device[") and key.endswith("/settings"):
                value = _json(custom.get("resource_value"))
                if isinstance(value, dict):
                    found.append(value)
        return found

    def _capacity_gbps(self, svc: Dict[str, Any]) -> Optional[float]:
        for c in svc.get("service_constraints", []):
            if "sla_capacity" in c:
                return float(c["sla_capacity"]["capacity_gbps"])
        return None

    def _apply(self, svc: Dict[str, Any], teardown: bool = False) -> Dict[str, Any]:
        """The Ceragon handler's SetEndpoint / DeleteEndpoint over the service path, as TeraFlowSDN runs it."""
        sid = svc["service_id"]["service_uuid"]["uuid"]
        settings = self._service_settings(svc)
        bandwidth = self.rules.resolve_bandwidth_mbps(settings, self._capacity_gbps(svc))
        is_l2 = svc.get("service_type") == "SERVICETYPE_L2NM"
        explicit = {k: v for k, v in settings.items() if k == "vlan_id"}
        access = self._access_points(svc) if is_l2 else []
        report: Dict[str, Any] = {}
        for device_uuid, endpoint_names in self.paths.get(sid, []):
            dev = self.devices[device_uuid]
            drivers = dev.get("device_drivers", [])
            if CERAGON in drivers:
                vlan = self.rules.resolve_vlan([None] * len(endpoint_names), explicit, access)
                if teardown:
                    json_rules = self.rules.compose_teardown_rules(sid, svc.get("name") or sid, vlan, endpoint_names)
                else:
                    json_rules = self.rules.compose_setup_rules(sid, svc.get("name") or sid, vlan, bandwidth,
                                                                endpoint_names, settings)
                resources = [(r["custom"]["resource_key"], r["custom"]["resource_value"]) for r in json_rules]
                driver = self.drivers.get(device_uuid)
                if driver is None:
                    report[device_uuid] = {"kind": "ceragon", "applied": False, "error": "device not connected"}
                    continue
                results = (driver.DeleteConfig(resources) if teardown else driver.SetConfig(resources)) if resources else []
                errors = [str(r) for r in results if r is not True]
                stored = self.service_rules[device_uuid]
                for (key, value), result in zip(resources, results):
                    if result is True:
                        if teardown:
                            stored.pop(key, None)
                        else:
                            stored[key] = value
                report[device_uuid] = {"kind": "ceragon", "endpoints": endpoint_names, "vlan": vlan,
                                       "bandwidth_mbps": bandwidth, "rules": json_rules, "applied": not errors,
                                       "errors": errors}
            elif any(d not in NO_DRIVER for d in drivers):
                report[device_uuid] = {"kind": "other", "endpoints": endpoint_names, "applied": False,
                                       "note": "not applied in the stand-in (no device behind this driver here)"}
            else:
                report[device_uuid] = {"kind": "site", "endpoints": endpoint_names}
        self.applied[sid] = report
        return report

    def create_vpn(self, body: Dict[str, Any], l2: bool) -> Dict[str, Any]:
        root = body.get("ietf-l2vpn-svc:l2vpn-svc" if l2 else "ietf-l3vpn-svc:l3vpn-svc") or body
        vpn = root["vpn-services"]["vpn-service"][0]
        name = vpn["vpn-id"]
        accesses = []
        for site in root.get("sites", {}).get("site", []):
            for acc in site.get("site-network-accesses", {}).get("site-network-access", []):
                device = acc.get("device-reference")
                ep = acc.get("network-access-id") or acc.get("site-network-access-id")
                bearer = (acc.get("bearer") or {}).get("bearer-reference")
                if bearer and ":" in bearer:
                    device, ep = bearer.split(":", 1)
                accesses.append((site.get("site-id"), device, ep, acc))
        if len(accesses) != 2:
            raise ValueError(f"expected two site network accesses, got {len(accesses)}")
        sid = _uuid("service", name)
        rules = []
        bw_bps, latency = None, None
        for _site, device, ep, acc in accesses:
            svc_part = acc.get("service") or {}
            bw_bps = bw_bps or svc_part.get("svc-input-bandwidth")
            for cls in ((svc_part.get("qos") or {}).get("qos-profile") or {}).get("classes", {}).get("class", []):
                latency = latency or (cls.get("latency") or {}).get("latency-boundary")
            ep_settings: Dict[str, Any] = {}
            if l2:
                tag = ((acc.get("connection") or {}).get("tagged-interface") or {}).get("dot1q-vlan-tagged") or {}
                if tag.get("cvlan-id") is not None:
                    ep_settings["vlan_id"] = int(tag["cvlan-id"])
            else:
                addr = ((acc.get("ip-connection") or {}).get("ipv4") or {}).get("addresses") or {}
                if addr:
                    ep_settings.update({"address_ip": addr.get("provider-address"),
                                        "address_prefix": addr.get("prefix-length"),
                                        "neighbor_address": addr.get("customer-address")})
            rules.append(_rule(f"/device[{device}]/endpoint[{ep}]/settings", ep_settings))
        settings: Dict[str, Any] = {"mtu": 1500}
        rules.insert(0, _rule("/settings", settings))
        constraints = []
        if bw_bps:
            constraints.append({"sla_capacity": {"capacity_gbps": float(bw_bps) / 1e9}})
        if latency:
            constraints.append({"sla_latency": {"e2e_latency_ms": float(latency)}})
        (_, da, ea, _), (_, db, eb, _) = accesses
        path = self.compute_path(da, ea, db, eb)
        svc = {
            "service_id": {"context_id": {"context_uuid": {"uuid": "admin"}}, "service_uuid": {"uuid": sid}},
            "name": name,
            "service_type": "SERVICETYPE_L2NM" if l2 else "SERVICETYPE_L3NM",
            "service_status": {"service_status": "SERVICESTATUS_PLANNED"},
            "service_endpoint_ids": [_endpoint_id(da, ea), _endpoint_id(db, eb)],
            "service_constraints": constraints,
            "service_config": {"config_rules": rules},
        }
        with self.lock:
            self.services[sid] = svc
            self.paths[sid] = path
            report = self._apply(svc)
            ok = all(r.get("applied", True) for r in report.values() if r["kind"] == "ceragon")
            svc["service_status"]["service_status"] = "SERVICESTATUS_ACTIVE" if ok else "SERVICESTATUS_FAILED"
        return svc

    def update_service(self, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        svc = self.find_service(key)
        if svc is None:
            raise KeyError(key)
        with self.lock:
            if "service_config" in body:
                svc["service_config"] = body["service_config"]
            report = self._apply(svc)
            ok = all(r.get("applied", True) for r in report.values() if r["kind"] == "ceragon")
            svc["service_status"]["service_status"] = "SERVICESTATUS_ACTIVE" if ok else "SERVICESTATUS_FAILED"
        return svc

    def delete_service(self, key: str) -> bool:
        svc = self.find_service(key)
        if svc is None:
            return False
        sid = svc["service_id"]["service_uuid"]["uuid"]
        with self.lock:
            self._apply(svc, teardown=True)
            self.services.pop(sid, None)
            self.paths.pop(sid, None)
        return True

    # reads ------------------------------------------------------------------
    def device_view(self, uid: str, live: bool = False) -> Optional[Dict[str, Any]]:
        """
        The device as TeraFlowSDN keeps it: its initial configuration and the rules
        services configured on it. With live=True (a request sent with
        Cache-Control: no-cache) a Ceragon radio is read back through its driver
        first: initial configuration, user bridges and radio settings.
        """
        dev = self.devices.get(uid)
        if dev is None:
            return None
        driver = self.drivers.get(uid)
        if driver is not None and live:
            rules = [r for r in dev["device_config"]["config_rules"]
                     if (r.get("custom") or {}).get("resource_key", "").startswith("_connect/")]
            flavour = None
            for key, value in driver.GetInitialConfig():
                rules.append(_rule(key, value))
                if key == "/device/capabilities" and isinstance(value, dict):
                    flavour = value.get("api_flavor")
            keys = [f"/restconf/{p}" for p in READBACK_SUBTREES.get(flavour or "", ())]
            for key, value in (driver.GetConfig(keys) if keys else []):
                if not isinstance(value, Exception) and value is not None:
                    rules.append(_rule(key, value))
            with self.lock:
                dev["device_config"]["config_rules"] = rules       # what TeraFlowSDN now knows
        dev = json.loads(json.dumps(dev))
        if driver is not None:
            for key, value in self.service_rules.get(uid, {}).items():
                dev["device_config"]["config_rules"].append(_rule(key, value))
        return dev

    def rfc8345(self) -> Dict[str, Any]:
        nodes, links = [], []
        for uid, dev in self.devices.items():
            nodes.append({"node-id": dev.get("name", uid),
                          "ietf-network-topology:termination-point": [{"tp-id": e["name"]} for e in dev.get("device_endpoints", [])]})
        for lid, link in self.links.items():
            eps = link.get("link_endpoint_ids", [])
            if len(eps) < 2:
                continue
            a, b = eps[0], eps[1]
            da, db = a["device_id"]["device_uuid"]["uuid"], b["device_id"]["device_uuid"]["uuid"]
            entry = {"link-id": lid,
                     "source": {"source-node": da, "source-tp": a["endpoint_uuid"]["uuid"]},
                     "destination": {"dest-node": db, "dest-tp": b["endpoint_uuid"]["uuid"]}}
            capacity = self._link_capacity_kbps(da, a["endpoint_uuid"]["uuid"])
            if capacity:
                entry["ietf-te-topology:te"] = {"te-link-attributes": {"max-link-bandwidth": {
                    "te-bandwidth": {"ietf-eth-te-topology:eth-bandwidth": capacity}}}}
            links.append(entry)
        return {"ietf-network:networks": {"network": [{"network-id": "admin", "node": nodes,
                                                         "ietf-network-topology:link": links}]}}

    def _link_capacity_kbps(self, device: str, endpoint: str) -> Optional[int]:
        """A radio link's capacity as the Ceragon driver reported it when the device was added, in kbit/s."""
        gbps = self.capacity_gbps.get((device, str(endpoint)))
        return int(gbps * 1_000_000) if gbps else None

    def _read_capacity(self, device: str, driver: Any) -> None:
        try:
            from device.service.drivers.ceragon.Tools import sector_capacity_gbps
            state = driver._refresh_state()  # pylint: disable=protected-access
            for ep in self.devices[device].get("device_endpoints", []):
                name = ep.get("name", "")
                if name.startswith("rf-sector-"):
                    gbps = sector_capacity_gbps(state, int(name.rsplit("-", 1)[-1]))
                    if gbps:
                        self.capacity_gbps[(device, name)] = float(gbps)
        except Exception:  # pylint: disable=broad-except
            LOG.debug("no capacity for %s", device, exc_info=True)


# ── HTTP ─────────────────────────────────────────────────────────────────────

def build_app(standin: StandIn, wire: Wire) -> Flask:
    app = Flask("tfs-standin")

    def caller() -> str:
        ua = request.headers.get("User-Agent", "")
        if "CER-Intent" in ua:
            return "CER-Intent"
        if "twin" in ua.lower():
            return "Digital twin"
        if ua.startswith("flow-launcher"):
            return "Operator"
        return ua.split("/")[0] or "client"

    @app.after_request
    def log_inbound(resp: Response) -> Response:
        quiet = request.headers.get("X-Flow-Quiet") == "1"     # dashboards polling for status
        if not request.path.startswith("/standin") and not quiet:
            t0 = request.environ.get("standin.t0", time.time())
            wire.add(src=caller(), dst="TeraFlowSDN", method=request.method, url=request.url, status=resp.status_code,
                     t=t0, ms=round((time.time() - t0) * 1000, 1),
                     req=_short(request.get_data()), res=_short(resp.get_data()), dir="north")
        resp.headers["X-TFS-Standin"] = "1"
        return resp

    @app.before_request
    def mark_time() -> None:
        request.environ["standin.t0"] = time.time()
        _QUIET.on = request.headers.get("X-Flow-Quiet") == "1"

    @app.teardown_request
    def unmark(_exc: Any = None) -> None:
        _QUIET.on = False

    def ok(body: Any = None, status: int = 200) -> Response:
        return Response(json.dumps(body if body is not None else {}), status=status, mimetype="application/json")

    # TFS-API ------------------------------------------------------------------
    @app.get("/tfs-api/contexts")
    def contexts():
        return ok({"contexts": [{"context_id": {"context_uuid": {"uuid": "admin"}}, "name": "admin"}]})

    @app.get("/tfs-api/context/<ctx>/topology_details/<topo>")
    def topology_details(ctx, topo):
        return ok({"topology_id": {"context_id": {"context_uuid": {"uuid": ctx}}, "topology_uuid": {"uuid": topo}},
                   "name": topo, "devices": list(standin.devices.values()), "links": list(standin.links.values())})

    @app.get("/tfs-api/context/<ctx>/topology/<topo>")
    def topology(ctx, topo):
        return ok({"topology_id": {"context_id": {"context_uuid": {"uuid": ctx}}, "topology_uuid": {"uuid": topo}},
                   "name": topo,
                   "device_ids": [d["device_id"] for d in standin.devices.values()],
                   "link_ids": [l["link_id"] for l in standin.links.values()]})

    @app.get("/tfs-api/devices")
    def devices():
        return ok({"devices": list(standin.devices.values())})

    @app.get("/tfs-api/device/<uid>")
    def device(uid):
        dev = standin.device_view(uid, live="no-cache" in request.headers.get("Cache-Control", ""))
        return ok(dev) if dev else ok({"error": f"device {uid} not found"}, 404)

    @app.get("/tfs-api/links")
    def links():
        return ok({"links": list(standin.links.values())})

    @app.get("/tfs-api/link/<lid>")
    def link(lid):
        lk = standin.links.get(lid)
        return ok(lk) if lk else ok({"error": f"link {lid} not found"}, 404)

    @app.get("/tfs-api/context/<ctx>/services")
    def services(ctx):
        return ok({"services": list(standin.services.values())})

    @app.route("/tfs-api/context/<ctx>/service/<sid>", methods=["GET", "PUT", "DELETE"])
    def service(ctx, sid):
        if request.method == "GET":
            svc = standin.find_service(sid)
            return ok(svc) if svc else ok({"error": f"service {sid} not found"}, 404)
        if request.method == "DELETE":
            return ok({}) if standin.delete_service(sid) else ok({"error": f"service {sid} not found"}, 404)
        try:
            svc = standin.update_service(sid, request.get_json(silent=True) or {})
        except KeyError:
            return ok({"error": f"service {sid} not found"}, 404)
        return ok(svc["service_id"])

    # IETF NBI -----------------------------------------------------------------
    def vpn_post(l2: bool):
        try:
            standin.create_vpn(request.get_json(silent=True) or {}, l2)
        except (ValueError, KeyError) as exc:
            return ok([{"error": str(exc)}], 400)
        return ok([], 201)       # TeraFlowSDN's VPN interfaces answer with a list of errors

    @app.post(f"{L2VPN_PATH}/vpn-services")
    def l2vpn_post():
        return vpn_post(True)

    @app.post(f"{L3VPN_PATH}/vpn-services")
    def l3vpn_post():
        return vpn_post(False)

    @app.delete(f"{L2VPN_PATH}/vpn-services/vpn-service=<vpn_id>")
    @app.delete(f"{L3VPN_PATH}/vpn-services/vpn-service=<vpn_id>")
    def vpn_delete(vpn_id):
        return ok([], 204) if standin.delete_service(vpn_id) else ok([{"error": f"{vpn_id} not found"}], 404)

    @app.get(f"{NETWORKS_PATH}/")
    @app.get(NETWORKS_PATH)
    def networks():
        return ok(standin.rfc8345())

    # stand-in diagnostics -----------------------------------------------------
    @app.get("/standin/wire")
    def wire_log():
        return ok({"seq": wire.seq, "items": wire.since(int(request.args.get("since", 0)))})

    @app.get("/standin/state")
    def state():
        return ok({"devices": {k: {"status": v.get("device_operational_status"), "drivers": v.get("device_drivers")}
                               for k, v in standin.devices.items()},
                   "services": {s["name"]: {"uuid": k, "status": s["service_status"]["service_status"],
                                            "path": [d for d, _ in standin.paths.get(k, [])],
                                            "applied": standin.applied.get(k, {})}
                                for k, s in standin.services.items()}})

    return app


def dst_by_address(standin_ref: Dict[str, StandIn]) -> Callable[[str], str]:
    def dst_of(url: str) -> str:
        from urllib.parse import urlsplit
        netloc = urlsplit(url).netloc
        standin = standin_ref.get("s")
        if standin:
            return standin.addresses.get(netloc, netloc)
        return netloc
    return dst_of


def create(descriptors_path: str, fork_src: str) -> Tuple[Flask, StandIn, Wire]:
    wire = Wire()
    ref: Dict[str, StandIn] = {}
    tap_requests(wire, "TeraFlowSDN", dst_by_address(ref))
    driver_cls, rules = load_fork(fork_src)
    with open(descriptors_path, encoding="utf-8") as f:
        descriptors = json.load(f)
    standin = StandIn({}, driver_cls, rules, wire)
    ref["s"] = standin
    for dev in descriptors.get("devices", []):
        standin.add_device(dev)
    for link in descriptors.get("links", []):
        standin.add_link(link)
    return build_app(standin, wire), standin, wire


def main() -> None:
    parser = argparse.ArgumentParser(description="TeraFlowSDN stand-in (NBI + the fork's Ceragon handler and driver)")
    parser.add_argument("--descriptors", required=True)
    parser.add_argument("--fork-src", default=os.getenv("TFS_FORK_SRC", "../teraflowsdn/src"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app, _standin, _wire = create(args.descriptors, args.fork_src)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
