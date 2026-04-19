"""
Hardware Knowledge Base
=======================
Service that manages hardware profiles and device capabilities.
Allows the Intent Architect to reason about device-specific limits.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from cer_intent.device.profiles.schema import DeviceProfile

logger = logging.getLogger(__name__)

DEFAULT_PROFILES_DIR = Path(__file__).parent / "profiles" / "data"


class HardwareKnowledgeBase:
    """
    Registry of hardware profiles loaded from JSON files.
    """

    def __init__(self, profiles_dir: Optional[Path] = None):
        self.profiles_dir = profiles_dir or DEFAULT_PROFILES_DIR
        self._profiles: Dict[str, DeviceProfile] = {}
        self._load_all_profiles()

    def _load_all_profiles(self):
        """Discovers and loads all .json profiles in the profiles directory."""
        if not self.profiles_dir.exists():
            logger.warning(f"Profiles directory not found: {self.profiles_dir}")
            return

        for profile_file in self.profiles_dir.glob("*.json"):
            try:
                with open(profile_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    profile = DeviceProfile(**data)
                    self._profiles[profile.model_name] = profile
                    logger.info(f"Loaded hardware profile: {profile.model_name} ({profile.vendor})")
            except Exception as e:
                logger.error(f"Failed to load profile {profile_file.name}: {e}")

        # Add a generic fallback profile if not present
        if "Generic" not in self._profiles:
            self._profiles["Generic"] = DeviceProfile(
                model_name="Generic",
                vendor="Generic",
                api_guide="Base configuration for undocumented transport hardware."
            )

    def get_profile(self, model_name: str) -> DeviceProfile:
        """Returns the profile for a given model, fallback to Generic if not found."""
        return self._profiles.get(model_name, self._profiles["Generic"])

    def list_models(self) -> List[str]:
        return list(self._profiles.keys())

    def get_all_profiles(self) -> List[DeviceProfile]:
        return list(self._profiles.values())
