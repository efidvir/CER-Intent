"""
Transport slice controller (RFC 9543) for CER-Intent.

One controller instance serves both the RFC 9543 RESTCONF interface and the
intent pipeline, so slices created either way share one datastore.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

_shared = None
_lock = threading.Lock()


def shared_controller(tfs_client: Optional[Any] = None, **kwargs: Any):
    """The process-wide NetworkSliceController, created on first use."""
    global _shared
    with _lock:
        if _shared is None:
            from cer_intent.nsc.nsc_controller import NetworkSliceController
            _shared = NetworkSliceController(tfs_client=tfs_client, **kwargs)
        elif tfs_client is not None and _shared.tfs_client is None:
            _shared.tfs_client = tfs_client
            _shared.realizer.tfs_client = tfs_client
        return _shared


def reset_shared_controller() -> None:
    """Drop the shared controller (tests, configuration reloads)."""
    global _shared
    with _lock:
        _shared = None
