"""
Ceragon ns-3 Functional Twin Runner
===================================
Runs the ``contrib/ceragon`` ns-3 module (Ceragon portfolio functional twin) on
the remote ns-3 host (default ``efid@cersrv-029``) over SSH.

Flow:
    CER-Intent topology (TFS-synced state)  --tfs_to_ceragon_twin.convert-->  .twin text
    .twin text  --ssh stdin-->  ns3.45-ceragon-twin-default --topology=<file>
    stdout ===CERAGON_TWIN_METRICS_START=== {json} ===CERAGON_TWIN_METRICS_END===  -> dict

Environment:
    NS3_SSH_HOST / NS3_HOST / NS3_USER   remote host (same as the TSN runner)
    NS3_DIR                              ns-3 tree (default /home/efid/ns3-dev)
    CERAGON_TWIN_BINARY                  override the twin executable path
    CERAGON_TWIN_TMPDIR                  remote TMPDIR (default /home/efid/.ceragon_tmp)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("CeragonNs3TwinRunner")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _REPO_ROOT / "ns3_ceragon" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

try:
    from tfs_to_ceragon_twin import convert as _convert_topology  # type: ignore
except Exception:  # pragma: no cover
    _convert_topology = None

METRICS_START = "===CERAGON_TWIN_METRICS_START==="
METRICS_END = "===CERAGON_TWIN_METRICS_END==="
PORTFOLIO_START = "===CERAGON_PORTFOLIO_START==="
PORTFOLIO_END = "===CERAGON_PORTFOLIO_END==="


def _extract(stdout: str, start: str, end: str) -> Optional[Any]:
    if start in stdout and end in stdout:
        return json.loads(stdout.split(start, 1)[1].split(end, 1)[0].strip())
    return None


class CeragonNs3TwinRunner:
    """Execute Ceragon functional-twin scenarios on the remote ns-3 host."""

    def __init__(self, host: Optional[str] = None, ns3_dir: Optional[str] = None,
                 binary: Optional[str] = None):
        default_host = os.getenv("NS3_SSH_HOST", os.getenv("NS3_HOST", "efid@cersrv-029"))
        if "@" not in default_host and default_host not in ("localhost", "127.0.0.1"):
            default_host = f"{os.getenv('NS3_USER', 'efid')}@{default_host}"
        self.host = host or default_host
        self.ns3_dir = ns3_dir or os.getenv("NS3_DIR", "/home/efid/ns3-dev")
        self.binary = binary or os.getenv(
            "CERAGON_TWIN_BINARY", f"{self.ns3_dir}/build/scratch/ns3.45-ceragon-twin-default")
        self.remote_tmp = os.getenv("CERAGON_TWIN_TMPDIR", "/home/efid/.ceragon_tmp")

    # ── topology ───────────────────────────────────────────────────────────
    @staticmethod
    def load_cer_topology(path: Optional[str] = None) -> Dict[str, Any]:
        p = Path(path) if path else _REPO_ROOT / "data" / "topology_state.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def build_twin_text(self, topology: Optional[Dict[str, Any]] = None,
                        rain: Optional[Sequence[float]] = None,
                        flows: Optional[List[str]] = None,
                        events: Optional[List[str]] = None,
                        auto_flows: int = 2) -> str:
        if _convert_topology is None:
            raise RuntimeError("ns3_ceragon/tools/tfs_to_ceragon_twin.py not importable")
        topo = topology if topology is not None else self.load_cer_topology()
        return _convert_topology(topo, rain=tuple(rain) if rain else None, flows=flows or [],
                                 auto_flows=auto_flows, events=events or [])

    # ── execution ──────────────────────────────────────────────────────────
    def _ssh(self, remote_cmd: str, stdin: Optional[str], timeout: int) -> subprocess.CompletedProcess:
        run_fn = subprocess.run
        tpool_exec = None
        if "eventlet" in sys.modules:
            try:
                from eventlet.patcher import original as _ev_original  # type: ignore
                from eventlet import tpool as _ev_tpool  # type: ignore
                run_fn = _ev_original("subprocess").run
                tpool_exec = _ev_tpool.execute
            except Exception:
                pass
        cmd = ["ssh", "-o", "ConnectTimeout=6", "-o", "BatchMode=yes", self.host, remote_cmd]
        kwargs: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": timeout}
        if stdin is not None:
            kwargs["input"] = stdin
        else:
            kwargs["stdin"] = subprocess.DEVNULL
        if tpool_exec is not None:
            return tpool_exec(run_fn, cmd, **kwargs)
        return run_fn(cmd, **kwargs)

    def run(self, twin_text: str, sim_time: float = 7.0, telemetry_interval: float = 0.25,
            timeout: int = 120) -> Dict[str, Any]:
        """Run a .twin scenario and return the parsed JSON report."""
        import base64
        started = time.time()
        run_id = uuid.uuid4().hex[:10]
        remote_file = f"{self.remote_tmp}/twin-{run_id}.twin"
        b64_payload = base64.b64encode(twin_text.encode("utf-8")).decode("ascii")
        args = f"--topology={remote_file} --simTime={sim_time} --telemetryInterval={telemetry_interval}"
        remote_cmd = (f"mkdir -p {self.remote_tmp} && echo '{b64_payload}' | base64 -d > {remote_file} && "
                      f"TMPDIR={self.remote_tmp} {self.binary} {args}; rc=$?; rm -f {remote_file}; exit $rc")
        proc = self._ssh(remote_cmd, None, timeout)
        report = _extract(proc.stdout, METRICS_START, METRICS_END)
        if report is None:
            raise RuntimeError(f"ns-3 twin returned no report (rc={proc.returncode}): "
                               f"{(proc.stderr or proc.stdout)[-800:]}")
        report["execution"] = {
            "engine": "ns-3.45 contrib/ceragon (Live SSH)",
            "host": self.host,
            "binary": self.binary,
            "command": f"{Path(self.binary).name} {args}",
            "wall_clock_ms": round((time.time() - started) * 1000, 1),
            "is_live_remote": True,
            "stderr_tail": (proc.stderr or "")[-400:],
        }
        return report

    def run_from_cer_topology(self, sim_time: float = 10.0, rain: Optional[Sequence[float]] = None,
                              flows: Optional[List[str]] = None, events: Optional[List[str]] = None,
                              auto_flows: int = 2) -> Dict[str, Any]:
        text = self.build_twin_text(rain=rain, flows=flows, events=events, auto_flows=auto_flows)
        report = self.run(text, sim_time=sim_time)
        report["twin_topology"] = text
        return report

    def portfolio(self, timeout: int = 30) -> List[Dict[str, Any]]:
        proc = self._ssh(f"{self.binary} --listPortfolio", None, timeout)
        data = _extract(proc.stdout, PORTFOLIO_START, PORTFOLIO_END)
        if data is None:
            raise RuntimeError(f"portfolio query failed: {(proc.stderr or proc.stdout)[-400:]}")
        return data


if __name__ == "__main__":  # manual smoke test
    logging.basicConfig(level=logging.INFO)
    r = CeragonNs3TwinRunner()
    print(json.dumps(r.portfolio()[:3], indent=2))
