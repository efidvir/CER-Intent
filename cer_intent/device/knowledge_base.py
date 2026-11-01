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

        # Enrich with full 36-model Ceragon portfolio from ceragon_tfs_adapter
        try:
            from ceragon_tfs_adapter.portfolio import list_models
            from ceragon_tfs_adapter.schemas import get_schemas_for_family
            from cer_intent.device.profiles.schema import Capability
            for spec in list_models():
                if spec.model not in self._profiles:
                    band_str = ", ".join(f"{b.name} ({b.freq_min_ghz}-{b.freq_max_ghz} GHz)" for b in spec.bands)
                    yang_mods = get_schemas_for_family(spec.family)
                    caps = {
                        "max_capacity_gbps": Capability(name="max_capacity_gbps", value=spec.max_capacity_gbps, unit="Gbps", description=f"{spec.family} peak PHY capacity"),
                        "carriers": Capability(name="carriers", value=spec.radio_carriers, unit="carriers", description="Integrated radio carriers per unit"),
                        "family": Capability(name="family", value=spec.family, unit="", description="Ceragon product family"),
                        "dialect": Capability(name="dialect", value=spec.api_flavor, unit="", description="Southbound YANG/RESTCONF dialect"),
                        "form_factor": Capability(name="form_factor", value=spec.form_factor, unit="", description="Hardware form factor"),
                        "bands_ghz": Capability(name="bands_ghz", value=band_str, unit="GHz", description="Supported RF frequency bands"),
                        "features": Capability(name="features", value=", ".join(spec.features), unit="", description="Hardware feature flags"),
                    }
                    self._profiles[spec.model] = DeviceProfile(
                        model_name=spec.model,
                        vendor="Ceragon",
                        type=spec.family,
                        capabilities=caps,
                        supported_modulations=[spec.max_modulation] if spec.max_modulation else ["QPSK", "16QAM", "64QAM", "256QAM", "2048QAM"],
                        channel_bandwidths_mhz=list(spec.channel_bandwidths_mhz),
                        api_guide=(
                            f"Ceragon {spec.model} ({spec.family} / {spec.product_line}, {spec.form_factor}) — "
                            f"Dialect: {spec.api_flavor}. Bands: {band_str}. "
                            f"Max Capacity: {spec.max_capacity_gbps} Gbps ({spec.radio_carriers}x carrier). "
                            f"YANG Modules ({len(yang_mods)}): {', '.join(yang_mods[:6])}."
                        ),
                    )
        except Exception as e:
            logger.warning(f"Portfolio enrichment skipped: {e}")

        # Add a generic fallback profile if not present
        if "Generic" not in self._profiles:
            self._profiles["Generic"] = DeviceProfile(
                model_name="Generic",
                vendor="Generic",
                api_guide="Base configuration for undocumented transport hardware."
            )

    def get_profile(self, model_name: str) -> DeviceProfile:
        """Returns the profile for a given model, fallback to Generic if not found."""
        if model_name in self._profiles:
            return self._profiles[model_name]
        try:
            from ceragon_tfs_adapter.portfolio import resolve_model
            spec = resolve_model(model_name)
            if spec and spec.model in self._profiles:
                return self._profiles[spec.model]
        except Exception:
            pass
        return self._profiles["Generic"]

    def list_models(self) -> List[str]:
        return list(self._profiles.keys())

    def get_all_profiles(self) -> List[DeviceProfile]:
        return list(self._profiles.values())
