"""
Device Profile Schema
====================
Models for hardware capabilities and configuration guides.
Used by the Intent Architect Agent to learn how to configure specific device types.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Capability(BaseModel):
    """Specific measurable capability of a hardware device."""
    name: str
    value: Any
    unit: str = ""
    description: str = ""


class ConfigParamMapping(BaseModel):
    """Maps an abstract intent parameter to a device-specific configuration key/path."""
    intent_param: str
    config_key: str                     # e.g., "mrmc_script_id" or "qos/traffic-class"
    transformation: Optional[str] = None # e.g., "direct", "scale_100", "lookup"
    default: Optional[Any] = None


class DeviceProfile(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    """
    Complete knowledge profile for a specific transport device type.
    Includes hardware limits, config mappings, and behavioral guides.
    """
    model_name: str
    vendor: str = "Ceragon"
    type: str = "wireless_transport"
    
    # Hardware Limits
    capabilities: Dict[str, Capability] = Field(default_factory=dict)
    
    # Configuration Rules
    supported_modulations: List[str] = Field(default_factory=list)
    channel_bandwidths_mhz: List[int] = Field(default_factory=list)
    
    # API / Configuration Guide
    config_mappings: List[ConfigParamMapping] = Field(default_factory=list)
    api_guide: str = ""  # Natural language 'cheat sheet' for the agent
    
    def get_capability(self, name: str, default=None) -> Any:
        cap = self.capabilities.get(name)
        return cap.value if cap else default

    def to_dict(self) -> dict:
        return self.model_dump()
