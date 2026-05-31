#!/usr/bin/env python
"""Download OHLCV kline data from Binance Data Vision and store as Parquet.

Usage:
    uv run python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05
    uv run python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-04 --month 2022-05
    uv run python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05 --force

URL pattern: {base_url}/data/futures/um/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-{YYYY-MM}.zip

Output: data/ohlcv/{symbol}_{month}.parquet
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

DEFAULT_INTERVAL = "5m"

COLUMNS: dict[str, str] = {
    "open_time": "BIGINT",
    "open": "DOUBLE",
    "high": "DOUBLE",
    "low": "DOUBLE",
    "close": "DOUBLE",
    "volume": "DOUBLE",
    "close_time": "BIGINT",
    "quote_volume": "DOUBLE",
    "count": "BIGINT",
    "taker_buy_volume": "DOUBLE",
    "taker_buy_quote_volume": "DOUBLE",
}


def build_url(base_url: str, symbol: str, interval: str, month: str) -> str:
    return (
        f"{base_url}/data/futures/um/monthly/klines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    )


def download_ohlcv(
    symbol: str,
    month: str,
    output_dir: Path,
    interval: str = DEFAULT_INTERVAL,
    base_url: str = BASE_URL,
    force: bool = False,
) -> bool:
    output_path = output_dir / f"{symbol}_{month}.parquet"
    if output_path.exists() and not force:
        logger.info("Already exists: %s (use --force to overwrite)", output_path)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    url = build_url(base_url, symbol, interval, month)
    csv_path: str | None = None

    try:
        zip_bytes = download_zip(url)
        csv_path = extract_csv(zip_bytes)
        row_count = csv_to_parquet(
            csv_path, output_path,
            columns=COLUMNS,
            where_clause="volume > 0",
        )

        con = duckdb.connect()
        ts_range = con.execute(
            f"SELECT MIN(open_time), MAX(open_time) FROM read_parquet('{output_path}')"
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
        description="Download OHLCV kline data from Binance Data Vision"
    )
    parser.add_argument("--symbol", default="LUNAUSDT")
    parser.add_argument("--month", action="append", required=True)
    parser.add_argument("--interval", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    base_url = BASE_URL
    interval = args.interval or DEFAULT_INTERVAL
    output_dir = Path("data/ohlcv")

    cfg, fallback = load_config_or_defaults()
    if cfg and not fallback:
        base_url = cfg.get("sources.binance.base_url", base_url)
        if args.interval is None:
            interval = cfg.get("sources.binance.intervals.ohlcv", interval)
        if args.output_dir is None:
            output_dir = Path(cfg.get("paths.ohlcv_dir", "data/ohlcv"))

    if args.output_dir:
        output_dir = Path(args.output_dir)

    success_count = 0
    for month in args.month:
        logger.info("--- %s %s ---", args.symbol, month)
        if download_ohlcv(symbol=args.symbol, month=month, output_dir=output_dir,
                          interval=interval, base_url=base_url, force=args.force):
            success_count += 1

    logger.info("Completed: %d/%d months downloaded", success_count, len(args.month))
    if success_count < len(args.month):
        sys.exit(1)


if __name__ == "__main__":
    main()
