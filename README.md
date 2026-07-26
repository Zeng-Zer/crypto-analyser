# Crypto Anomaly Analyser

Historical batch pipeline comparing how derivatives market structure—funding rates and open interest—and pre-onset news affect LLM classifications of crypto price anomalies.

**[Open the LUNA crash evidence workbench](https://zeng-zer.github.io/crypto-analyser/)**

[![Crypto Anomaly Analyser showing LUNA Episode 04](docs/images/evidence-workbench-v2.png)](https://zeng-zer.github.io/crypto-analyser/?onset=1652136300000)

An **unexplained** price episode has neither unusual derivatives activity nor credible retrieved news. Such episodes would support the hypothesis that price can move before a public explanation appears; this LUNA case produced no episode unexplained by both isolated sources.

## Pipeline

```text
Binance historical data
  → rolling Z-score episodes
  → derivatives features at episode onset
  → structured LLM classification
  → mode-isolated JSON reports

Controlled context comparison:
  Run A: derivatives only
  Run B: derivatives + pre-onset historical news
  Run C: pre-onset historical news only
  Compare verdicts; check Run B rationale with Ragas Faithfulness
```

## Current storage

| Data | Storage |
|---|---|
| OHLCV, funding, open interest | Monthly Parquet queried directly with DuckDB |
| Historical news and embeddings | PostgreSQL with pgvector |
| Live news candidates | Configurable free-crypto-news HTTP API; transient embedding rank |
| Pipeline intermediates and reports | Gitignored JSON under `data/` |

Live bars stay browser-only and in-memory. Confirmed episodes go to a localhost bridge for current-news retrieval and structured LLM classification; this repository has no time-series serving database.

## Quickstart

```bash
uv sync --locked
cp .env.example .env

# Historical pipeline; downloads Binance data when missing
uv run crypto-analyser run \
  --symbol LUNAUSDT \
  --start 2022-05-07 \
  --end 2022-05-11 \
  --mode derivatives_only
```

`derivatives_rag` and `news_only` retrieve articles published at or before each episode onset. Missing retrieval files fail closed rather than silently producing an empty RAG run. Use `--data-dir` to place every pipeline artifact under one alternative root.

### Historical news database

```bash
docker compose up -d pgvector
uv run crypto-analyser news init
uv run crypto-analyser news load --archive-dir /path/to/archive
uv run crypto-analyser news embed \
  --start 2022-05-06 --end 2022-05-12 \
  --query 'LUNA OR UST OR Terra'
uv run crypto-analyser news search --query 'Terra UST depeg'

# Run all three context modes, then evaluate
uv run crypto-analyser run --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode derivatives_only
uv run crypto-analyser run --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode derivatives_rag --skip-download
uv run crypto-analyser run --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode news_only --skip-download
uv sync --locked --extra evaluation
uv run crypto-analyser evaluate
```

Required environment variables: `DATABASE_URL`, `LLM_API_URL`, and `LLM_API_KEY`. `NEWS_ARCHIVE_DIR` can replace `--archive-dir`.

### Interactive analyst workbench

Historical replay needs only a static server:

```bash
uv run python -m http.server 8000 --directory visuals
```

Live news RAG needs localhost bridge so LLM credentials never enter browser code:

```bash
# Works immediately; public free endpoint currently returns at most 3 candidates
NEWS_API_URL=https://cryptocurrency.cv/api/news uv run crypto-analyser live

# Better retrieval: run sibling free-crypto-news for full candidate results
cd ../free-crypto-news && npm run dev
cd ../crypto-analyser && uv run crypto-analyser live
```

Open `http://localhost:8000` for historical replay or `http://localhost:8000/live.html` for live BTCUSDT observation. Live mode charts absolute BTC price from closed Binance 5-minute bars and runs the historical detector on each update. Funding rate and 4-hour open-interest change refresh every 60 seconds; latest Bitcoin headlines refresh every 90 seconds. Neither refresh calls the LLM. At second flagged price bar, localhost recomputes the episode, freezes funding, OI, and news at onset, embedding-ranks five articles, then runs the existing derivatives + RAG classifier. Results are cached by event reference; bars are not persisted. `NEWS_API_URL` defaults to `http://127.0.0.1:3000/api/news` and falls back to public free endpoint when local sibling is unavailable.

Historical replay starts with Episode 01 and guides reviewers chronologically through all eight episodes: focused anomaly chart, onset-safe context, hybrid retrieval results with publisher links and archive fallbacks, structured LLM output, then a compact explanation check. The comparison records verdict changes across context modes; Ragas Faithfulness checks whether claims in the combined rationale follow from supplied context. It does not score verdict correctness or prove causality. Page embeds a committed historical snapshot, so GitHub Pages serves it without a backend. After generating new local pipeline artifacts, refresh it with `uv run python scripts/build_visual_data.py`.

Run browser tests after installing Chromium once:

```bash
uv run playwright install chromium
uv run pytest -q tests/test_visuals.py
```

## Layout

```text
src/crypto_analyser/
├── downloaders/       # Binance OHLCV, funding, and open-interest acquisition
├── detection/         # Z-score episode detection
├── features/          # Derivatives feature extraction
├── classification/    # Structured episode classification
├── rag/               # News loading, embeddings, and retrieval
├── reporting/         # Mode-isolated JSON reports
├── cli.py             # Single installed command surface
├── pipeline.py        # In-process orchestration
├── evaluation.py      # Direct + Ragas comparison
├── assets/            # Packaged prompts and database/JSON schemas
├── constants.py       # Project defaults
├── llm_client.py
└── live.py            # Local live RAG/LLM bridge

data/                  # Gitignored parquet and generated JSON
```

## Case study

Milestone 1 analyzes one case: the LUNAUSDT crash window from May 7–11, 2022 using Binance Data Vision. It does not establish general source superiority.

## Contributors

- [Luc Zhang (@luckk11)](https://github.com/luckk11) — PostgreSQL news schema, embedding and indexing workflow, vector retrieval prototype, and time-bounded RAG retrieval.

## Documentation

- [CONTEXT.md](CONTEXT.md) — domain language and classification outcomes
- [docs/storage.md](docs/storage.md) — storage design
- [docs/adr/](docs/adr/) — architecture decisions

## Status

Milestone 1 LUNA run is complete. Eight episodes produced 24 classifications across three modes. Derivatives-only and news-only each explained seven episodes; six overlapped, one was derivatives-only, and one was news-only. This single event shows evidence overlap, not general source superiority. See `reports/FINAL_PHASE1_SUMMARY.json`.
