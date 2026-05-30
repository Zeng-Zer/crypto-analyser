#!/usr/bin/env python
"""Download OHLCV kline data from Binance Data Vision and store as Parquet.

Usage:
    python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05
    python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-04 --month 2022-05
    python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05 --force

Binance Data Vision provides FREE historical data — no API key or rate limits.
URL pattern: {base_url}/data/futures/um/monthly/klines/{SYMBOL}/5m/{SYMBOL}-5m-{YYYY-MM}.zip

Output: data/ohlcv/{symbol}_{month}.parquet
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

# Allow running as script or module
try:
    from crypto_analyser.config import load_config
    from crypto_analyser.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    load_config = None
    get_logger = None

    import logging

    logger = logging.getLogger(__name__)


# ── Binance Data Vision constants ────────────────────────────────────

BASE_URL = "https://data.binance.vision"
DEFAULT_INTERVAL = "5m"

# Parquet schema: explicit column list avoids SQL reserved word issues
# and ensures consistent types across symbols (e.g. volume is BIGINT for
# LUNAUSDT but DOUBLE for BTCUSDT — we cast all to DOUBLE).
COLUMN_PROJECTION = """
    open_time::BIGINT     AS open_time,
    open::DOUBLE          AS open,
    high::DOUBLE          AS high,
    low::DOUBLE           AS low,
    close::DOUBLE         AS close,
    volume::DOUBLE        AS volume,
    close_time::BIGINT    AS close_time,
    quote_volume::DOUBLE  AS quote_volume,
    count::BIGINT         AS trade_count,
    taker_buy_volume::DOUBLE       AS taker_buy_volume,
    taker_buy_quote_volume::DOUBLE AS taker_buy_quote_volume
"""


def build_url(base_url: str, symbol: str, interval: str, month: str) -> str:
    """Build Binance Data Vision download URL for a monthly kline archive."""
    return (
        f"{base_url}/data/futures/um/monthly/klines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    )


def download_zip(url: str, timeout: int = 60) -> bytes:
    """Download a zip archive from Binance Data Vision.

    Raises:
        requests.HTTPError: On non-200 responses (e.g. 404 for missing months).
    """
    logger.info("Downloading %s", url)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def extract_csv(zip_bytes: bytes) -> str:
    """Extract the first CSV from an in-memory zip archive.

    Returns:
        Path to a temporary CSV file. Caller is responsible for cleanup.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = zf.namelist()[0]
        csv_data = zf.read(csv_name)

    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb")
    tmp.write(csv_data)
    tmp.close()
    return tmp.name


def csv_to_parquet(
    csv_path: str,
    output_path: Path,
    filter_zero_volume: bool = True,
) -> int:
    """Convert a Binance kline CSV to Parquet via DuckDB.

    Args:
        csv_path: Path to the extracted CSV file.
        output_path: Destination Parquet file.
        filter_zero_volume: Remove post-delisting zero-volume rows.

    Returns:
        Number of rows written.
    """
    where_clause = "WHERE volume > 0" if filter_zero_volume else ""

    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT {COLUMN_PROJECTION}
                FROM read_csv('{csv_path}', header=true, all_varchar=true)
            ) sub
            {where_clause}
            ORDER BY open_time
        ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION 'zstd');
        """
    )

    row_count = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{output_path}')"
    ).fetchone()[0]
    return row_count


def download_ohlcv(
    symbol: str,
    month: str,
    output_dir: Path,
    interval: str = DEFAULT_INTERVAL,
    base_url: str = BASE_URL,
    force: bool = False,
) -> bool:
    """Download OHLCV data for one symbol-month combination.

    Args:
        symbol: Trading pair (e.g. LUNAUSDT).
        month: Month in YYYY-MM format.
        output_dir: Directory for Parquet output.
        interval: Kline interval (default 5m).
        base_url: Binance Data Vision base URL.
        force: Overwrite existing Parquet file.

    Returns:
        True if download succeeded, False otherwise.
    """
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
        row_count = csv_to_parquet(csv_path, output_path)

        # Log summary with date range
        con = duckdb.connect()
        ts_range = con.execute(
            f"SELECT MIN(open_time), MAX(open_time) FROM read_parquet('{output_path}')"
        ).fetchone()
        first_dt = datetime.fromtimestamp(ts_range[0] / 1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(ts_range[1] / 1000, tz=timezone.utc)
        logger.info(
            "Wrote %d rows to %s (%s to %s)",
            row_count,
            output_path,
            first_dt.strftime("%Y-%m-%d %H:%M"),
            last_dt.strftime("%Y-%m-%d %H:%M"),
        )
        return True

    except requests.HTTPError as e:
        logger.error("HTTP error downloading %s: %s", url, e)
        # Remove empty/corrupt Parquet if it was created
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
    parser.add_argument(
        "--symbol",
        default="LUNAUSDT",
        help="Trading pair symbol (default: LUNAUSDT)",
    )
    parser.add_argument(
        "--month",
        action="append",
        required=True,
        help="Month in YYYY-MM format (can specify multiple)",
    )
    parser.add_argument(
        "--interval",
        default=None,
        help="Kline interval (default: 5m, or from config)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing Parquet files",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: from config or data/ohlcv)",
    )
    args = parser.parse_args()

    # Load config if available (graceful fallback for standalone use)
    base_url = BASE_URL
    interval = args.interval or DEFAULT_INTERVAL
    output_dir = Path("data/ohlcv")

    if load_config is not None:
        try:
            config = load_config()
            base_url = config.get("sources.binance.base_url", base_url)
            if args.interval is None:
                interval = config.get("sources.binance.intervals.ohlcv", interval)
            config_output = config.get("paths.ohlcv_dir", None)
            if config_output and args.output_dir is None:
                output_dir = Path(config_output)
        except RuntimeError:
            logger.warning("Config has placeholder values — using defaults")

    if args.output_dir:
        output_dir = Path(args.output_dir)

    # Process each month
    success_count = 0
    for month in args.month:
        logger.info("--- %s %s ---", args.symbol, month)
        if download_ohlcv(
            symbol=args.symbol,
            month=month,
            output_dir=output_dir,
            interval=interval,
            base_url=base_url,
            force=args.force,
        ):
            success_count += 1

    total = len(args.month)
    logger.info("Completed: %d/%d months downloaded", success_count, total)

    if success_count < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
