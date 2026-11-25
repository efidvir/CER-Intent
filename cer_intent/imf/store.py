"""
Where intent records live
=========================
One JSON file (CER_IMF_STORE, default data/imf_intents.json; ":memory:" keeps
them in memory only) and an append-only audit log next to it
(imf_audit.jsonl): who did what to which intent, with the role they acted in.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from cer_intent.imf.model import IntentRecord, State

ROOT = Path(__file__).resolve().parents[2]


class IntentStore:
    def __init__(self, path: Optional[str] = None):
        path = path or os.getenv("CER_IMF_STORE") or str(ROOT / "data" / "imf_intents.json")
        self.memory = path == ":memory:"
        self.path = None if self.memory else Path(path)
        self.audit_path = None if self.memory else self.path.with_name("imf_audit.jsonl")
        self._lock = threading.RLock()
        self._items: Dict[str, IntentRecord] = {}
        self._audit: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for raw in data.get("intents", []):
                rec = IntentRecord.model_validate(raw)
                self._items[rec.id] = rec
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"intents": [r.model_dump(mode="json") for r in self._items.values()]}, indent=1))
        tmp.replace(self.path)

    def put(self, rec: IntentRecord) -> IntentRecord:
        with self._lock:
            self._items[rec.id] = rec
            self._save()
        return rec

    def get(self, rid: str) -> Optional[IntentRecord]:
        with self._lock:
            rec = self._items.get(rid)
            if rec is None:          # a name works too
                rec = next((r for r in self._items.values() if r.name == rid), None)
            return rec

    def all(self, states: Optional[Iterable[State]] = None, session: Optional[str] = None) -> List[IntentRecord]:
        want = set(states) if states else None
        with self._lock:
            out = [r for r in self._items.values()
                   if (want is None or r.state in want) and (session is None or r.session == session)]
        return sorted(out, key=lambda r: r.created_at)

    def delete(self, rid: str) -> bool:
        with self._lock:
            gone = self._items.pop(rid, None) is not None
            self._save()
            return gone

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._audit.clear()
            self._save()

    def audit(self, event: str, rid: Optional[str], who: str = "system", role: str = "system", **detail: Any) -> Dict[str, Any]:
        entry = {"t": time.time(), "event": event, "intent": rid, "who": who, "role": role, **detail}
        with self._lock:
            self._audit.append(entry)
            if self.audit_path is not None:
                self.audit_path.parent.mkdir(parents=True, exist_ok=True)
                with self.audit_path.open("a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def audit_log(self, rid: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            items = [a for a in self._audit if rid is None or a.get("intent") == rid]
        return items[-limit:]
