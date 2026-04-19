"""
Intent Reconciler (Closed-Loop Assurance)
==========================================
Background thread that periodically compares active intents against
current device telemetry/state and re-applies configs if drift is detected.
"""
from __future__ import annotations

import threading
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any

from cer_intent.intent_schema import Intent, IntentStatus, IntentType

logger = logging.getLogger(__name__)

# Drift detection thresholds
DRIFT_THRESHOLDS = {
    "capacity": {"throughput_delta_pct": 0.20},   # > 20% below target
    "modulation": {"snr_degraded_db": 12.0},       # SNR < 12 triggers re-check
    "qos": {"latency_excess_ms": 5.0},             # > 5ms above target
}


class IntentReconciler:
    """Periodically checks that applied intents are still being fulfilled."""

    def __init__(self, registry, audit_log, socketio, interval: int = 10):
        self._registry = registry
        self._audit = audit_log
        self._sio = socketio
        self._interval = interval
        self._running = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="reconciler")
        # Shared intent store (set by API server)
        self._active_intents: Dict[str, Intent] = {}
        self._telemetry_ref: Dict[str, Any] = {}

    def set_intents(self, intents: Dict[str, Intent]):
        self._active_intents = intents

    def set_telemetry(self, telemetry: Dict[str, Any]):
        self._telemetry_ref = telemetry

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._reconcile()
            except Exception as e:
                logger.error(f"Reconciler error: {e}")

    def _reconcile(self):
        applied = [
            i for i in self._active_intents.values()
            if i.status in (IntentStatus.APPLIED, IntentStatus.DRIFT, IntentStatus.REMEDIATED)
        ]
        if not applied:
            return

        drifted = []
        for intent in applied:
            if intent.is_expired():
                intent.status = IntentStatus.EXPIRED
                continue
            drift = self._check_drift(intent)
            if drift:
                drifted.append((intent, drift))

        for intent, drift_msg in drifted:
            logger.warning(f"Drift detected for intent {intent.intent_id[:8]}: {drift_msg}")
            self._audit.intent_drift(
                intent_id=intent.intent_id,
                device_id=intent.target.identifier,
                drift_detail=drift_msg,
            )
            intent.status = IntentStatus.DRIFT

            # Emit drift event to dashboard
            try:
                self._sio.emit("intent_drift", {
                    "intent_id": intent.intent_id,
                    "intent_type": intent.intent_type.value,
                    "target": intent.target.identifier,
                    "drift": drift_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

    def _check_drift(self, intent: Intent) -> str:
        """Return a drift description string, or empty string if OK."""
        ttype = intent.intent_type
        target = intent.target

        # Get telemetry for affected links
        affected_tels = []
        for link_id, tel in self._telemetry_ref.items():
            if target.target_type.value == "all":
                affected_tels.append(tel)
            elif target.target_type.value == "link" and link_id == target.identifier:
                affected_tels.append(tel)
            elif target.target_type.value in ("sector", "node"):
                if tel.get("src") in self._get_sector_nodes(target.identifier) or \
                   tel.get("dst") in self._get_sector_nodes(target.identifier):
                    affected_tels.append(tel)

        if not affected_tels:
            return ""

        if ttype == IntentType.CAPACITY:
            target_gbps = intent.parameters.get("min_throughput_gbps", 0)
            for tel in affected_tels:
                actual = tel.get("throughput_gbps", 0)
                cap = tel.get("capacity_gbps", 1)
                if actual < target_gbps * 0.8 and tel.get("utilization", 1) > 0.9:
                    return f"Throughput {actual:.2f} < target {target_gbps:.2f} Gbps on {tel['link_id']}"

        elif ttype == IntentType.QOS:
            max_lat = intent.parameters.get("max_latency_ms")
            if max_lat:
                for tel in affected_tels:
                    actual_lat = tel.get("latency_ms", 0)
                    if actual_lat > max_lat + DRIFT_THRESHOLDS["qos"]["latency_excess_ms"]:
                        return f"Latency {actual_lat:.1f}ms exceeds target {max_lat}ms on {tel['link_id']}"

        elif ttype == IntentType.MODULATION:
            min_mod = intent.parameters.get("min_modulation", "QPSK")
            for tel in affected_tels:
                if tel.get("snr_db", 30) < DRIFT_THRESHOLDS["modulation"]["snr_degraded_db"]:
                    return (f"SNR {tel['snr_db']:.1f} dB on {tel['link_id']} "
                            f"may not sustain min modulation {min_mod}")

        return ""

    def _get_sector_nodes(self, sector_or_node: str) -> List[str]:
        nodes = self._registry.get_nodes_in_sector(sector_or_node)
        if nodes:
            return [n["id"] for n in nodes]
        node = self._registry.get_node(sector_or_node)
        return [node["id"]] if node else []
