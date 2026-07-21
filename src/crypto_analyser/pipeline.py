"""In-process orchestration for the historical analysis pipeline."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from crypto_analyser._paths import data_root
from crypto_analyser.classification.episodes import classify_batch
from crypto_analyser.constants import (
    BINANCE_BASE_URL,
    DRAWDOWN_HOURS,
    DRAWDOWN_THRESHOLD,
    LLM_MODEL,
    MAX_GAP,
    MIN_CONSECUTIVE,
    OHLCV_INTERVAL,
    RETURN_HOURS,
    RETURN_THRESHOLD,
    WINDOW_HOURS,
    ZSCORE_THRESHOLD,
)
from crypto_analyser.detection.zscore import detect_episodes
from crypto_analyser.downloaders.funding import download_funding
from crypto_analyser.downloaders.ohlcv import download_ohlcv
from crypto_analyser.downloaders.open_interest import download_oi_range
from crypto_analyser.features.derivatives import write_context
from crypto_analyser.rag.retrieval import write_episode_contexts
from crypto_analyser.reporting.json_reports import VALID_MODES, generate


def months_in_range(start: str, end: str) -> list[str]:
    """Return each calendar month touched by an inclusive date range."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start date must not be after end date")
    months: list[str] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _require_environment(*names: str) -> dict[str, str]:
    values = {name: os.getenv(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"required environment variables missing: {', '.join(missing)}")
    return {name: value for name, value in values.items() if value is not None}


def run_pipeline(
    symbol: str,
    start: str,
    end: str,
    mode: str = "derivatives_only",
    *,
    data_dir: str | Path = "data",
    skip_download: bool = False,
    force_download: bool = False,
    window_hours: float = WINDOW_HOURS,
    threshold: float = ZSCORE_THRESHOLD,
    drawdown_hours: float = DRAWDOWN_HOURS,
    drawdown_threshold: float = DRAWDOWN_THRESHOLD,
    return_hours: float = RETURN_HOURS,
    return_threshold: float = RETURN_THRESHOLD,
    max_gap: int = MAX_GAP,
    min_consecutive: int = MIN_CONSECUTIVE,
    llm_model: str = LLM_MODEL,
) -> Path:
    """Run one historical analysis and return its summary report path."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")
    root = data_root(data_dir)
    months = months_in_range(start, end)

    if not skip_download:
        for month in months:
            if not download_ohlcv(
                symbol,
                month,
                root / "ohlcv",
                interval=OHLCV_INTERVAL,
                base_url=BINANCE_BASE_URL,
                force=force_download,
            ):
                raise RuntimeError(f"OHLCV download failed for {month}")
            if not download_funding(
                symbol,
                month,
                root / "funding",
                base_url=BINANCE_BASE_URL,
                force=force_download,
            ):
                raise RuntimeError(f"funding download failed for {month}")
        if not download_oi_range(
            symbol,
            date.fromisoformat(start),
            date.fromisoformat(end),
            root / "oi",
            base_url=BINANCE_BASE_URL,
            force=force_download,
        ):
            raise RuntimeError("open-interest download failed")

    anomalies = detect_episodes(
        symbol,
        start,
        end,
        data_dir=root,
        window_hours=window_hours,
        threshold=threshold,
        drawdown_hours=drawdown_hours,
        drawdown_threshold=drawdown_threshold,
        return_hours=return_hours,
        return_threshold=return_threshold,
        max_gap=max_gap,
        min_consecutive=min_consecutive,
    )
    anomalies_path = root / "anomalies" / f"{symbol}_{start}_{end}.json"
    anomalies_path.parent.mkdir(parents=True, exist_ok=True)
    anomalies_path.write_text(json.dumps(anomalies, indent=2), encoding="utf-8")

    if mode != "news_only":
        write_context(anomalies_path, data_dir=root)
    if mode in {"derivatives_rag", "news_only"}:
        env = _require_environment("DATABASE_URL", "LLM_API_URL", "LLM_API_KEY")
        write_episode_contexts(
            anomalies_path,
            env["DATABASE_URL"],
            env["LLM_API_URL"],
            env["LLM_API_KEY"],
            output_dir=root / "rag",
        )

    classify_batch(
        anomalies_path,
        mode,
        data_dir=root,
        model=llm_model,
    )
    summary_path, _ = generate(symbol, start, end, mode, data_dir=root)
    return summary_path
