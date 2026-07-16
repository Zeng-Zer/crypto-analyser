"""In-process orchestration for the historical analysis pipeline."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from crypto_analyser._paths import repo_root
from crypto_analyser.classification.episodes import classify_batch
from crypto_analyser.config import Config, load_config
from crypto_analyser.detection.zscore import detect_episodes
from crypto_analyser.downloaders.funding import download_funding
from crypto_analyser.downloaders.ohlcv import download_ohlcv
from crypto_analyser.downloaders.open_interest import download_oi_range
from crypto_analyser.features.derivatives import write_context
from crypto_analyser.rag.retrieval import write_episode_contexts
from crypto_analyser.reporting.json_reports import VALID_MODES, generate
from crypto_analyser.tracing import trace_step


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


def _path(cfg: Config, key: str, fallback: str) -> Path:
    path = Path(cfg.get(key, fallback))
    return path if path.is_absolute() else repo_root() / path


def _require_environment(*names: str) -> dict[str, str]:
    values = {name: os.getenv(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"required environment variables missing: {', '.join(missing)}")
    return {name: value for name, value in values.items() if value is not None}


@trace_step(name="pipeline.run")
def run_pipeline(
    symbol: str,
    start: str,
    end: str,
    mode: str = "derivatives_only",
    *,
    skip_download: bool = False,
    force_download: bool = False,
    config: Config | None = None,
) -> Path:
    """Run one historical analysis and return its summary report path."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")
    cfg = config or load_config()
    months = months_in_range(start, end)

    if not skip_download:
        base_url = cfg.get("sources.binance.base_url", "https://data.binance.vision")
        interval = cfg.get("sources.binance.intervals.ohlcv", "5m")
        for month in months:
            if not download_ohlcv(
                symbol,
                month,
                _path(cfg, "paths.ohlcv_dir", "data/ohlcv"),
                interval=interval,
                base_url=base_url,
                force=force_download,
            ):
                raise RuntimeError(f"OHLCV download failed for {month}")
            if not download_funding(
                symbol,
                month,
                _path(cfg, "paths.funding_dir", "data/funding"),
                base_url=base_url,
                force=force_download,
            ):
                raise RuntimeError(f"funding download failed for {month}")
        if not download_oi_range(
            symbol,
            date.fromisoformat(start),
            date.fromisoformat(end),
            _path(cfg, "paths.oi_dir", "data/oi"),
            base_url=base_url,
            force=force_download,
        ):
            raise RuntimeError("open-interest download failed")

    anomaly_cfg = cfg["anomaly_detection"]
    anomalies = detect_episodes(
        symbol,
        start,
        end,
        window_hours=float(anomaly_cfg.get("window_hours", 24)),
        threshold=float(anomaly_cfg.get("threshold", 2.5)),
        min_consecutive=int(anomaly_cfg.get("min_consecutive", 2)),
    )
    anomalies_path = _path(cfg, "paths.anomalies_dir", "data/anomalies") / f"{symbol}_{start}_{end}.json"
    anomalies_path.parent.mkdir(parents=True, exist_ok=True)
    anomalies_path.write_text(json.dumps(anomalies, indent=2), encoding="utf-8")

    if mode != "news_only":
        write_context(anomalies_path)
    if mode in {"derivatives_rag", "news_only"}:
        env = _require_environment("DATABASE_URL", "LLM_API_URL", "LLM_API_KEY")
        write_episode_contexts(
            anomalies_path,
            env["DATABASE_URL"],
            env["LLM_API_URL"],
            env["LLM_API_KEY"],
        )

    classify_batch(anomalies_path, mode)
    summary_path, _ = generate(symbol, start, end, mode)
    return summary_path
