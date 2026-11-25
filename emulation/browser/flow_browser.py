"""
The end-to-end flow in a browser tab
====================================
Pyodide runs CER-Intent, the TeraFlowSDN stand-in (with the TeraFlowSDN fork's
Ceragon service handler and CeragonDriver), two radio emulators and the digital
twin in the page, on the in-process network of emulation/vnet.py: the same code
as `python emulation/flow_stack.py up`, without sockets. The twin replays
NS-3.45 runs recorded with emulation/flow/record_ns3.py.

The page calls handle(method, path, body) for every request it would send to
CER-Intent; the answer is {"status": ..., "body": ...} as JSON.
"""
from __future__ import annotations

import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
CER = "http://localhost:5000"
DASHBOARD_AGENT = {"User-Agent": "flow-dashboard/1.0", "X-Flow-Client": "Operator",
                   "Content-Type": "application/json", "Accept": "application/json"}
_stack = None


def _stub_modules() -> None:
    """Packages CER-Intent imports that have no use without a server: Socket.IO and CORS."""
    sio = types.ModuleType("flask_socketio")

    class SocketIO:  # the dashboard here polls; nothing is pushed
        def __init__(self, *a, **k):
            pass

        def init_app(self, *a, **k):
            pass

        def emit(self, *a, **k):
            pass

        def on(self, *a, **k):
            return lambda fn: fn

        def run(self, *a, **k):
            raise RuntimeError("no server in the browser")

    sio.SocketIO = SocketIO
    sio.emit = lambda *a, **k: None
    sys.modules["flask_socketio"] = sio
    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *a, **k: None
    cors.cross_origin = lambda *a, **k: (lambda fn: fn)
    sys.modules["flask_cors"] = cors


def boot() -> str:
    """Build the stack once. Returns a short JSON summary."""
    global _stack
    if _stack is not None:
        return json.dumps({"ok": True})
    os.chdir(os.path.join(ROOT, "cer-intent"))
    for p in (os.path.join(ROOT, "site"), os.path.join(ROOT, "cer-intent"),
              os.path.join(ROOT, "cer-intent", "emulation"), os.path.join(ROOT, "cer-intent", "ceragon_tfs_adapter")):
        if p not in sys.path:
            sys.path.insert(0, p)
    _stub_modules()
    os.environ.update({
        "CERAGON_TWIN_BINARY": "",
        "NS3_TWIN_MODE": "replay",
        "NS3_TWIN_RECORDINGS": os.path.join(ROOT, "ns3_recordings.json"),
        "TMPDIR": "/tmp",
        "STATE_FILE": "/tmp/cer_intent_state.json",
        "GEMINI_API_KEY": "",
    })
    import logging
    logging.basicConfig(level=logging.WARNING, force=True)   # the page's console stays readable
    import flow_stack  # noqa: E402
    _stack = flow_stack.inprocess({
        "fork_src": os.path.join(ROOT, "teraflowsdn", "src"),
        "twin_src": os.path.join(ROOT, "twin"),
        "ns3_binary": "",
        "recordings": os.path.join(ROOT, "ns3_recordings.json"),
    })
    import tfs_digital_twin_api  # noqa: E402            # its request log would fill the console
    tfs_digital_twin_api.DigitalTwinHttpHandler.log_message = lambda self, *a: None
    logging.getLogger().setLevel(logging.WARNING)       # the page's console stays readable
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.WARNING)
    return json.dumps({"ok": True, "existing": _stack["existing"]["status"]})


def handle(method: str, path: str, body: str = None) -> str:
    import vnet  # noqa: E402
    data = body.encode("utf-8") if body else b""
    try:
        status, headers, raw = vnet.serve(method, CER + path, DASHBOARD_AGENT, data)
    except Exception as exc:  # the page shows it as a failed call
        return json.dumps({"status": 599, "body": {"error": f"{type(exc).__name__}: {exc}"}})
    try:
        parsed = json.loads(raw) if raw else None
    except ValueError:
        parsed = {"text": raw.decode("utf-8", "replace")[:2000]}
    return json.dumps({"status": status, "body": parsed})
