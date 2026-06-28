"""Repo-root resolution shared across the package.

Used by config loaders and asset finders (settings.yaml, JSON schema, prompts,
data dirs). Pure stdlib so any module can import without dragging in yaml /
dotenv / requests.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Walk up from this file until ``pyproject.toml`` is found.

    Robust to depth changes in the src tree and to file relocation; only
    assumption is that ``pyproject.toml`` lives at the repo root above this
    package.
    """
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    raise RuntimeError(f"Could not locate repo root: no pyproject.toml above {__file__}")
