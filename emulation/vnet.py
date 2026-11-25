"""
In-process network for the end-to-end flow
==========================================
Runs CER-Intent, the TeraFlowSDN stand-in, the radio emulators and the digital
twin in one Python process, talking HTTP to each other without sockets: a
request made with the requests library to a registered host:port is served by
the WSGI application or the http.server handler registered there. The
components' own code is unchanged; it builds the same requests and parses the
same responses as over a real network.

Used by the end-to-end tests and by the browser copy of the demo, which has no
sockets.

    from emulation import vnet
    vnet.install()
    vnet.add_wsgi("localhost", 5000, flask_app)
    vnet.add_handler("127.0.0.1", 8101, RadioHandler)
"""
from __future__ import annotations

import io
import threading
import types
from http.client import responses as _REASONS
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

_LOCAL = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_services: Dict[Tuple[str, int], Callable[[str, str, Dict[str, str], bytes], Tuple[int, Dict[str, str], bytes]]] = {}
_lock = threading.RLock()


def _norm(host: str) -> str:
    host = (host or "").lower()
    return "localhost" if host in _LOCAL else host


def add_wsgi(host: str, port: int, app: Any) -> None:
    """Serve a WSGI application (Flask, ...) at host:port."""
    from werkzeug.test import EnvironBuilder, run_wsgi_app

    def call(method: str, target: str, headers: Dict[str, str], body: bytes):
        path, _, query = target.partition("?")
        hdrs = {k: v for k, v in headers.items() if k.lower() not in ("content-length", "host")}
        builder = EnvironBuilder(method=method, path=path, query_string=query, headers=hdrs,
                                 data=body or None, base_url=f"http://{host}:{port}")
        try:
            environ = builder.get_environ()
        finally:
            builder.close()
        app_iter, status, out_headers = run_wsgi_app(app, environ, buffered=True)
        try:
            data = b"".join(app_iter)
        finally:
            close = getattr(app_iter, "close", None)
            if close:
                close()
        return int(str(status).split(" ", 1)[0]), dict(out_headers.items()), data

    with _lock:
        _services[(_norm(host), int(port))] = call


def add_handler(host: str, port: int, handler_cls: type) -> None:
    """Serve a http.server BaseHTTPRequestHandler subclass at host:port."""

    def call(method: str, target: str, headers: Dict[str, str], body: bytes):
        head = [f"{method} {target} HTTP/1.1", f"Host: {host}:{port}"]
        head += [f"{k}: {v}" for k, v in headers.items() if k.lower() not in ("content-length", "host", "connection")]
        head.append(f"Content-Length: {len(body or b'')}")
        head.append("Connection: close")
        raw = ("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + (body or b"")
        handler = handler_cls.__new__(handler_cls)
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.client_address = ("127.0.0.1", 0)
        handler.server = types.SimpleNamespace(server_name="vnet", server_port=port, server_address=(host, port))
        handler.request = None
        handler.close_connection = True
        handler.handle_one_request()
        return _parse_response(handler.wfile.getvalue())

    with _lock:
        _services[(_norm(host), int(port))] = call


def remove(host: str, port: int) -> None:
    with _lock:
        _services.pop((_norm(host), int(port)), None)


def clear() -> None:
    with _lock:
        _services.clear()


def _parse_response(raw: bytes) -> Tuple[int, Dict[str, str], bytes]:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ", 2)[1])
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    length = headers.get("Content-Length")
    if length is not None and length.isdigit():
        body = body[: int(length)]
    return status, headers, body


def serve(method: str, url: str, headers: Optional[Dict[str, str]] = None,
          body: bytes = b"") -> Tuple[int, Dict[str, str], bytes]:
    """One exchange on the virtual network (also what the browser page calls)."""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    with _lock:
        call = _services.get((_norm(parts.hostname or ""), port))
    if call is None:
        raise ConnectionRefusedError(f"nothing listens on {parts.hostname}:{port} in the virtual network")
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return call(method.upper(), target, dict(headers or {}), body or b"")


_original_send = None


def _registered(url: str) -> bool:
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    with _lock:
        return (_norm(parts.hostname or ""), port) in _services


def install(strict: bool = False) -> None:
    """
    Route the requests library's HTTP adapter through the virtual network (once).
    Requests to addresses nobody registered go to the real network, unless strict.
    """
    global _original_send
    import requests
    from requests.adapters import HTTPAdapter
    from requests.structures import CaseInsensitiveDict
    from requests.utils import get_encoding_from_headers

    if getattr(HTTPAdapter.send, "_vnet", False):
        return
    _original_send = HTTPAdapter.send

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):  # noqa: ANN001
        if not strict and not _registered(request.url):
            return _original_send(self, request, stream=stream, timeout=timeout, verify=verify, cert=cert,
                                  proxies=proxies)
        body = request.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            status, headers, data = serve(request.method, request.url, dict(request.headers), body or b"")
        except ConnectionRefusedError as exc:
            raise requests.exceptions.ConnectionError(str(exc), request=request) from exc
        resp = requests.Response()
        resp.status_code = status
        resp.reason = _REASONS.get(status, "")
        resp.headers = CaseInsensitiveDict(headers)
        resp.encoding = get_encoding_from_headers(resp.headers)
        resp._content = data
        resp._content_consumed = True
        resp.raw = io.BytesIO(data)
        resp.url = request.url
        resp.request = request
        resp.connection = self
        return resp

    send._vnet = True
    HTTPAdapter.send = send


def uninstall() -> None:
    """Give the requests library its own HTTP adapter back."""
    global _original_send
    from requests.adapters import HTTPAdapter
    if _original_send is not None:
        HTTPAdapter.send = _original_send
        _original_send = None
