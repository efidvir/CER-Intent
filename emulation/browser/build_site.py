"""
Build the browser copy of the flow dashboard
============================================
A static site that runs the whole flow in the visitor's browser: Pyodide (from
the site's own files), CER-Intent, the TeraFlowSDN stand-in with the fork's
Ceragon handler and driver, the radio emulators and the twin (replaying
recorded NS-3.45 runs). Output:

  index.html            dashboard/intent-flow.html with the Pyodide boot script
  bundle.zip.b64.txt    the Python sources, zipped and base64-encoded
  ns3_recordings.json   recorded NS-3.45 runs
  pyodide/              Pyodide core and the wheels the stack needs

What the bundle leaves out: YANG modules (the schema packages are replaced by
stubs), tests, the LLM client, and lab host names and addresses, which are
replaced by documentation values.

    python emulation/browser/build_site.py --out /tmp/flow-site \\
        --pyodide <dir with pyodide.js, pyodide.asm.*, python_stdlib.zip, pyodide-lock.json, wheels> \\
        --wheels <dir with flask, werkzeug, itsdangerous, blinker wheels>
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

HERE = Path(__file__).resolve().parent
CER = HERE.parents[1]
PYODIDE_PACKAGES = ["pydantic", "requests", "jinja2", "markupsafe", "click"]
PYODIDE_FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]

FORK_FILES = [
    "common/__init__.py", "common/proto/__init__.py", "common/tools/__init__.py",
    "common/tools/object_factory/__init__.py", "common/tools/object_factory/ConfigRule.py",
    "device/__init__.py", "device/service/__init__.py",
    "device/service/driver_api/__init__.py", "device/service/driver_api/_Driver.py",
    "device/service/drivers/ceragon/__init__.py", "device/service/drivers/ceragon/CeragonDriver.py",
    "device/service/drivers/ceragon/Tools.py", "device/service/drivers/ceragon/client.py",
    "device/service/drivers/ceragon/config.py", "device/service/drivers/ceragon/models.py",
    "device/service/drivers/ceragon/portfolio.py", "device/service/drivers/ceragon/routing.py",
    "service/service/service_handlers/ceragon_transport/ConfigRules.py",
]
TWIN_FILES = ["tfs_digital_twin_api.py", "tfs_api_client.py", "rfc8345_import.py",
              "ceragon_ns3_twin_runner.py", "ceragon_preflight.py"]
EMULATION_FILES = ["vnet.py", "radio_emulator.py", "tfs_standin.py", "flow_stack.py",
                   "flow/topology.json", "flow/site_plan.json"]

SCHEMA_STUB = '''"""
YANG schemas are not part of the browser copy of the demo; the driver works
without them (they serve the schema-inspection API only).
"""
from typing import Any, Dict, List, Optional, Tuple

SCHEMAS_DIR = None


def list_schemas() -> List[str]:
    return []


def get_schema_path(module_name: str) -> Optional[Any]:
    return None


def get_schema_content(module_name: str) -> Optional[str]:
    return None


def get_all_schemas() -> Dict[str, str]:
    return {}


def get_schema_metadata(module_name: str) -> Optional[Dict[str, Any]]:
    return None


def list_schema_catalog() -> List[Dict[str, Any]]:
    return []


def get_schemas_for_family(family_or_flavor: str) -> List[str]:
    return []


def validate_schema_closure() -> Tuple[bool, Dict[str, Any]]:
    return True, {"modules": 0, "note": "schemas not bundled"}
'''

# lab hosts, users, directories, addresses and radio names that appear as defaults in the
# sources -> documentation values (written as patterns, so this file names none of them)
SCRUB: List[Tuple[str, str]] = [
    (r"\b[a-z][a-z0-9_]*@[a-z]+srv-\d+\b", "user@ns3-host"),
    (r"\b[a-z]+srv-\d+\b", "ns3-host"),
    (r"/home/(?!user\b|pyodide\b)[a-z][a-z0-9_]*", "/home/user"),
    (r"(NS3_USER['\"],\s*['\"])[a-z][a-z0-9_]*(['\"])", r"\1user\2"),
    (r"192\.168\.\d+\.(\d+)", r"192.0.2.\1"),
    (r"\bctu-(\d+)\b", r"radio-\1"),
]
FORBIDDEN = re.compile(r"\b[a-z]+srv-\d+\b|/home/(?!user\b|pyodide\b)[a-z]|192\.168\.|\bctu-\d+\b")


def scrub(text: str) -> Tuple[str, int]:
    count = 0
    for pattern, repl in SCRUB:
        text, n = re.subn(pattern, repl, text)
        count += n
    return text, count


def files_under(root: Path, patterns: Iterable[str]) -> List[Path]:
    out = []
    for pattern in patterns:
        out += [p for p in root.glob(pattern) if p.is_file() and "__pycache__" not in p.parts]
    return sorted(set(out))


def build_bundle(fork: Path, twin: Path, wheels: Path) -> Tuple[bytes, Dict[str, int]]:
    entries: Dict[str, bytes] = {}

    def add(arcname: str, data: bytes) -> None:
        entries[arcname] = data

    for p in files_under(CER / "cer_intent", ["**/*.py", "**/*.json"]):
        add(f"cer-intent/{p.relative_to(CER)}", p.read_bytes())
    adapter = CER / "ceragon_tfs_adapter" / "ceragon_tfs_adapter"
    for p in files_under(adapter, ["*.py"]):
        if p.name != "cli.py":
            add(f"cer-intent/{p.relative_to(CER)}", p.read_bytes())
    add("cer-intent/ceragon_tfs_adapter/ceragon_tfs_adapter/schemas/__init__.py", SCHEMA_STUB.encode())
    for rel in EMULATION_FILES:
        add(f"cer-intent/emulation/{rel}", (CER / "emulation" / rel).read_bytes())
    add("cer-intent/data/option_a_topology.json", (CER / "data" / "option_a_topology.json").read_bytes())
    for rel in FORK_FILES:
        add(f"teraflowsdn/src/{rel}", (fork / rel).read_bytes())
    add("teraflowsdn/src/device/service/drivers/ceragon/schemas/__init__.py", SCHEMA_STUB.encode())
    for rel in TWIN_FILES:
        add(f"twin/{rel}", (twin / rel).read_bytes())
    add("flow_browser.py", (HERE / "flow_browser.py").read_bytes())
    for whl in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(whl) as z:
            for name in z.namelist():
                if not name.endswith("/"):
                    add(f"site/{name}", z.read(name))

    stats = {"files": 0, "scrubbed": 0}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arcname, data in sorted(entries.items()):
            if arcname.endswith(".yang") or "/yang/" in arcname:
                raise SystemExit(f"refusing to bundle a YANG module: {arcname}")
            if arcname.endswith((".py", ".json", ".txt")) and not arcname.startswith("site/"):
                text, n = scrub(data.decode("utf-8"))
                stats["scrubbed"] += n
                if FORBIDDEN.search(text):
                    raise SystemExit(f"lab-specific text left in {arcname}: {FORBIDDEN.search(text).group(0)}")
                data = text.encode("utf-8")
            z.writestr(arcname, data)
            stats["files"] += 1
    return buf.getvalue(), stats


BOOT = r"""
<script>
// ── The browser copy: the whole stack runs here, in Pyodide ───────────────────
(() => {
  const OWN = new URL("pyodide/", location.href).href;
  const CDN = "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/";
  const PACKAGES = __PACKAGES__;
  let PY = null;
  const steps = [];
  function step(text, state) {
    const ol = document.getElementById("bootSteps");
    if (state === undefined) { steps.push(text); const li = document.createElement("li"); li.className = "run"; li.textContent = "⚙ " + text; ol.appendChild(li); return; }
    const li = ol.lastElementChild; if (!li) return;
    li.className = state; li.textContent = (state === "ok" ? "✓ " : "✖ ") + text;
  }
  function loadScript(src) {
    return new Promise((ok, fail) => { const el = document.createElement("script"); el.src = src; el.onload = ok; el.onerror = () => fail(new Error("could not load " + src)); document.head.appendChild(el); });
  }
  function b64bytes(text) {
    const bin = atob(text.trim()); const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  window.FLOW_HOSTED = true;
  window.FLOW_BOOT = (async () => {
    document.getElementById("boot").classList.add("show");
    const t0 = performance.now();
    let base = OWN;
    try {
      step("Python 3.13 in WebAssembly (Pyodide 0.29.3)");
      try { await loadScript(OWN + "pyodide.js"); } catch (e) { base = CDN; await loadScript(CDN + "pyodide.js"); }
      const py = await loadPyodide({ indexURL: base });
      step(`Python 3.13 in WebAssembly (Pyodide 0.29.3${base === CDN ? ", CDN" : ""})`, "ok");
      step("pydantic, requests, Jinja2");
      await py.loadPackage(PACKAGES, { messageCallback: () => {} });
      step("pydantic, requests, Jinja2", "ok");
      step("CER-Intent, TeraFlowSDN NBI + Ceragon handler and driver, radios, twin");
      const [bundle, rec] = await Promise.all([fetch("bundle.zip.b64.txt").then((r) => r.text()), fetch("ns3_recordings.json").then((r) => r.arrayBuffer())]);
      py.unpackArchive(b64bytes(bundle), "zip", { extractDir: "/home/pyodide/flow" });
      py.FS.writeFile("/home/pyodide/flow/ns3_recordings.json", new Uint8Array(rec));
      step("CER-Intent, TeraFlowSDN NBI + Ceragon handler and driver, radios, twin", "ok");
      step("Starting the stack: radios, TeraFlowSDN, twin sync, CER-Intent, slice backhaul-ran");
      py.runPython("import sys; sys.path.insert(0, '/home/pyodide/flow')");
      PY = py.pyimport("flow_browser");
      const res = JSON.parse(PY.boot());
      step(`Stack running · backhaul-ran in service (HTTP ${res.existing}) · ${((performance.now() - t0) / 1000).toFixed(1)} s`, "ok");
      await new Promise((r) => setTimeout(r, 500));
      document.getElementById("boot").classList.remove("show");
    } catch (e) {
      step(String(e && e.message || e).slice(0, 300), "bad");
      console.error(e);
      throw e;
    }
  })();
  window.FLOW_BACKEND = async (method, path, body) => {
    await window.FLOW_BOOT;
    return JSON.parse(PY.handle(method, path, body === undefined ? null : JSON.stringify(body)));
  };
})();
</script>
"""


def build_page() -> str:
    page = (CER / "dashboard" / "intent-flow.html").read_text(encoding="utf-8")
    boot = BOOT.replace("__PACKAGES__", json.dumps(PYODIDE_PACKAGES))
    marker = '<script>\n"use strict";'
    if marker not in page:
        raise SystemExit("dashboard script marker not found")
    page = page.replace(marker, boot + marker, 1)
    page = page.replace("<title>CER-Intent · Intent to radio, end to end</title>",
                        "<title>CER-Intent end-to-end flow</title>", 1)
    if FORBIDDEN.search(page):
        raise SystemExit("lab-specific text in the page")
    return page


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pyodide", required=True)
    parser.add_argument("--wheels", required=True)
    parser.add_argument("--fork-src", default=os.getenv("TFS_FORK_SRC", str(CER.parent / "teraflowsdn" / "src")))
    parser.add_argument("--twin", default=os.getenv("TWIN_SRC", str(CER.parent / "tfs-ns3-digital-twin")))
    parser.add_argument("--recordings", default=str(CER / "emulation" / "flow" / "ns3_recordings.json"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "pyodide").mkdir(parents=True)
    bundle, stats = build_bundle(Path(args.fork_src), Path(args.twin), Path(args.wheels))
    (out / "bundle.zip.b64.txt").write_text(base64.b64encode(bundle).decode("ascii"), encoding="ascii")
    rec = json.loads(Path(args.recordings).read_text(encoding="utf-8"))
    (out / "ns3_recordings.json").write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    pyo = Path(args.pyodide)
    lock = json.loads((pyo / "pyodide-lock.json").read_text(encoding="utf-8"))
    needed, todo = set(), list(PYODIDE_PACKAGES)
    while todo:
        name = todo.pop().lower().replace("_", "-")
        if name in needed:
            continue
        needed.add(name)
        todo += lock["packages"][name].get("depends", [])
    for f in PYODIDE_FILES + [lock["packages"][n]["file_name"] for n in sorted(needed)]:
        shutil.copy2(pyo / f, out / "pyodide" / f)
    (out / "index.html").write_text(build_page(), encoding="utf-8")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(json.dumps({"out": str(out), "bundle_files": stats["files"], "scrubbed": stats["scrubbed"],
                      "bundle_kb": round(len(bundle) / 1024), "pyodide_packages": sorted(needed),
                      "total_mb": round(total / 1e6, 1)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
