"""
Ceragon MultiHaul TG radio emulator (RESTCONF)
==============================================
A small stand-in for a radio's management plane, so the chain

    OpenSlice -> CER-Intent (RFC 9543) -> TeraFlowSDN (L3VPN/L2VPN)
              -> Ceragon driver -> radio

can run without hardware. It serves the parts of the radio-bridge YANG
datastore the Ceragon driver reads and writes:

  GET    /restconf/ds/ietf-datastores:candidate[/<subtree>]   datastore (running + staged)
  PATCH  /restconf/ds/ietf-datastores:candidate/<subtree>     stage a change
  DELETE /restconf/ds/ietf-datastores:candidate/<subtree>     stage a deletion
  POST   /restconf/operations/ietf-netconf:commit             apply staged changes
  POST   /restconf/operations/ietf-netconf:discard-changes    drop staged changes
  POST   /restconf/operations/<other rpc>                     empty answer

Emulator controls (not part of the radio API):
  GET  /emulator/state     committed bridges, link conditions, commit count
  POST /emulator/link      {"speed_mbps", "rssi", "snr", "mcs"}: change the air link

In Containerlab it can also be the data plane of the hop: --bridge eth1,eth2
joins the two ports in a Linux bridge, and --shape-dev eth2 caps that port at
the air link's speed with tc, updated on every link change. Both need
NET_ADMIN; without the flags the emulator only answers RESTCONF.

    python emulation/radio_emulator.py --port 8080 --node-name radio-a
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

LOG = logging.getLogger("radio-emulator")

CANDIDATE = "/restconf/ds/ietf-datastores:candidate"
RUNNING = "/restconf/ds/ietf-datastores:running"
OPERATIONS = "/restconf/operations/"
BRIDGE_PATH_RE = re.compile(r"^radio-bridge-tg-user-bridge:user-bridge/bridge=(?P<id>\d+)$")


class RadioState:
    """Committed configuration, staged changes and air-link conditions of one radio."""

    def __init__(self, node_name: str, model: str, serial: str, frequency_mhz: int = 60480,
                 speed_mbps: float = 1800.0, ports: Tuple[str, ...] = ("eth1",)) -> None:
        self.lock = threading.RLock()
        self.node_name, self.model, self.serial = node_name, model, serial
        self.ports = ports
        self.running: Dict[str, Any] = {
            "bridges": {},
            "node_config": {"operation-mode": "DN", "tx-power-control": "auto"},
            "sectors": {1: {"frequency": str(frequency_mhz), "admin-status": "up"}},
        }
        self.staged: List[Tuple[str, str, Any]] = []   # (op, path, payload)
        self.link = {"speed_mbps": speed_mbps, "rssi": -45.0, "snr": 21.0, "mcs": 9}
        self.counters = {"in": 0, "out": 0}
        self.commits = 0
        self.on_link_change = None  # set by the shaper

    # ── datastore ────────────────────────────────────────────────────────────
    def _apply(self, config: Dict[str, Any], op: str, path: str, payload: Any) -> None:
        bridge = BRIDGE_PATH_RE.match(path)
        if bridge:
            bid = int(bridge.group("id"))
            if op == "delete":
                config["bridges"].pop(bid, None)
            else:
                entries = (payload or {}).get("radio-bridge-tg-user-bridge:bridge", [])
                if entries:
                    config["bridges"][bid] = entries[0]
            return
        if path.endswith("radio-common/node-config"):
            if op == "delete":
                return
            config["node_config"].update((payload or {}).get("radio-bridge-tg-radio-common:node-config", {}))
            return
        m = re.search(r"sector=(\d+)$", path)
        if m and op != "delete":
            sector = config["sectors"].setdefault(int(m.group(1)), {"admin-status": "up"})
            for key in ("radio-bridge-tg-radio-dn:sector", "radio-bridge-tg-radio-common:sector"):
                for entry in (payload or {}).get(key, []):
                    if "admin-status" in entry:
                        sector["admin-status"] = entry["admin-status"]
                    freq = (entry.get("radio-profile") or {}).get("frequency")
                    if freq:
                        sector["frequency"] = str(freq)
            return
        LOG.info("ignored %s on %s", op, path)

    def candidate(self) -> Dict[str, Any]:
        with self.lock:
            config = copy.deepcopy(self.running)
            for op, path, payload in self.staged:
                self._apply(config, op, path, payload)
            return config

    def stage(self, op: str, path: str, payload: Any) -> None:
        with self.lock:
            self.staged.append((op, path, payload))

    def commit(self) -> None:
        with self.lock:
            self.running = self.candidate()
            self.staged.clear()
            self.commits += 1

    def discard(self) -> None:
        with self.lock:
            self.staged.clear()

    def set_link(self, **values: Any) -> Dict[str, Any]:
        with self.lock:
            for key in ("speed_mbps", "rssi", "snr", "mcs"):
                if values.get(key) is not None:
                    self.link[key] = float(values[key]) if key != "mcs" else int(values[key])
            link = dict(self.link)
        if self.on_link_change:
            self.on_link_change(link)
        return link

    # ── RESTCONF view ────────────────────────────────────────────────────────
    def datastore(self) -> Dict[str, Any]:
        config = self.candidate()
        with self.lock:
            self.counters["in"] += int(self.link["speed_mbps"] * 1e6 / 8 * 0.4)   # traffic keeps flowing
            self.counters["out"] += int(self.link["speed_mbps"] * 1e6 / 8 * 0.4)
            link, counters = dict(self.link), dict(self.counters)
        interfaces = [{"ifIndex": 1, "name": "host", "iftype": "host", "oper-status": "up"}]
        for i, port in enumerate(self.ports, start=2):
            interfaces.append({"ifIndex": i, "name": port, "iftype": "ethernet", "ifSpeed": 10_000_000_000,
                               "admin-status": "up", "oper-status": "up",
                               "ifInOctets": counters["in"], "ifOutOctets": counters["out"]})
        interfaces.append({"ifIndex": 9, "name": "rf", "iftype": "rf", "oper-status": "up"})
        return {
            "radio-bridge-tg-system:system": {"name": self.node_name, "state": {"product": self.model, "uptime": "1d"}},
            "radio-bridge-tg-inventory:inventory": {"component": [{
                "physical-class": "chassis", "model-name": self.model, "serial-num": self.serial,
                "hardware-rev": "EMU", "software-rev": "emulator", "mfg-name": "Ceragon (emulated)"}]},
            "radio-bridge-tg-interfaces:interfaces": {"interface": interfaces},
            "radio-bridge-tg-radio-common:radio-common": {
                "node-config": config["node_config"],
                "links": {"active": [{
                    "remote-assigned-name": "peer", "actual-local-sector-index": 1, "actual-remote-sector-index": 1,
                    "rssi": link["rssi"], "snr": link["snr"], "mcs-tx": link["mcs"], "mcs-rx": link["mcs"],
                    "speed-tx": link["speed_mbps"], "speed-rx": link["speed_mbps"]}]},
                "sectors-config": {"sector": [
                    {"index": idx, "admin-status": s.get("admin-status", "up"),
                     "state": {"frequency": s.get("frequency", "60480"), "antenna-mode": "beamforming"}}
                    for idx, s in sorted(config["sectors"].items())]},
            },
            "radio-bridge-tg-user-bridge:user-bridge": {
                "bridge": [config["bridges"][k] for k in sorted(config["bridges"])]},
        }


class Shaper:
    """Linux data plane of the hop: a bridge between two ports and a rate cap on the air port."""

    def __init__(self, bridge_ports: Optional[List[str]], shape_dev: Optional[str]) -> None:
        self.bridge_ports, self.shape_dev = bridge_ports, shape_dev

    @staticmethod
    def _run(*cmd: str) -> None:
        LOG.info("$ %s", " ".join(cmd))
        subprocess.run(cmd, check=False)

    @staticmethod
    def wait_for(ports: List[str], timeout_s: float = 120.0) -> None:
        """Containerlab adds the data ports after the container starts: wait for them."""
        import os
        import time
        deadline = time.time() + timeout_s
        while time.time() < deadline and not all(os.path.exists(f"/sys/class/net/{p}") for p in ports):
            time.sleep(1.0)

    def setup(self) -> None:
        ports = list(self.bridge_ports or []) + ([self.shape_dev] if self.shape_dev else [])
        if ports:
            self.wait_for(ports)
        if self.bridge_ports:
            self._run("ip", "link", "add", "br0", "type", "bridge")
            for port in self.bridge_ports:
                self._run("ip", "link", "set", port, "master", "br0")
                self._run("ip", "link", "set", port, "up")
            self._run("ip", "link", "set", "br0", "up")

    def apply(self, link: Dict[str, Any]) -> None:
        if self.shape_dev:
            rate = max(1, int(link["speed_mbps"]))
            self._run("tc", "qdisc", "replace", "dev", self.shape_dev, "root", "tbf",
                      "rate", f"{rate}mbit", "burst", "256kbit", "latency", "20ms")


def make_handler(state: RadioState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CeragonRadioEmulator/0.1"

        def log_message(self, fmt, *args):  # route through logging
            LOG.debug(fmt, *args)

        def _body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            try:
                return json.loads(self.rfile.read(length))
            except ValueError:
                return None

        def _send(self, status: int, payload: Any = None) -> None:
            data = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/yang-data+json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _subtree(self) -> Tuple[Optional[str], str]:
            path = unquote(urlparse(self.path).path)
            for root in (CANDIDATE, RUNNING):
                if path == root or path.startswith(root + "/"):
                    return root, path[len(root):].lstrip("/")
            return None, path

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/emulator/state":
                with state.lock:
                    return self._send(200, {"bridges": state.running["bridges"], "link": state.link,
                                            "commits": state.commits, "staged": len(state.staged)})
            root, subtree = self._subtree()
            if root is None:
                return self._send(404, {"error": "unknown path"})
            data = state.datastore()
            if not subtree:
                return self._send(200, {"ietf-restconf:data": data})
            top = subtree.split("/", 1)[0]
            if top in data:
                return self._send(200, {top: data[top]})
            return self._send(404, {"error": f"no data for {subtree}"})

        def do_PATCH(self):  # noqa: N802
            root, subtree = self._subtree()
            if root != CANDIDATE or not subtree:
                return self._send(405, {"error": "PATCH the candidate datastore"})
            state.stage("merge", subtree, self._body())
            return self._send(204)

        def do_PUT(self):  # noqa: N802
            return self.do_PATCH()

        def do_DELETE(self):  # noqa: N802
            root, subtree = self._subtree()
            if root != CANDIDATE or not subtree:
                return self._send(405, {"error": "DELETE in the candidate datastore"})
            state.stage("delete", subtree, None)
            return self._send(204)

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            body = self._body()
            if path == "/emulator/link":
                return self._send(200, state.set_link(**(body or {})))
            if not path.startswith(OPERATIONS):
                return self._send(404, {"error": "unknown operation"})
            rpc = path[len(OPERATIONS):]
            if rpc == "ietf-netconf:commit":
                state.commit()
                return self._send(204)
            if rpc == "ietf-netconf:discard-changes":
                state.discard()
                return self._send(204)
            if rpc == "ietf-netconf:validate":
                return self._send(204)
            module = rpc.split(":", 1)[0]
            return self._send(200, {f"{module}:output": {}})

    return Handler


def serve(state: RadioState, host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(state))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ceragon MultiHaul TG radio emulator (RESTCONF)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--node-name", default="radio-emu")
    parser.add_argument("--model", default="MH-T261")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--speed-mbps", type=float, default=1800.0)
    parser.add_argument("--bridge", default="", help="comma-separated ports to bridge, e.g. eth1,eth2")
    parser.add_argument("--shape-dev", default="", help="port to cap at the air link speed, e.g. eth2")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    state = RadioState(args.node_name, args.model, args.serial or f"EMU-{args.node_name}", speed_mbps=args.speed_mbps)
    shaper = Shaper([p for p in args.bridge.split(",") if p] or None, args.shape_dev or None)
    state.on_link_change = shaper.apply

    def data_plane() -> None:
        shaper.setup()
        shaper.apply(state.link)
    threading.Thread(target=data_plane, name="data-plane", daemon=True).start()
    httpd = serve(state, args.host, args.port)
    LOG.info("radio emulator %s (%s) on %s:%d", args.node_name, args.model, args.host, args.port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
