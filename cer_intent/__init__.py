"""CER-Intent package."""
import os
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("cer-intent")
except PackageNotFoundError:
    __version__ = os.getenv("CER_INTENT_VERSION", "0.2.0")
