"""Download Binance open-interest metrics and convert them to Parquet."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import requests

from crypto_analyser.downloaders.common import (
    BASE_URL,
    build_projection,
    download_zip,
    extract_csv,
    logger,
)

COLUMNS: dict[str, str] = {
    "create_time": "TIMESTAMP",
    "symbol": "VARCHAR",
    "sum_open_interest": "DOUBLE",
    "sum_open_interest_value": "DOUBLE",
    "count_long_short_ratio": "DOUBLE",
    "sum_taker_long_short_vol_ratio": "DOUBLE",
}


def build_url(base_url: str, symbol: str, day: str) -> str:
    return f"{base_url}/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{day}.zip"


def download_oi_range(
    symbol: str,
    start_date: date,
    end_date: date,
    output_dir: Path,
    base_url: str = BASE_URL,
    force: bool = False,
) -> bool:
    start_month = start_date.strftime("%Y-%m")
    output_path = output_dir / f"{symbol}_{start_month}.parquet"
    if output_path.exists() and not force:
        logger.info("Already exists: %s (use --force to overwrite)", output_path)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_paths: list[str] = []

    try:
        current = start_date
        while current <= end_date:
            day_str = current.strftime("%Y-%m-%d")
            try:
                csv_path = extract_csv(download_zip(build_url(base_url, symbol, day_str)))
                csv_paths.append(csv_path)
            except requests.HTTPError as e:
                if e.response and e.response.status_code == 404:
                    logger.warning("No data for %s (skip)", day_str)
                else:
                    raise
            current += timedelta(days=1)

        if not csv_paths:
            logger.error("No data downloaded")
            return False

        projection = build_projection(COLUMNS)
        con = duckdb.connect()
        union_parts = [f"SELECT {projection} FROM read_csv('{p}', header=true, all_varchar=true)" for p in csv_paths]
        con.execute(
            f"""
            COPY (
                SELECT * FROM (
                    {" UNION ALL ".join(union_parts)}
                ) sub ORDER BY create_time
            ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION 'zstd');
            """
        )

        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{output_path}')").fetchone()[0]
        ts_range = con.execute(
            f"SELECT MIN(create_time), MAX(create_time) FROM read_parquet('{output_path}')"
        ).fetchone()
        con.close()
        logger.info(
            "Wrote %d rows to %s (%s to %s)",
            row_count,
            output_path,
            ts_range[0].strftime("%Y-%m-%d %H:%M"),
            ts_range[1].strftime("%Y-%m-%d %H:%M"),
        )
        return True

    except requests.HTTPError as e:
        logger.error("HTTP error: %s", e)
        if output_path.exists():
            output_path.unlink()
        return False
    finally:
        for p in csv_paths:
            Path(p).unlink(missing_ok=True)
