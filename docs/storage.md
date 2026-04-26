# Storage Strategy

## Overview

This project uses two complementary storage approaches:

| Format   | Purpose                                      | When Used                        |
|----------|----------------------------------------------|----------------------------------|
| Parquet  | Columnar storage for historical OHLCV data  | Batch writes, analytical queries |
| DuckDB   | In-process analytical database for queries   | Ad-hoc queries, joins, aggregations |

## Directory Structure

```
data/
  ohlcv/           # OHLCV Parquet files (1-min klines from Binance Data Vision)
  funding/          # Funding rate Parquet files (8h intervals)
  oi/               # Open Interest Parquet files (5-min metrics)
  anomalies/        # Detected anomalies JSON (Z-score outputs)
  context/          # Derivatives context JSON (funding + OI at anomaly timestamps)
  classifications/  # LLM classification results (structured verdicts)
  reports/          # Final JSON reports (ablation study outputs)
  raw/              # Downloaded CSV/ZIP before Parquet conversion
  crypto.duckdb     # DuckDB database (created on first query)
```

## DuckDB Database

**Path:** `data/crypto.duckdb`

DuckDB is used as an in-process analytical database. It reads Parquet files
directly without loading them into memory, enabling efficient queries on
historical time-series data.

```python
import duckdb

conn = duckdb.connect("data/crypto.duckdb")

# Query Parquet files directly
conn.execute("""
    SELECT * FROM read_parquet('data/ohlcv/*.parquet')
    WHERE symbol = 'LUNAUSDT'
      AND timestamp BETWEEN '2022-05-07' AND '2022-05-11'
""")

conn.close()
```

## Why Parquet + DuckDB

| Concern       | Parquet                                  | DuckDB                                      |
|---------------|------------------------------------------|---------------------------------------------|
| Storage       | Compressed columnar, 60-80% smaller      | Zero-copy reads from Parquet                 |
| Queries       | Requires loading into a DataFrame        | SQL interface, no data movement              |
| Schema        | Embedded in file metadata                | Inferred from Parquet schema                 |
| Time-series   | Partitioned by symbol/date              | Native date/timestamp functions              |
| Interop       | Pandas, Polars, Spark, DuckDB           | Reads Parquet, CSV, JSON directly            |

## Data Flow

```
Binance Data Vision (CSV/ZIP)
        |
        v
    data/raw/          -- Downloaded archives, ephemeral
        |
        v
    Parquet conversion -- Batch script reads CSV, writes Parquet
        |
        v
    data/ohlcv/        -- Partitioned Parquet files
    data/funding/
    data/oi/
        |
        v
    DuckDB queries     -- Analytical SQL on Parquet files
        |
        v
    data/anomalies/    -- Z-score detection outputs (JSON)
        |
        v
    data/context/      -- Derivatives context at anomalies (JSON)
        |
        v
    data/classifications/  -- LLM verdicts (JSON)
        |
        v
    data/reports/      -- Final ablation reports (JSON)
```

## Git Policy

Binary data files (Parquet, DuckDB, CSV, ZIP) are excluded from version control
via `data/.gitignore`. Only the directory structure (preserved via `.gitkeep`
files) and the gitignore rules are tracked.

Re-downloading data from Binance Data Vision is free and deterministic, so
there is no need to version the data itself.
