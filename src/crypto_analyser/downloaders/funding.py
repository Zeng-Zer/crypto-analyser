"""Download Binance funding-rate archives and convert them to Parquet."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

from crypto_analyser.downloaders.common import (
    BASE_URL,
    csv_to_parquet,
    download_zip,
    extract_csv,
    logger,
)

COLUMNS: dict[str, str] = {
    "calc_time": "BIGINT",
    "funding_interval_hours": "BIGINT",
    "last_funding_rate": "DOUBLE",
}


def build_url(base_url: str, symbol: str, month: str) -> str:
    return f"{base_url}/data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"


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
            csv_path,
            output_path,
            columns=COLUMNS,
            sort_column="calc_time",
        )

        con = duckdb.connect()
        ts_range = con.execute(f"SELECT MIN(calc_time), MAX(calc_time) FROM read_parquet('{output_path}')").fetchone()
        con.close()
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
        if output_path.exists():
            output_path.unlink()
        return False

    finally:
        if csv_path:
            Path(csv_path).unlink(missing_ok=True)
