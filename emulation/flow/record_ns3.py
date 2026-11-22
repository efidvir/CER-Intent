"""
Record NS-3.45 runs for the browser copy of the flow
====================================================
The browser has no ns-3 build, so its twin replays runs recorded here, on a
machine that has one (NS3_TWIN_MODE=replay). Every run is the real binary on a
scenario the twin itself builds from the stack's network:

  presets   the dashboard's example intents, through the whole flow, in the
            orders a demo can take them (exact replays)
  grid      one or two new slices next to the slice already in service, at
            50 Mbps steps (one slice) and 50, 100, 200 ... 1000 Mbps (two),
            for intents typed by hand (nearest recorded rate, labelled as such)

    CERAGON_TWIN_BINARY=.../ns3.45-ceragon-twin \\
        python emulation/flow/record_ns3.py [--out emulation/flow/ns3_recordings.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent)]

PRESETS = {
    "l2": "Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; "
          "keep the radio link at MCS4 or better",
    "l2-big": "Connect region-a and edge over VLAN 310 with 800 Mbps, at most 10 ms latency and 0.1% loss",
    "l3": "Routed L3VPN slice between region-a 192.0.2.1/30 and edge 198.51.100.1/30 with 50 Mbps "
          "and at most 5 ms latency; keep the radio at MCS6 or better",
}
AGENT = {"User-Agent": "flow-recorder/1.0", "X-Flow-Client": "Operator"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(HERE / "ns3_recordings.json"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--no-grid", action="store_true")
    args = parser.parse_args()
    if not os.getenv("CERAGON_TWIN_BINARY"):
        raise SystemExit("set CERAGON_TWIN_BINARY to the ns3.45-ceragon-twin binary")
    out = Path(args.out).resolve()
    os.environ["NS3_TWIN_RECORD_TO"] = str(out)

    import requests
    import flow_stack
    stack = flow_stack.inprocess()
    cer = stack["urls"]["cer"]
    s = requests.Session()
    s.headers.update(AGENT)
    started = time.time()

    def submit(text: str) -> str:
        r = s.post(f"{cer}/api/v1/intent", json={"intent": text, "source": "recorder"})
        r.raise_for_status()
        iid = r.json()["intent_id"]
        s.post(f"{cer}/api/v1/flow/preview", json={"intent_id": iid}).raise_for_status()
        return iid

    def simulate(iid: str) -> str:
        r = s.post(f"{cer}/api/v1/flow/simulate", json={"intent_id": iid})
        r.raise_for_status()
        return r.json()["preflight"]["verdict"]

    def apply(iid: str) -> None:
        s.post(f"{cer}/api/v1/intents/{iid}/approve", params={"override": "1"}).raise_for_status()

    def remove(slice_id: str) -> None:
        s.delete(f"{cer}/restconf/data/ietf-network-slice-service:network-slice-services/slice-service={slice_id}")

    # presets, in the orders a demo takes them
    ids = {name: submit(text) for name, text in PRESETS.items()}
    for name in PRESETS:
        print(f"  clean      {name:<7} {simulate(ids[name])}")
    apply(ids["l2"])
    for name in ("l2-big", "l3"):
        print(f"  +l2        {name:<7} {simulate(submit(PRESETS[name]))}")
    l3 = submit(PRESETS["l3"])
    simulate(l3)
    apply(l3)
    print(f"  +l2 +l3    l2-big  {simulate(submit(PRESETS['l2-big']))}")
    remove("slice-region-a-edge-300")
    for name in ("l2", "l2-big"):
        print(f"  +l3        {name:<7} {simulate(submit(PRESETS[name]))}")
    remove("slice-region-a-edge")

    if not args.no_grid:
        from ceragon_ns3_twin_runner import CeragonNs3TwinRunner
        import ceragon_preflight as pf
        ndti = stack["ndti"]
        ndti.sync_from_physical()
        devices, links = ndti.topology_shadow["nodes"], ndti.topology_shadow["links"]
        details = {d["uuid"]: ndti.tfs_client.get_device_details(d["uuid"]) for d in devices if d.get("is_ceragon")}
        plan = pf.load_site_plan()
        model = pf.build_model(devices, links, details, plan, start="region-a")
        backhaul = pf.Flow("backhaul-ran", "region-a", "edge", 200.0, pf.EXISTING_DSCP, "existing", "backhaul-ran")
        runner = CeragonNs3TwinRunner()
        jobs = []
        for r in range(50, 1001, 50):
            jobs.append([backhaul, pf.Flow("grid-a", "region-a", "edge", float(r), pf.DEFAULT_SLICE_DSCP, "slice")])
        steps = [50] + list(range(100, 1001, 100))
        for i1, r1 in enumerate(steps):
            for r2 in steps[i1:]:
                jobs.append([backhaul,
                             pf.Flow("grid-a", "region-a", "edge", float(r1), pf.DEFAULT_SLICE_DSCP, "slice"),
                             pf.Flow("grid-b", "region-a", "edge", float(r2), pf.DEFAULT_SLICE_DSCP, "slice")])

        def run(flows):
            text = pf.twin_text(model, flows, plan, "recorded grid point")
            runner.run(text, sim_time=float(plan["sim_time_s"]))
            return [f.rate_mbps for f in flows]

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i, rates in enumerate(pool.map(run, jobs), start=1):
                if i % 10 == 0 or i == len(jobs):
                    print(f"  grid {i}/{len(jobs)}  last: {rates}")

    data = compact(json.loads(out.read_text(encoding="utf-8")))
    out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['runs'])} runs in {out} ({out.stat().st_size / 1e6:.1f} MB, {time.time() - started:.0f} s)")
    return 0


def compact(data: dict) -> dict:
    """Keep what the twin and the dashboard read: every second telemetry sample, no per-carrier detail."""
    for run in data.get("runs", []):
        rep = run["report"]
        for link, points in (rep.get("series") or {}).items():
            rep["series"][link] = points[1::2] if len(points) > 50 else points
        for lk in rep.get("links", []) or []:
            state = lk.pop("state", None) or {}
            carriers = state.get("carriers") or []
            if carriers:
                lk["state"] = {"carriers": [{"modulation": c.get("modulation")} for c in carriers]}
    return data


if __name__ == "__main__":
    sys.exit(main())
