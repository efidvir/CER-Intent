"""
Intent Schema
=============
Canonical data models for the CER-Intent system using Pydantic v2.
All intents flowing through the system are validated against these models.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────

class IntentType(str, Enum):
    CAPACITY    = "capacity"     # Throughput / bandwidth requirement
    QOS         = "qos"          # Latency, jitter, packet-loss requirement
    MODULATION  = "modulation"   # ACM / MRMC configuration
    RESILIENCE  = "resilience"   # Protection / redundancy
    SLICE       = "slice"        # Network slicing / resource allocation
    ENERGY      = "energy"       # Power saving / sleep mode
    SYNC        = "sync"         # Timing / SyncE / PTP 
    SECURITY    = "security"     # Payload encryption / MACsec


class IntentStatus(str, Enum):
    PENDING      = "pending"
    PARSING      = "parsing"
    VALIDATED    = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    TRANSLATING  = "translating"
    APPLYING     = "applying"
    APPLIED      = "applied"
    DRIFT        = "drift"          # Applied but real state diverged
    REMEDIATED   = "remediated"     # Closed-loop re-applied
    FAILED       = "failed"
    EXPIRED      = "expired"


class TargetType(str, Enum):
    LINK    = "link"
    NODE    = "node"
    SECTOR  = "sector"
    ALL     = "all"


class ProtectionMode(str, Enum):
    HSB      = "1+1-hsb"         # Hot Standby
    COLD     = "1+1-cold"        # Cold Standby
    SD       = "space-diversity"
    FD       = "frequency-diversity"
    NONE     = "none"


class SliceType(str, Enum):
    EMBB    = "eMBB"
    URLLC   = "URLLC"
    MMTC    = "mMTC"
    CUSTOM  = "custom"


class QoSClass(str, Enum):
    EF      = "EF"    # Expedited Forwarding (highest priority)
    AF4     = "AF4"
    AF3     = "AF3"
    AF2     = "AF2"
    AF1     = "AF1"
    BE      = "BE"    # Best Effort


# ──────────────────────────────────────────────────────────────────────────────
# Intent Target
# ──────────────────────────────────────────────────────────────────────────────

class IntentTarget(BaseModel):
    target_type: TargetType = Field(..., description="Type of network element targeted")
    identifier: str = Field(..., description="Link ID, Node ID, Sector name, or 'all'")
    direction: Optional[str] = Field(None, description="For links: 'tx', 'rx', or 'both'")


# ──────────────────────────────────────────────────────────────────────────────
# Intent Parameters (per type)
# ──────────────────────────────────────────────────────────────────────────────

class CapacityParameters(BaseModel):
    min_throughput_gbps: float = Field(..., ge=0.001, description="Minimum required throughput in Gbps")
    max_throughput_gbps: Optional[float] = Field(None, description="Maximum allowed throughput in Gbps")
    channel_bandwidth_mhz: Optional[int] = Field(None, description="Preferred channel BW in MHz (e.g. 28, 56, 112)")
    slice_type: Optional[SliceType] = None


class QoSParameters(BaseModel):
    max_latency_ms: Optional[float] = Field(None, ge=0, description="Maximum one-way latency in ms")
    max_jitter_ms: Optional[float] = Field(None, ge=0, description="Maximum jitter in ms")
    max_packet_loss_pct: Optional[float] = Field(None, ge=0, le=100)
    traffic_class: Optional[QoSClass] = QoSClass.AF2
    dscp_marking: Optional[int] = Field(None, ge=0, le=63)
    bandwidth_guaranteed_mbps: Optional[float] = Field(None, ge=0)


class ModulationParameters(BaseModel):
    min_modulation: str = Field("QPSK", description="Minimum modulation (e.g. QPSK, 16QAM, 256QAM)")
    max_modulation: str = Field("2048QAM", description="Maximum modulation (e.g. 1024QAM, 2048QAM)")
    acm_enabled: bool = True
    tx_power_dbm: Optional[float] = Field(None, description="TX power in dBm")
    mrmc_script_id: Optional[int] = Field(None, description="Override specific MRMC script index")


class ResilienceParameters(BaseModel):
    protection_mode: ProtectionMode = ProtectionMode.HSB
    revert_mode: str = Field("revertive", description="'revertive' or 'non-revertive'")
    wtr_seconds: int = Field(300, description="Wait-to-Restore time in seconds")
    holdoff_ms: int = Field(0, description="Hold-off time in milliseconds")


class SliceParameters(BaseModel):
    slice_name: str = Field(..., description="Slice identifier")
    slice_type: SliceType = SliceType.EMBB
    bandwidth_pct: Optional[float] = Field(None, ge=0, le=100, description="% of link capacity to allocate")
    bandwidth_mbps: Optional[float] = Field(None, ge=0)
    priority_level: int = Field(5, ge=1, le=8)
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)


class EnergyParameters(BaseModel):
    sleep_mode_enabled: bool = Field(False, description="Enable deep sleep mode")
    tx_power_reduction_db: Optional[float] = Field(None, description="Reduce TX power by X dB")
    schedule: Optional[str] = Field(None, description="E.g. '02:00-05:00'")


class SyncParameters(BaseModel):
    ptp_profile: Optional[str] = Field(None, description="e.g. 'G.8275.1'")
    synce_enabled: bool = Field(True, description="Enable SyncE")


class SecurityParameters(BaseModel):
    macsec_enabled: bool = Field(True, description="Enable MACsec encryption")
    encryption_algorithm: Optional[str] = Field(None, description="e.g. 'AES-256'")

# ──────────────────────────────────────────────────────────────────────────────
# D5.1 / 3GPP TS 28.312 & TM Forum ODA Lifecycle & Service Models
# ──────────────────────────────────────────────────────────────────────────────

class IntentLifecycle3GPP(str, Enum):
    """3GPP TS 28.312 Release 19 Intent Operational States (D5.1 Section 3.3.2.2)"""
    PREPARATION     = "preparation"     # Intent ingested, validated, decomposed
    COMMISSIONING   = "commissioning"   # SAGA transaction, domains allocating resources
    OPERATION       = "operation"       # Active, monitored by closed-loop assurance
    DECOMMISSIONING = "decommissioning" # Terminating, resource clean-up


class ServiceDLCState(str, Enum):
    """UNITY-6G Service Development LifeCycle (ServiceDLC) States (D5.1 Figure 2-10)"""
    ACTIVATION  = "activation"
    RUNNING     = "running"
    PAUSED      = "paused"      # Low-demand freeze for green energy / resource conservation
    SUSPENDED   = "suspended"   # Preempted / frozen for high-priority emergency services
    CLOSED      = "closed"


class ActuationOutcomeType(str, Enum):
    """UNITY-6G D2.4 Section 7.4 Typed Actuation Outcomes (Req-T23-ACT-03)."""
    ACKNOWLEDGED_VERIFIED   = "acknowledged_verified"    # Controller ACK + verified independent read-back state match (only success state)
    ACKNOWLEDGED_UNVERIFIED = "acknowledged_unverified"  # Controller ACK, but read-back absent, inconclusive or mismatched
    REJECTED                = "rejected"                 # Controller explicitly refused command
    UNRESOLVED              = "unresolved"               # Timeout or loss of transport; state unknown


class CustomerFacingService(BaseModel):
    """TM Forum TMF641 / IG1253 Customer Facing Service (CFS) (D5.1 Section 3.3.2.1)"""
    cfs_id: str = Field(default_factory=lambda: f"cfs-{str(uuid.uuid4())[:8]}")
    name: str
    service_category: str
    customer_sla: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requested_agent_loop: bool = Field(True, description="Whether customer requested an autonomous closed-loop agent")
    requested_mode: str = Field("closed_loop", description="Requested composition class: closed_loop or open_loop")


class ResourceFacingService(BaseModel):
    """TM Forum TMF652 Resource Facing Service (RFS) (D5.1 Section 3.3.2.1 & D2.4 Section 1.3)"""
    rfs_id: str = Field(default_factory=lambda: f"rfs-{str(uuid.uuid4())[:8]}")
    target_domain: str
    resource_type: str  # e.g. "agent-instantiation-service" or "wireless-xhaul-carrier"
    allocated_parameters: Dict[str, Any] = Field(default_factory=dict)
    agent_descriptor_id: Optional[str] = None
    agent_instance_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Canonical Intent Model
# ──────────────────────────────────────────────────────────────────────────────

class Intent(BaseModel):
    intent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent_type: IntentType
    status: IntentStatus = IntentStatus.PENDING
    target: IntentTarget
    parameters: Dict[str, Any] = Field(..., description="Type-specific parameters dict")
    priority: int = Field(5, ge=1, le=10, description="1=lowest, 10=highest priority")
    ttl_seconds: Optional[int] = Field(
        None, description="Time-to-live in seconds. None means indefinite."
    )
    raw_input: Optional[str] = Field(None, description="Original natural-language or JSON input")
    source: str = Field("operator", description="Who submitted (operator, agent, api)")
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied_at: Optional[datetime] = None
    error_message: Optional[str] = None
    applied_config: Optional[Dict[str, Any]] = None  # The config that was pushed
    architect_plan: Optional[Dict[str, Any]] = None  # Reasoning strategy from the Architect Agent
    context_intents: Optional[List[Dict[str, Any]]] = None # For conflict check
    tags: List[str] = Field(default_factory=list)

    # ── 3GPP TS 28.312 & D5.1 Lifecycle & TM Forum CFS/RFS ────────────────────
    state_3gpp: IntentLifecycle3GPP = IntentLifecycle3GPP.PREPARATION
    service_dlc_state: ServiceDLCState = ServiceDLCState.ACTIVATION
    cfs: Optional[CustomerFacingService] = None
    rfs_list: List[ResourceFacingService] = Field(default_factory=list)

    # ── D2.4 Governance & Actuation Attributes ────────────────────────────────
    actuation_outcome: Optional[ActuationOutcomeType] = None
    conflict_token: Optional[str] = Field(None, description="Conflict-resolution token checked at actuation (Req-T23-CG-07)")
    readback_evidence: Optional[Dict[str, Any]] = Field(None, description="Independent read-back verification evidence (Req-T23-ACT-04)")

    def decompose_to_cfs_rfs(self) -> None:
        """Decompose incoming intent into TM Forum CFS and RFS per D5.1 Section 3.3.2.1 and D2.4 Section 1.3."""
        cfs_name = f"CFS-{self.intent_type.value.upper()}-{self.target.identifier}"
        self.cfs = CustomerFacingService(
            name=cfs_name,
            service_category=f"{self.intent_type.value}_service",
            customer_sla=self.parameters,
            requested_agent_loop=True,
            requested_mode="closed_loop" if self.priority >= 5 else "open_loop"
        )

        # 1. RFS that runs the service instantiating the agent (using descriptor, authority ceiling, tuples)
        rfs_agent = ResourceFacingService(
            target_domain="transport-xhaul",
            resource_type="agent-instantiation-service",
            agent_descriptor_id=f"urn:unity6g:agent:ceragon:{self.intent_type.value}-loop",
            agent_instance_id=f"agent-{str(uuid.uuid4())[:8]}",
            allocated_parameters={
                "descriptor_id": f"urn:unity6g:agent:ceragon:{self.intent_type.value}-loop",
                "version": "1.0.0",
                "composition_class": "closed_loop",
                "authority_ceiling": "closed_loop_full" if self.priority >= 6 else "advisory",
                "target": self.target.identifier,
                "generation": 1,
                "tuples": ["MS", "AE", "DE", "ACT"],
                "operational_timeout": "30s"
            }
        )

        # 2. RFS that provides the underlying transport resources
        rfs_transport = ResourceFacingService(
            target_domain="transport-xhaul",
            resource_type="wireless-xhaul-carrier",
            allocated_parameters={
                "target": self.target.identifier,
                "type": self.intent_type.value,
                "params": self.parameters,
                "priority": self.priority
            }
        )
        self.rfs_list = [rfs_agent, rfs_transport]

        # 3. RFS for O-RAN F1u socket if slicing requested
        if self.intent_type == IntentType.SLICE or "slice" in str(self.parameters).lower():
            rfs_oran = ResourceFacingService(
                target_domain="oran",
                resource_type="f1u-socket-midhaul",
                allocated_parameters={"sst": self.parameters.get("sst", 1), "dscp": self.parameters.get("dscp", 6)}
            )
            self.rfs_list.append(rfs_oran)

    def model_post_init(self, __context: Any) -> None:
        if self.cfs is None:
            self.decompose_to_cfs_rfs()

    # ── Computed helpers ──────────────────────────────────────────────────────
    def typed_parameters(self):
        """Return a typed parameter model based on intent_type."""
        model_map = {
            IntentType.CAPACITY:   CapacityParameters,
            IntentType.QOS:        QoSParameters,
            IntentType.MODULATION: ModulationParameters,
            IntentType.RESILIENCE: ResilienceParameters,
            IntentType.SLICE:      SliceParameters,
            IntentType.ENERGY:     EnergyParameters,
            IntentType.SYNC:       SyncParameters,
            IntentType.SECURITY:   SecurityParameters,
        }
        cls = model_map.get(self.intent_type)
        return cls(**self.parameters) if cls else self.parameters

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        age = (datetime.now(timezone.utc) - self.submitted_at).total_seconds()
        return age > self.ttl_seconds

    def summary(self) -> str:
        return (
            f"[{self.intent_type.value.upper()}] {self.target.target_type.value}:"
            f"{self.target.identifier} priority={self.priority} status={self.status.value}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


# ──────────────────────────────────────────────────────────────────────────────
# Device Configuration Model (output of translation)
# ──────────────────────────────────────────────────────────────────────────────

class DeviceConfig(BaseModel):
    device_id: str
    config_type: str                        # e.g. "radio", "qos", "protection"
    yang_module: str = "ceragon-radio-link" # e.g. "ceragon-radio-link", "radio-bridge-tg-radio-dn"
    parameters: Dict[str, Any]             # Flat config parameters
    yang_xml: Optional[str] = None         # Full NETCONF edit-config XML
    intent_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


# ──────────────────────────────────────────────────────────────────────────────
# Translation Result
# ──────────────────────────────────────────────────────────────────────────────

class TranslationResult(BaseModel):
    intent_id: str
    success: bool
    device_configs: List[DeviceConfig] = Field(default_factory=list)
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    explanation: str = Field("", description="Human-readable explanation of the translation")
