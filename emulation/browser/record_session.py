"""
Record a live session of the flow for the hosted copy
=====================================================
Drives a running stack (`python emulation/flow_stack.py up`, ns-3.45 local)
the way the dashboard does, and writes every call's answer and every exchange
on the wire to a session file. replay.js serves that file to the dashboard, so
a page with no server shows what the live stack did, call for call.

Runs each example intent from each state the demo can reach (which slices are
in service), and the removal of the new slices from each state. Emulator
passwords are masked.

    python emulation/browser/record_session.py --cer http://localhost:5000 \\
        --out emulation/browser/flow_session.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

PRESETS = {
    "l2": "Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; "
          "keep the radio link at MCS4 or better",
    "l2-big": "Connect region-a and edge over VLAN 310 with 800 Mbps, at most 10 ms latency and 0.1% loss",
    "l3": "Routed L3VPN slice between region-a 192.0.2.1/30 and edge 198.51.100.1/30 with 50 Mbps "
          "and at most 5 ms latency; keep the radio at MCS6 or better",
}
SLICES = {"l2": "slice-region-a-edge-300", "l3": "slice-region-a-edge"}
RFC9543 = "/restconf/data/ietf-network-slice-service:network-slice-services"
HEADERS = {"User-Agent": "flow-dashboard/1.0", "X-Flow-Client": "Operator", "Content-Type": "application/json"}


def mask(value: Any) -> Any:
    """Emulator credentials out of the published file."""
    text = json.dumps(value)
    text = re.sub(r'(\\?"password\\?"\s*:\s*\\?")[^"\\]*', r"\1••••", text)
    return json.loads(text)


class Recorder:
    def __init__(self, cer: str) -> None:
        self.cer = cer.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.cursor = self.s.get(f"{self.cer}/api/v1/flow/wire", params={"since": "0:0"}).json()["cursor"]
        self.states: Dict[str, Any] = {}
        self.runs: Dict[str, Any] = {}
        self.removes: Dict[str, Any] = {}

    def wire(self) -> List[Dict[str, Any]]:
        data = self.s.get(f"{self.cer}/api/v1/flow/wire", params={"since": self.cursor}).json()
        self.cursor = data["cursor"]
        return data["items"]

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.wire()                                     # start from a clean cursor
        t0 = time.time()
        r = self.s.request(method, f"{self.cer}{path}", json=body, timeout=600)
        t1 = time.time()
        time.sleep(0.2)
        try:
            payload = r.json() if r.content else None
        except ValueError:
            payload = {"text": r.text[:2000]}
        return {"method": method, "path": path, "status": r.status_code, "body": mask(payload),
                "t0": t0, "duration": round(t1 - t0, 3), "wire": mask(self.wire())}

    def status(self) -> Dict[str, Any]:
        return self.s.get(f"{self.cer}/api/v1/flow/status").json()

    def state_key(self) -> str:
        st = self.status()
        ids = sorted(s["id"] for s in st["slices"] if s["id"] != "backhaul-ran")
        key = "|".join(ids)
        self.states[key] = mask(st)
        return key

    def run(self, preset: str, withdraw: bool = True) -> Tuple[str, str]:
        before = self.state_key()
        steps = [self.call("POST", "/api/v1/intent", {"intent": PRESETS[preset], "source": "flow-dashboard"})]
        iid = (steps[0]["body"] or {}).get("intent_id")
        verdict = None
        if steps[0]["status"] == 202 and iid:
            steps.append(self.call("POST", "/api/v1/flow/preview", {"intent_id": iid}))
            steps.append(self.call("POST", "/api/v1/flow/simulate", {"intent_id": iid}))
            verdict = ((steps[-1]["body"] or {}).get("preflight") or {}).get("verdict")
            if verdict == "pass":
                steps.append(self.call("POST", f"/api/v1/intents/{iid}/approve"))
                steps.append(self.call("POST", "/api/v1/flow/verify", {"intent_id": iid}))
            elif withdraw:
                steps.append(self.call("DELETE", f"/api/v1/intents/{iid}"))
        after = self.state_key()
        self.runs[f"{before}#{preset}"] = {"preset": preset, "before": before, "after": after, "steps": steps}
        print(f"  [{before or 'none'}] {preset:<7} -> {verdict}  [{after or 'none'}]")
        return before, after

    def remove(self) -> None:
        before = self.state_key()
        st = self.states[before]
        steps = []
        for sl in st["slices"]:
            if sl["id"] != "backhaul-ran":
                steps.append(self.call("DELETE", f"{RFC9543}/slice-service={sl['id']}"))
        after = self.state_key()
        self.removes[before] = {"before": before, "after": after, "steps": steps}
        print(f"  [{before or 'none'}] remove  -> [{after or 'none'}]")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cer", default="http://localhost:5000")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "flow_session.json"))
    args = parser.parse_args(argv)
    rec = Recorder(args.cer)
    if rec.state_key():
        rec.remove()
    # every state the demo reaches without overriding the twin, each example from each
    rec.run("l2-big"); rec.run("l3")                         # none -> l3
    rec.run("l2-big"); rec.run("l3"); rec.run("l2")          # l3 -> l2+l3
    rec.run("l2-big"); rec.run("l2"); rec.run("l3")
    rec.remove()                                             # l2+l3 -> none
    rec.run("l3"); rec.remove()                              # l3 -> none
    rec.run("l2")                                            # none -> l2
    rec.run("l2-big"); rec.run("l2"); rec.remove()           # l2 -> none
    rec.run("l2"); rec.run("l3"); rec.remove()               # l2 -> l2+l3 -> none
    status = rec.status()
    out = {
        "recorded_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "engine": (status.get("twin") or {}).get("engine"),
        "presets": PRESETS,
        "states": rec.states,
        "runs": rec.runs,
        "removes": rec.removes,
    }
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rec.runs)} runs, {len(rec.removes)} removals -> {args.out} ({Path(args.out).stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
