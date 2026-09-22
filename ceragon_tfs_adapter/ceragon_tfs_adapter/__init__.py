"""
Ceragon TeraFlowSDN (TFS) REST Adapter
======================================
Connects Ceragon wireless transport nodes (MultiHaul TG / Terragraph / EtherHaul / CeraOS IP-50)
to ETSI TeraFlowSDN via REST / RESTCONF (RFC 8040).
"""

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.client import CeragonRestClient
from ceragon_tfs_adapter.models import CeragonDeviceState, NetworkInterface, RadioSector
from ceragon_tfs_adapter.mapper import CeragonTFSMapper
from ceragon_tfs_adapter.registrar import TFSRegistrar
from ceragon_tfs_adapter.driver import TFSCeragonDriver

__version__ = "1.0.0"
__all__ = [
    "AdapterConfig",
    "CeragonRestClient",
    "CeragonDeviceState",
    "NetworkInterface",
    "RadioSector",
    "CeragonTFSMapper",
    "TFSRegistrar",
    "TFSCeragonDriver",
]
