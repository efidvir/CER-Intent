"""
Flask API Server
================
REST API + Socket.IO server for CER-Intent.
Serves the web dashboard and exposes the intent management API.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

from cer_intent.intent_schema import (
    Intent, IntentStatus, IntentTarget, IntentType,
    IntentLifecycle3GPP, ServiceDLCState, CustomerFacingService, ResourceFacingService,
    ActuationOutcomeType
)
from cer_intent.governance.conflict_fabric import get_conflict_fabric, VerdictType
from cer_intent.intent_parser import IntentParser
from cer_intent.intent_validator import IntentValidator
from cer_intent.translators import get_translator
from cer_intent.device.adapter import create_adapter
from cer_intent.device.state_store import StateStore
from cer_intent.device.knowledge_base import HardwareKnowledgeBase
from cer_intent.architect.agent import IntentArchitectAgent
from cer_intent.architect.executor import ArchitectExecutor
from cer_intent.api.digital_twin_routes import dt_bp
from cer_intent.api.restconf_routes import restconf_bp

logger = logging.getLogger(__name__)

# Shared SocketIO instance (imported by run.py)
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")

# In-process intent store
_intent_store: Dict[str, Intent] = {}

# Dashboard static files directory
DASHBOARD_DIR = Path(__file__).parent.parent.parent / "dashboard"


def create_app(registry, audit_log) -> Flask:
    app = Flask(__name__, static_folder=None)
    CORS(app)
    socketio.init_app(app)
    app.register_blueprint(dt_bp)
    app.register_blueprint(restconf_bp)

    # One-time init of shared components
    state_store = StateStore(os.getenv("STATE_FILE", "data/topology_state.json"))
    adapter = create_adapter(state_store, registry=registry)
    conflict_fabric = get_conflict_fabric()
    parser = IntentParser()
    validator = IntentValidator(registry=registry)
    
    # Initialize Hardware Knowledge and Architect Agent
    kb = HardwareKnowledgeBase()
    architect = IntentArchitectAgent(registry=registry, state_store=state_store, knowledge_base=kb)
    executor = ArchitectExecutor(registry=registry)

    # Wire intent store and telemetry into reconciler (run.py sets these up after create_app)
    app.config["intent_store"] = _intent_store
    app.config["conflict_fabric"] = conflict_fabric
    app.config["registry"] = registry
    app.config["audit_log"] = audit_log
    app.config["adapter"] = adapter
    app.config["state_store"] = state_store
    app.config["kb"] = kb
    app.config["architect"] = architect
    app.config["executor"] = executor

    # ── Dashboard ─────────────────────────────────────────────────────────────

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_dashboard(path):
        if DASHBOARD_DIR.exists():
            file_path = DASHBOARD_DIR / (path or "index.html")
            if file_path.exists() and file_path.is_file():
                return send_from_directory(str(DASHBOARD_DIR), path or "index.html")
            return send_from_directory(str(DASHBOARD_DIR), "index.html")
        return "<h1>CER-Intent API is running</h1><p>Dashboard not found at dashboard/</p>", 200

    # ── Intent API ────────────────────────────────────────────────────────────

    @app.route("/api/v1/intent", methods=["POST"])
    def submit_intent():
        """Submit a new intent (NL text or structured JSON)."""
        body = request.get_json(silent=True) or {}
        raw_input = body.get("intent") or body.get("raw") or body
        source = body.get("source", "api")

        audit_log.system_event(f"Intent received from {source}")

        try:
            # 1. Parse
            try:
                intent = parser.parse(raw_input, source=source)
            except ValueError as e:
                # E.g. prompt injection, nonsensical string, or entirely absent keyword match
                import uuid
                dummy_intent = Intent(
                    intent_id=str(uuid.uuid4()),
                    intent_type=IntentType.CAPACITY, # Dummy to satisfy schema
                    target=IntentTarget(target_type="all", identifier="all"),
                    parameters={},
                    status=IntentStatus.FAILED,
                    error_message=f"Parsing Failed: {str(e)}",
                    raw_input=str(raw_input)
                )
                _intent_store[dummy_intent.intent_id] = dummy_intent
                _emit_intent_update(dummy_intent)
                return jsonify({
                    **_intent_to_dict(dummy_intent),
                    "status": "failed",
                    "error": str(e)
                }), 400
                
            intent.status = IntentStatus.PARSING
            _intent_store[intent.intent_id] = intent
            audit_log.intent_parsed(intent.intent_id, str(raw_input)[:120], "llm-or-rule")
            _emit_intent_update(intent)

            # 2. Validate
            intent.status = IntentStatus.VALIDATED
            active = list(_intent_store.values())
            validation = validator.validate(intent, active_intents=active)
            audit_log.intent_validated(
                intent.intent_id, validation.valid,
                validation.errors, validation.warnings
            )

            if not validation.valid:
                intent.status = IntentStatus.FAILED
                intent.error_message = "; ".join(validation.errors)
                _emit_intent_update(intent)
                return jsonify({
                    **_intent_to_dict(intent),
                    "status": "rejected",
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                }), 422

            # 3. Architect Reasoning
            intent.status = IntentStatus.VALIDATED
            _emit_intent_update(intent)
            
            # Populate active intents for conflict check
            intent.context_intents = [i.to_dict() for i in _intent_store.values() if i.intent_id != intent.intent_id]
            
            # Fetch current telemetry from simulator (passed via app.config if possible or mock)
            # For PoC, we'll try to get it from the reconciler's reference if available
            telemetry = getattr(app, 'telemetry_snapshot', {})
            
            plan = architect.create_plan(intent, telemetry)
            intent.architect_plan = plan.to_dict()
            audit_log.system_event(f"Architect plan created: {plan.selected_strategy.name if plan.selected_strategy else 'none'}")
            
            # Check for HITL Approval
            always_apply = body.get("always_apply", False)
            if not always_apply:
                intent.status = IntentStatus.AWAITING_APPROVAL
                _emit_intent_update(intent)
                audit_log.system_event(f"Intent {intent.intent_id[:8]} paused for manual approval.")
                return jsonify({
                    **_intent_to_dict(intent),
                    "status": "awaiting_approval",
                    "plan": intent.architect_plan
                }), 202

            # 4. Translate / Architect Execution
            intent.status = IntentStatus.TRANSLATING
            intent.state_3gpp = IntentLifecycle3GPP.COMMISSIONING
            _emit_intent_update(intent)
            
            target_devices = registry.get_devices_for_target(
                intent.target.target_type.value,
                intent.target.identifier,
            )
            # Enrich with state-store data for 'already applied' detection
            device_states = state_store.get_all_device_states()
            for dev in target_devices:
                dev["applied_configs"] = device_states.get(dev["id"], {}).get("configs", {})
            if not target_devices:
                target_devices = registry.get_devices_for_target("all", "all")
                validation.warnings.append(f"Target '{intent.target.identifier}' not found; applying to all devices")

            # Try Architect Execution first
            # Bypass architect if direct/legacy is requested or custom frequencies are specified
            bypass_architect = (
                body.get("direct_translation") or 
                body.get("legacy_translation") or
                "tx_frequency" in intent.parameters or
                "rx_frequency" in intent.parameters
            )
            if plan and plan.selected_strategy and not bypass_architect:
                audit_log.system_event(f"Executing architect strategy: {plan.selected_strategy.name}")
                translation = executor.execute_plan(plan, intent)
            else:
                # Fallback to direct translation
                audit_log.system_event(f"Falling back to legacy translation for intent {intent.intent_id[:8]}")
                translator = get_translator(intent.intent_type)
                translation = translator.translate(intent, target_devices)

            audit_log.translation_complete(
                intent.intent_id, len(translation.device_configs), translation.explanation
            )

            if not translation.success:
                intent.status = IntentStatus.FAILED
                intent.error_message = translation.error
                _emit_intent_update(intent)
                return jsonify({"status": "translation_failed", "error": translation.error}), 500

            # 3b. External Conflict Fabric Mediation (D2.4 Section 10 & Req-T23-DE-02)
            verdict = conflict_fabric.submit(intent)
            intent.conflict_token = verdict.token
            audit_log.system_event(
                f"Conflict Fabric Verdict for {intent.intent_id[:8]}: {verdict.verdict.value} "
                f"(Token: {verdict.token}, Reason: {verdict.reason_code})"
            )

            if verdict.verdict == VerdictType.DENY:
                intent.status = IntentStatus.FAILED
                intent.error_message = f"Conflict Fabric Denied Intent: {verdict.reason_code}"
                _emit_intent_update(intent)
                return jsonify({
                    **_intent_to_dict(intent),
                    "status": "denied",
                    "reason": verdict.reason_code,
                    "verdict": verdict.model_dump(mode="json")
                }), 409

            if verdict.verdict == VerdictType.DEFER:
                intent.status = IntentStatus.PENDING
                intent.error_message = f"Conflict Fabric Deferred Intent: {verdict.reason_code}"
                _emit_intent_update(intent)
                return jsonify({
                    **_intent_to_dict(intent),
                    "status": "deferred",
                    "retry_after": verdict.retry_after,
                    "verdict": verdict.model_dump(mode="json")
                }), 202

            # 4. Apply through Actuator with last-mile token check (Req-T23-CG-07)
            intent.status = IntentStatus.APPLYING
            _emit_intent_update(intent)

            backend_name = type(adapter).__name__
            apply_results = adapter.apply_all(translation.device_configs, conflict_token=verdict.token)
            all_ok = all(r.success for r in apply_results)

            if apply_results:
                intent.actuation_outcome = apply_results[0].outcome
                intent.readback_evidence = apply_results[0].readback_evidence
            else:
                intent.actuation_outcome = ActuationOutcomeType.ACKNOWLEDGED_VERIFIED

            intent.status = IntentStatus.APPLIED if all_ok else IntentStatus.FAILED
            intent.state_3gpp = IntentLifecycle3GPP.OPERATION if all_ok else IntentLifecycle3GPP.COMMISSIONING
            if all_ok:
                if intent.intent_type == IntentType.ENERGY or intent.parameters.get("power_mode") in ["eco", "sleep"]:
                    intent.service_dlc_state = ServiceDLCState.PAUSED
                else:
                    intent.service_dlc_state = ServiceDLCState.RUNNING
            intent.applied_at = datetime.now(timezone.utc)
            intent.applied_config = {
                "configs": [c.to_dict() for c in translation.device_configs],
                "explanation": translation.explanation,
                "warnings": validation.warnings + translation.warnings,
            }

            for r in apply_results:
                audit_log.config_applied(
                    intent.intent_id, r.device_id,
                    translation.device_configs[0].config_type if translation.device_configs else "unknown",
                    r.success, r.message, backend_name,
                )
                # Persist successful configs to state store
                if r.success:
                    # Find the corresponding device config
                    cfg = next((c for c in translation.device_configs if c.device_id == r.device_id), None)
                    if cfg:
                        state_store.update_device_config(
                            cfg.device_id, cfg.config_type, cfg.parameters, 
                            intent.intent_id, cfg.yang_xml
                        )
            
            _emit_intent_update(intent)

            return jsonify({
                **_intent_to_dict(intent),
                "status": "applied" if all_ok else "partial_failure",
                "configs_applied": sum(1 for r in apply_results if r.success),
                "configs_total": len(apply_results),
                "explanation": translation.explanation,
                "backend": backend_name,
            }), 200

        except Exception as e:
            logger.exception(f"Intent processing error: {e}")
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/v1/intents", methods=["GET"])
    def list_intents():
        """List all intents with optional status filter."""
        status_filter = request.args.get("status")
        intents = list(_intent_store.values())
        if status_filter:
            intents = [i for i in intents if i.status.value == status_filter]
        # Sort by submitted_at descending
        intents.sort(key=lambda i: i.submitted_at, reverse=True)
        limit = int(request.args.get("limit", 50))
        return jsonify([_intent_to_dict(i) for i in intents[:limit]])

    @app.route("/api/v1/intents/<intent_id>", methods=["GET"])
    def get_intent(intent_id: str):
        intent = _intent_store.get(intent_id)
        if not intent:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_intent_to_dict(intent))

    @app.route("/api/v1/intents/<intent_id>", methods=["DELETE"])
    def delete_intent(intent_id: str):
        if intent_id in _intent_store:
            intent = _intent_store[intent_id]
            intent.state_3gpp = IntentLifecycle3GPP.DECOMMISSIONING
            intent.service_dlc_state = ServiceDLCState.CLOSED
            _emit_intent_update(intent)
            audit_log.system_event(f"Intent {intent_id[:8]} decommissioned and removed.")
            del _intent_store[intent_id]
            return jsonify({
                "status": "deleted",
                "state_3gpp": "decommissioning",
                "service_dlc_state": "closed"
            })
        return jsonify({"error": "Not found"}), 404

    # ── TM Forum ODA & D5.1 Lifecycle API ─────────────────────────────────────

    @app.route("/api/v1/tmf/cfs", methods=["GET"])
    def list_cfs():
        """List all TM Forum TMF641 / IG1253 Customer Facing Services (CFS)."""
        cfs_list = [i.cfs.model_dump(mode="json") for i in _intent_store.values() if i.cfs]
        return jsonify(cfs_list)

    @app.route("/api/v1/tmf/rfs", methods=["GET"])
    def list_rfs():
        """List all TM Forum TMF652 Resource Facing Services (RFS)."""
        rfs_list = [
            {**rfs.model_dump(mode="json"), "intent_id": i.intent_id}
            for i in _intent_store.values()
            for rfs in i.rfs_list
        ]
        return jsonify(rfs_list)

    @app.route("/api/v1/tmf/isr", methods=["GET"])
    def get_intent_state_registry():
        """D5.1 Intent State Registry (ISR) & Service State Registry (SSR) tracking."""
        isr_records = []
        for i in _intent_store.values():
            isr_records.append({
                "intent_id": i.intent_id,
                "intent_type": i.intent_type.value,
                "target": i.target.identifier,
                "state_3gpp": i.state_3gpp.value if hasattr(i.state_3gpp, "value") else str(i.state_3gpp),
                "service_dlc_state": i.service_dlc_state.value if hasattr(i.service_dlc_state, "value") else str(i.service_dlc_state),
                "actuation_outcome": i.actuation_outcome.value if hasattr(i.actuation_outcome, "value") else str(i.actuation_outcome or "unspecified"),
                "conflict_token": i.conflict_token,
                "cfs_id": i.cfs.cfs_id if i.cfs else None,
                "cfs_name": i.cfs.name if i.cfs else None,
                "rfs_count": len(i.rfs_list),
                "rfs_domains": list(set(r.target_domain for r in i.rfs_list)),
                "status": i.status.value if hasattr(i.status, "value") else str(i.status),
                "submitted_at": i.submitted_at.isoformat() if i.submitted_at else None,
                "applied_at": i.applied_at.isoformat() if i.applied_at else None,
            })
        return jsonify(isr_records)

    @app.route("/api/v1/tmf/service-dlc/<intent_id>/pause", methods=["POST"])
    def pause_service_dlc(intent_id: str):
        """D5.1 ServiceDLC Pausing (Green energy freeze / eco sleep)."""
        intent = _intent_store.get(intent_id)
        if not intent:
            return jsonify({"error": "Intent not found"}), 404
        intent.service_dlc_state = ServiceDLCState.PAUSED
        audit_log.system_event(f"ServiceDLC for intent {intent_id[:8]} paused (Green-6G sleep).")
        _emit_intent_update(intent)
        return jsonify({"intent_id": intent_id, "service_dlc_state": intent.service_dlc_state.value})

    @app.route("/api/v1/tmf/service-dlc/<intent_id>/resume", methods=["POST"])
    def resume_service_dlc(intent_id: str):
        """D5.1 ServiceDLC Resume back to Running state."""
        intent = _intent_store.get(intent_id)
        if not intent:
            return jsonify({"error": "Intent not found"}), 404
        intent.service_dlc_state = ServiceDLCState.RUNNING
        audit_log.system_event(f"ServiceDLC for intent {intent_id[:8]} resumed to running.")
        _emit_intent_update(intent)
        return jsonify({"intent_id": intent_id, "service_dlc_state": intent.service_dlc_state.value})

    @app.route("/api/v1/tmf/service-dlc/<intent_id>/suspend", methods=["POST"])
    def suspend_service_dlc(intent_id: str):
        """D5.1 ServiceDLC Suspension (Emergency preemption for critical URLLC)."""
        intent = _intent_store.get(intent_id)
        if not intent:
            return jsonify({"error": "Intent not found"}), 404
        intent.service_dlc_state = ServiceDLCState.SUSPENDED
        audit_log.system_event(f"ServiceDLC for intent {intent_id[:8]} suspended for emergency preemption.")
        _emit_intent_update(intent)
        return jsonify({"intent_id": intent_id, "service_dlc_state": intent.service_dlc_state.value})

    # ── Conflict Fabric Mediation API (D2.4 Chapter 10) ─────────────────────────

    @app.route("/api/v1/conflict-fabric/status", methods=["GET"])
    def get_conflict_fabric_status():
        """Return diagnostic status of the external conflict fabric integration."""
        return jsonify(conflict_fabric.get_status())

    @app.route("/api/v1/conflict-fabric/verdicts/<intent_id>", methods=["GET"])
    def get_conflict_verdict(intent_id: str):
        """Retrieve mediation verdict and issued token for an intent."""
        v = conflict_fabric.verdict(intent_id)
        if not v:
            return jsonify({"error": "No verdict found for intent"}), 404
        return jsonify(v.model_dump(mode="json"))


    # ── Topology API ──────────────────────────────────────────────────────────

    @app.route("/api/v1/topology", methods=["GET"])
    def get_topology():
        refresh = request.args.get("refresh", "false").lower() == "true"
        if refresh and hasattr(registry, "sync_from_tfs"):
            registry.sync_from_tfs()

        topo = registry.get_topology()
        # Enrich nodes with their applied config summary
        device_states = state_store.get_all_device_states()
        for node in topo.get("nodes", []):
            node["applied_configs"] = device_states.get(node["id"], {}).get("configs", {})
        
        topo["source_of_truth"] = registry.get_source_of_truth()
        return jsonify(topo)

    @app.route("/api/v1/tfs/sync", methods=["POST"])
    def sync_tfs_topology():
        """Trigger an on-demand re-sync of the topology from TeraFlowSDN."""
        audit_log.system_event("Manual TeraFlowSDN topology sync requested")
        synced = False
        if hasattr(registry, "sync_from_tfs"):
            synced = registry.sync_from_tfs()

        topo = registry.get_topology()
        # Update telemetry simulator links if running
        sim = app.config.get("telemetry_sim")
        if sim and hasattr(sim, "refresh_links"):
            sim.refresh_links()

        # Emit live topology update to connected dashboard clients
        socketio.emit("topology_update", topo)

        return jsonify({
            "synced": synced,
            "source_of_truth": registry.get_source_of_truth(),
            "nodes_count": len(registry.get_all_nodes()),
            "links_count": len(registry.get_all_links()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), (200 if synced else 503)

    # ── Telemetry API ─────────────────────────────────────────────────────────

    @app.route("/api/v1/telemetry", methods=["GET"])
    def get_telemetry():
        # Gets the live snapshot from the telemetry simulator via the socketio context
        # The dashboard uses Socket.IO for live updates; this endpoint is for REST polling
        return jsonify({"message": "Use Socket.IO event 'telemetry_update' for real-time data"})

    # ── Audit Log API ─────────────────────────────────────────────────────────

    @app.route("/api/v1/audit-log", methods=["GET"])
    def get_audit_log():
        limit = int(request.args.get("limit", 100))
        event_type = request.args.get("event_type")
        return jsonify(audit_log.get_recent(limit=limit, event_type=event_type))

    # ── Device State API ──────────────────────────────────────────────────────

    @app.route("/api/v1/devices/<device_id>/state", methods=["GET"])
    def get_device_state(device_id: str):
        state = state_store.get_device_state(device_id)
        if not state:
            return jsonify({"device_id": device_id, "configs": {}}), 200
        return jsonify({"device_id": device_id, **state})

    @app.route("/api/v1/devices", methods=["GET"])
    def list_devices():
        return jsonify({
            "nodes": registry.get_all_nodes(),
            "links": registry.get_all_links(),
            "source_of_truth": registry.get_source_of_truth(),
        })

    # ── Option A Testbed (8 IP-50 + 8 TG Conducted Bench) ──────────────────────
    from cer_intent.architect.dpir_marl_engine import get_option_a_engine
    option_a_engine = get_option_a_engine()

    @app.route("/api/v1/testbed/option-a/state", methods=["GET"])
    def get_option_a_state():
        """Retrieve live operational state of Option A testbed."""
        return jsonify(option_a_engine.get_state())

    @app.route("/api/v1/testbed/option-a/disaster-cut", methods=["POST"])
    def trigger_option_a_disaster():
        """Simulate disaster event: PDUs cut CORE & HUB power, attenuators at max."""
        state = option_a_engine.trigger_disaster()
        audit_log.system_event("Option A Testbed: Switched PDUs cut CORE & HUB power. Programmable attenuators set to MAX (90 dB). 4 isolated islands formed.")
        socketio.emit("testbed_state_changed", state)
        return jsonify(state)

    @app.route("/api/v1/testbed/option-a/marl-recover", methods=["POST"])
    def trigger_option_a_marl_recover():
        """Trigger decentralized MARL edge actors to ignite 3 candidate bridges and restore tree."""
        token_verdict = conflict_fabric.submit_raw(
            requester_id="urn:unity6g:agent:ceragon:marl-recovery-actor",
            target_urn="urn:unity6g:resource:ceragon:transport:option-a",
            action="action.transport.ignite_marl_bridges",
            proposed_state={
                "bridges": ["bridge-1", "bridge-2", "bridge-3"],
                "policy": "d2.4_disaster_recovery"
            }
        )
        token = token_verdict.token

        from cer_intent.device.tg_adapter import SikluTGAdapter
        tg_adapter = SikluTGAdapter(state_store)
        for b in option_a_engine.topology_data.get("marl_candidate_bridges", []):
            tg_adapter.ignite_candidate_bridge(
                bridge_id=b["bridge_id"],
                igniter=b["igniter"],
                target=b["target"],
                steer_angle_deg=b["steer_angle_deg"],
                snr_db=b["snr_db"],
                modulation=b["modulation"],
                capacity_mbps=b["capacity_mbps"],
                conflict_token=token
            )

        state = option_a_engine.trigger_marl_recovery()
        audit_log.system_event(
            f"Option A Testbed: MARL 3-Bridge Reconnection complete under token {token}. "
            f"Tree restored: F1 (W1-W2-E2-E1), F2 (W2-E2), svc W1-S, svc W2-E2-E1-N."
        )
        socketio.emit("testbed_state_changed", state)
        return jsonify(state)

    @app.route("/api/v1/testbed/option-a/reset", methods=["POST"])
    def reset_option_a_testbed():
        """Reset Option A testbed to normal DPIR operation."""
        state = option_a_engine.reset_to_normal()
        audit_log.system_event("Option A Testbed: Reset to Normal DPIR operation.")
        socketio.emit("testbed_state_changed", state)
        return jsonify(state)

    @app.route("/api/v1/testbed/option-a/ignite-bridge", methods=["POST"])
    def ignite_option_a_bridge():
        """Ignite an individual MARL bridge (bridge-1, bridge-2, or bridge-3)."""
        body = request.get_json(silent=True) or {}
        bridge_id = body.get("bridge_id", "bridge-1")
        
        candidate = next((b for b in option_a_engine.topology_data.get("marl_candidate_bridges", []) if b["bridge_id"] == bridge_id), None)
        if not candidate:
            return jsonify({"error": f"Bridge {bridge_id} not found"}), 404

        token_verdict = conflict_fabric.submit_raw(
            requester_id=f"urn:unity6g:agent:ceragon:marl-actor-{candidate['igniter'].lower()}",
            target_urn=f"urn:unity6g:resource:ceragon:node:{candidate['igniter'].lower()}",
            action="action.transport.ignite_link",
            proposed_state=candidate
        )
        token = token_verdict.token

        from cer_intent.device.tg_adapter import SikluTGAdapter
        tg_adapter = SikluTGAdapter(state_store)
        res = tg_adapter.ignite_candidate_bridge(
            bridge_id=candidate["bridge_id"],
            igniter=candidate["igniter"],
            target=candidate["target"],
            steer_angle_deg=candidate["steer_angle_deg"],
            snr_db=candidate["snr_db"],
            modulation=candidate["modulation"],
            capacity_mbps=candidate["capacity_mbps"],
            conflict_token=token
        )
        audit_log.system_event(
            f"Option A Bridge {bridge_id} ignited by {candidate['igniter']} -> {candidate['target']}: {res.outcome.value}"
        )
        return jsonify({
            "result": res.to_dict(),
            "candidate": candidate
        })

    # ── Health ────────────────────────────────────────────────────────────────

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "adapter_backend": type(adapter).__name__,
            "source_of_truth": registry.get_source_of_truth(),
            "nodes_count": len(registry.get_all_nodes()),
            "links_count": len(registry.get_all_links()),
            "intents_active": len(_intent_store),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })



    @app.route("/api/v1/hardware/profiles", methods=["GET"])
    def list_hardware_profiles():
        profiles = kb.get_all_profiles()
        return jsonify([p.to_dict() for p in profiles])

    @app.route("/api/v1/hardware/profiles/<model>", methods=["GET"])
    def get_hardware_profile(model: str):
        profile = kb.get_profile(model)
        return jsonify(profile.to_dict())

    # ── Approval API ──────────────────────────────────────────────────────────

    @app.route("/api/v1/intents/<intent_id>/approve", methods=["POST"])
    def approve_intent(intent_id):
        """Resume execution for an intent that was awaiting architecture approval."""
        intent = _intent_store.get(intent_id)
        if not intent:
            return jsonify({"error": "Intent not found"}), 404
            
        if intent.status != IntentStatus.AWAITING_APPROVAL:
            return jsonify({"error": f"Intent is in state {intent.status}, cannot approve."}), 400

        from cer_intent.architect.strategy import ArchitectPlan, Strategy, ConfigAction, ActionType
        plan_dict = intent.architect_plan
        if not plan_dict:
            return jsonify({"error": "No architecture plan found to approve."}), 400
        
        # 1. Reconstruct Strategy & Plan objects
        s_dict = plan_dict["selected_strategy"]
        selected_strategy = Strategy(
            name=s_dict["name"],
            description=s_dict["description"],
            skill_source=s_dict["skill_source"],
            confidence=s_dict["confidence"],
            rationale=s_dict["rationale"],
            actions=[ConfigAction(
                action_type=ActionType(a["action_type"]),
                parameter_overrides=a["parameter_overrides"],
                intent_type_override=a["intent_type_override"],
                target_override=a["target_override"],
                rationale=a["rationale"],
                execution_order=a["execution_order"]
            ) for a in s_dict["actions"]]
        )
        
        full_plan = ArchitectPlan(
            intent_id=intent.intent_id,
            selected_strategy=selected_strategy,
            reasoning_trace=plan_dict["reasoning_trace"]
        )

        try:
            intent.status = IntentStatus.TRANSLATING
            intent.state_3gpp = IntentLifecycle3GPP.COMMISSIONING
            _emit_intent_update(intent)
            
            audit_log.system_event(f"User approved plan: {selected_strategy.name}")
            translation = executor.execute_plan(full_plan, intent)
            
            audit_log.translation_complete(
                intent.intent_id, len(translation.device_configs), translation.explanation
            )

            if not translation.success:
                intent.status = IntentStatus.FAILED
                intent.error_message = translation.error
                _emit_intent_update(intent)
                return jsonify({"status": "failed", "error": translation.error}), 500

            # Mediate through external Conflict Fabric before actuation
            verdict = conflict_fabric.submit(intent)
            intent.conflict_token = verdict.token
            audit_log.system_event(
                f"Conflict Fabric Verdict for approved intent {intent.intent_id[:8]}: {verdict.verdict.value} (Token: {verdict.token})"
            )

            if verdict.verdict == VerdictType.DENY:
                intent.status = IntentStatus.FAILED
                intent.error_message = f"Conflict Fabric Denied Intent: {verdict.reason_code}"
                _emit_intent_update(intent)
                return jsonify({"status": "denied", "reason": verdict.reason_code}), 409

            # 2. Apply configs with token
            intent.status = IntentStatus.APPLYING
            _emit_intent_update(intent)
            
            backend_name = type(adapter).__name__
            last_res = None
            for cfg in translation.device_configs:
                success_res = adapter.apply(cfg, conflict_token=verdict.token)
                last_res = success_res
                if success_res.success:
                    state_store.update_device_config(cfg.device_id, cfg.config_type, cfg.parameters, intent.intent_id)
                
                audit_log.config_applied(
                    intent.intent_id, cfg.device_id, cfg.config_type,
                    success_res.success, success_res.message, backend_name
                )

            if last_res:
                intent.actuation_outcome = last_res.outcome
                intent.readback_evidence = last_res.readback_evidence
            else:
                intent.actuation_outcome = ActuationOutcomeType.ACKNOWLEDGED_VERIFIED

            intent.status = IntentStatus.APPLIED
            intent.state_3gpp = IntentLifecycle3GPP.OPERATION
            if intent.intent_type == IntentType.ENERGY or intent.parameters.get("power_mode") in ["eco", "sleep"]:
                intent.service_dlc_state = ServiceDLCState.PAUSED
            else:
                intent.service_dlc_state = ServiceDLCState.RUNNING
            intent.applied_at = datetime.now(timezone.utc)
            intent.applied_config = translation.model_dump(mode="json")
            _emit_intent_update(intent)
            
            return jsonify({
                **_intent_to_dict(intent),
                "status": "applied",
                "configs_applied": len(translation.device_configs), # Simplification
                "configs_total": len(translation.device_configs),
                "explanation": translation.explanation,
            }), 200
            
        except Exception as e:
            logger.error(f"Error during approval execution: {e}")
            intent.status = IntentStatus.FAILED
            intent.error_message = str(e)
            _emit_intent_update(intent)
            return jsonify({"status": "error", "error": str(e)}), 500

    # ── Socket.IO Events ──────────────────────────────────────────────────────

    @socketio.on("connect")
    def on_connect():
        logger.info("Dashboard client connected")
        # Send current state on connect
        socketio.emit("initial_state", {
            "intents": [_intent_to_dict(i) for i in _intent_store.values()],
            "topology": registry.get_topology(),
            "telemetry": list(app.config.get("telemetry_sim").get_snapshot().values()) if app.config.get("telemetry_sim") else []
        })

    @socketio.on("submit_intent")
    def on_submit_intent(data):
        """Allow intent submission directly via WebSocket."""
        with app.test_request_context():
            pass  # handled by REST endpoint

    return app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _intent_to_dict(intent: Intent) -> dict:
    """Safely convert Intent model to dictionary for JSON serialization."""
    try:
        d = intent.to_dict()
        d["summary"] = intent.summary() or "Unclassified Intent"
        # Ensure enums and nested objects are stringified if needed (to_dict usually handles this)
        # but we explicitly check type and target for frontend safety
        d["intent_type"] = d.get("intent_type") or "intent"
        d["target_name"] = intent.target.identifier if intent.target else "unknown"
        return d
    except Exception as e:
        logger.error(f"Error serializing intent {intent.intent_id}: {e}")
        return {
            "intent_id": intent.intent_id,
            "status": intent.status.value if hasattr(intent.status, "value") else str(intent.status),
            "intent_type": "unknown",
            "summary": "Serialization Error"
        }


def _emit_intent_update(intent: Intent):
    try:
        socketio.emit("intent_update", _intent_to_dict(intent))
    except Exception:
        pass
