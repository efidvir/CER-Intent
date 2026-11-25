"""
The end-to-end flow's stack: CER-Intent, TeraFlowSDN (stand-in), two radios,
the digital twin with NS-3.45
================================================================================

  radio-1, radio-2   emulation/radio_emulator.py        RESTCONF  127.0.0.1:8101, :8102
  TeraFlowSDN        emulation/tfs_standin.py           NBI       localhost:8088
                     (the fork's Ceragon handler and driver)
  Digital twin       tfs-ns3-digital-twin               DTI       localhost:9100
                     (NS-3.45 Ceragon module: local binary, or recorded runs)
  CER-Intent         run.py                             API       localhost:5000

Two ways to run it:

  python emulation/flow_stack.py up      processes on this machine, real sockets;
                                         open http://localhost:5000/intent-flow.html
  inprocess()                            everything in one Python process over the
                                         virtual network (emulation/vnet.py): the
                                         end-to-end tests and the browser copy

Before the demo starts, one slice is already in service: "backhaul-ran"
(VLAN 100, 200 Mbps), created through CER-Intent's RFC 9543 interface, so the
twin has existing traffic to protect.

Environment:
  TFS_FORK_SRC          TeraFlowSDN fork src/      (default ../teraflowsdn/src)
  TWIN_SRC              twin repository            (default ../tfs-ns3-digital-twin)
  CERAGON_TWIN_BINARY   ns3.45-ceragon-twin; without it the twin replays recorded runs
  NS3_TWIN_RECORDINGS   recorded runs for replay   (default emulation/flow/ns3_recordings.json)
  PYTHON                interpreter for the processes (default: this one)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FLOW = HERE / "flow"
TOPOLOGY = FLOW / "topology.json"
SITE_PLAN = FLOW / "site_plan.json"
RECORDINGS = FLOW / "ns3_recordings.json"
RADIOS = (("radio-1", 8101), ("radio-2", 8102))
RADIO_MODEL, RADIO_SPEED_MBPS = "MH-T261", 1000.0
TFS_PORT, TWIN_PORT, CER_PORT = 8088, 9100, 5000
LAUNCHER_AGENT = "flow-launcher/1.0"

EXISTING_SLICE = {
    "id": "backhaul-ran",
    "description": "RAN backhaul, in service before the demo",
    "sdps": [
        {"id": "1", "node_id": "region-a", "tp_id": "eth1", "vlan_id": 100},
        {"id": "2", "node_id": "edge", "tp_id": "eth1", "vlan_id": 100},
    ],
    "bandwidth_mbps": 200,
    "realization_technology": "L2VPN",
}


def default_paths() -> Dict[str, str]:
    return {
        "fork_src": os.getenv("TFS_FORK_SRC", str(ROOT.parent / "teraflowsdn" / "src")),
        "twin_src": os.getenv("TWIN_SRC", str(ROOT.parent / "tfs-ns3-digital-twin")),
        "ns3_binary": os.getenv("CERAGON_TWIN_BINARY", ""),
        "recordings": os.getenv("NS3_TWIN_RECORDINGS", str(RECORDINGS)),
    }


def twin_env(paths: Dict[str, str], tfs_url: str) -> Dict[str, str]:
    env = {
        "TERAFLOW_URL": tfs_url,
        "TWIN_TOPOLOGY_SOURCE": "rfc8345",
        "TWIN_SITE_PLAN": str(SITE_PLAN),
        "NS3_TWIN_RECORDINGS": paths["recordings"],
    }
    if paths["ns3_binary"] and Path(paths["ns3_binary"]).exists():
        env.update({"NS3_TWIN_MODE": "local", "CERAGON_TWIN_BINARY": paths["ns3_binary"]})
    else:
        env["NS3_TWIN_MODE"] = "replay"
    return env


def cer_env(tfs_url: str, twin_url: str) -> Dict[str, str]:
    return {
        "ADAPTER_BACKEND": "teraflow",
        "TERAFLOW_URL": tfs_url,
        "TFS_REALIZATION": "ietf",
        "TWIN_URL": twin_url,
        "CER_INTENT_MCP_MODE": "advise",
        "TERAFLOW_TIMEOUT_SEC": "10",
    }


def provision_existing(cer_url: str) -> Dict[str, Any]:
    """The slice in service before the demo, through CER-Intent's RFC 9543 interface."""
    import requests
    r = requests.post(f"{cer_url}/restconf/data/ietf-network-slice-service:network-slice-services",
                      json=EXISTING_SLICE, headers={"User-Agent": LAUNCHER_AGENT, "X-Flow-Client": "flow-launcher"},
                      timeout=30)
    return {"status": r.status_code, "body": r.json() if r.content else None}


# ── one process, virtual network ─────────────────────────────────────────────

