"""
State Store
===========
Persists device configuration state to a JSON file.
Acts as the source of truth for the dashboard and reconciler.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateStore:
    """Thread-safe JSON state store for device configurations."""

    def __init__(self, path: str = "data/topology_state.json"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("devices", {})
                        data.setdefault("config_history", [])
                        return data
            except json.JSONDecodeError:
                logger.warning("State file corrupt, resetting")
        return {"devices": {}, "config_history": []}

    def _save(self):
        with open(self._path, "w") as f:
            json.dump(self._state, f, indent=2, default=str)

    # ── Device Config ─────────────────────────────────────────────────────────

    def update_device_config(
        self,
        device_id: str,
        config_type: str,
        parameters: Dict[str, Any],
        intent_id: str,
        yang_xml: Optional[str] = None,
    ):
        with self._lock:
            if device_id not in self._state["devices"]:
                self._state["devices"][device_id] = {"configs": {}, "last_updated": None}

            entry = {
                "config_type": config_type,
                "parameters": parameters,
                "intent_id": intent_id,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "yang_xml_snippet": (yang_xml or "")[:500],  # Truncate for storage
            }
            self._state["devices"][device_id]["configs"][config_type] = entry
            self._state["devices"][device_id]["last_updated"] = entry["applied_at"]

            # Append to history (keep last 100)
            self._state["config_history"].append({
                "device_id": device_id,
                **entry,
            })
            if len(self._state["config_history"]) > 100:
                self._state["config_history"] = self._state["config_history"][-100:]

            self._save()

    def get_device_state(self, device_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._state["devices"].get(device_id, {})

    def get_all_device_states(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state["devices"])

    def get_config_history(self, limit: int = 50) -> List[dict]:
        with self._lock:
            return self._state["config_history"][-limit:]

    def clear(self):
        with self._lock:
            self._state = {"devices": {}, "config_history": []}
            self._save()
