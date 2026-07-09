# Storage Strategy

## Current architecture

| Data | Storage | Access pattern |
|---|---|---|
| OHLCV, funding, open interest | Parquet partitioned by symbol and month | DuckDB SQL scans and joins |
| News articles and embeddings | PostgreSQL with pgvector | Full-text and vector retrieval |
| Episodes, features, classifications, reports | Gitignored JSON | Batch pipeline handoff and reproducible artifacts |

PostgreSQL tables for pipeline outputs and TimescaleDB live ingestion are planned for Milestone 2. They are not implemented in Milestone 1.

## Data directory

```text
data/
├── ohlcv/                         # {symbol}_{YYYY-MM}.parquet, 5-minute candles
├── funding/                       # {symbol}_{YYYY-MM}.parquet, 8-hour snapshots
├── oi/                            # {symbol}_{YYYY-MM}.parquet, 5-minute metrics
├── anomalies/                     # Episode batches from Z-score detection
├── context/                       # Derivatives features at episode onset
├── classifications/
│   ├── derivatives_only/
│   └── derivatives_rag/
├── rag/                           # Per-episode retrieved-news context
└── reports/
    ├── derivatives_only/
    └── derivatives_rag/
```

All generated files under `data/` are ignored by Git and can be regenerated.

## Parquet and DuckDB

Binance archives are converted to compressed Parquet. DuckDB queries those files directly; no persistent `.duckdb` file or load step is required.

```python
import duckdb

rows = duckdb.sql("""
    SELECT open_time, close
    FROM read_parquet('data/ohlcv/LUNAUSDT_*.parquet')
    WHERE open_time BETWEEN 1651881600000 AND 1652313599999
    ORDER BY open_time
""").fetchall()
```

This keeps immutable historical data columnar while retaining SQL filtering, aggregation, and joins.

## PostgreSQL and pgvector

`sql/schema.sql` creates:

- `crypto_news` article metadata
- generated combined-text and `tsvector` columns
- a 4,096-dimensional embedding column
- GIN, BRIN, and HNSW indexes

Run:

```bash
docker compose up -d pgvector
./scripts/init_db.sh
uv run python scripts/load_archive.py --archive-dir /path/to/archive/2022/05
uv run python scripts/generate_embeddings.py
```

The HNSW index uses the first 2,000 dimensions because pgvector's `vector` HNSW operator class has a 2,000-dimension limit. Retrieval queries must use the same indexed expression.

## Deployment path

- Milestone 1 showcase: publish curated report data from a completed batch run.
- Historical data at larger scale: store Parquet in object storage and query with DuckDB.
- Milestone 2 live writes: add a serving/time-series database after ingestion and query requirements are defined.