def inprocess(paths: Optional[Dict[str, str]] = None, provision: bool = True) -> Dict[str, Any]:
    """Build the whole stack in this process on the virtual network. Returns the parts."""
    paths = {**default_paths(), **(paths or {})}
    sys.path[:0] = [p for p in (str(HERE), str(ROOT)) if p not in sys.path]
    import vnet  # noqa: E402
    vnet.install()

    tfs_url, twin_url, cer_url = (f"http://localhost:{TFS_PORT}", f"http://localhost:{TWIN_PORT}",
                                  f"http://localhost:{CER_PORT}")

    # radios
    import radio_emulator  # noqa: E402
    radios = {}
    for name, port in RADIOS:
        state = radio_emulator.RadioState(name, RADIO_MODEL, f"EMU-{name}", speed_mbps=RADIO_SPEED_MBPS)
        vnet.add_handler("127.0.0.1", port, radio_emulator.make_handler(state))
        radios[name] = state

    # TeraFlowSDN stand-in with the fork's handler and driver
    import tfs_standin  # noqa: E402
    tfs_app, standin, tfs_wire = tfs_standin.create(str(TOPOLOGY), paths["fork_src"])
    vnet.add_wsgi("localhost", TFS_PORT, tfs_app)

    # digital twin
    os.environ.update(twin_env(paths, tfs_url))
    for p in (paths["twin_src"],):
        if p not in sys.path:
            sys.path.insert(0, p)
    import tfs_digital_twin_api as twin_api  # noqa: E402
    from tfs_api_client import TfsApiClient  # noqa: E402
    twin_client = TfsApiClient(rest_url=tfs_url, timeout=10)
    ndti = twin_api.NetworkDigitalTwinInstance(
        instance_id=twin_api.DigitalTwinHttpHandler.default_ndti_id,
        name="Ceragon transport twin", scope="transport", tfs_client=twin_client)
    ndti.sync_from_physical()
    twin_api.DigitalTwinHttpHandler.tfs_client = twin_client
    twin_api.DigitalTwinHttpHandler.ndti_manager[ndti.instance_id] = ndti
    vnet.add_handler("localhost", TWIN_PORT, twin_api.DigitalTwinHttpHandler)

    # CER-Intent
    os.environ.update(cer_env(tfs_url, twin_url))
    os.environ.setdefault("STATE_FILE", os.path.join(os.getenv("TMPDIR", "/tmp"), "cer_intent_flow_state.json"))
    from cer_intent.api.server import create_app  # noqa: E402
    from cer_intent.assurance.audit_log import AuditLog  # noqa: E402
    from cer_intent.device.registry import DeviceRegistry  # noqa: E402
    app = create_app(registry=DeviceRegistry(),
                     audit_log=AuditLog(os.path.join(os.getenv("TMPDIR", "/tmp"), "cer_intent_flow_audit.jsonl")))
    vnet.add_wsgi("localhost", CER_PORT, app)

    existing = provision_existing(cer_url) if provision else None
    return {"app": app, "standin": standin, "tfs_wire": tfs_wire, "radios": radios, "ndti": ndti,
            "existing": existing, "urls": {"tfs": tfs_url, "twin": twin_url, "cer": cer_url}}


