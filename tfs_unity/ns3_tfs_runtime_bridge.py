"""
NS-3 <-> TFS Runtime Bidirectional Bridge & Co-Simulation Controller
===================================================================
Orchestrates real-time closed-loop synchronization between NS-3 packet simulation
and physical/simulated Ceragon transport equipment via ETSI TeraFlowSDN.

Features:
1. Telemetry Ingestion Loop:
   - Polls TFS Northbound API for physical Ceragon link status (RSSI, SNR, active MCS).
   - Writes real-time physical link parameters to `ns3_link_state.json` (read by NS-3).
2. Reactive Control Server:
   - Exposes a lightweight HTTP/JSON control endpoint on port 9099.
   - Listens for simulation events from NS-3 (e.g. queue overflow, SLA breach).
   - Dynamically mutates Ceragon hardware parameters via TFS configuration rules
     (Frequency tuning, ATPC power boost, ACM floor hardening, VLAN slicing).
"""
from __future__ import annotations

import argparse
import http.server
import json
import logging
import os
import socketserver
import threading
import time
from typing import Any, Dict, Optional

from tfs_api_client import TfsApiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [NS3-TFS-Bridge]: %(message)s")
logger = logging.getLogger("Bridge")

# Default IPC shared state file for NS-3
DEFAULT_IPC_FILE = "ns3_link_state.json"


class BridgeState:
    """Thread-safe state container shared between polling and control servers."""
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_telemetry: Dict[str, Any] = {}
        self.commands_executed: int = 0
        self.running: bool = True


GLOBAL_STATE = BridgeState()
GLOBAL_CLIENT: Optional[TfsApiClient] = None
TARGET_DEVICE_UUID: str = "f676623c-1a65-54bd-b1e8-279c8a6d8a1c"


