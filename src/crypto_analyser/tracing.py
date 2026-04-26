"""Langfuse tracing integration for crypto-analyser.

Provides decorators and helpers to automatically trace pipeline steps
and attach scores to Langfuse traces.
"""
from __future__ import annotations

import functools
import os
from typing import Any, Callable, TypeVar

from crypto_analyser.config import Config, load_config

_F = TypeVar("_F", bound=Callable[..., Any])

# Global Langfuse instance (lazily initialised)
_langfuse_instance: Any | None = None
_langfuse_initialised: bool = False


def _get_langfuse() -> Any | None:
    """Return a Langfuse client initialised from config, or None if unavailable."""
    global _langfuse_instance, _langfuse_initialised  # noqa: PLW0603

    if _langfuse_initialised:
        return _langfuse_instance

    try:
        from langfuse import Langfuse
    except Exception:  # pragma: no cover
        _langfuse_initialised = True
        return None

    cfg: Config | None = None
    try:
        cfg = load_config()
    except Exception:
        _langfuse_initialised = True
        return None

    # Allow env overrides for CI / containers
    host = os.getenv("LANGFUSE_HOST") or cfg.get("langfuse.host")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY") or cfg.get("langfuse.public_key")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY") or cfg.get("langfuse.secret_key")

    # Skip if any are missing or still placeholders
    if not host or not public_key or not secret_key:
        _langfuse_initialised = True
        return None

    placeholder_patterns = ("changeme_", "your_", "placeholder")
    for value in (host, public_key, secret_key):
        if any(p in str(value).lower() for p in placeholder_patterns):
            _langfuse_initialised = True
            return None

    try:
        _langfuse_instance = Langfuse(
            host=str(host).rstrip("/"),
            public_key=str(public_key),
            secret_key=str(secret_key),
        )
    except Exception:
        _langfuse_initialised = True
        return None

    _langfuse_initialised = True
    return _langfuse_instance


def trace_step(
    *,
    name: str | None = None,
    capture_input: bool = True,
    capture_output: bool = True,
) -> Callable[[_F], _F]:
    """Decorator that traces a function execution as a Langfuse span.

    If Langfuse is unavailable or mis-configured the function runs
    normally — tracing is best-effort.

    Args:
        name: Custom trace/span name (defaults to ``func.__name__``).
        capture_input: Whether to record positional and keyword args.
        capture_output: Whether to record the return value.
    """

    def decorator(func: _F) -> _F:
        trace_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            lf = _get_langfuse()
            if lf is None:
                return func(*args, **kwargs)

            try:
                trace = lf.trace(name=trace_name)
            except Exception:
                return func(*args, **kwargs)

            try:
                span = trace.span(
                    name=trace_name,
                    input=({"args": args, "kwargs": kwargs} if capture_input else None),
                )
            except Exception:
                span = None

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                try:
                    if span is not None:
                        span.update(
                            output=None,
                            level="ERROR",
                            status_message=str(exc),
                        )
                except Exception:
                    pass
                raise
            else:
                try:
                    if span is not None:
                        span.update(
                            output=result if capture_output else None,
                            level="DEFAULT",
                        )
                except Exception:
                    pass
                return result

        return wrapper  # type: ignore[return-value]

    return decorator


def score_attachment(
    trace_id: str | None,
    name: str,
    value: float,
    comment: str | None = None,
) -> None:
    """Attach a numeric score to an existing Langfuse trace.

    If Langfuse is unavailable this is a no-op.

    Args:
        trace_id: The Langfuse trace ID (e.g. from ``trace.id``).
        name: Score metric name (e.g. ``"faithfulness"``).
        value: Numeric score value.
        comment: Optional human-readable explanation.
    """
    if trace_id is None:
        return

    lf = _get_langfuse()
    if lf is None:
        return

    try:
        lf.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
    except Exception:
        pass
