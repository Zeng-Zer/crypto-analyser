# Crypto Analyzer

Historical batch pipeline that validates a hypothesis: **derivatives market structure (funding rate, open interest) classifies crypto price crashes better than lagging news feeds.**

The core insight — **unexplained price moves** (where derivatives data show nothing unusual) often precede news by 30min–24h. This system tests that on real historical events with measurable metrics, not intuition.

## Pipeline

```
Historical OHLCV → Z-score offline → Derivatives features at onset → LLM classify → JSON report

Ablation study:
├── Run A: Derivatives-only classification
├── Run B: Derivatives + RAG context (historical news)
└── Ragas evaluation (faithfulness, answer relevancy)
```

## Architecture

| Data class | Storage | Why |
|---|---|---|
| Raw OHLCV / funding / open interest | **Parquet on disk + DuckDB query engine** | Columnar analytical data. SQL-on-files. Wrong tool for a row-store DB. |
| News + embeddings | **pgvector in Postgres** | Vector similarity search. Already running. |
| Classifications, episodes, pipeline runs | **Tables in Postgres** | Relational outputs at scale. Joins across runs/modes. |
| Live ingestion (Milestone 2) | Postgres hypertables (TimescaleDB) | Single-row streaming writes; parquet is append-only. |

## Validation window

**LUNA crash week (May 7–11, 2022)** — LUNAUSDT on Binance Data Vision. Symbol delisted May 12.

## Quickstart

```bash
uv sync
cp .env.example .env   # fill LLM_API_URL, LLM_API_KEY, DATABASE_URL

# Optional: pgvector + Langfuse for RAG + observability
docker compose up -d

# Run the full pipeline on the LUNA window
uv run python scripts/run_pipeline.py \
  --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 \
  --mode derivatives_rag
```

## Layout

```
src/crypto_analyser/
├── downloaders/      # Binance Data Vision bulk downloads (zip → csv → parquet)
├── detection/        # Z-score anomaly detection + derivatives feature extraction
├── classifiers/      # LLM-driven episode classification
├── reporting/        # JSON report generation
├── rag/              # RAG retrieval over news (Milestone 1 Task 16)
├── llm_client.py     # Streaming LLM proxy client (GLM-5.2, no proxy reasoning)
├── config.py         # settings.yaml loader
├── _paths.py         # repo-root resolution
├── logging_config.py
└── tracing.py        # Langfuse observability
```

## Documentation

- [CONTEXT.md](CONTEXT.md) — domain language (anomaly, episode, classification outcomes)
- [docs/storage.md](docs/storage.md) — storage architecture
- [docs/adr/](docs/adr/) — architecture decision records
- [.sisyphus/PROJECT.md](.sisyphus/PROJECT.md) — full project overview

## Status

Milestone 1 (historical): in progress.
Ablation study + Ragas evaluation pending (Tasks 21–23).