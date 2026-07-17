"""Runtime workspace and packaged-asset path resolution."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return checkout root when editable, otherwise current workspace."""
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    return Path.cwd().resolve()


def data_root(path: str | Path = "data") -> Path:
    """Resolve runtime data directory against current workspace."""
    path = Path(path)
    return path if path.is_absolute() else repo_root() / path


def asset_path(name: str) -> Path:
    """Return a packaged immutable asset path."""
    return Path(__file__).with_name("assets") / name