def check(paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    The demo's three intents through the in-process stack, as the dashboard runs
    them: a 500 Mbps L2 slice (applied and verified), an 800 Mbps one (held by
    the twin, nothing sent) and its removal. Returns what each step answered.
    """
    stack = inprocess(paths)
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "flow-dashboard/1.0", "X-Flow-Client": "Operator"})
    cer = stack["urls"]["cer"]
    out: Dict[str, Any] = {"existing": stack["existing"]["status"]}

    def run(text: str) -> Dict[str, Any]:
        step: Dict[str, Any] = {}
        r = s.post(f"{cer}/api/v1/intent", json={"intent": text, "source": "check"})
        step["intent"] = r.status_code
        iid = r.json().get("intent_id")
        step["strategy"] = ((r.json().get("plan") or {}).get("selected_strategy") or {}).get("name")
        pv = s.post(f"{cer}/api/v1/flow/preview", json={"intent_id": iid}).json()
        step["candidate"] = pv.get("candidate")
        sim = s.post(f"{cer}/api/v1/flow/simulate", json={"intent_id": iid})
        pf = sim.json().get("preflight", {})
        step["verdict"], step["checks"] = pf.get("verdict"), pf.get("checks")
        step["engine"] = (pf.get("engine") or {}).get("mode")
        ap = s.post(f"{cer}/api/v1/intents/{iid}/approve")
        step["approve"] = ap.status_code
        if ap.status_code == 200:
            v = s.post(f"{cer}/api/v1/flow/verify", json={"intent_id": iid}).json()
            step["verify"] = {"ok": v.get("ok"), "checks": v.get("checks"), "radios": v.get("radios"),
                              "diff_leaves": len(v.get("diff", []))}
        return step

    cursor = s.get(f"{cer}/api/v1/flow/wire", params={"since": "0:0"}).json()["cursor"]
    out["l2"] = run("Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; "
                    "keep the radio link at MCS4 or better")
    out["l2_big"] = run("Connect region-a and edge over VLAN 310 with 800 Mbps, at most 10 ms latency and 0.1% loss")
    d = s.delete(f"{cer}/restconf/data/ietf-network-slice-service:network-slice-services/"
                 f"slice-service=slice-region-a-edge-300")
    out["remove"] = d.status_code
    out["radios_after_remove"] = {name: sorted(state.running["bridges"]) for name, state in stack["radios"].items()}
    wire = s.get(f"{cer}/api/v1/flow/wire", params={"since": cursor}).json()["items"]
    out["wire"] = [{"src": e["src"], "dst": e["dst"], "method": e["method"], "path": e["path"].split("?")[0],
                    "status": e["status"], "std": e["std"]["std"], "transport": e["transport"]} for e in wire]
    return out


def imf_check(paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    The intent manager through the in-process stack, over its three interfaces:
    a conversation (/api/v2/converse), TMF921 v5 and 3GPP TS 28.312. Returns what
    each step answered and the exchanges on the wire.
    """
    os.environ.update({"CER_IMF_STORE": ":memory:", "CER_IMF_TICK_S": "0"})
    stack = inprocess(paths)
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "intent-studio/1.0", "X-Flow-Client": "Operator", "X-User": "check", "X-Role": "approver"})
    cer = stack["urls"]["cer"]
    out: Dict[str, Any] = {"existing": stack["existing"]["status"]}
    cursor = s.get(f"{cer}/api/v1/flow/wire", params={"since": "0:0"}).json()["cursor"]

    def say(text: str) -> Dict[str, Any]:
        r = s.post(f"{cer}/api/v2/converse", json={"session": "check", "text": text})
        b = r.json()
        rec = b.get("intent") or {}
        return {"status": r.status_code, "how": b.get("how"), "state": rec.get("state"), "reply": b.get("reply"),
                "id": rec.get("id"), "twin": ((rec.get("check") or {}).get("twin") or {}).get("verdict"),
                "questions": [q["field"] for q in rec.get("questions", [])], "slices": (rec.get("links") or {}).get("slices")}

    out["deliver"] = say("Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; "
                         "keep the radio link at MCS4 or better")
    out["approve"] = say("approve")
    out["radios"] = {name: sorted(st.running["bridges"]) for name, st in stack["radios"].items()}
    out["clarify"] = say("Connect HQ and edge with 50 Mbps")
    out["answer"] = say("region-a")
    out["cancel"] = say("cancel")
    out["headroom"] = say("How much more can the hop carry in heavy rain?")
    out["inventory"] = say("What runs over radio-1?")
    out["scope"] = say("Configure BGP on the core routers")
    tmf = s.post(f"{cer}/tmf-api/intentManagement/v5/intent",
                 json={"name": "cctv", "description": "Connect region-a and edge with 60 Mbps, at most 20 ms"}).json()
    out["tmf_create"] = {"status": tmf.get("lifecycleStatus"), "id": tmf.get("id"), "type": tmf.get("@type"),
                         "reply": s.get(f"{cer}/api/v2/intents/{tmf.get('id')}").json().get("reply")}
    p = s.patch(f"{cer}/tmf-api/intentManagement/v5/intent/{tmf['id']}", json={"lifecycleStatus": "active"}).json()
    out["tmf_active"] = p.get("lifecycleStatus")
    rep = s.get(f"{cer}/tmf-api/intentManagement/v5/intent/{tmf['id']}/intentReport").json()
    out["tmf_report"] = rep[0]["expression"]["expressionValue"]["icm:intentHandlingState"] if rep else None
    g = s.put(f"{cer}/3gpp-intent/v1/IntentHandlingFunction=1/Intent=video-1", json={"Intent": {
        "userLabel": "video", "intentAdminState": "ACTIVATED", "intentExpectations": [{
            "expectationId": "e1", "expectationVerb": "DELIVER",
            "expectationObject": {"objectType": "TransportNetworkSlice", "objectInstance": "slice-video",
                                  "objectContexts": [{"contextAttribute": "serviceDemarcationPoints", "contextCondition": "IS_ALL_OF",
                                                      "contextValueRange": [{"node": "region-a"}, {"node": "edge"}]}]},
            "expectationTargets": [{"targetName": "oneWayBandwidth", "targetCondition": "IS_EQUAL_TO_OR_GREATER_THAN",
                                    "targetValueRange": 10, "targetUnit": "Mbps"}]}]}}).json()
    out["g3_put"] = {"state": g.get("cerState"), "id": g.get("id")}
    r3 = s.get(f"{cer}/3gpp-intent/v1/IntentHandlingFunction=1/Intent=video-1/IntentReport").json()
    out["g3_report"] = r3["intentFulfilmentReport"]["intentFulfilmentInfo"]["fulfilmentStatus"]
    net = s.get(f"{cer}/api/v2/network").json()
    out["network_slices"] = sorted(x["id"] for x in net["slices"])
    out["withdraw"] = s.delete(f"{cer}/api/v2/intents/{out['approve']['id']}").json().get("state")
    out["slices_after"] = sorted(x["id"] for x in s.get(f"{cer}/api/v2/network").json()["slices"])
    wire = s.get(f"{cer}/api/v1/flow/wire", params={"since": cursor}).json()["items"]
    out["wire"] = [{"src": e["src"], "dst": e["dst"], "method": e["method"], "path": e["path"].split("?")[0],
                    "status": e["status"], "std": e["std"]["std"]} for e in wire]
    return out


