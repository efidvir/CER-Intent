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

from cer_intent.intent_schema import Intent, IntentStatus, IntentTarget, IntentType
from cer_intent.intent_parser import IntentParser
from cer_intent.intent_validator import IntentValidator
from cer_intent.translators import get_translator
from cer_intent.device.adapter import create_adapter
from cer_intent.device.state_store import StateStore
from cer_intent.device.knowledge_base import HardwareKnowledgeBase
from cer_intent.architect.agent import IntentArchitectAgent
from cer_intent.architect.executor import ArchitectExecutor

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

    # One-time init of shared components
    state_store = StateStore(os.getenv("STATE_FILE", "data/topology_state.json"))
    adapter = create_adapter(state_store, registry=registry)
    parser = IntentParser()
    validator = IntentValidator(registry=registry)
    
    # Initialize Hardware Knowledge and Architect Agent
    kb = HardwareKnowledgeBase()
    architect = IntentArchitectAgent(registry=registry, state_store=state_store, knowledge_base=kb)
    executor = ArchitectExecutor(registry=registry)

    # Wire intent store and telemetry into reconciler (run.py sets these up after create_app)
    app.config["intent_store"] = _intent_store
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

            # 4. Apply
            intent.status = IntentStatus.APPLYING
            _emit_intent_update(intent)

            backend_name = type(adapter).__name__
            apply_results = adapter.apply_all(translation.device_configs)
            all_ok = all(r.success for r in apply_results)

            intent.status = IntentStatus.APPLIED if all_ok else IntentStatus.FAILED
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
            del _intent_store[intent_id]
            return jsonify({"status": "deleted"})
        return jsonify({"error": "Not found"}), 404

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

            # 2. Apply configs
            intent.status = IntentStatus.APPLYING
            _emit_intent_update(intent)
            
            backend_name = type(adapter).__name__
            for cfg in translation.device_configs:
                success_res = adapter.apply(cfg)
                if success_res.success:
                    state_store.update_device_config(cfg.device_id, cfg.config_type, cfg.parameters, intent.intent_id)
                
                audit_log.config_applied(
                    intent.intent_id, cfg.device_id, cfg.config_type,
                    success_res.success, success_res.message, backend_name
                )

            intent.status = IntentStatus.APPLIED
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
