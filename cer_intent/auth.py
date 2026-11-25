"""
Who is acting
=============
Two modes, chosen with CER_AUTH:

  headers (default)  X-User and X-Role are taken as sent. Suits a lab behind its own access
                     control, or a deployment whose identity-aware proxy sets these headers
                     (and strips any a client sends).

  token              Each person or system has a token, listed in CER_AUTH_TOKENS_FILE
                     (YAML or JSON), or inline in CER_AUTH_TOKENS (JSON):

                         - user: ann
                           role: admin
                           token_sha256: 9f86d0...      # sha256 of the token (preferred)
                         - user: mcp-agent
                           role: viewer
                           token: "..."                 # or the token itself

                     A request proves who it is with "Authorization: Bearer <token>", or with
                     the session cookie that /login sets (so every dashboard works once signed
                     in). The role comes from the token; X-User and X-Role are ignored.
                     Writing (POST, PUT, PATCH, DELETE) needs a token: on the intent manager's
                     interfaces any role (a viewer may ask and file, the manager decides who may
                     approve), elsewhere a role that may act (operator, approver, admin).
                     Reading stays open unless CER_AUTH_OPEN_READ=0; probes (/healthz,
                     /readyz) are always open.

Session cookies are signed with CER_SECRET_KEY (random per start when unset: everyone signs
in again after a restart). Set CER_COOKIE_SECURE=1 when the API is served over HTTPS.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, g, jsonify, redirect, request, session

logger = logging.getLogger(__name__)

ROLES = ("viewer", "operator", "approver", "admin")
ACTING = ("operator", "approver", "admin")
WRITES = ("POST", "PUT", "PATCH", "DELETE")
OPEN_PATHS = ("/healthz", "/readyz", "/login", "/logout", "/api/v2/whoami")
SAFE_POSTS = ("/api/v2/read",)                       # a POST that only reads (the reading preview)
IMF_PATHS = ("/api/v2/", "/tmf-api/intentManagement/", "/3gpp-intent/")   # the intent manager checks roles itself
INTERNAL = "cer.internal"            # set on in-process calls (the intent manager calling /api/v1)


def mode() -> str:
    return (os.getenv("CER_AUTH", "headers") or "headers").strip().lower()


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_tokens() -> Dict[str, Dict[str, str]]:
    """sha256(token) -> {"user", "role"}; entries with an unknown role or no token are left out (and logged)."""
    raw: Any = None
    path = os.getenv("CER_AUTH_TOKENS_FILE")
    if path:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            logger.error("auth: cannot read the tokens file %s (%s); nobody can sign in", path, e.__class__.__name__)
            return {}
        try:
            raw = json.loads(text)
        except ValueError:
            import yaml
            raw = yaml.safe_load(text)
    elif os.getenv("CER_AUTH_TOKENS"):
        raw = json.loads(os.environ["CER_AUTH_TOKENS"])
    if isinstance(raw, dict):
        raw = raw.get("tokens", [])
    out: Dict[str, Dict[str, str]] = {}
    for i, entry in enumerate(raw or []):
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", "")).lower()
        digest = str(entry.get("token_sha256") or "").lower() or (_sha(str(entry["token"])) if entry.get("token") else "")
        if role not in ROLES or not digest or not entry.get("user"):
            logger.warning("auth: token entry %d left out (needs user, a role of %s, and token or token_sha256)", i, ROLES)
            continue
        out[digest] = {"user": str(entry["user"]), "role": role}
    return out


class Auth:
    def __init__(self, tokens: Optional[Dict[str, Dict[str, str]]] = None):
        self.mode = mode()
        self.tokens = tokens if tokens is not None else (load_tokens() if self.mode == "token" else {})
        self.open_read = os.getenv("CER_AUTH_OPEN_READ", "1").strip().lower() not in ("0", "false", "no", "off")
        if self.mode == "token" and not self.tokens:
            logger.warning("auth: CER_AUTH=token but no tokens are configured; nothing can change state")

    def lookup(self, token: Optional[str]) -> Optional[Dict[str, str]]:
        if not token:
            return None
        digest = _sha(token.strip())
        for known, who in self.tokens.items():
            if hmac.compare_digest(known, digest):
                return who
        return None

    def identity(self) -> Optional[Dict[str, str]]:
        """Who this request is, in token mode: the bearer token, else the signed session."""
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return self.lookup(header[7:])
        digest = session.get("tok")
        if digest and digest in self.tokens:
            return self.tokens[digest]
        return None


def who(default_user: str = "operator", default_role: str = "operator") -> Tuple[str, str]:
    """The acting user and role for this request (both modes)."""
    if mode() == "token":
        ident = getattr(g, "identity", None)
        if ident:
            return ident["user"], ident["role"]
        return "anonymous", "viewer"
    body = request.get_json(silent=True) if request.is_json else None
    body = body if isinstance(body, dict) else {}
    return (request.headers.get("X-User") or body.get("who") or default_user,
            (request.headers.get("X-Role") or body.get("role") or default_role).lower())


LOGIN_PAGE = """<!doctype html><meta charset="utf-8"><title>CER-Intent · sign in</title>
<style>body{font:14px system-ui,sans-serif;background:#0b1220;color:#e2e8f0;display:grid;place-items:center;height:100vh;margin:0}
form{background:#111a2e;border:1px solid #2a3a5c;border-radius:12px;padding:22px;width:340px}
input{width:100%;box-sizing:border-box;margin:10px 0;padding:8px;border-radius:7px;border:1px solid #2a3a5c;background:#0b1220;color:#e2e8f0}
button{padding:8px 14px;border-radius:7px;border:0;background:#0ea5e9;color:#fff;cursor:pointer}.e{color:#f59e0b}</style>
<form method="post"><b>CER-Intent</b><div style="color:#94a3b8;margin-top:4px">Sign in with your access token.</div>
<input type="password" name="token" placeholder="token" autofocus><input type="hidden" name="next" value="{next}">
<div class="e">{error}</div><button>Sign in</button></form>"""


def _safe_next(target: Optional[str]) -> str:
    target = target or "/"
    return target if target.startswith("/") and not target.startswith("//") else "/"


def install(app: Flask) -> Auth:
    """Sign-in routes, the session cookie and the check on every request."""
    auth = Auth()
    app.extensions["cer_auth"] = auth
    app.secret_key = os.getenv("CER_SECRET_KEY") or app.secret_key or secrets.token_hex(32)
    app.config.update(PERMANENT_SESSION_LIFETIME=timedelta(hours=float(os.getenv("CER_SESSION_HOURS", "12"))),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      SESSION_COOKIE_SECURE=os.getenv("CER_COOKIE_SECURE", "0").lower() in ("1", "true", "yes"),
                      SESSION_COOKIE_NAME="cer_session")

    @app.before_request
    def _check():
        g.identity = None
        if auth.mode != "token" or request.environ.get(INTERNAL) or request.method == "OPTIONS":
            return None
        g.identity = auth.identity()
        if request.path in OPEN_PATHS:
            return None
        if request.method in WRITES and request.path not in SAFE_POSTS:
            if g.identity is None:
                return jsonify({"error": "sign in first: Authorization: Bearer <token>, or /login"}), 401
            if g.identity["role"] not in ACTING and not request.path.startswith(IMF_PATHS):
                return jsonify({"error": f"the {g.identity['role']} role cannot change anything"}), 403
            return None
        if not auth.open_read and g.identity is None and request.path.startswith(("/api/", "/restconf/", "/tmf-api/", "/3gpp-intent/")):
            return jsonify({"error": "sign in first: Authorization: Bearer <token>, or /login"}), 401
        return None

    @app.get("/api/v2/whoami")
    def _whoami():
        if auth.mode != "token":
            u, r = who()
            return jsonify({"auth": "headers", "user": u, "role": r, "signed_in": False})
        ident = g.get("identity")
        return jsonify({"auth": "token", "signed_in": bool(ident), "user": (ident or {}).get("user"),
                        "role": (ident or {}).get("role", "viewer"), "open_read": auth.open_read})

    @app.route("/login", methods=["GET", "POST"])
    def _login():
        nxt = _safe_next(request.values.get("next"))
        if auth.mode != "token":
            return redirect(nxt)
        if request.method == "GET":
            return LOGIN_PAGE.replace("{next}", nxt).replace("{error}", "")
        token = (request.get_json(silent=True) or {}).get("token") if request.is_json else request.form.get("token")
        ident = auth.lookup(token)
        if ident is None:
            if request.is_json:
                return jsonify({"error": "unknown token"}), 401
            return LOGIN_PAGE.replace("{next}", nxt).replace("{error}", "Unknown token."), 401
        session.clear()
        session["tok"] = _sha(token.strip())
        session.permanent = True
        logger.info("auth: %s signed in (%s)", ident["user"], ident["role"])
        return jsonify({"user": ident["user"], "role": ident["role"]}) if request.is_json else redirect(nxt)

    @app.post("/logout")
    def _logout():
        session.clear()
        return jsonify({"signed_in": False})

    return auth


def tokens_summary(auth: Auth) -> List[Dict[str, str]]:
    return [{"user": v["user"], "role": v["role"]} for v in auth.tokens.values()]
