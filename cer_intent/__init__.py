"""CER-Intent package."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("cer-intent")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"
