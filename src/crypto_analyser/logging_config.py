"""Structured logging configuration for crypto-analyser.

Provides a `get_logger` factory that returns loggers with both
console and rotating-file handlers.  Logs are written to ``logs/app.log``
relative to the project root.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Final

_LOG_DIR_NAME: Final[str] = "logs"
_LOG_FILE_NAME: Final[str] = "app.log"
_LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

# Module-level cache so repeated calls are cheap
_handler_cache: list[logging.Handler] = []


def _project_root() -> Path:
    """Return the project root by walking up from this file."""
    return Path(__file__).resolve().parent.parent.parent


def _ensure_handlers() -> list[logging.Handler]:
    """Create (once) and return the shared handler list."""
    global _handler_cache  # noqa: PLW0603
    if _handler_cache:
        return _handler_cache

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler — INFO and above
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    # Rotating file handler — DEBUG and above
    log_dir = _project_root() / _LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    file_path = log_dir / _LOG_FILE_NAME

    # Use WatchedFileHandler so external logrotation (e.g. logrotate) works
    file_handler = logging.handlers.WatchedFileHandler(file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    _handler_cache = [console, file_handler]
    return _handler_cache


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger with project-standard handlers attached.

    Args:
        name: Logger namespace (defaults to the caller's module name
            when imported and used directly).

    Returns:
        A :class:`logging.Logger` instance writing to both stdout and
        ``logs/app.log``.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers on repeated calls
    if not logger.handlers:
        for handler in _ensure_handlers():
            logger.addHandler(handler)

    return logger


def configure_root_logger(level: int = logging.DEBUG) -> None:
    """Configure the root logger with project handlers.

    Useful in entry-point scripts that want *all* library logs
    (e.g. ``requests``, ``urllib3``) to flow through the same sinks.
    """
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        for handler in _ensure_handlers():
            root.addHandler(handler)
