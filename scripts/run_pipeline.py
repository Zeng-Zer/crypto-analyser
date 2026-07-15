#!/usr/bin/env python3
"""Run the historical anomaly-classification pipeline for one date window.

Stages execute as subprocesses so each component uses the same CLI path whether
run independently or through this orchestrator. Milestone 1 is batch-only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date

from crypto_analyser._paths import repo_root
from crypto_analyser.tracing import trace_step

VALID_MODES = {"derivatives_only", "derivatives_rag", "news_only"}


def _months_in_range(start: str, end: str) -> list[str]:
    """Return every calendar month covered by an inclusive date range."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start date must not be after end date")

    months: list[str] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _run_module(module: str, argv: list[str]) -> None:
    """Invoke one package CLI from the repository root."""
    cmd = [sys.executable, "-m", f"crypto_analyser.{module}", *argv]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root(), check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{module} exited with code {result.returncode}")


def _repeat_months(months: list[str]) -> list[str]:
    return [token for month in months for token in ("--month", month)]


@trace_step(name="pipeline.download_ohlcv")
def run_download_ohlcv(symbol: str, months: list[str], force: bool) -> None:
    argv = ["--symbol", symbol, *_repeat_months(months)]
    if force:
        argv.append("--force")
    _run_module("downloaders.ohlcv", argv)


@trace_step(name="pipeline.download_funding")
def run_download_funding(symbol: str, months: list[str], force: bool) -> None:
    argv = ["--symbol", symbol, *_repeat_months(months)]
    if force:
        argv.append("--force")
    _run_module("downloaders.funding", argv)


@trace_step(name="pipeline.download_oi")
def run_download_oi(symbol: str, start: str, end: str, force: bool) -> None:
    argv = ["--symbol", symbol, "--start", start, "--end", end]
    if force:
        argv.append("--force")
    _run_module("downloaders.open_interest", argv)


@trace_step(name="pipeline.zscore")
def run_zscore(symbol: str, start: str, end: str) -> None:
    _run_module("detection.zscore", ["--symbol", symbol, "--start", start, "--end", end])


@trace_step(name="pipeline.derivatives")
def run_derivatives(symbol: str, start: str, end: str) -> None:
    anomalies = f"data/anomalies/{symbol}_{start}_{end}.json"
    _run_module("features.derivatives", ["--anomalies", anomalies])


@trace_step(name="pipeline.retrieval")
def run_retrieval(symbol: str, start: str, end: str) -> None:
    anomalies = f"data/anomalies/{symbol}_{start}_{end}.json"
    _run_module("rag.retrieval", ["--anomalies", anomalies])


@trace_step(name="pipeline.classifier")
def run_classifier(symbol: str, start: str, end: str, mode: str) -> None:
    anomalies = f"data/anomalies/{symbol}_{start}_{end}.json"
    if mode in {"derivatives_rag", "news_only"}:
        run_retrieval(symbol, start, end)
    _run_module("classification.episodes", ["--anomalies", anomalies, "--mode", mode])


@trace_step(name="pipeline.report")
def run_report(symbol: str, start: str, end: str, mode: str) -> None:
    _run_module("reporting.json_reports", ["--symbol", symbol, "--start", start, "--end", end, "--mode", mode])


def run_pipeline(
    symbol: str,
    start: str,
    end: str,
    mode: str,
    skip_download: bool = False,
    force_download: bool = False,
) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")
    months = _months_in_range(start, end)

    print(f"\n=== pipeline: {symbol} {start}..{end} mode={mode} ===")
    if not skip_download:
        print(f"\n[1/6] download ohlcv (months: {' '.join(months)})")
        run_download_ohlcv(symbol, months, force_download)
        print(f"\n[2/6] download funding (months: {' '.join(months)})")
        run_download_funding(symbol, months, force_download)
        print("\n[3/6] download open interest")
        run_download_oi(symbol, start, end, force_download)
    else:
        print("\n[1-3/6] download skipped (--skip-download)")

    print("\n[4/6] z-score episodes")
    run_zscore(symbol, start, end)
    print("\n[5/6] evidence context + classification")
    if mode != "news_only":
        run_derivatives(symbol, start, end)
    run_classifier(symbol, start, end, mode)
    print("\n[6/6] reports")
    run_report(symbol, start, end, mode)
    print(f"\n=== pipeline done: data/reports/{mode}/{symbol}_{start}_{end}_summary.json ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the historical crypto-analyser pipeline")
    parser.add_argument("--symbol", default="LUNAUSDT")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="derivatives_only",
        help="Choose derivatives-only, derivatives+news, or news-only evidence",
    )
    parser.add_argument("--skip-download", action="store_true", help="Use existing parquet files")
    parser.add_argument("--force-download", action="store_true", help="Overwrite existing parquet files")
    args = parser.parse_args()

    try:
        run_pipeline(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            mode=args.mode,
            skip_download=args.skip_download,
            force_download=args.force_download,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"\n[ERROR] pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
