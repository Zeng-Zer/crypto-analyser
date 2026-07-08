#!/usr/bin/env python3
"""End-to-end pipeline orchestrator (Task 20).

Chains every Wave 2-3 component for a given symbol/date window:

    download (ohlcv + funding + oi)
        -> zscore         (Task 14: episodes)
        -> derivatives    (Task 15: per-episode features)
        -> classifier     (Task 18: LLM verdict per episode)
        -> report         (Task 19: per-episode + summary)

Each stage runs as an in-process call to the same module main() that the
standalone CLIs expose, so behaviour matches the per-task QA scenarios. Every
stage is wrapped in ``@trace_step`` so Langfuse (if configured) records one
span per stage of the run; with placeholder credentials tracing is a no-op.

Milestone 1 note (AGENTS.md): batch/historical only. RAG retrieval stage
(Task 16) not yet shipped; ``--mode derivatives_rag`` runs the Run B
prompt with an empty news block per the Task 17 contract — classifications
still succeed, they just lack retrieved-news context.
"""

from __future__ import annotations

import argparse
import sys

from crypto_analyser.tracing import trace_step

# Two pipeline modes direct: derivatives_only (Run A) and derivatives_rag
# (Run B). downstream classifier / report_generator accept the same two
# values, so no mapping layer is needed — the orchestrator passes --mode
# through verbatim. When Task 16 ships RAG retrieval, run_derivatives_rag
# (or its successor stage) inserts itself before the classifier.
VALID_MODES = {"derivatives_only", "derivatives_rag"}


def _months_in_range(start: str, end: str) -> list[str]:
    """Return ``['2022-04', '2022-05']`` for ``start='2022-04-25' end='2022-05-02'``.

    Cross-month windows download every covered month's parquet file. The
    zscore / derivatives loaders glob ``{symbol}_*.parquet`` so multi-month
    loading works without per-month handling there too.
    """
    import datetime as _dt

    s = _dt.date.fromisoformat(start)
    e = _dt.date.fromisoformat(end)
    months: list[str] = []
    y, m = s.year, s.month
    while (y, m) <= (e.year, e.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _download_script(name: str, argv: list[str]) -> None:
    """Run a scripts/ download CLI via ``python scripts/<name>.py``."""
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent / f"{name}.py"
    cmd = [sys.executable, str(script), *argv]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{name} exited with code {result.returncode}")


def _run_module(module: str, argv: list[str]) -> None:
    """Invoke ``python -m crypto_analyser.<module>`` with the given argv.

    Subprocess avoids duplicating each CLI's path/config resolution here;
    cost is a few seconds per stage of uv/python startup, acceptable for a
    batch pipeline that runs once per window.
    """
    import subprocess

    cmd = [sys.executable, "-m", f"crypto_analyser.{module}", *argv]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{module} exited with code {result.returncode}")


def _repeat_months(months: list[str]) -> list[str]:
    """Flatten ['2022-04','2022-05'] to ['--month','2022-04','--month','2022-05']."""
    return [tok for m in months for tok in ("--month", m)]


@trace_step(name="pipeline.download_ohlcv")
def run_download_ohlcv(symbol: str, months: list[str], force: bool) -> None:
    argv = ["--symbol", symbol, *_repeat_months(months)]
    if force:
        argv.append("--force")
    _download_script("download_ohlcv", argv)


@trace_step(name="pipeline.download_funding")
def run_download_funding(symbol: str, months: list[str], force: bool) -> None:
    argv = ["--symbol", symbol, *_repeat_months(months)]
    if force:
        argv.append("--force")
    _download_script("download_funding", argv)


@trace_step(name="pipeline.download_oi")
def run_download_oi(symbol: str, start: str, end: str, force: bool) -> None:
    argv = ["--symbol", symbol, "--start", start, "--end", end]
    if force:
        argv.append("--force")
    _download_script("download_oi", argv)


@trace_step(name="pipeline.zscore")
def run_zscore(symbol: str, start: str, end: str) -> None:
    _run_module("zscore", ["--symbol", symbol, "--start", start, "--end", end])


@trace_step(name="pipeline.derivatives")
def run_derivatives(symbol: str, start: str, end: str) -> None:
    anomalies = f"data/anomalies/{symbol}_{start}_{end}.json"
    _run_module("derivatives_context", ["--anomalies", anomalies])


@trace_step(name="pipeline.classifier")
def run_classifier(symbol: str, start: str, end: str, mode: str) -> None:
    anomalies = f"data/anomalies/{symbol}_{start}_{end}.json"
    _run_module("classifier", ["--anomalies", anomalies, "--mode", mode])


@trace_step(name="pipeline.report")
def run_report(symbol: str, start: str, end: str, mode: str) -> None:
    _run_module("report_generator", ["--symbol", symbol, "--start", start, "--end", end, "--mode", mode])


def run_pipeline(
    symbol: str,
    start: str,
    end: str,
    mode: str,
    skip_download: bool = False,
    force_download: bool = False,
) -> None:
    """Execute the full LUNA-style pipeline for the given window."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")
    months = _months_in_range(start, end)

    print(f"\n=== Task 20 pipeline: {symbol} {start}..{end} mode={mode} ===")

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

    print("\n[5/6] derivatives context + classification")
    run_derivatives(symbol, start, end)
    run_classifier(symbol, start, end, mode)

    print("\n[6/6] reports")
    run_report(symbol, start, end, mode)

    print(f"\n=== pipeline done: reports/{symbol}_{start}_{end}_summary.json ===")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Run the crypto-analyser end-to-end pipeline (Task 20)",
    )
    p.add_argument("--symbol", default="LUNAUSDT")
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="derivatives_only",
        help=(
            "Pipeline mode. 'derivatives_only' = Run A (no RAG). "
            "'derivatives_rag' = Run B (RAG block empty until Task 16)."
        ),
    )
    p.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip OHLCV/funding/OI download (use existing parquet files).",
    )
    p.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download even if parquet files exist (passed to --force on download scripts).",
    )
    args = p.parse_args()

    try:
        run_pipeline(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            mode=args.mode,
            skip_download=args.skip_download,
            force_download=args.force_download,
        )
    except RuntimeError as exc:
        print(f"\n[ERROR] pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
