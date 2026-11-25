"""
End-to-end demo: RFC 9543 slice through CER-Intent and TeraFlowSDN to the radios
================================================================================
Runs the ETSI chain on the Containerlab topology in emulation/containerlab/:

  1. onboard the topology into TeraFlowSDN (TFS API: contexts, topologies, devices, links)
  2. wait until every device is enabled
  3. order the slice from CER-Intent's RFC 9543 interface (mapper -> technology
     selector -> realizer -> L3SM to TeraFlowSDN)
  4. wait for TeraFlowSDN's service to become active
  5. read a radio's RFC 8561 view from TeraFlowSDN (as reported at onboarding)
  6. optionally fade the air link on the emulator (--fade-mbps)
  7. delete the slice

    python emulation/e2e_demo.py --tfs http://<tfs-host> --cer-intent http://<cer-intent>:5000
    python emulation/e2e_demo.py --dry-run          # print the requests only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

HERE = Path(__file__).resolve().parent
RFC9543 = "/restconf/data/ietf-network-slice-service:network-slice-services"


class Demo:
    def __init__(self, tfs: str, cer_intent: str, dry_run: bool, auth=("admin", "admin"),
                 out: Callable[[str], None] = print) -> None:
        self.tfs, self.cer, self.dry_run, self.auth, self.out = tfs.rstrip("/"), cer_intent.rstrip("/"), dry_run, auth, out
        self.sent: List[Dict[str, Any]] = []

    def call(self, method: str, url: str, body: Optional[Dict[str, Any]] = None, expect=(200, 201, 204)) -> Any:
        self.sent.append({"method": method, "url": url, "body": body})
        if self.dry_run:
            self.out(f"  {method} {url}" + (f"  ({len(json.dumps(body))} bytes)" if body else ""))
            return {}
        resp = requests.request(method, url, json=body, auth=self.auth, timeout=60)
        if resp.status_code not in expect:
            raise RuntimeError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    def wait(self, what: str, check: Callable[[], bool], timeout_s: float = 180) -> None:
        if self.dry_run:
            self.out(f"  (wait: {what})")
            return
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if check():
                self.out(f"  {what}: ok")
                return
            time.sleep(3)
        raise TimeoutError(what)

    # ── steps ──────────────────────────────────────────────────────────────
    def onboard(self, topology: Dict[str, Any]) -> None:
        self.out("1. Onboard the topology into TeraFlowSDN")
        self.call("POST", f"{self.tfs}/tfs-api/contexts", {"contexts": topology["contexts"]})
        self.call("POST", f"{self.tfs}/tfs-api/context/admin/topologies", {"topologies": topology["topologies"]})
        self.call("POST", f"{self.tfs}/tfs-api/devices", {"devices": topology["devices"]})
        self.call("POST", f"{self.tfs}/tfs-api/links", {"links": topology["links"]})

    def devices_enabled(self, names: List[str]) -> None:
        self.out("2. Wait for the devices")

        def enabled() -> bool:
            devices = self.call("GET", f"{self.tfs}/tfs-api/devices").get("devices", [])
            status = {d["device_id"]["device_uuid"]["uuid"]: d.get("device_operational_status") for d in devices}
            by_name = {d.get("name"): d.get("device_operational_status") for d in devices}
            return all("ENABLED" in str(status.get(n) or by_name.get(n)) for n in names)
        self.wait("devices enabled", enabled)

    def order_slice(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.out("3. Order the slice from CER-Intent (RFC 9543)")
        res = self.call("POST", f"{self.cer}{RFC9543}", request)
        pipeline = res.get("nsc_pipeline", {})
        if pipeline:
            sel = pipeline["technology_selector"]
            self.out(f"  technology: {sel['technology']} ({sel['reason']}); realization: {pipeline['realizer']['status']}")
        return res

    def service_active(self, slice_id: str) -> None:
        self.out("4. Wait for the TeraFlowSDN service")

        def active() -> bool:
            svc = self.call("GET", f"{self.tfs}/tfs-api/context/admin/service/{slice_id}")
            return "ACTIVE" in str((svc.get("service_status") or {}).get("service_status"))
        self.wait(f"service {slice_id} active", active)

    def radio_view(self, radio: str) -> Optional[Dict[str, Any]]:
        self.out(f"5. RFC 8561 view of {radio}")
        dev = self.call("GET", f"{self.tfs}/tfs-api/device/{radio}")
        for rule in (dev.get("device_config") or {}).get("config_rules", []):
            custom = rule.get("custom") or {}
            if custom.get("resource_key") == "/microwave-radio-link":
                view = custom["resource_value"]
                view = json.loads(view) if isinstance(view, str) else view
                carrier = view["ietf-interfaces:interfaces"]["interface"][0]
                self.out(f"  {carrier['name']}: {json.dumps(carrier.get('ietf-microwave-radio-link:radio-performance', {}))}")
                return view
        return None

    def fade(self, radio_mgmt: str, mbps: float) -> None:
        self.out(f"6. Fade the air link to {mbps} Mbps on the emulator")
        link = self.call("POST", f"http://{radio_mgmt}:8080/emulator/link", {"speed_mbps": mbps, "snr": 9, "mcs": 4})
        self.out(f"  emulator link: {json.dumps(link)}; tc caps the air port at the new speed, and the Ceragon "
                 f"driver reports it as LINK_TOTAL_CAPACITY_GBPS at the next KPI sample")

    def delete_slice(self, slice_id: str) -> None:
        self.out("7. Delete the slice")
        self.call("DELETE", f"{self.cer}{RFC9543}/slice-service={slice_id}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tfs", default=os.getenv("TERAFLOW_URL", "http://localhost:80"))
    parser.add_argument("--cer-intent", default=os.getenv("CER_INTENT_URL", "http://localhost:5000"))
    parser.add_argument("--topology", default=str(HERE / "containerlab" / "tfs-topology.json"))
    parser.add_argument("--slice", default=str(HERE / "containerlab" / "slice-request.json"))
    parser.add_argument("--skip-onboarding", action="store_true")
    parser.add_argument("--fade-mbps", type=float, default=None)
    parser.add_argument("--keep", action="store_true", help="leave the slice in place")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    topology = json.loads(Path(args.topology).read_text())
    request = json.loads(Path(args.slice).read_text())
    demo = Demo(args.tfs, args.cer_intent, args.dry_run,
                auth=(os.getenv("TFS_USERNAME", "admin"), os.getenv("TFS_PASSWORD", "admin")))
    if not args.skip_onboarding:
        demo.onboard(topology)
    demo.devices_enabled([d["device_id"]["device_uuid"]["uuid"] for d in topology["devices"]])
    demo.order_slice(request)
    demo.service_active(request["id"])
    demo.radio_view("radio-a")
    if args.fade_mbps:
        demo.fade("172.20.20.121", args.fade_mbps)
    if not args.keep:
        demo.delete_slice(request["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
