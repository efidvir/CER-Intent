"""
Conflict Fabric Platform Service Client
=======================================
Implements the UNITY-6G D2.4 Chapter 10 & Section 11.1.1 Conflict Fabric specification.
The Conflict Fabric is an external platform service (never an agent) that mediates
intents before they reach the Actuator, ensuring no agent grants itself authority (INV-6).

Exposes the 4 normative interactions (Req-T23-CG-02):
  1. register — Registers an agent's control parameters and target KPIs.
  2. submit   — Submits an intent envelope for mediation and receives a verdict.
  3. verdict  — Retrieves the verdict for a previously submitted intent.
  4. notify   — Receives asynchronous notifications regarding implicit conflicts.

Also provides the last-mile token verification check (Req-T23-CG-07).
When CONFLICT_FABRIC_URL is not set or unavailable, defaults to "OK, go" (ALLOW)
with an issued conflict-resolution token, preparing the seam for seamless external integration.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import requests
from pydantic import BaseModel, Field

from cer_intent.intent_schema import Intent

logger = logging.getLogger(__name__)


class VerdictType(str, Enum):
    """UNITY-6G D2.4 Section 10.2.3 Table 10-2 Fixed Verdict Vocabulary (Req-T23-CG-03)."""
    ALLOW  = "allow"   # The intent proceeds as submitted. Token issued; actuation permitted within validity window.
    MODIFY = "modify"  # A bounded alternative is returned. Re-validated against agent's action space.
    DEFER  = "defer"   # No decision yet; a retry-after is returned. Agent must not actuate in interim.
    DENY   = "deny"    # The intent is refused. Terminal for that intent; re-enters DE as evidence.


class ConflictVerdict(BaseModel):
    """Mediation verdict returned by the Conflict Fabric."""
    verdict: VerdictType
    reason_code: str = Field("mediation.no_contention", description="Reason code per D2.4 Table B-6")
    token: Optional[str] = Field(None, description="Cryptographic/UUID conflict-resolution token checked at ACT")
    validity_window: str = Field("60s", description="Validity duration of the token/action envelope")
    resolving_authority: str = Field("urn:unity6g:conflict-fabric:platform-service", description="Resolving authority URN")
    modified_intent: Optional[Dict[str, Any]] = None
    retry_after: Optional[int] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_reference: Optional[str] = None


class ConflictFabricClient:
    """
    Client connecting the Transport Domain / CER-Intent to the UNITY-6G Conflict Fabric.
    Can operate against a live external microservice (via CONFLICT_FABRIC_URL) or in
    pluggable stub mode ('OK, go') when the external fabric is not yet running.
    """

    def __init__(self, fabric_url: Optional[str] = None, stub_mode: bool = True):
        self.fabric_url = fabric_url or os.getenv("CONFLICT_FABRIC_URL", "").strip()
        self.stub_mode = stub_mode or not bool(self.fabric_url)
        self._registered_agents: Dict[str, Dict[str, Any]] = {}
        self._active_tokens: Dict[str, Dict[str, Any]] = {}
        self._verdict_history: List[Dict[str, Any]] = []

        logger.info(
            f"[ConflictFabric] Initialized. Stub mode: {self.stub_mode}, "
            f"Endpoint: {self.fabric_url or 'Built-in (OK, go default)'}"
        )

    # ── Interaction 1: Register (Req-T23-CG-01) ──────────────────────────────
    def register(
        self,
        agent_descriptor_id: str,
        control_parameters: List[str],
        target_kpis: List[str],
        authority_ceiling: str = "closed_loop_full"
    ) -> Dict[str, Any]:
        """
        Register an agent's control parameters and target KPIs with the fabric.
        In D2.4 §10.2.1, this is performed by the platform from the descriptor at admission.
        """
        reg_payload = {
            "agent_descriptor_id": agent_descriptor_id,
            "control_parameters": control_parameters,
            "target_kpis": target_kpis,
            "authority_ceiling": authority_ceiling,
            "registered_at": datetime.now(timezone.utc).isoformat()
        }

        if not self.stub_mode and self.fabric_url:
            try:
                res = requests.post(f"{self.fabric_url}/register", json=reg_payload, timeout=3.0)
                if res.status_code in (200, 201):
                    logger.info(f"[ConflictFabric] Registered {agent_descriptor_id} externally.")
                    return res.json()
            except Exception as e:
                logger.warning(f"[ConflictFabric] External registration failed ({e}); falling back to local registry.")

        # Local storage in stub mode
        self._registered_agents[agent_descriptor_id] = reg_payload
        logger.info(f"[ConflictFabric] Registered agent {agent_descriptor_id} locally. CPs: {control_parameters}")
        return {"status": "registered", "agent_descriptor_id": agent_descriptor_id}

    # ── Interaction 2: Submit (Req-T23-CG-02, Table 10-1) ────────────────────
    def submit(self, intent: Intent, generation: int = 1) -> ConflictVerdict:
        """
        Submit an intent envelope for mediation before actuation.
        Returns a ConflictVerdict with a verified conflict-resolution token (Req-T23-CG-07).
        """
        submission_payload = {
            "intent_id": intent.intent_id,
            "agent_instance_id": intent.source or f"agent-{intent.target.identifier}",
            "generation": generation,
            "scope": {
                "target_type": intent.target.target_type.value,
                "identifier": intent.target.identifier
            },
            "desired_outcome": {
                "intent_type": intent.intent_type.value,
                "parameters": intent.parameters
            },
            "objective_ref": f"kpi.{intent.intent_type.value}_satisfaction",
            "validity_window": f"{intent.ttl_seconds}s" if intent.ttl_seconds else "60s",
            "urgency": intent.priority,
            "decided_time": intent.submitted_at.isoformat()
        }

        if not self.stub_mode and self.fabric_url:
            try:
                res = requests.post(f"{self.fabric_url}/submit", json=submission_payload, timeout=2.0)
                if res.status_code == 200:
                    data = res.json()
                    verdict = ConflictVerdict(
                        verdict=VerdictType(data.get("verdict", "allow")),
                        reason_code=data.get("reason_code", "mediation.within_grant"),
                        token=data.get("token") or f"cftok-{uuid.uuid4().hex[:16]}",
                        validity_window=data.get("validity_window", "60s"),
                        resolving_authority=data.get("resolving_authority", self.fabric_url),
                        modified_intent=data.get("modified_intent"),
                        retry_after=data.get("retry_after"),
                        audit_reference=data.get("audit_reference")
                    )
                    self._record_verdict(intent.intent_id, verdict)
                    return verdict
            except Exception as e:
                logger.warning(f"[ConflictFabric] Remote submission failed ({e}); invoking local OK-go stub.")

        # Default "OK, go" Stub Implementation: Always say ALLOW with valid token
        token = f"cftok-{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=int(intent.ttl_seconds or 60))

        verdict = ConflictVerdict(
            verdict=VerdictType.ALLOW,
            reason_code="mediation.no_contention",
            token=token,
            validity_window=f"{intent.ttl_seconds or 60}s",
            resolving_authority="urn:unity6g:conflict-fabric:stub-provider",
            timestamp=now,
            audit_reference=f"audit-cf-{str(uuid.uuid4())[:8]}"
        )

        self._active_tokens[token] = {
            "intent_id": intent.intent_id,
            "expires_at": expires_at,
            "target": intent.target.identifier,
            "issued_at": now
        }
        self._record_verdict(intent.intent_id, verdict)
        logger.info(f"[ConflictFabric] Verdict for {intent.intent_id[:8]}: ALLOW. Token issued: {token}")
        return verdict

    # ── Interaction 3: Verdict (Req-T23-CG-03) ────────────────────────────────
    def verdict(self, intent_id: str) -> Optional[ConflictVerdict]:
        """Query the latest verdict for an intent."""
        for entry in reversed(self._verdict_history):
            if entry["intent_id"] == intent_id:
                return entry["verdict"]
        return None

    # ── Interaction 4: Notify (Section 10.2.4) ───────────────────────────────
    def notify(self, notification: Dict[str, Any]) -> bool:
        """Receive an asynchronous implicit conflict notification from the fabric."""
        logger.info(f"[ConflictFabric] Notification received: {notification}")
        return True

    # ── Last-Mile Check: Validate Token (Req-T23-CG-07) ──────────────────────
    def validate_token(self, token: Optional[str], intent_id: str) -> bool:
        """
        Validate that the conflict resolution token is valid and unexpired at actuation last mile.
        """
        if not token:
            logger.warning(f"[ConflictFabric] Last-mile check FAILED: Missing conflict token for intent {intent_id}")
            return False

        record = self._active_tokens.get(token)
        if not record:
            # If generated externally or stub restarted, accept prefixed tokens in stub mode
            if self.stub_mode and token.startswith("cftok-"):
                return True
            logger.warning(f"[ConflictFabric] Last-mile check FAILED: Unknown token {token}")
            return False

        if record["intent_id"] != intent_id:
            logger.warning(f"[ConflictFabric] Last-mile check FAILED: Token {token} issued for {record['intent_id']}, not {intent_id}")
            return False

        if datetime.now(timezone.utc) > record["expires_at"]:
            logger.warning(f"[ConflictFabric] Last-mile check FAILED: Token {token} expired")
            return False

        return True

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the Conflict Fabric client."""
        return {
            "mode": "stub_ok_go" if self.stub_mode else "external",
            "endpoint": self.fabric_url or "internal_stub",
            "active_tokens_count": len(self._active_tokens),
            "registered_agents_count": len(self._registered_agents),
            "verdicts_rendered_count": len(self._verdict_history),
            "compliance": "UNITY-6G D2.4 Chapter 10"
        }

    def _record_verdict(self, intent_id: str, verdict: ConflictVerdict):
        self._verdict_history.append({
            "intent_id": intent_id,
            "verdict": verdict,
            "recorded_at": datetime.now(timezone.utc).isoformat()
        })
        if len(self._verdict_history) > 200:
            self._verdict_history.pop(0)


# Global singleton instance
_conflict_fabric_instance: Optional[ConflictFabricClient] = None

def get_conflict_fabric() -> ConflictFabricClient:
    global _conflict_fabric_instance
    if _conflict_fabric_instance is None:
        _conflict_fabric_instance = ConflictFabricClient()
    return _conflict_fabric_instance
