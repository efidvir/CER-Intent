"""
Build the hosted copy of the flow dashboard: a live session, replayed
=====================================================================
The dashboard page with a backend that answers from a session recorded on the
live stack (record_session.py): every answer, every exchange on the wire and
the time each call took are the live stack's, served again in the same order
for the same example intent from the same state. Free text is not served:
for any intent, run the stack (`python emulation/flow_stack.py up`) or the
in-browser build (build_site.py).

    python emulation/browser/build_replay.py --session emulation/browser/flow_session.json --out /tmp/flow-replay
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CER = HERE.parents[1]
FORBIDDEN = re.compile(r"\b[a-z]+srv-\d+\b|/home/(?!user\b|pyodide\b)[a-z]|192\.168\.|\bctu-\d+\b"
                       r"|password\\?\"\s*:\s*\\?\"[^•\"\\]")      # an unmasked password

REPLAY = r"""
<script>
// ── Hosted copy: a session recorded on the live stack, served call for call ────
(() => {
  const RFC9543 = "/restconf/data/ietf-network-slice-service:network-slice-services";
  const MAX_CALL_S = 15;
  let S = null, state = "", active = null, seq = 0;
  const pending = [], released = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  window.FLOW_REPLAY = "loading";
  window.FLOW_BOOT = fetch("flow_session.json").then((r) => r.json()).then((s) => {
    S = s; window.FLOW_REPLAY = `recorded ${s.recorded_at}`;
  });
  function release() {
    const now = Date.now();
    for (let i = pending.length - 1; i >= 0; i--) {
      if (pending[i].release <= now) { released.push(pending[i]); pending.splice(i, 1); }
    }
    released.sort((a, b) => a.t - b.t);
  }
  async function play(step) {
    const start = Date.now();
    const scale = step.duration > MAX_CALL_S ? MAX_CALL_S / step.duration : 1;
    for (const e of step.wire) {
      const rel = Math.max(0, (e.t - step.t0) * scale);
      pending.push({ ...e, id: "r" + (++seq), t: start / 1000 + rel, release: start + (rel + (e.ms || 0) / 1000 * scale) * 1000 });
    }
    await sleep(Math.min(step.duration, MAX_CALL_S) * 1000);
    if (/\/approve$/.test(step.path) && step.status === 200) state = active.after;
    active.idx += 1;
    if (active.idx >= active.steps.length) { state = active.after; active = null; }
    return { status: step.status, body: step.body };
  }
  function notRecorded(text) {
    return { status: 400, body: { error: text, status: "not recorded" } };
  }
  window.FLOW_BACKEND = async (method, path, body) => {
    await window.FLOW_BOOT;
    if (method === "GET" && path.startsWith("/api/v1/flow/status")) return { status: 200, body: S.states[state] || S.states[""] };
    if (method === "GET" && path.startsWith("/api/v1/flow/wire")) {
      release();
      const m = /since=r:(\d+)/.exec(path);
      const from = m ? Number(m[1]) : released.length;
      return { status: 200, body: { cursor: `r:${released.length}`, items: released.slice(from) } };
    }
    if (method === "POST" && path === "/api/v1/intent") {
      active = null;
      const text = String((body || {}).intent || "").trim();
      const preset = Object.entries(S.presets).find(([, t]) => t.trim() === text);
      await sleep(250);
      if (!preset) return notRecorded("This copy replays a session recorded on the live stack for the example intents. For any other intent run the stack: python emulation/flow_stack.py up");
      const run = S.runs[`${state}#${preset[0]}`];
      if (!run) return notRecorded("This example was not recorded from the current state.");
      active = { steps: run.steps, idx: 0, after: run.after };
    }
    if (method === "DELETE" && path.startsWith(RFC9543) && (!active || !active.remove)) {
      const rm = S.removes[state];
      if (!rm) return { status: 404, body: { error: "no slice to remove" } };
      active = { steps: rm.steps, idx: 0, after: rm.after, remove: true };
    }
    if (active && active.idx < active.steps.length) {
      const step = active.steps[active.idx];
      if (step.method === method && step.path === path) return play(step);
    }
    await sleep(150);
    return { status: 409, body: { error: "not part of the recorded session" } };
  };
})();
</script>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", default=str(HERE / "flow_session.json"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    session = Path(args.session).read_text(encoding="utf-8")
    page = (CER / "dashboard" / "intent-flow.html").read_text(encoding="utf-8")
    marker = '<script>\n"use strict";'
    if marker not in page:
        raise SystemExit("dashboard script marker not found")
    page = page.replace(marker, REPLAY + marker, 1)
    page = page.replace("<title>CER-Intent · Intent to radio, end to end</title>",
                        "<title>CER-Intent end-to-end flow</title>", 1)
    for name, text in (("index.html", page), ("flow_session.json", session)):
        hit = FORBIDDEN.search(text)
        if hit:
            raise SystemExit(f"{name}: lab-specific or credential text: {hit.group(0)}")
        (out / name).write_text(text, encoding="utf-8")
    data = json.loads(session)
    print(json.dumps({"out": str(out), "runs": len(data["runs"]), "removes": len(data["removes"]),
                      "session_mb": round(len(session) / 1e6, 2), "recorded_at": data["recorded_at"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
