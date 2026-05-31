#!/usr/bin/env python
"""Download funding rate data from Binance Data Vision and store as Parquet.

Usage:
    uv run python scripts/download_funding.py --symbol LUNAUSDT --month 2022-05
    uv run python scripts/download_funding.py --symbol LUNAUSDT --month 2022-04 --month 2022-05
    uv run python scripts/download_funding.py --symbol LUNAUSDT --month 2022-05 --force

URL pattern: {base_url}/data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{YYYY-MM}.zip

Funding rate is 8-hour intervals (3 funding events per day).

Output: data/funding/{symbol}_{month}.parquet
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

from crypto_analyser.download_utils import (
    BASE_URL,
    csv_to_parquet,
    download_zip,
    extract_csv,
    load_config_or_defaults,
    logger,
)

COLUMNS: dict[str, str] = {
    "calc_time": "BIGINT",
    "funding_interval_hours": "BIGINT",
    "last_funding_rate": "DOUBLE",
}


def build_url(base_url: str, symbol: str, month: str) -> str:
    return (
        f"{base_url}/data/futures/um/monthly/fundingRate/"
        f"{symbol}/{symbol}-fundingRate-{month}.zip"
    )


def download_funding(
    symbol: str,
    month: str,
    output_dir: Path,
    base_url: str = BASE_URL,
    force: bool = False,
) -> bool:
    output_path = output_dir / f"{symbol}_{month}.parquet"
    if output_path.exists() and not force:
        logger.info("Already exists: %s (use --force to overwrite)", output_path)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    url = build_url(base_url, symbol, month)
    csv_path: str | None = None

    try:
        zip_bytes = download_zip(url)
        csv_path = extract_csv(zip_bytes)
        row_count = csv_to_parquet(
            csv_path, output_path,
            columns=COLUMNS,
            sort_column="calc_time",
        )

        con = duckdb.connect()
        ts_range = con.execute(
            f"SELECT MIN(calc_time), MAX(calc_time) FROM read_parquet('{output_path}')"
        ).fetchone()
        first_dt = datetime.fromtimestamp(ts_range[0] / 1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(ts_range[1] / 1000, tz=timezone.utc)
        logger.info(
            "Wrote %d rows to %s (%s to %s)",
            row_count, output_path,
            first_dt.strftime("%Y-%m-%d %H:%M"),
            last_dt.strftime("%Y-%m-%d %H:%M"),
        )
        return True

    except requests.HTTPError as e:
        logger.error("HTTP error downloading %s: %s", url, e)
        if output_path.exists():
            output_path.unlink()
        return False

    finally:
        if csv_path:
            Path(csv_path).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download funding rate data from Binance Data Vision"
    )
    parser.add_argument("--symbol", default="LUNAUSDT")
    parser.add_argument("--month", action="append", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    base_url = BASE_URL
    output_dir = Path("data/funding")

    cfg, fallback = load_config_or_defaults()
    if cfg and not fallback:
        base_url = cfg.get("sources.binance.base_url", base_url)
        if args.output_dir is None:
            output_dir = Path(cfg.get("paths.funding_dir", "data/funding"))

    if args.output_dir:
        output_dir = Path(args.output_dir)

    success_count = 0
    for month in args.month:
        logger.info("--- %s %s ---", args.symbol, month)
        if download_funding(symbol=args.symbol, month=month, output_dir=output_dir,
                            base_url=base_url, force=args.force):
            success_count += 1

    logger.info("Completed: %d/%d months downloaded", success_count, len(args.month))
    if success_count < len(args.month):
        sys.exit(1)


if __name__ == "__main__":
    main()