# ── processes, real sockets ──────────────────────────────────────────────────

def _wait(url: str, timeout: float = 60.0) -> bool:
    import requests
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.get(url, timeout=2, headers={"X-Flow-Quiet": "1"}).status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def up(paths: Dict[str, str], python: str, logs: Path) -> List[subprocess.Popen]:
    logs.mkdir(parents=True, exist_ok=True)
    procs: List[subprocess.Popen] = []
    tfs_url, twin_url, cer_url = (f"http://localhost:{TFS_PORT}", f"http://localhost:{TWIN_PORT}",
                                  f"http://localhost:{CER_PORT}")

    def start(name: str, args: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> None:
        out = open(logs / f"{name}.log", "w", encoding="utf-8")
        procs.append(subprocess.Popen(args, cwd=str(cwd), env={**os.environ, **(env or {})},
                                      stdout=out, stderr=subprocess.STDOUT))
        print(f"  started {name:<12} (log: {logs / (name + '.log')})")

    for name, port in RADIOS:
        start(name, [python, str(HERE / "radio_emulator.py"), "--port", str(port), "--node-name", name,
                     "--model", RADIO_MODEL, "--speed-mbps", str(RADIO_SPEED_MBPS)], ROOT)
    for name, port in RADIOS:
        if not _wait(f"http://127.0.0.1:{port}/emulator/state", 20):
            raise SystemExit(f"{name} did not start")
    start("teraflowsdn", [python, str(HERE / "tfs_standin.py"), "--descriptors", str(TOPOLOGY),
                          "--fork-src", paths["fork_src"], "--port", str(TFS_PORT)], ROOT)
    if not _wait(f"{tfs_url}/tfs-api/contexts", 30):
        raise SystemExit("TeraFlowSDN stand-in did not start")
    start("twin", [python, "tfs_digital_twin_api.py", str(TWIN_PORT)], Path(paths["twin_src"]),
          twin_env(paths, tfs_url))
    if not _wait(f"{twin_url}/healthz", 30):
        raise SystemExit("digital twin did not start")
    start("cer-intent", [python, "run.py"], ROOT,
          {**cer_env(tfs_url, twin_url), "FLASK_PORT": str(CER_PORT), "FLASK_DEBUG": "false"})
    if not _wait(f"{cer_url}/api/v1/flow/status", 60):
        raise SystemExit("CER-Intent did not start")
    existing = provision_existing(cer_url)
    print(f"  existing slice backhaul-ran: HTTP {existing['status']}")
    return procs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["up", "check", "imf"])
    parser.add_argument("--logs", default=str(ROOT / "data" / "flow-logs"))
    args = parser.parse_args(argv)
    paths = default_paths()
    if args.command == "check":
        print(json.dumps(check(paths), indent=1))
        return 0
    if args.command == "imf":
        print(json.dumps(imf_check(paths), indent=1))
        return 0
    python = os.getenv("PYTHON", sys.executable)
    mode = "NS-3.45 local binary" if paths["ns3_binary"] and Path(paths["ns3_binary"]).exists() else "recorded NS-3 runs"
    print(f"Starting the flow stack (twin: {mode})")
    procs = up(paths, python, Path(args.logs))
    print(f"\n  Flow dashboard: http://localhost:{CER_PORT}/intent-flow.html   (Ctrl+C stops everything)\n")

    def stop(*_a: Any) -> None:
        for p in reversed(procs):
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        for p in procs:
            if p.poll() is not None:
                print(f"a component exited (pid {p.pid}, code {p.returncode}); stopping")
                stop()
        time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
