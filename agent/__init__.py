"""Public interface for the BlackRoad agent package.

This package provides:
- Telemetry collection (local and remote)
- Job execution on remote hosts
- Device flashing utilities
- Model inference capabilities
- Audio transcription
- Configuration management
"""
from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import active_target, auth_token, load, save, set_target

__version__ = "0.1.0"

# Default configuration values
DEFAULT_REMOTE_HOST = os.getenv("BLACKROAD_REMOTE_HOST", "jetson-01")
DEFAULT_REMOTE_USER = os.getenv("BLACKROAD_REMOTE_USER", "pi")
DEFAULT_DB_PATH = Path(os.getenv("BLACKROAD_JOBS_DB", "/var/lib/blackroad/jobs.db"))

# Lazy-loaded module exports
_MODULE_EXPORTS = {
    "discover": "discover",
    "flash": "flash",
    "jobs": "jobs",
    "models": "models",
    "store": "store",
    "telemetry": "telemetry",
    "transcribe": "transcribe",
}

if TYPE_CHECKING:
    from . import discover, flash, jobs, models, store, telemetry, transcribe


def __getattr__(name: str) -> Any:
    """Lazily import agent submodules when accessed."""
    if name in _MODULE_EXPORTS:
        module = import_module(f"{__name__}.{_MODULE_EXPORTS[name]}")
        globals()[name] = module
        return module
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _host_user(host: str | None = None, user: str | None = None) -> tuple[str, str]:
    """Resolve the remote host/user pair for SSH operations."""
    resolved_host = host or DEFAULT_REMOTE_HOST
    resolved_user = user or DEFAULT_REMOTE_USER
    return resolved_host, resolved_user


__all__ = [
    # Version
    "__version__",
    # Configuration
    "active_target",
    "auth_token",
    "load",
    "save",
    "set_target",
    # Defaults
    "DEFAULT_REMOTE_HOST",
    "DEFAULT_REMOTE_USER",
    "DEFAULT_DB_PATH",
    # Utilities
    "_host_user",
    # Lazy-loaded modules
    "discover",
    "flash",
    "jobs",
    "models",
    "store",
    "telemetry",
    "transcribe",
]
