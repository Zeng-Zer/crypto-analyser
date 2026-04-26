"""Configuration loader for crypto-analyser.

Loads config/settings.yaml and exposes a typed Config dataclass.
Warns if placeholder API keys are detected.
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_PLACEHOLDER_PATTERNS: tuple[str, ...] = ("changeme_", "your_", "placeholder")


def _is_placeholder(value: str) -> bool:
    """Check if a config value is still a placeholder."""
    return any(pattern in value.lower() for pattern in _PLACEHOLDER_PATTERNS)


def _check_placeholders(config: dict) -> list[str]:
    """Recursively scan config dict for unfilled placeholders."""
    found: list[str] = []

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                walk(val, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            for idx, val in enumerate(obj):
                walk(val, f"{path}[{idx}]")
        elif isinstance(obj, str) and obj.strip() and _is_placeholder(obj):
            found.append(path)

    walk(config)
    return found


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to settings.yaml. Defaults to config/settings.yaml
            relative to the project root.

    Returns:
        Config: Typed configuration object.

    Raises:
        FileNotFoundError: If config file does not exist.
        RuntimeError: If critical placeholder keys are not filled.
    """
    if config_path is None:
        root = Path(__file__).resolve().parent.parent.parent
        config_path = root / "config" / "settings.yaml"
        # Fallback if src layout changes — search from cwd up to project root
        if not config_path.exists():
            for ancestor in Path.cwd().resolve().parents:
                candidate = ancestor / "config" / "settings.yaml"
                if candidate.exists():
                    config_path = candidate
                    break

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    placeholders = _check_placeholders(raw)
    if placeholders:
        required_api_keys = [
            p for p in placeholders
            if p.startswith("api_keys.") or p.startswith("langfuse.")
        ]
        msg = (
            f"Placeholder values detected in config: {', '.join(placeholders)}\n"
            "Please fill in your API keys in config/settings.yaml."
        )
        if required_api_keys:
            raise RuntimeError(msg)
        warnings.warn(msg, stacklevel=2)

    return Config(raw)


@dataclass(frozen=True, slots=True)
class Config:
    """Typed wrapper around the raw YAML configuration."""

    _data: dict

    def __getitem__(self, key: str) -> Any:
        keys = key.split(".")
        value = self._data
        for k in keys:
            if not isinstance(value, dict):
                raise KeyError(f"Config path not found: {key}")
            value = value[k]
        return value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __getattr__(self, name: str) -> Any:
        """Dynamically resolve top-level config keys as attributes."""
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(f"Config has no key '{name}'") from exc

    def to_dict(self) -> dict:
        return self._data.copy()
