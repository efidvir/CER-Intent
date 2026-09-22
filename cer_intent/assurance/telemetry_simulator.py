"""
Telemetry Simulator
===================
Background thread that emits realistic per-link telemetry at a configurable interval.
Simulates SNR fluctuations, modulation shifts, and traffic load variations.
Pushes updates to clients via Socket.IO.
"""
from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any

from cer_intent.device.registry import DeviceRegistry


class TelemetrySimulator:

    # Stable base values per link
    _BASE = {
        "link-A-B": {"snr": 28.0, "util": 0.65, "mod": "1024QAM",   "tx_pwr": 20.0},
        "link-A-C": {"snr": 22.0, "util": 0.40, "mod": "256QAM",    "tx_pwr": 24.0},
        "link-B-D": {"snr": 25.0, "util": 0.55, "mod": "512QAM",    "tx_pwr": 22.0},
        "link-B-F": {"snr": 20.0, "util": 0.70, "mod": "256QAM",    "tx_pwr": 26.0},
        "link-C-D": {"snr": 24.0, "util": 0.35, "mod": "256QAM",    "tx_pwr": 23.0},
        "link-D-E": {"snr": 30.0, "util": 0.80, "mod": "2048QAM",   "tx_pwr": 18.0},
        "link-E-H": {"snr": 32.0, "util": 0.75, "mod": "2048QAM",   "tx_pwr": 17.0},
        "link-F-G": {"snr": 21.0, "util": 0.50, "mod": "256QAM",    "tx_pwr": 25.0},
        "link-G-H": {"snr": 14.0, "util": 0.30, "mod": "64QAM",     "tx_pwr": 28.0},
        "link-A-F": {"snr": 18.0, "util": 0.45, "mod": "128QAM",    "tx_pwr": 27.0},
    }
    _TICKS = 0

    def __init__(self, registry: DeviceRegistry, socketio, interval: int = 5):
        self._registry = registry
        self._sio = socketio
        self._interval = interval
        self._running = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry-sim")
        self._telemetry: Dict[str, Dict[str, Any]] = {}
        self._alerts: list = []
        self._init_telemetry()

    def _init_telemetry(self):
        for link in self._registry.get_all_links():
            lid = link["id"]
            base = self._BASE.get(lid, {"snr": 20.0, "util": 0.5, "mod": "256QAM", "tx_pwr": 23.0})
            cap = link.get("capacity_gbps", 5.0)
            self._telemetry[lid] = {
                "link_id": lid,
                "src": link["src"],
                "dst": link["dst"],
                "status": link["status"],
                "snr_db": base["snr"],
                "utilization": base["util"],
                "current_modulation": base["mod"],
                "tx_power_dbm": base["tx_pwr"],
                "throughput_gbps": round(base["util"] * cap, 3),
                "capacity_gbps": cap,
                "packet_loss_pct": 0.0,
                "latency_ms": round(5 + random.uniform(0, 2), 2),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    def get_snapshot(self) -> Dict[str, Any]:
        return dict(self._telemetry)

    def refresh_links(self):
        """Re-initialise telemetry when registry topology updates."""
        self._init_telemetry()

    def _loop(self):
        while self._running:
            self._update()
            time.sleep(self._interval)

    def _update(self):
        TelemetrySimulator._TICKS += 1
        t = TelemetrySimulator._TICKS
        updates = {}

        for link in self._registry.get_all_links():
            lid = link["id"]
            base = self._BASE.get(lid, {"snr": 25.0, "util": 0.45, "mod": "512QAM", "tx_pwr": 22.0})
            if lid not in self._telemetry:
                self._init_telemetry()
            tel = self._telemetry.get(lid)
            if not tel:
                continue

            # Simulate slow SNR drift with noise
            snr = base["snr"] + 4 * math.sin(t * 0.15 + hash(lid) % 7) + random.gauss(0, 0.8)
            snr = max(5.0, min(40.0, snr))

            # Utilization: daily cycle pattern + random burst
            util = base["util"] + 0.15 * math.sin(t * 0.08) + random.gauss(0, 0.05)
            util = max(0.01, min(0.99, util))

            # Modulation follows SNR (ACM simulation)
            mod = self._snr_to_modulation(snr)

            # Packet loss higher when SNR is low
            loss = max(0.0, (20 - snr) * 0.05 + random.uniform(0, 0.1)) if snr < 18 else 0.0

            cap = link.get("capacity_gbps", 5.0)
            throughput = round(util * cap, 3)

            tel.update({
                "status": link.get("status", "active"),
                "snr_db": round(snr, 2),
                "utilization": round(util, 3),
                "current_modulation": mod,
                "throughput_gbps": throughput,
                "packet_loss_pct": round(loss, 3),
                "latency_ms": round(2 + (1 - snr / 35) * 8 + random.uniform(0, 0.5), 2),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })
            updates[lid] = tel

        self._telemetry = updates

        # Emit over Socket.IO
        try:
            self._sio.emit("telemetry_update", {
                "links": list(updates.values()),
                "tick": t,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    @staticmethod
    def _snr_to_modulation(snr: float) -> str:
        thresholds = [
            (32, "2048QAM"),
            (29, "1024QAM"),
            (26, "512QAM"),
            (23, "256QAM"),
            (20, "128QAM"),
            (17, "64QAM"),
            (14, "32QAM"),
            (11, "16QAM"),
            (0,  "QPSK"),
        ]
        for threshold, mod in thresholds:
            if snr >= threshold:
                return mod
        return "QPSK"
