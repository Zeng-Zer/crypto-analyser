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
| Live bars | Bounded backend memory; streamed read-only to viewers with SSE |
| Live news candidates | Configurable free-crypto-news HTTP API; transient keyword + vector RRF rank |
| Confirmed live episodes | PostgreSQL snapshots, LLM results, and Ragas Faithfulness evaluation |
| Pipeline intermediates and reports | Gitignored JSON under `data/` |

Live backend owns Binance ingestion, anomaly detection, news and market-context refreshes, RAG/LLM analysis, and episode persistence. Browser only renders server state and reads persisted history.

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
uv run crypto-analyser evaluate
```

Required environment variables: `DATABASE_URL`, `LLM_API_URL`, and `LLM_API_KEY`. `NEWS_ARCHIVE_DIR` can replace `--archive-dir`.

### Interactive analyst workbench

Historical replay needs only a static server:

```bash
uv run python -m http.server 8000 --directory visuals
```

Live news RAG keeps LLM credentials in backend:

```bash
# Terminal 1: full 24-hour paginated news source
cd ../free-crypto-news && npm run dev

# Terminal 2: PostgreSQL-backed live observation and episode replay
cd ../crypto-analyser
docker compose up -d pgvector
uv run crypto-analyser live

# Optional recent-window refill
uv run crypto-analyser live-backfill --days 5

```

Open `http://localhost:8000` for curated historical replay or `http://localhost:8000/live.html` for live BTCUSDT observation. Saved live episodes open in the same replay page with their persisted BTC context. Live backend backfills and streams closed Binance 5-minute bars, runs historical detector on each update, and publishes read-only state to browsers over SSE. It refreshes funding rate and 4-hour open-interest change every 60 seconds and preceding-24-hour Bitcoin headlines every 90 seconds; ambient refresh does not call LLM. At the second qualifying anomalous bar, backend records the first anomalous bar as onset and the confirmation bar close as detection. Funding and OI stay anchored at onset; news may be published no later than detection. Backend fuses keyword and vector ranks with RRF, runs market-only, news-only, and combined classifiers, then evaluates combined rationale with Ragas Faithfulness. Replay shows the same three-context Explanation check and Ragas audit as historical replay. Complete and failed episodes persist while PostgreSQL storage remains intact. Analysis interrupted by backend restart becomes an explicit failed episode rather than silently remaining pending or repeating billable calls. `live-backfill` applies the unchanged detector to the exact requested window plus a hidden 24-hour warm-up, then runs the same time-safe pipeline for each detected BTC episode. `live-event` applies that pipeline to an explicit UTC window and merges a documented timestamped source corpus from JSON; seed articles published or modified after detector confirmation are rejected. It can detect zero episodes. Existing event references are skipped, so reruns do not repeat LLM/Ragas spend. History defaults to Explained across all dates, newest first; an optional viewer-local date narrows the full episode cards. Each card opens the exact BTC episode through `index.html?source=live`, where Previous/Next navigates that day. Replay shows onset, detection, and detector-relative news timing. `NEWS_API_URL` defaults to sibling `free-crypto-news` at `http://127.0.0.1:3000/api/news`; public fallback remains limited to three sample articles.

### Backend deployment

Requirements: Docker Compose and `free-crypto-news` checked out beside this repository.

```bash
cp .env.example .env
chmod 600 .env
# Replace PGVECTOR_PASSWORD and configure LLM_API_URL/LLM_API_KEY in .env.

docker compose up -d --build
curl --fail http://127.0.0.1:8000/healthz
```

Compose binds application and PostgreSQL to host loopback. Containers communicate over private Compose network. Run one application replica because each process owns market worker. Public hosting must provide HTTPS, route live UI with `/api/*` on same origin, overwrite `X-Forwarded-For`, and apply request limits. Backend allows 120 requests per client per fixed minute and two SSE streams per client, caps total HTTP/SSE connections, rejects write methods, sanitizes public errors, and emits browser security headers. Forwarded addresses are ignored unless direct ingress peer is listed in `TRUSTED_PROXY_CIDRS`; when unset, all traffic through one proxy shares one conservative limit.

Configure GitHub Pages with public backend origin:

```bash
gh variable set LIVE_URL --body 'https://live.example.com'
gh workflow run pages.yml
```

Pages publishes historical `index.html` only and points live links at configured backend origin. Backend container serves live UI and same-origin `/api/*` routes.

Back up PostgreSQL off host regularly:

```bash
mkdir -p backups
docker compose exec -T pgvector sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/crypto-$(date +%F).dump"
```

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
└── live.py            # Backend live stream, detector, RAG/LLM, SSE, and history

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
