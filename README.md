# Crypto Analyzer

Historical batch pipeline testing whether derivatives market structure—funding rates and open interest—classifies crypto price crashes more faithfully than lagging news.

An **unexplained** price episode has neither unusual derivatives activity nor credible retrieved news. Those episodes are the hypothesis signal: price can move before a public explanation appears.

## Pipeline

```text
Binance historical data
  → rolling Z-score episodes
  → derivatives features at episode onset
  → structured LLM classification
  → mode-isolated JSON reports

Ablation:
  Run A: derivatives only
  Run B: derivatives + pre-onset historical news
  Run C: pre-onset historical news only
  Compare verdict overlap, news timing, faithfulness, and answer relevancy
```

## Current storage

| Data | Storage |
|---|---|
| OHLCV, funding, open interest | Monthly Parquet queried directly with DuckDB |
| News and embeddings | PostgreSQL with pgvector |
| Pipeline intermediates and reports | Gitignored JSON under `data/` |

PostgreSQL output tables and TimescaleDB-backed live ingestion are Milestone 2 plans, not current behavior.

## Quickstart

```bash
uv sync --locked
cp .env.example .env

# Historical pipeline; downloads Binance data when missing
uv run python scripts/run_pipeline.py \
  --symbol LUNAUSDT \
  --start 2022-05-07 \
  --end 2022-05-11 \
  --mode derivatives_only
```

`derivatives_rag` and `news_only` retrieve articles published at or before each episode onset. Missing retrieval files fail closed rather than silently producing an empty RAG run.

### Historical news database

```bash
docker compose up -d pgvector
./scripts/init_db.sh
uv run python scripts/load_archive.py --archive-dir /path/to/archive
uv run python scripts/generate_embeddings.py \
  --start 2022-05-06 --end 2022-05-12 \
  --query 'LUNA OR UST OR Terra'

# Run all three evidence modes, then evaluate
uv run python scripts/run_pipeline.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode derivatives_only
uv run python scripts/run_pipeline.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode derivatives_rag --skip-download
uv run python scripts/run_pipeline.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode news_only --skip-download
uv run python scripts/evaluate_ragas.py
```

Required environment variables: `DATABASE_URL`, `LLM_API_URL`, and `LLM_API_KEY`. `NEWS_ARCHIVE_DIR` can replace `--archive-dir`.

## Layout

```text
src/crypto_analyser/
├── downloaders/       # Binance OHLCV, funding, and open-interest acquisition
├── detection/         # Z-score episode detection
├── features/          # Derivatives feature extraction
├── classification/    # Structured episode classification
├── rag/               # News loading, embeddings, and retrieval
├── reporting/         # Mode-isolated JSON reports
├── llm_client.py
├── config.py
├── logging_config.py
└── tracing.py

scripts/               # Thin CLI wrappers and pipeline orchestration
sql/                   # PostgreSQL schema and indexes
data/                  # Gitignored parquet and generated JSON
```

## Validation case

Milestone 1 validates the LUNAUSDT crash window from May 7–11, 2022 using Binance Data Vision. FTX and Bybit windows are planned enrichment cases.

## Documentation

- [CONTEXT.md](CONTEXT.md) — domain language and classification outcomes
- [docs/storage.md](docs/storage.md) — storage design
- [docs/adr/](docs/adr/) — architecture decisions
- [.sisyphus/PROJECT.md](.sisyphus/PROJECT.md) — project roadmap

## Status

Milestone 1 LUNA run is complete. Five episodes produced 15 classifications across three modes. Derivatives-only and news-only each explained four episodes; three overlapped, one was derivatives-only, and one was news-only. This single event shows complementary evidence, not general derivatives superiority. See `reports/FINAL_PHASE1_SUMMARY.json`.
