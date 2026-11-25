"""
Probes for a deployment
=======================
  /healthz   the process answers (liveness)
  /readyz    ready to serve (readiness): the data directory is writable and the intent
             manager is up. TeraFlowSDN and the twin are reported too; they make the
             service unready only when listed in CER_READY_REQUIRE ("teraflow,twin"),
             so the studio stays reachable to explain an outage.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import requests
from flask import Blueprint, jsonify

import cer_intent

ops_bp = Blueprint("ops", __name__)
STARTED = time.time()
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_lock = threading.Lock()


def data_dir() -> Path:
    from cer_intent.imf.store import ROOT
    store = os.getenv("CER_IMF_STORE")
    return Path(store).parent if store and store != ":memory:" else ROOT / "data"


def _probe(name: str, url: str, ttl: float = 10.0) -> Dict[str, Any]:
    """GET url with a short timeout; cached for ttl seconds so probes do not hammer a dependency."""
    now = time.time()
    with _lock:
        hit = _cache.get(name)
        if hit and now - hit[0] < ttl:
            return hit[1]
    t0 = time.time()
    try:
        r = requests.get(url, timeout=float(os.getenv("CER_READY_TIMEOUT_S", "2")), headers={"X-Flow-Quiet": "1"})
        out = {"ok": r.status_code < 500, "status": r.status_code}
    except requests.RequestException as e:
        out = {"ok": False, "error": e.__class__.__name__}
    out.update({"url": url, "ms": round((time.time() - t0) * 1000)})
    with _lock:
        _cache[name] = (now, out)
    return out


@ops_bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "version": cer_intent.__version__, "uptime_s": round(time.time() - STARTED)})


@ops_bp.get("/readyz")
def readyz():
    checks: Dict[str, Any] = {}
    d = data_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d, prefix=".ready-", delete=True):
            pass
        checks["data"] = {"ok": True, "path": str(d)}
    except OSError as e:
        checks["data"] = {"ok": False, "path": str(d), "error": str(e)}
    try:
        from cer_intent.imf.api import manager
        m = manager()
        checks["intent_manager"] = {"ok": True, "intents": len(m.store.all()), "auto_approval": m.policy.auto.enabled}
    except Exception as e:  # pylint: disable=broad-except
        checks["intent_manager"] = {"ok": False, "error": str(e)[:200]}
    tfs = os.getenv("TERAFLOW_URL", "").rstrip("/")
    if tfs and os.getenv("ADAPTER_BACKEND", "teraflow") == "teraflow":
        checks["teraflow"] = _probe("teraflow", f"{tfs}/tfs-api/contexts")
    twin = os.getenv("TWIN_URL", "").rstrip("/")
    if twin and os.getenv("CER_IMF_TWIN", "1") not in ("0", "false", "off"):
        checks["twin"] = _probe("twin", f"{twin}/healthz")
    required = {"data", "intent_manager"} | {x.strip() for x in os.getenv("CER_READY_REQUIRE", "").split(",") if x.strip()}
    ready = all(checks.get(k, {"ok": False})["ok"] for k in required)
    return jsonify({"ready": ready, "version": cer_intent.__version__, "checks": checks,
                    "required": sorted(required)}), (200 if ready else 503)
