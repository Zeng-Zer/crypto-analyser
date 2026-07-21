# Storage Strategy

## Current architecture

| Data | Storage | Access pattern |
|---|---|---|
| OHLCV, funding, open interest | Parquet partitioned by symbol and month | DuckDB SQL scans and joins |
| News articles and embeddings | PostgreSQL with pgvector | Full-text and vector retrieval |
| Episodes, features, classifications, reports | Gitignored JSON | Batch pipeline handoff and reproducible artifacts |

PostgreSQL stores news and embeddings only. Pipeline outputs remain JSON; no real-time ingestion or time-series serving database is implemented.

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
│   ├── derivatives_rag/
│   └── news_only/
├── rag/                           # Per-episode retrieved-news context
└── reports/
    ├── derivatives_only/
    ├── derivatives_rag/
    └── news_only/
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

Packaged `crypto_analyser/assets/schema.sql` creates:

- `crypto_news` article metadata
- generated combined-text and `tsvector` columns
- a 4,096-dimensional embedding column
- GIN, BRIN, and HNSW indexes

Run:

```bash
docker compose up -d pgvector
uv run crypto-analyser news init
uv run crypto-analyser news load --archive-dir /path/to/archive
uv run crypto-analyser news embed \
  --start 2022-05-06 --end 2022-05-12 \
  --query 'LUNA OR UST OR Terra'
```

The HNSW index uses the first 2,000 dimensions because pgvector's `vector` HNSW operator class has a 2,000-dimension limit. Retrieval queries must use the same indexed expression.

## Deployment

GitHub Pages serves the committed static snapshot in `visuals/`. Local pipeline execution, PostgreSQL/pgvector, source Parquet, and generated JSON are not part of the hosted site.