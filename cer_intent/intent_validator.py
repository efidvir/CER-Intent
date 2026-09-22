"""
Intent Validator
================
Validates parsed intents against:
  - Topology constraints (target must exist)
  - Hardware capability tables (max modulation per device model)
  - Conflict detection with existing active intents
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from cer_intent.intent_schema import (
    Intent, IntentType, IntentStatus,
    CapacityParameters, ModulationParameters, ResilienceParameters
)

logger = logging.getLogger(__name__)


# Modulation order for comparison
MODULATION_ORDER = {
    "QPSK": 1, "16QAM": 2, "32QAM": 3, "64QAM": 4, "128QAM": 5,
    "256QAM": 6, "512QAM": 7, "1024QAM": 8, "2048QAM": 9
}

# Hardware capability constraints per Ceragon model
DEVICE_CAPABILITIES = {
    "IP-50FX": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 10.0,
        "supported_bw_mhz": [7, 14, 28, 56, 112],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "IP-20C": {
        "max_modulation": "1024QAM",
        "max_throughput_gbps": 2.5,
        "supported_bw_mhz": [7, 14, 28, 56],
        "supports_hsb": True,
        "supports_sd": False,
    },
    "IP-50C": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 2.5,
        "supported_bw_mhz": [7, 14, 28, 56, 112],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "IP-20N": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 5.0,
        "supported_bw_mhz": [7, 14, 28, 56, 112],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "IP-20S": {
        "max_modulation": "512QAM",
        "max_throughput_gbps": 1.0,
        "supported_bw_mhz": [7, 14, 28],
        "supports_hsb": False,
        "supports_sd": False,
    },
    "IP-50E": {
        "max_modulation": "512QAM",
        "max_throughput_gbps": 20.0,
        "supported_bw_mhz": [250, 500, 1000, 2000],
        "supports_hsb": True,
        "supports_sd": False,
    },
    "Core-DC": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 100.0,
        "supported_bw_mhz": [1000, 10000, 40000, 100000],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "O-CU": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 50.0,
        "supported_bw_mhz": [100, 200, 400, 1000],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "O-DU": {
        "max_modulation": "2048QAM",
        "max_throughput_gbps": 25.0,
        "supported_bw_mhz": [100, 200, 400],
        "supports_hsb": True,
        "supports_sd": True,
    },
    "O-RU": {
        "max_modulation": "1024QAM",
        "max_throughput_gbps": 10.0,
        "supported_bw_mhz": [50, 100, 200],
        "supports_hsb": False,
        "supports_sd": False,
    },
}


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class IntentValidator:
    """
    Validates intents against topology & hardware constraints,
    and detects conflicts with active intents.
    """

    def __init__(self, registry=None):
        self._registry = registry  # Optional DeviceRegistry reference

    def validate(self, intent: Intent, active_intents: Optional[List[Intent]] = None) -> ValidationResult:
        result = ValidationResult(valid=True)

        # 1. Basic parameter validation
        self._validate_parameters(intent, result)

        # 2. Topology validation (if registry is available)
        if self._registry:
            self._validate_topology(intent, result)
            self._validate_hardware_capabilities(intent, result)

        # 3. Conflict detection
        if active_intents:
            self._detect_conflicts(intent, active_intents, result)

        if result.valid:
            logger.info(f"Intent {intent.intent_id[:8]} validated OK")
        else:
            logger.warning(f"Intent {intent.intent_id[:8]} validation failed: {result.errors}")

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Parameter Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_parameters(self, intent: Intent, result: ValidationResult):
        params = intent.parameters

        if intent.intent_type == IntentType.CAPACITY:
            if params.get("min_throughput_gbps", 0) <= 0:
                result.add_error("Capacity intent requires min_throughput_gbps > 0")
            max_tp = params.get("max_throughput_gbps")
            min_tp = params.get("min_throughput_gbps", 0)
            if max_tp and max_tp < min_tp:
                result.add_error("max_throughput_gbps must be >= min_throughput_gbps")

        elif intent.intent_type == IntentType.MODULATION:
            min_m = params.get("min_modulation", "QPSK")
            max_m = params.get("max_modulation", "2048QAM")
            if min_m not in MODULATION_ORDER:
                result.add_error(f"Unknown modulation '{min_m}'. Valid: {list(MODULATION_ORDER.keys())}")
            if max_m not in MODULATION_ORDER:
                result.add_error(f"Unknown modulation '{max_m}'. Valid: {list(MODULATION_ORDER.keys())}")
            if min_m in MODULATION_ORDER and max_m in MODULATION_ORDER:
                if MODULATION_ORDER[min_m] > MODULATION_ORDER[max_m]:
                    result.add_error(f"min_modulation {min_m} is higher than max_modulation {max_m}")

        elif intent.intent_type == IntentType.QOS:
            latency = params.get("max_latency_ms")
            if latency and latency <= 0:
                result.add_error("max_latency_ms must be > 0")

        elif intent.intent_type == IntentType.SLICE:
            pct = params.get("bandwidth_pct")
            mbps = params.get("bandwidth_mbps")
            if pct is None and mbps is None:
                result.add_warning("Slice intent has no bandwidth specification; using best-effort")
            if pct and (pct <= 0 or pct > 100):
                result.add_error("bandwidth_pct must be between 0 and 100")

        elif intent.intent_type == IntentType.RESILIENCE:
            mode = params.get("protection_mode", "1+1-hsb")
            valid_modes = ["1+1-hsb", "1+1-cold", "space-diversity", "frequency-diversity", "none"]
            if mode not in valid_modes:
                result.add_error(f"Invalid protection_mode '{mode}'. Valid: {valid_modes}")

    # ─────────────────────────────────────────────────────────────────────────
    # Topology Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_topology(self, intent: Intent, result: ValidationResult):
        target = intent.target
        if target.target_type.value == "all":
            return  # Always valid

        existing_ids = self._registry.get_all_identifiers()

        if target.identifier not in existing_ids:
            result.add_warning(
                f"Target '{target.identifier}' not found in current topology. "
                f"Known identifiers: {', '.join(list(existing_ids)[:10])}"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Hardware Capability Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_hardware_capabilities(self, intent: Intent, result: ValidationResult):
        if self._registry is None:
            return

        target_devices = self._registry.get_devices_for_target(
            intent.target.target_type.value,
            intent.target.identifier
        )
        if not target_devices:
            return

        for device in target_devices:
            model = device.get("model", "IP-50FX")
            caps = DEVICE_CAPABILITIES.get(model, DEVICE_CAPABILITIES["IP-50FX"])

            if intent.intent_type == IntentType.MODULATION:
                max_m = intent.parameters.get("max_modulation", "2048QAM")
                hw_max = caps["max_modulation"]
                if MODULATION_ORDER.get(max_m, 0) > MODULATION_ORDER.get(hw_max, 0):
                    result.add_warning(
                        f"Device {device['id']} ({model}) supports max {hw_max}, "
                        f"requested {max_m} — will be capped"
                    )

            elif intent.intent_type == IntentType.CAPACITY:
                requested = intent.parameters.get("min_throughput_gbps", 0)
                hw_max = caps["max_throughput_gbps"]
                if requested > hw_max:
                    result.add_warning(
                        f"Device {device['id']} ({model}) max capacity is {hw_max} Gbps, "
                        f"but {requested} Gbps requested"
                    )
                bw = intent.parameters.get("channel_bandwidth_mhz")
                if bw and bw not in caps["supported_bw_mhz"]:
                    result.add_error(
                        f"Device {device['id']} ({model}) does not support {bw} MHz. "
                        f"Supported: {caps['supported_bw_mhz']}"
                    )

            elif intent.intent_type == IntentType.RESILIENCE:
                mode = intent.parameters.get("protection_mode", "1+1-hsb")
                if mode == "1+1-hsb" and not caps["supports_hsb"]:
                    result.add_warning(f"Device {device['id']} ({model}) does not support HSB protection — alternative may be selected")
                if mode == "space-diversity" and not caps["supports_sd"]:
                    result.add_warning(f"Device {device['id']} ({model}) does not support Space Diversity — falling back to next best mode")

    # ─────────────────────────────────────────────────────────────────────────
    # Conflict Detection
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_conflicts(self, intent: Intent, active_intents: List[Intent], result: ValidationResult):
        for existing in active_intents:
            if existing.status in (IntentStatus.FAILED, IntentStatus.EXPIRED):
                continue
            if existing.intent_id == intent.intent_id:
                continue

            # Same type + overlapping target = potential conflict
            if (existing.intent_type == intent.intent_type and
                    self._targets_overlap(existing.target, intent.target)):

                if intent.intent_type == IntentType.CAPACITY:
                    existing_min = existing.parameters.get("min_throughput_gbps", 0)
                    new_min = intent.parameters.get("min_throughput_gbps", 0)
                    if abs(existing_min - new_min) > 0.1:
                        result.add_warning(
                            f"Conflicts with existing intent {existing.intent_id[:8]}: "
                            f"capacity {existing_min}→{new_min} Gbps (new overrides)"
                        )

                elif intent.intent_type == IntentType.RESILIENCE:
                    ex_mode = existing.parameters.get("protection_mode")
                    new_mode = intent.parameters.get("protection_mode")
                    if ex_mode != new_mode:
                        result.add_warning(
                            f"Conflicts with existing resilience intent {existing.intent_id[:8]}: "
                            f"mode {ex_mode}→{new_mode}"
                        )

    def _targets_overlap(self, t1, t2) -> bool:
        if t1.target_type.value == "all" or t2.target_type.value == "all":
            return True
        return t1.identifier == t2.identifier
