"""Shared utilities for downloading data from Binance Data Vision.

Provides zip download/extraction, CSV-to-Parquet conversion,
and config loading — common across all download scripts.

Usage:
    from crypto_analyser.download_utils import download_zip, extract_csv, csv_to_parquet
"""
from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from pathlib import Path

import duckdb
import requests

from crypto_analyser.config import load_config as _load_config
from crypto_analyser.logging_config import get_logger as _get_logger

logger = _get_logger(__name__)

# ── Binance Data Vision ──────────────────────────────────────────────

BASE_URL = "https://data.binance.vision"


def load_config_or_defaults():
    """Load project config, falling back to defaults if placeholders not filled.

    Returns:
        (config_dict, use_fallback) — config is None when fallback is used.
    """
    try:
        cfg = _load_config()
        return cfg, False
    except RuntimeError:
        logger.warning("Config has placeholder values — using defaults")
        return None, True


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
    column_projection: str,
    where_clause: str | None = None,
    sort_column: str = "open_time",
) -> int:
    """Convert a Binance CSV to Parquet via DuckDB.

    Args:
        csv_path: Path to the extracted CSV file.
        output_path: Destination Parquet file.
        column_projection: SQL snippet for column casting (e.g.
            ``open_time::BIGINT AS open_time, close::DOUBLE AS close``).
        where_clause: Optional SQL WHERE clause (without "WHERE" keyword).
        sort_column: Column to ORDER BY (default open_time).

    Returns:
        Number of rows written.
    """
    where = f"WHERE {where_clause}" if where_clause else ""

    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT {column_projection}
                FROM read_csv('{csv_path}', header=true, all_varchar=true)
            ) sub
            {where}
            ORDER BY {sort_column}
        ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION 'zstd');
        """
    )

    row_count = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{output_path}')"
    ).fetchone()[0]
    return row_count

    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT {column_projection}
            FROM read_csv('{csv_path}', header=true, all_varchar=true)
            {where}
            ORDER BY {sort_column}
        ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION 'zstd');
        """
    )

    row_count = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{output_path}')"
    ).fetchone()[0]
    return row_count
