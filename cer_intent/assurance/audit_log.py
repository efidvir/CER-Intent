"""
Audit Log
=========
Append-only log of all system events: intent submissions, translations,
config pushes, state changes, and reconciliation actions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditLog:
    """Thread-safe append-only JSONL audit log."""

    def __init__(self, path: str = "data/audit_log.jsonl"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        # In-memory ring buffer (last 500 events)
        self._buffer: List[dict] = self._load_recent(500)

    def _load_recent(self, n: int) -> List[dict]:
        if not self._path.exists():
            return []
        entries = []
        try:
            with open(self._path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        return entries[-n:]

    def _record(self, event_type: str, data: Dict[str, Any], level: str = "INFO"):
        entry = {
            "event_type": event_type,
            "level": level,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > 500:
                self._buffer = self._buffer[-500:]
            try:
                with open(self._path, "a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
            except Exception as e:
                logger.error(f"Audit log write error: {e}")
        return entry

    # ── Public event methods ──────────────────────────────────────────────────

    def intent_received(self, intent_id: str, intent_type: str, target: str, source: str):
        return self._record("INTENT_RECEIVED", {
            "intent_id": intent_id, "intent_type": intent_type,
            "target": target, "source": source,
        })

    def intent_parsed(self, intent_id: str, raw_input: str, parser: str):
        return self._record("INTENT_PARSED", {
            "intent_id": intent_id,
            "input_preview": raw_input[:120] if raw_input else "",
            "parser": parser,
        })

    def intent_validated(self, intent_id: str, valid: bool, errors: List[str], warnings: List[str]):
        level = "INFO" if valid else "WARN"
        return self._record("INTENT_VALIDATED", {
            "intent_id": intent_id, "valid": valid,
            "errors": errors, "warnings": warnings,
        }, level=level)

    def translation_complete(self, intent_id: str, num_configs: int, explanation: str):
        return self._record("TRANSLATION_COMPLETE", {
            "intent_id": intent_id, "num_configs": num_configs, "explanation": explanation,
        })

    def config_applied(self, intent_id: str, device_id: str, config_type: str,
                       success: bool, message: str, backend: str):
        level = "INFO" if success else "ERROR"
        return self._record("CONFIG_APPLIED", {
            "intent_id": intent_id, "device_id": device_id,
            "config_type": config_type, "success": success,
            "message": message, "backend": backend,
        }, level=level)

    def intent_drift(self, intent_id: str, device_id: str, drift_detail: str):
        return self._record("INTENT_DRIFT", {
            "intent_id": intent_id, "device_id": device_id, "detail": drift_detail,
        }, level="WARN")

    def intent_remediated(self, intent_id: str, device_id: str):
        return self._record("INTENT_REMEDIATED", {
            "intent_id": intent_id, "device_id": device_id,
        })

    def telemetry_alert(self, link_id: str, metric: str, value: float, threshold: float):
        return self._record("TELEMETRY_ALERT", {
            "link_id": link_id, "metric": metric,
            "value": value, "threshold": threshold,
        }, level="WARN")

    def system_event(self, message: str, level: str = "INFO"):
        return self._record("SYSTEM_EVENT", {"message": message}, level=level)

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_recent(self, limit: int = 100, event_type: Optional[str] = None) -> List[dict]:
        with self._lock:
            entries = list(self._buffer)
        if event_type:
            entries = [e for e in entries if e["event_type"] == event_type]
        return entries[-limit:]

    def get_for_intent(self, intent_id: str) -> List[dict]:
        with self._lock:
            return [e for e in self._buffer if e.get("intent_id") == intent_id]
