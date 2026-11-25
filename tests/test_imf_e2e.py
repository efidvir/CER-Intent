"""
The intent manager through the whole in-process stack (TeraFlowSDN stand-in with
the fork's Ceragon handler and driver, emulated radios, the twin): the conversation
API, TMF921 v5 and 3GPP TS 28.312, down to the radios' bridges.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORK = Path(os.getenv("TFS_FORK_SRC", str(ROOT.parent / "teraflowsdn" / "src")))
TWIN = Path(os.getenv("TWIN_SRC", str(ROOT.parent / "tfs-ns3-digital-twin")))
RECORDINGS = ROOT / "emulation" / "flow" / "ns3_recordings.json"

pytestmark = pytest.mark.skipif(
    not ((FORK / "device" / "service" / "drivers" / "ceragon").exists()
         and (TWIN / "ceragon_preflight.py").exists() and RECORDINGS.exists()),
    reason="needs the TeraFlowSDN fork and the twin repository next to this one")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("imf")
    env = {**os.environ, "CERAGON_TWIN_BINARY": "", "NS3_TWIN_RECORDINGS": str(RECORDINGS),
           "TFS_FORK_SRC": str(FORK), "TWIN_SRC": str(TWIN), "TMPDIR": str(tmp),
           "STATE_FILE": str(tmp / "state.json"), "PYTHONPATH": str(ROOT)}
    proc = subprocess.run([sys.executable, str(ROOT / "emulation" / "flow_stack.py"), "imf"],
                          capture_output=True, text=True, timeout=600, env=env, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout[proc.stdout.index("{"):])


def test_a_spoken_intent_is_checked_on_the_twin_and_reaches_the_radios(run):
    assert run["deliver"]["state"] == "checked" and run["deliver"]["twin"] == "pass"
    assert run["approve"]["state"] == "active" and run["approve"]["slices"] == ["slice-region-a-edge-300"]
    assert all(len(v) == 2 for v in run["radios"].values())          # the backhaul's bridge and the new one


def test_questions_answers_and_cancel(run):
    assert run["clarify"]["questions"] == ["endpoint[0]"] and run["answer"]["state"] == "checked"
    assert run["cancel"]["state"] == "withdrawn"
    assert "Mbps more fits" in run["headroom"]["reply"] and "backhaul-ran" in run["inventory"]["reply"]
    assert run["scope"]["state"] == "rejected"


def test_tmf921_and_3gpp_intents_are_realized(run):
    assert run["tmf_create"]["type"] == "Intent" and run["tmf_active"] == "active"
    assert run["tmf_report"] == "icm:StateFulfilled"
    assert run["g3_put"]["state"] == "active" and run["g3_report"] == "FULFILLED"
    assert "slice-video" in run["network_slices"]


def test_withdrawing_removes_what_the_intent_made(run):
    assert run["withdraw"] == "withdrawn"
    assert "slice-region-a-edge-300" not in run["slices_after"] and "backhaul-ran" in run["slices_after"]


def test_the_wire_names_each_interface(run):
    stds = Counter(e["std"] for e in run["wire"])
    assert {"Intent API", "TMF921", "TS 28.312", "RFC 9543", "RFC 8466", "TFS-API", "RFC 8040", "Twin API"} <= set(stds)
