"""
Acting on an approved intent
============================
Every change goes through the interfaces CER-Intent already uses, so the flow
dashboard shows it hop by hop:

  deliver      an RFC 9543 slice request to the slice controller (mapper,
               planner, technology selector, realizer: L2SM / L3SM to TeraFlowSDN)
  change       the slice controller updates the slice in place (TeraFlowSDN
               service constraints and settings); a VLAN change re-creates it
  lifecycle    suspend withdraws the slice and keeps its request on the record;
               resume re-creates it; remove withdraws it
  optimise     energy: automatic transmit power control on the hop's radios,
               carried as TeraFlowSDN service settings ("radio"), for the window
  revert       the record of what an action replaced is kept, so a window's end
               or a rollback puts it back

Radio and modulation actions only use what the Ceragon driver exposes; anything
else is answered on the twin and recorded as such.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from cer_intent.imf.model import Expectation, IntentRecord
from cer_intent.imf.radio import mcs_for_snr


def _wire(kind: str, slice_id: Optional[str], request: Any, response: Any, t0: float) -> None:
    try:
        from cer_intent.flow.wiretap import slice_request_handled
        slice_request_handled(kind, slice_id, request, response, t0)
    except Exception:  # pylint: disable=broad-except
        pass


def slice_request(e: Expectation, rec: IntentRecord) -> Dict[str, Any]:
    """The RFC 9543 request (CER-Intent's compact form) for a delivery."""
    eps = e.object.endpoints
    sdps = []
    for i, ep in enumerate(eps[:2], 1):
        sdp = {"id": str(i), "node_id": ep.node, "tp_id": ep.port or "eth1"}
        if ep.vlan is not None:
            sdp["vlan_id"] = int(ep.vlan)
        if ep.ip:
            sdp["ip_address"] = ep.ip
        sdps.append(sdp)
    req: Dict[str, Any] = {"id": e.name, "description": (rec.text or e.summary())[:160], "sdps": sdps,
                           "realization_technology": e.value("technology") or "L2VPN",
                           "intent_text": rec.text, "intent_id": rec.id}
    for metric, key in (("bandwidth", "bandwidth_mbps"), ("latency", "max_latency_ms"), ("loss", "packet_loss_pct"),
                        ("availability", "availability_pct"), ("jitter", "jitter_ms")):
        v = e.value(metric)
        if v is not None:
            req[key] = float(v)
    floor = e.value("modulation_floor")
    if floor:
        req["acm"] = {"min_modulation": floor}
    return req


class Actuator:
    def __init__(self, nsc: Callable[[], Any]):
        self._nsc = nsc

    @property
    def nsc(self):
        return self._nsc()

    # ── deliver ──────────────────────────────────────────────────────────────
    def deliver(self, e: Expectation, rec: IntentRecord) -> Dict[str, Any]:
        req = slice_request(e, rec)
        t0 = time.time()
        res = self.nsc.create_or_update_slice_service(req)
        _wire("create", req["id"], req, res, t0)
        realization = ((res.get("nsc_pipeline") or {}).get("realizer") or {})
        ok = "nsc_pipeline" in res and realization.get("status") != "failed"
        if not ok and req["id"] in getattr(self.nsc, "slices", {}):
            self.nsc.delete_slice_service(req["id"])            # half-made: the controller kept a record of it
        act = {"t": time.time(), "op": "deliver", "slice": req["id"], "ok": ok, "request": req,
               "technology": ((res.get("nsc_pipeline") or {}).get("technology_selector") or {}).get("technology"),
               "realization": ((res.get("nsc_pipeline") or {}).get("realizer") or {}).get("status"),
               "hop_floor": res.get("hop_floor"), "undo": {"op": "remove", "slice": req["id"]}}
        if not ok:
            act["error"] = res.get("error") or realization.get("error") or "the slice controller refused the request"
        else:
            rec.links.setdefault("slices", [])
            if req["id"] not in rec.links["slices"]:
                rec.links["slices"].append(req["id"])
        return act

    # ── change ───────────────────────────────────────────────────────────────
    def change(self, e: Expectation, rec: IntentRecord, revert: bool = False) -> List[Dict[str, Any]]:
        out = []
        for sid in e.object.ids:
            nsc = self.nsc
            stored = nsc.requests.get(sid)
            if stored is None:
                out.append({"t": time.time(), "op": "change", "slice": sid, "ok": False, "error": f"{sid} is not in the slice controller"})
                continue
            before = {"bandwidth": stored["slos"].get("bandwidth_mbps"), "latency": stored["slos"].get("max_latency_ms"),
                      "modulation_floor": (stored.get("acm") or {}).get("min_modulation"),
                      "vlan": next((x.get("vlan_id") for x in stored["service"].get("sdps", []) if isinstance(x, dict)), None)}
            target = dict(e.action.get("before", {}).get(sid, {})) if revert else {}
            metric = e.action.get("metric")
            if not revert:
                for m in ("bandwidth", "latency", "modulation_floor"):
                    if e.target(m) is not None:
                        target[m] = e.value(m)
                if metric == "vlan":
                    target["vlan"] = e.action.get("value")
            if "vlan" in target and target["vlan"] is not None and target["vlan"] != before["vlan"]:
                out.append(self._recreate_with_vlan(sid, int(target["vlan"]), rec))
                continue
            t0 = time.time()
            res = nsc.update_slice_slos(sid, bandwidth_mbps=target.get("bandwidth"), max_latency_ms=target.get("latency"),
                                        acm={"min_modulation": target["modulation_floor"]} if target.get("modulation_floor") else None)
            _wire("update", sid, {"slice": sid, **target}, res, t0)
            ok = bool(res) and res.get("status") == "updated"
            act = {"t": time.time(), "op": "revert" if revert else "change", "slice": sid, "ok": ok, "set": target,
                   "before": before, "undo": {"op": "change", "slice": sid, "set": {k: before.get(k) for k in target}}}
            if not ok:
                act["error"] = (res or {}).get("error", "update refused")
            out.append(act)
            if not revert:
                e.action.setdefault("before", {})[sid] = {k: before.get(k) for k in target}
        return out

    def _recreate_with_vlan(self, sid: str, vlan: int, rec: IntentRecord) -> Dict[str, Any]:
        nsc = self.nsc
        stored = json.loads(json.dumps(nsc.requests[sid]["service"]))
        old_vlan = next((x.get("vlan_id") for x in stored.get("sdps", []) if isinstance(x, dict)), None)
        for x in stored.get("sdps", []):
            if isinstance(x, dict):
                x["vlan_id"] = vlan
        t0 = time.time()
        gone = nsc.delete_slice_service(sid)
        _wire("delete", sid, {"slice": sid}, gone, t0)
        t0 = time.time()
        res = nsc.create_or_update_slice_service(stored)
        _wire("create", sid, stored, res, t0)
        ok = "nsc_pipeline" in res
        return {"t": time.time(), "op": "change", "slice": sid, "ok": ok, "set": {"vlan": vlan}, "before": {"vlan": old_vlan},
                "note": "the VLAN is part of the attachment: the slice was re-created (a short interruption)",
                "undo": {"op": "change", "slice": sid, "set": {"vlan": old_vlan}}, **({} if ok else {"error": res.get("error")})}

    # ── lifecycle ────────────────────────────────────────────────────────────
    def lifecycle(self, e: Expectation, rec: IntentRecord) -> List[Dict[str, Any]]:
        out = []
        op = e.action.get("op")
        held = rec.links.setdefault("suspended", {})
        for sid in e.object.ids:
            nsc = self.nsc
            if op in ("suspend", "delete"):
                stored = nsc.requests.get(sid)
                t0 = time.time()
                res = nsc.delete_slice_service(sid)
                _wire("delete", sid, {"slice": sid}, res, t0)
                ok = res is not None and res.get("status") != "failed"
                if ok and op == "suspend" and stored is not None:
                    held[sid] = stored["service"]
                out.append({"t": time.time(), "op": op, "slice": sid, "ok": ok,
                            **({"undo": {"op": "resume", "slice": sid}} if op == "suspend" else {}),
                            **({} if ok else {"error": "not found or refused"})})
            elif op == "resume":
                req = held.get(sid) or self._suspended_elsewhere(sid)
                if req is None:
                    out.append({"t": time.time(), "op": "resume", "slice": sid, "ok": False, "error": f"{sid} is not suspended"})
                    continue
                t0 = time.time()
                res = nsc.create_or_update_slice_service(req)
                _wire("create", sid, req, res, t0)
                ok = "nsc_pipeline" in res
                if ok:
                    held.pop(sid, None)
                out.append({"t": time.time(), "op": "resume", "slice": sid, "ok": ok, **({} if ok else {"error": res.get("error")})})
        return out

    _suspended_lookup: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None

    def _suspended_elsewhere(self, sid: str) -> Optional[Dict[str, Any]]:
        return self._suspended_lookup(sid) if self._suspended_lookup else None

    def remove(self, sid: str) -> Dict[str, Any]:
        t0 = time.time()
        res = self.nsc.delete_slice_service(sid)
        _wire("delete", sid, {"slice": sid}, res, t0)
        return {"t": time.time(), "op": "remove", "slice": sid, "ok": res is not None and res.get("status") != "failed"}

    # ── optimise: energy ─────────────────────────────────────────────────────
    def energy(self, e: Expectation, rec: IntentRecord, on: bool, net) -> List[Dict[str, Any]]:
        out = []
        nsc = self.nsc
        for hid in e.object.ids:
            a, _, b = hid.partition("|")
            carriers = [s.id for s in net.slices_on(net.hop(a, b)) if s.id in nsc.slices] if net else []
            if not carriers:
                out.append({"t": time.time(), "op": "energy", "hop": hid, "ok": True, "twin_only": True,
                            "note": "no slice runs on this hop to carry radio settings: the saving is shown on the twin only"})
                continue
            sid = carriers[0]
            settings = {"radio": {"atpc_enabled": True}} if on else {"radio": dict(rec.links.get("radio_before", {}).get(hid) or {"atpc_enabled": True})}
            t0 = time.time()
            try:
                nsc.tfs_client.update_service_settings(sid, settings)
                ok, err = True, None
            except Exception as exc:  # pylint: disable=broad-except
                ok, err = False, str(exc)
            _wire("update", sid, settings, {"ok": ok}, t0)
            out.append({"t": time.time(), "op": "energy-on" if on else "energy-off", "hop": hid, "via": sid, "ok": ok,
                        "settings": settings, **({"error": err} if err else {})})
        return out


# ── what the radios report now ─────────────────────────────────────────────────

_MCS_RX = re.compile(r'"(?:mcs-tx|mcs|current[-_]modulation|selected-cm)"\s*:\s*"?(?:[\w:-]*?mcs-?)?(\d{1,2})\b', re.I)
_SNR_RX = re.compile(r'"(?:actual-snir|snr)"\s*:\s*(-?\d+(?:\.\d+)?)', re.I)


def radio_state(tfs_client, radios: List[str]) -> Dict[str, Dict[str, Any]]:
    """Current modulation per radio, from the device views the Ceragon driver reports to TeraFlowSDN."""
    out: Dict[str, Dict[str, Any]] = {}
    if tfs_client is None:
        return out
    for name in radios:
        try:
            try:
                dev = tfs_client.get_device(name, fresh=True)
            except TypeError:                  # clients without read-back
                dev = tfs_client.get_device(name)
        except Exception:  # pylint: disable=broad-except
            continue
        text = json.dumps(dev.get("device_config", {}) if isinstance(dev, dict) else {})
        mcs = _MCS_RX.search(text.replace('\\"', '"'))
        snr = _SNR_RX.search(text.replace('\\"', '"'))
        state: Dict[str, Any] = {}
        if snr:
            state["snr_db"] = float(snr.group(1))
        if mcs:
            state["mcs"] = f"MCS{int(mcs.group(1))}"
        elif snr:
            state["mcs"] = mcs_for_snr(float(snr.group(1)))
        if state:
            out[name] = state
    return out
