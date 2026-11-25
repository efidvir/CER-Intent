"""
Which standard each exchange of the end-to-end flow speaks
==========================================================
classify() names the interface of one exchange from its endpoints, method and
path, for the flow dashboard's underlay panel.
"""
from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import urlsplit

RFC9543 = {"std": "RFC 9543", "name": "IETF network slice service",
           "ref": "RFC 9543 framework · ietf-network-slice-service YANG", "layer": "slice"}

_RULES = [
    # (predicate on (method, path), label)
    (lambda m, p: p.startswith("/tmf-api/intentManagement/v5"),
     {"std": "TMF921", "name": "TM Forum intent management", "ref": "TMF921 Intent Management API v5 · TM Forum intent ontology",
      "layer": "intent"}),
    (lambda m, p: p.startswith("/3gpp-intent/"),
     {"std": "TS 28.312", "name": "3GPP intent handling", "ref": "3GPP TS 28.312 intent-driven management (IntentHandlingFunction)",
      "layer": "intent"}),
    (lambda m, p: p.startswith("/api/v2/converse"),
     {"std": "Intent API", "name": "operator conversation", "ref": "CER-Intent intent API v2 · 3GPP TS 28.312 intent lifecycle",
      "layer": "intent"}),
    (lambda m, p: p.startswith("/api/v2/intents"),
     {"std": "Intent API", "name": "intent record", "ref": "CER-Intent intent API v2 · 3GPP TS 28.312 intent lifecycle",
      "layer": "intent"}),
    (lambda m, p: p.startswith("/api/v1/intents/") and p.endswith("/approve"),
     {"std": "Intent API", "name": "approval (operator in the loop)",
      "ref": "CER-Intent intent API · 3GPP TS 28.312 intent lifecycle", "layer": "intent"}),
    (lambda m, p: p == "/api/v1/intent" or p.startswith("/api/v1/intents"),
     {"std": "Intent API", "name": "intent submission",
      "ref": "CER-Intent intent API · 3GPP TS 28.312 intent lifecycle", "layer": "intent"}),
    (lambda m, p: "ietf-network-slice-service:" in p, RFC9543),
    (lambda m, p: "ietf-l2vpn-svc:" in p,
     {"std": "RFC 8466", "name": "L2SM · L2VPN service model", "ref": "RFC 8466 over RESTCONF (RFC 8040)",
      "layer": "service"}),
    (lambda m, p: "ietf-l3vpn-svc:" in p,
     {"std": "RFC 8299", "name": "L3SM · L3VPN service model", "ref": "RFC 8299 over RESTCONF (RFC 8040)",
      "layer": "service"}),
    (lambda m, p: "ietf-network:networks" in p,
     {"std": "RFC 8345", "name": "network topology", "ref": "RFC 8345 + RFC 8795 TE bandwidth",
      "layer": "topology"}),
    (lambda m, p: p.startswith("/tfs-api/"),
     {"std": "TFS-API", "name": "TeraFlowSDN NBI", "ref": "ETSI TeraFlowSDN REST NBI (TFS-API)",
      "layer": "controller"}),
    (lambda m, p: p.startswith("/restconf/operations/ietf-netconf:commit"),
     {"std": "RFC 8040", "name": "commit candidate → running", "ref": "RESTCONF RPC · ietf-netconf commit (RFC 6241)",
      "layer": "device"}),
    (lambda m, p: p.startswith("/restconf/ds/ietf-datastores:"),
     {"std": "RFC 8040", "name": "RESTCONF datastore", "ref": "RESTCONF (RFC 8040) on the NMDA candidate datastore (RFC 8527)",
      "layer": "device"}),
    (lambda m, p: p.startswith("/restconf/"),
     {"std": "RFC 8040", "name": "RESTCONF", "ref": "RESTCONF (RFC 8040)", "layer": "device"}),
    (lambda m, p: p.startswith("/api/v1/dti/sync"),
     {"std": "Twin API", "name": "sync twin from the network", "ref": "digital twin interface · ITU-T Y.3090 twin layer",
      "layer": "twin"}),
    (lambda m, p: p.startswith("/api/v1/dti/ceragon/preflight"),
     {"std": "Twin API", "name": "slice pre-flight on NS-3.45", "ref": "digital twin interface · ns-3.45 Ceragon module",
      "layer": "twin"}),
    (lambda m, p: p.startswith("/api/v1/dti/") or p == "/what-if",
     {"std": "Twin API", "name": "digital twin", "ref": "digital twin interface", "layer": "twin"}),
]

_UNKNOWN = {"std": "HTTP", "name": "", "ref": "", "layer": "other"}


def classify(method: str, url: str) -> Dict[str, Any]:
    path = urlsplit(url).path if "://" in url else url.split("?", 1)[0]
    path = re.sub(r"/+$", "", path) or "/"
    for pred, label in _RULES:
        if pred(method.upper(), path):
            return dict(label)
    return dict(_UNKNOWN)
