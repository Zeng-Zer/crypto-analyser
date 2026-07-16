from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from crypto_analyser._paths import asset_path


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file and inject .env secrets.

    Args:
        config_path: Path to settings.yaml.

    Returns:
        Config: Typed configuration object.
    """
    # Load environment variables from the .env file
    load_dotenv()

    if config_path is None:
        config_path = asset_path("settings.yaml")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

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
