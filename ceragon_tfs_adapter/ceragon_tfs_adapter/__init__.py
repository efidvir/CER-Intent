"""
Ceragon TeraFlowSDN (TFS) REST Adapter
======================================
Connects the Ceragon wireless transport portfolio to ETSI TeraFlowSDN via REST / RESTCONF (RFC 8040):
FibeAir IP-20, IP-50, IP-100 (CeraOS) and Siklu EtherHaul / MultiHaul TG.
See ``ceragon_tfs_adapter.portfolio`` for the model catalog and capability matrix,
and ``ceragon_tfs_adapter.schemas`` for the 85-module YANG 1.1 schema repository.
"""

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.client import CeragonRestClient
from ceragon_tfs_adapter.models import (
    CeragonDeviceState,
    NetworkInterface,
    PMTelemetrySample,
    RadioLinkState,
    RadioSector,
)
from ceragon_tfs_adapter.mapper import CeragonTFSMapper
from ceragon_tfs_adapter.registrar import TFSRegistrar
from ceragon_tfs_adapter.driver import TFSCeragonDriver
from ceragon_tfs_adapter.portfolio import ProductSpec, resolve_model, list_models, check_config_support
from ceragon_tfs_adapter.schemas import (
    list_schemas,
    get_schema_content,
    get_schema_metadata,
    get_schemas_for_family,
    validate_schema_closure,
)

__version__ = "1.2.0"
__all__ = [
    "AdapterConfig",
    "CeragonRestClient",
    "CeragonDeviceState",
    "NetworkInterface",
    "RadioSector",
    "RadioLinkState",
    "PMTelemetrySample",
    "CeragonTFSMapper",
    "TFSRegistrar",
    "TFSCeragonDriver",
    "ProductSpec",
    "resolve_model",
    "list_models",
    "check_config_support",
    "list_schemas",
    "get_schema_content",
    "get_schema_metadata",
    "get_schemas_for_family",
    "validate_schema_closure",
]
