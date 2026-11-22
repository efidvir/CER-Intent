"""
CER-Intent's side of the wire
=============================
Records the exchanges CER-Intent takes part in, for the flow dashboard:

  inbound    the operator's calls on CER-Intent's interfaces (intent API,
             RFC 9543 slice service)
  outbound   CER-Intent's own HTTP requests (TeraFlowSDN, the digital twin),
             made with the requests library
  internal   the RFC 9543 request the intent engine hands to the slice
             controller inside this process

Outbound requests are recognised by their User-Agent, so other components
running in the same process (as in the browser copy of the demo) are left out:
requests that still carry the library's default agent are CER-Intent's and are
relabelled with USER_AGENT.
"""
from __future__ import annotations

import collections
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

USER_AGENT = "CER-Intent/1.0"
BODY_LIMIT = 12000


def short(body: Any, limit: int = BODY_LIMIT) -> Any:
    """A body as JSON where it is JSON, trimmed for the log."""
    if body is None or body in (b"", ""):
        return None
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return body[:limit]
    text = json.dumps(body, default=str)
    return body if len(text) <= limit else text[:limit] + "…"


class WireLog:
    def __init__(self, keep: int = 3000) -> None:
        self.lock = threading.Lock()
        self.items: "collections.deque[Dict[str, Any]]" = collections.deque(maxlen=keep)
        self.seq = 0

    def add(self, **entry: Any) -> Dict[str, Any]:
        with self.lock:
            self.seq += 1
            entry["seq"] = self.seq
            entry.setdefault("t", time.time())
            self.items.append(entry)
            return entry

    def since(self, seq: int) -> List[Dict[str, Any]]:
        with self.lock:
            return [e for e in self.items if e["seq"] > seq]

    def clear(self) -> None:
        with self.lock:
            self.items.clear()


LOG = WireLog()


def peer_name(url: str) -> str:
    """The component behind a URL, by the URLs CER-Intent is configured with."""
    base = url.split("?", 1)[0]
    for env, name in (("TERAFLOW_URL", "TeraFlowSDN"), ("TWIN_URL", "Digital twin")):
        target = os.getenv(env, "").rstrip("/")
        if target and base.startswith(target):
            return name
    return urlsplit(url).netloc or url


def _skipped(url: str) -> bool:
    return "/standin/" in url          # the stand-in's own diagnostics


def install() -> None:
    """Record CER-Intent's outbound requests (once per process)."""
    import requests

    if getattr(requests.Session.request, "_cer_intent_tap", False):
        return
    original = requests.Session.request

    def request_(self, method, url, *args, **kwargs):  # noqa: ANN001
        per_request = {str(k).lower(): v for k, v in (kwargs.get("headers") or {}).items()}
        ua = str(per_request.get("user-agent") or self.headers.get("User-Agent", ""))
        if not per_request.get("user-agent") and (ua.startswith("python-requests") or not ua):
            self.headers["User-Agent"] = ua = USER_AGENT
        if ua != USER_AGENT or _skipped(url):
            return original(self, method, url, *args, **kwargs)
        t0 = time.time()
        body = kwargs.get("json")
        if body is None:
            body = kwargs.get("data")
        try:
            resp = original(self, method, url, *args, **kwargs)
        except Exception as exc:
            LOG.add(src="CER-Intent", dst=peer_name(url), method=method.upper(), url=url, status=None, t=t0,
                    ms=round((time.time() - t0) * 1000, 1), req=short(body), res=str(exc), dir="out",
                    transport="http")
            raise
        LOG.add(src="CER-Intent", dst=peer_name(url), method=method.upper(), url=url, status=resp.status_code,
                t=t0, ms=round((time.time() - t0) * 1000, 1), req=short(body), res=short(resp.content),
                dir="out", transport="http")
        return resp

    request_._cer_intent_tap = True
    requests.Session.request = request_


def record_internal(src: str, dst: str, method: str, url: str, req: Any, res: Any, status: int,
                    t0: float) -> None:
    LOG.add(src=src, dst=dst, method=method, url=url, status=status, t=t0,
            ms=round((time.time() - t0) * 1000, 1), req=short(req), res=short(res), dir="internal",
            transport="in-process")


def record_inbound(src: str, method: str, url: str, status: int, req: Any, res: Any, t0: float) -> None:
    LOG.add(src=src, dst="CER-Intent", method=method, url=url, status=status, t=t0,
            ms=round((time.time() - t0) * 1000, 1), req=short(req), res=short(res), dir="in", transport="http")


# The slice controller tells the flow about RFC 9543 requests it handles in this process.
_listeners: List[Callable[..., None]] = []


def on_slice_request(fn: Callable[..., None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def slice_request_handled(kind: str, slice_id: Optional[str], request: Any, response: Any, t0: float) -> None:
    for fn in list(_listeners):
        try:
            fn(kind=kind, slice_id=slice_id, request=request, response=response, t0=t0)
        except Exception:  # a dashboard hook never breaks the controller
            pass
