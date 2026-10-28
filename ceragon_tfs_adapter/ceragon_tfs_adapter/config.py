"""
Adapter Configuration
=====================
Loads configuration settings from environment variables, CLI options, or config dictionaries.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdapterConfig:
    """Holds connectivity and operational parameters for the Ceragon TFS Adapter."""

    # Ceragon Device Parameters
    device_ip: str = field(default_factory=lambda: os.getenv("CERAGON_IP", "192.168.1.225"))
    device_port: int = field(default_factory=lambda: int(os.getenv("CERAGON_PORT", "80")))
    username: str = field(default_factory=lambda: os.getenv("CERAGON_USER", "admin"))
    password: str = field(default_factory=lambda: os.getenv("CERAGON_PASSWORD", "admin"))
    use_https: bool = field(default_factory=lambda: os.getenv("CERAGON_USE_HTTPS", "false").lower() == "true")
    verify_tls: bool = field(default_factory=lambda: os.getenv("CERAGON_VERIFY_TLS", "false").lower() == "true")
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("CERAGON_TIMEOUT_SEC", "10")))
    # Optional product hint (e.g. "IP-50C", "EH-8010FX", "MH-N366"). Used to pick the
    # southbound API flavor before probing and as a fallback when the datastore
    # does not report a model name.
    model_hint: Optional[str] = field(default_factory=lambda: os.getenv("CERAGON_MODEL"))

    # TeraFlowSDN Parameters
    tfs_url: str = field(default_factory=lambda: os.getenv("TERAFLOW_URL", "http://localhost:8088").rstrip("/"))
    tfs_context: str = field(default_factory=lambda: os.getenv("TFS_CONTEXT", "admin"))
    tfs_topology: str = field(default_factory=lambda: os.getenv("TFS_TOPOLOGY", "admin"))
    tfs_token: Optional[str] = field(default_factory=lambda: os.getenv("TERAFLOW_TOKEN"))

    # Adapter Operational Parameters
    sync_interval_seconds: int = field(default_factory=lambda: int(os.getenv("ADAPTER_SYNC_INTERVAL_SEC", "15")))
    log_level: str = field(default_factory=lambda: os.getenv("ADAPTER_LOG_LEVEL", "INFO"))

    @property
    def ceragon_base_url(self) -> str:
        scheme = "https" if self.use_https or self.device_port in (443, 8443) else "http"
        port = 443 if (scheme == "https" and self.device_port == 80) else self.device_port
        return f"{scheme}://{self.device_ip}:{port}"
