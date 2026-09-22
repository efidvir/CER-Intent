"""
Adapter Daemon Service
======================
Background worker providing continuous synchronization between Ceragon hardware and TeraFlowSDN.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from typing import Optional

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.driver import TFSCeragonDriver

logger = logging.getLogger(__name__)


class AdapterService:
    """Daemon process syncing physical Ceragon device state into TFS."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig()
        self.driver = TFSCeragonDriver(self.config)
        self._running = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Run the service loop synchronously (blocks until interrupted)."""
        self._running = True
        logger.info("Starting Ceragon TFS Adapter Daemon...")
        logger.info(f"Target Ceragon Device: {self.config.ceragon_base_url}")
        logger.info(f"Target TeraFlowSDN NBI: {self.config.tfs_url}")
        logger.info(f"Sync Interval: {self.config.sync_interval_seconds}s")

        # Initial probe
        ok, msg = self.driver.connect()
        if not ok:
            logger.warning(f"Initial connection check warning: {msg}")
        else:
            logger.info(f"Initial connection check successful: {msg}")

        # Initial sync
        try:
            res = self.driver.sync_to_tfs()
            logger.info(f"Initial sync complete: Device {res.get('device_name')} registered in TFS")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")

        # Main loop
        while not self._stop_event.is_set():
            try:
                self._stop_event.wait(self.config.sync_interval_seconds)
                if self._stop_event.is_set():
                    break
                
                logger.debug("Executing scheduled synchronization cycle...")
                res = self.driver.sync_to_tfs()
                logger.debug(f"Sync cycle OK: {res.get('device_uuid')}")
            except Exception as e:
                logger.error(f"Error during synchronization loop: {e}")

        logger.info("Ceragon TFS Adapter Daemon stopped gracefully.")

    def stop(self) -> None:
        """Signal the daemon loop to stop."""
        self._running = False
        self._stop_event.set()
