"""
Governance & Conflict Resolution Package
=========================================
Implements the UNITY-6G D2.4 Chapter 10 Conflict Fabric interface,
mediating between independently reasoning agent loops before actuation.
"""
from cer_intent.governance.conflict_fabric import (
    VerdictType,
    ConflictVerdict,
    ConflictFabricClient,
    get_conflict_fabric
)

__all__ = [
    "VerdictType",
    "ConflictVerdict",
    "ConflictFabricClient",
    "get_conflict_fabric"
]
