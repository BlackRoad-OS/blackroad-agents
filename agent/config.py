"""Configuration helpers for the BlackRoad agent services."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

CONFIG_PATH = Path(os.environ.get("BLACKROAD_CONFIG", "/etc/blackroad/config.yaml"))
DEFAULT_USER = "jetson"

DEFAULTS: Dict[str, Any] = {
    "jetson": {"host": "192.168.4.23", "user": "jetson"},
    "auth": {"token": ""},
}


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_update(dict(base[key]), value)
        else:
            base[key] = value
    return base


def load() -> Dict[str, Any]:
    """Load the persisted configuration merged with defaults."""
    data: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            raw = yaml.safe_load(CONFIG_PATH.read_text())
            if isinstance(raw, dict):
                data = raw
        except yaml.YAMLError:
            data = {}
    from copy import deepcopy
    merged = deepcopy(DEFAULTS)
    return _deep_update(merged, data)


def save(config: Dict[str, Any]) -> None:
    """Persist the configuration to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(config, sort_keys=True) if config else "{}\n"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(CONFIG_PATH.parent), encoding="utf-8") as tmp:
        tmp.write(serialized)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, CONFIG_PATH)


def auth_token() -> str:
    """Return the configured authentication token (empty when disabled)."""
    return str(load().get("auth", {}).get("token", ""))


def active_target() -> Tuple[str, str]:
    """Return the currently configured Jetson host and user."""
    cfg = load()
    jetson = cfg.get("jetson", {})
    host = jetson.get("host", DEFAULTS["jetson"]["host"])
    user = jetson.get("user", DEFAULTS["jetson"]["user"])
    return (host, user)


def set_target(host: str, user: str = DEFAULT_USER) -> None:
    """Persist a new Jetson target."""
    if not host:
        raise ValueError("host must be provided")
    user = user or DEFAULT_USER
    config = load()
    jetson = config.get("jetson") if isinstance(config.get("jetson"), dict) else {}
    jetson.update({
        "host": host,
        "user": user,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    config["jetson"] = jetson
    save(config)


__all__ = ["load", "save", "auth_token", "active_target", "set_target", "DEFAULT_USER"]