class Ns3ControlRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP API allowing NS-3 simulation hooks or external scripts to control Ceragon devices."""

    def do_GET(self):
        """Retrieve current telemetry snapshot."""
        if self.path == "/status" or self.path == "/telemetry":
            with GLOBAL_STATE.lock:
                data = dict(GLOBAL_STATE.latest_telemetry)
            self._send_json(200, {
                "status": "healthy",
                "target_device": TARGET_DEVICE_UUID,
                "telemetry": data,
                "commands_executed": GLOBAL_STATE.commands_executed,
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        """Execute a control action on Ceragon hardware via TFS."""
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)
        try:
            cmd = json.loads(post_body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON payload: {e}"})
            return

        action = cmd.get("action", "").lower()
        dev_uuid = cmd.get("device_uuid", TARGET_DEVICE_UUID)
        logger.info(f"Received NS-3 control command: '{action}' for device '{dev_uuid}'")

        success = False
        msg = ""

        if action == "tune_radio":
            freq = float(cmd.get("frequency_mhz", 64800.0))
            channel = int(cmd.get("channel_id", 4))
            tx_pwr = str(cmd.get("tx_power_control", "auto"))
            mcs = int(cmd.get("target_mcs", 8))
            success = GLOBAL_CLIENT.set_radio_tuning(dev_uuid, freq, channel, tx_pwr, mcs)
            msg = f"Tuned carrier to {freq} MHz (Channel {channel})"

        elif action in ("rain_fade_protect", "harden_acm"):
            min_mcs = int(cmd.get("min_mcs", 2))
            min_mod = str(cmd.get("min_modulation", "QPSK"))
            boost = float(cmd.get("atpc_boost_dbm", 3.0))
            success = GLOBAL_CLIENT.set_acm_floor(dev_uuid, min_mcs, min_mod, boost)
            msg = f"Hardened ACM floor to {min_mod} (MCS {min_mcs}, ATPC +{boost} dBm)"

        elif action == "create_slice":
            s_name = str(cmd.get("slice_name", "slice-uran-6g"))
            vlan = int(cmd.get("vlan_id", 200))
            bw = int(cmd.get("bandwidth_mbps", 1000))
            priority = int(cmd.get("priority", 7))
            success = GLOBAL_CLIENT.set_slice_qos(dev_uuid, s_name, vlan, bw, priority)
            msg = f"Provisioned transport slice '{s_name}' (VLAN {vlan}, {bw} Mbps)"

        else:
            self._send_json(400, {"error": f"Unknown action: {action}. Supported: tune_radio, rain_fade_protect, create_slice"})
            return

        if success:
            with GLOBAL_STATE.lock:
                GLOBAL_STATE.commands_executed += 1
            self._send_json(200, {"status": "success", "action": action, "message": msg})
        else:
            self._send_json(500, {"status": "failed", "action": action, "message": "TFS rejected configuration rule"})

    def _send_json(self, code: int, data: Dict[str, Any]):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress noisy standard HTTP logs
        return


def telemetry_polling_loop(client: TfsApiClient, device_uuid: str, interval_sec: float, ipc_file: str):
    """Background worker that continuously queries physical device telemetry and writes to IPC file."""
    logger.info(f"Starting telemetry polling loop for device {device_uuid} (Interval: {interval_sec}s)...")
    while GLOBAL_STATE.running:
        try:
            telemetry = client.get_device_telemetry(device_uuid)
            with GLOBAL_STATE.lock:
                GLOBAL_STATE.latest_telemetry = telemetry

            # Write to NS-3 IPC file atomically
            temp_file = f"{ipc_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.time(),
                    "device_uuid": device_uuid,
                    "link_parameters": telemetry,
                }, f, indent=2)
            os.replace(temp_file, ipc_file)

        except Exception as e:
            logger.warning(f"Telemetry polling error: {e}")

        time.sleep(interval_sec)


def main():
    parser = argparse.ArgumentParser(description="NS-3 <-> TFS Runtime Bidirectional Bridge")
    parser.add_argument("--tfs-url", default="http://localhost:8088", help="TFS Northbound REST URL (default: http://localhost:8088)")
    parser.add_argument("--device-uuid", default=TARGET_DEVICE_UUID, help="Ceragon device UUID to monitor/control")
    parser.add_argument("--control-port", type=int, default=9099, help="HTTP Control Server Port for NS-3 hooks (default: 9099)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Telemetry polling interval in seconds (default: 1.0)")
    parser.add_argument("--ipc-file", default=DEFAULT_IPC_FILE, help="Path to shared JSON IPC file read by NS-3")
    parser.add_argument("--descriptor-file", help="Path to offline TFS descriptor fallback JSON")
    args = parser.parse_args()

    global GLOBAL_CLIENT, TARGET_DEVICE_UUID
    TARGET_DEVICE_UUID = args.device_uuid

    # Default fallback path if not specified
    fallback = args.descriptor_file
    if not fallback:
        # Check standard CER-Intent data paths
        cand1 = r"c:\CER_Intent\data\6g_transport_tfs_descriptors.json"
        if os.path.exists(cand1):
            fallback = cand1

    GLOBAL_CLIENT = TfsApiClient(rest_url=args.tfs-url if hasattr(args, 'tfs-url') else args.tfs_url, descriptor_fallback_path=fallback)

    ok, msg = GLOBAL_CLIENT.test_connection()
    logger.info(f"TFS Connection Status: {msg}")

    # Start telemetry polling in background thread
    poll_thread = threading.Thread(
        target=telemetry_polling_loop,
        args=(GLOBAL_CLIENT, args.device_uuid, args.poll_interval, args.ipc_file),
        daemon=True,
    )
    poll_thread.start()

    # Start HTTP Control Server for NS-3
    server_address = ("", args.control_port)
    httpd = socketserver.TCPServer(server_address, Ns3ControlRequestHandler)
    logger.info(f"NS-3 Control API listening on http://localhost:{args.control_port}/")
    logger.info(f"IPC link state file updating at: {os.path.abspath(args.ipc_file)}")
    logger.info("Ready to receive NS-3 simulation events. Press Ctrl+C to terminate.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down bridge...")
        GLOBAL_STATE.running = False
        httpd.shutdown()
        logger.info("Bridge stopped cleanly.")


if __name__ == "__main__":
    main()
