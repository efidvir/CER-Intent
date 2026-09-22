"""
CER-Intent: 6G Transport Domain Intent Management System
=========================================================
PoC entry point. Starts the Flask API server with SocketIO,
the telemetry simulator, and the closed-loop reconciler.
"""
try:
    import eventlet
    eventlet.monkey_patch()
except Exception:
    pass

import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)

from cer_intent.api.server import create_app, socketio
from cer_intent.assurance.telemetry_simulator import TelemetrySimulator
from cer_intent.assurance.reconciler import IntentReconciler
from cer_intent.device.registry import DeviceRegistry
from cer_intent.assurance.audit_log import AuditLog


def main():
    """Launch the CER-Intent system."""
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    # Initialise shared singletons
    registry = DeviceRegistry()
    audit_log = AuditLog(os.getenv("AUDIT_LOG_FILE", "data/audit_log.jsonl"))

    # Build Flask app
    app = create_app(registry=registry, audit_log=audit_log)

    # Start telemetry simulator (background thread)
    telemetry_sim = TelemetrySimulator(
        registry=registry,
        socketio=socketio,
        interval=int(os.getenv("TELEMETRY_INTERVAL_SECONDS", 5)),
    )
    app.config["telemetry_sim"] = telemetry_sim
    telemetry_sim.start()

    # Start closed-loop reconciler (background thread)
    reconciler = IntentReconciler(
        registry=registry,
        audit_log=audit_log,
        socketio=socketio,
        interval=int(os.getenv("RECONCILE_INTERVAL_SECONDS", 10)),
    )
    # Wire shared references
    reconciler.set_intents(app.config["intent_store"])
    reconciler.set_telemetry(telemetry_sim._telemetry)
    reconciler.start()

    sep = "=" * 60
    print(f"\n{sep}")
    print("  CER-Intent -- 6G Transport Intent Management PoC")
    print(sep)
    print(f"  Dashboard : http://localhost:{port}/")
    print(f"  API       : http://localhost:{port}/api/v1/")
    print(f"  Topology  : http://localhost:{port}/api/v1/topology")
    print(f"{sep}\n")

    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
