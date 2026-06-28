# Crypto Analyzer Phase 1 (Milestone 1) - Historical Analysis Pipeline

## TL;DR

> **Quick Summary**: Build historical crypto anomaly detection system that validates hypothesis: derivatives market structure (funding rates, open interest) can classify price crashes better than lagging news feeds.
> 
> **Deliverables**:
> - Historical OHLCV + derivatives data download scripts
> - Z-score anomaly detection engine
> - Historical RAG pipeline (local news archive → PostgreSQL → pgvector)
> - LLM classifier with structured JSON output
> - Ablation study: derivatives-only vs derivatives+RAG
> - JSON reports with classifications
> 
> **Estimated Effort**: Medium (6 features, greenfield)
> **Parallel Execution**: YES - 4 waves + verification wave
> **Critical Path**: Wave 0 (verification) → Wave 1 → Wave 2 → Wave 3 → Wave 4 → Verification

---

## Context

### Data Sources (100% FREE - No Paid APIs Required)

| Data              | Source                    | Location                                    | Cost | Coverage            |
|-------------------+---------------------------+---------------------------------------------+------+---------------------|
| **OHLCV**         | Binance Data Vision       | `data/futures/um/monthly/klines/LUNAUSDT/5m/`| FREE | Full May 2022       |
| **Open Interest** | Binance Data Vision       | `data/futures/um/daily/metrics/LUNAUSDT/`    | FREE | May 1-12 (5-min)    |
| **Funding Rate**  | Binance Data Vision       | `data/futures/um/monthly/fundingRate/`       | FREE | Full May 2022       |
| **News Archive**  | Local JSON files          | `/Users/david/Dev/free-crypto-news/archive/` | FREE | 172K articles       |

**Total Data Cost: $0**

**News Archive Details**:
- Local archive contains 172,087 articles from Sep 2017 to Jan 2026
- May 2022 fully covered (all 31 days available, ~289 articles/day)
- Pre-extracted tickers (`currencies` array), structured metadata
- Direct PostgreSQL load — no scraping, no rate limits, no Wayback dependency

Base URL: `https://data.binance.vision/`

---

### Original Request
Historical crypto anomaly detection system. Milestone 1: entirely batch/historical (no real-time). Validate hypothesis on LUNA crash (May 2022), then FTX/Bybit as intern enrichment.

### Interview Summary
**Key Discussions**:
- Local news archive discovered — eliminates Wayback scraping entirely
- RAG pipeline simplified: load local JSON → PostgreSQL → retrieval (no external APIs)
- Tech stack validated: UV, pgvector, Langfuse, Ragas, OpenRouter all APPROVED
- Kafka/Quix/Redis deferred to Milestone 2
- Storage: DuckDB + Parquet for OHLCV, PostgreSQL for news
- LLM/Embedding: placeholder (user fills)
- Test strategy: Agent-Executed QA Scenarios

**Validation Window**: May 7-11, 2022 (pre-crash focus due to LUNA delisting on May 12)

**News Archive Structure** (confirmed):
- Daily JSON files: `archive/2022/05/2022-05-{DD}.json`
- Each article has: title, link, pubDate, source, currencies[] array, description (some NULL)
- No enrichment needed at load time — PostgreSQL computes derived columns

### Metis Review
**Identified Gaps** (addressed):
- **BLOCKER #1**: OI data unavailable for May 2022 → **RESOLVED**: FREE via Binance Data Vision (5-min intervals)
- **BLOCKER #2**: LUNA delisting May 12 → Focus on May 7-11 pre-crash validation
- **BLOCKER #3**: Wayback publisher blocking → **ELIMINATED**: Local archive bypasses external APIs entirely

**Guardrails Applied**:
- MUST NOT add more derivatives signals (basis, taker volume) - "start simple" constraint
- MUST NOT add automated test suite - "manual scripts" constraint
- MUST NOT add Bull/Bear/Judge debate - polish, deferred
- MUST NOT add ML classifier - deferred per PROJECT.md
- MUST NOT build real-time infrastructure - Milestone 2
- MUST NOT run sentiment/entity enrichment on articles — use PostgreSQL query-time filtering

### Conventions (resolved during Task 14 / ADR-0001)

- **Package layout**: Python code lives under the `crypto_analyser` package, i.e.
  `src/crypto_analyser/<module>.py`. Every `src/<module>.py` reference in this
  plan resolves there. A thin `src/<module>.py` shim (re-exporting `main`) may
  exist as a CLI entrypoint; the implementation is always the package module.
- **Anomaly unit = one contiguous episode**, not one per-bar flag. See
  `docs/adr/0001-anomaly-is-episode.md`. The bulk anomaly file contains an
  `episodes[]` array plus a `meta` block; each episode carries `onset_ts`,
  `peak_ts`, `peak_z`, `severity`, `direction`, `close_onset`,
  `baseline_close`, `duration_bars`.
- **Derivatives anchor = `onset_ts`.** Downstream tasks that pull
  funding-rate / OI features (Task 15) and that classify an episode (Task 18)
  anchor on `onset_ts` — the moment the deviation became statistically real.
  `peak_ts` is descriptive, not the query anchor. This keeps the contract
  aligned with the hypothesis (unexplained *moves* precede news).
- **Generated `data/` outputs are gitignored.** `data/.gitignore` ignores
  everything under `data/` except `.gitkeep`. Anomalies, derivatives context,
  and per-episode classifications are regenerable from scripts + source data,
  so they are never committed. Validation outputs that ARE the project result
  (ablation comparison, final summary) live at repo root in `results/` and
  `reports/` and ARE tracked.

---

## Work Objectives

### Core Objective
Build complete historical analysis pipeline that validates: derivatives signals (funding rate, OI) + RAG context (historical news) can classify crypto crashes better than news-only approaches.

### Concrete Deliverables
- Data pipeline: OHLCV + funding rate + OI from **Binance Data Vision (FREE)**
- Z-score engine: anomaly detection on 5-min candles
- RAG pipeline: Wayback RSS → embed → pgvector → retrieval
- LLM classifier: structured JSON output (classification, severity, confidence, rationale)
- Ablation study: Ragas evaluation comparing approaches
- JSON reports: saved per event

### Definition of Done
- [ ] LUNA pre-crash window (May 7-11) validates: Z-score catches anomalies
- [ ] LLM classifies anomalies with structured output
- [ ] Ablation study produces publishable result (faithfulness scores)
- [ ] JSON reports saved with classifications
- [ ] All data sources verified (Binance Data Vision, Wayback RSS)

### Must Have
- Historical OHLCV download working (Binance Data Vision - FREE)
- Funding rate download working (Binance Data Vision - FREE)
- OI download working (Binance Data Vision metrics - FREE)
- Z-score anomaly detection producing anomalies for LUNA window
- LLM classifier producing valid JSON schema
- At least one RSS source verified for Wayback retrieval

### Must NOT Have (Guardrails)
- More than 2 derivatives signals (funding rate + OI only)
- Automated test suite (manual scripts for fast iteration)
- Bull/Bear/Judge debate (single classifier first)
- ML classifier (LLM zero-shot)
- Real-time infrastructure (Kafka/Quix/Redis)
- Reranker in RAG (over-engineering risk)
- Intern on critical path (LUNA validation is main developer task)

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (greenfield)
- **Automated tests**: NO (manual scripts for fast iteration per PROJECT.md)
- **Agent-Executed QA**: ALWAYS (mandatory for all tasks)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

| Deliverable Type | Verification Tool                    | Method                                         |
|------------------+--------------------------------------+------------------------------------------------|
| Data Pipeline    | Bash (curl + duckdb CLI)             | Download data, query for coverage              |
| Z-Score Engine   | Bash (python script)                 | Run detection, validate anomaly count > 0      |
| RAG Pipeline     | Bash (curl Wayback + pgvector query) | Verify RSS snapshots exist, query pgvector     |
| LLM Classifier   | Bash (curl localhost:8000)           | POST anomaly, validate JSON schema             |
| Reports          | Bash (jq)                            | Validate JSON structure, classification fields |

---

## Execution Strategy

### Parallel Execution Waves

> Maximize throughput by grouping independent tasks into parallel waves.
> Each wave completes before the next begins.
> Target: 5-8 tasks per wave.

```
Wave 0 (Blocker Resolution - MUST COMPLETE FIRST):
├── Task 0.1: Verify Binance historical data availability [quick] — YOU
└── Task 0.3: Verify pgvector Docker setup works [quick] — YOU

Wave 1 (Foundation - scaffolding + configuration):
├── Task 1: Project scaffolding + UV initialization [quick] — YOU
├── Task 2: DuckDB + Parquet directory structure [quick] — YOU
├── Task 3: Docker Compose setup (pgvector + Langfuse) [quick] — YOU
├── Task 4: Configuration files (API placeholders, thresholds) [quick] — YOU
├── Task 5: LLM client wrapper with placeholder support [quick] — YOU
└── Task 6: Logging + Langfuse SDK integration [quick] — YOU

Wave 2 (Data Pipeline - PARALLEL TRACKS):
├── TRACK A (YOU - Critical Path):
│   ├── Task 7: OHLCV download script (Binance Data Vision) [quick] — YOU
│   ├── Task 8: Funding rate download script (Binance Data Vision) [quick] — YOU
│   └── Task 9: OI download script (Binance Data Vision) [quick] — YOU
│
└── TRACK B (INTERN - News Database, runs parallel):
    ├── Task 10: Define schema + computed columns [quick] — INTERN
    ├── Task 11: Load local archive to PostgreSQL [quick] — INTERN
    ├── Task 12: Generate embeddings [quick] — INTERN
    ├── Task 13: Create database indexes [quick] — INTERN
    └── Task 13.5: Vector Search Demo CLI [quick] — INTERN (showcase task)

Wave 3 (Detection + Classification - 4 PHASES):
│
│   Phase 1 (parallel after Wave 2):
│   ├── Task 14: Z-score computation engine [unspecified-high] — YOU
│   ├── Task 16: Build RAG retrieval query [unspecified-high] — INTERN
│   └── Task 17: LLM classifier prompt + schema [quick] — YOU
│
│   Phase 2 (after Task 14):
│   └── Task 15: Derivatives context extractor [quick] — YOU
│
│   Phase 3 (after Tasks 14, 15, 16, 17):
│   └── Task 18: Classifier execution wrapper [quick] — YOU
│
│   Phase 4 (after Task 18):
│   └── Task 19: JSON report generator [quick] — YOU
│
│   Execution order: 14→15→18→19, with 16,17 parallel with 14

Wave 4 (Validation - YOU waits for intern's Task 16 before Task 22):
├── Task 20: Run pipeline on LUNA May 7-11 window (derivatives-only first) [deep] — YOU
├── Task 21: Ablation study: derivatives-only run [deep] — YOU
│   ▼ HYPOTHESIS PARTIALLY VALIDATED (derivatives-only works)
│   ▼ YOU waits for intern to finish Task 16
├── Task 22: Ablation study: derivatives+RAG run [deep] — YOU (needs intern's Task 16)
├── Task 23: Ragas evaluation + comparison [unspecified-high] — YOU
└── Task 24: JSON report finalization [quick] — YOU

Wave FINAL (Independent Review - 4 parallel):
├── Task F1: Plan compliance audit (oracle) — YOU
├── Task F2: Code quality review (unspecified-high) — YOU
├── Task F3: Real manual QA (unspecified-high) — YOU
└── Task F4: Scope fidelity check (deep) — YOU

Critical Path: Wave 0 → Wave 1 → Wave 2 Track A → Wave 3 Track A → Task 20 → Task 21
              ▼ (YOU proceeds to Milestone 2 while intern finishes RAG)
              Optional: Task 22 (needs intern's Task 16 complete)

Intern Track: Wave 2 Track B → Wave 3 Track B → Task 16 complete
              ▼ (Intern validates FTX/Bybit while YOU on Milestone 2)

Parallel Speedup: ~70% faster than sequential
Max Concurrent: 7 (Wave 2 - 3 YOU + 4 INTERN parallel, demo runs after indexes)
```

---

### Work Allocation Summary

| Developer                | Tasks                                              | Skills Developed/Leveraged                                                          |
|--------------------------+----------------------------------------------------+-------------------------------------------------------------------------------------|
| **YOU (Main Developer)** | Tasks 0.1, 0.3, 1-9, 14-15, 17-24, F1-F4 (19 tasks) | Architecture, hypothesis logic, pipeline design, validation, evaluation             |
| **INTERN**               | Tasks 10-13, 13.5, 16 (6 tasks)                    | Data engineering, PostgreSQL schema, ML embeddings, indexing, CLI demo, hybrid search |

---

### Intern Task Breakdown

| Task                        | What Intern Builds                                       | Skills Learned                              | Blocking YOU?       |
|------------------------------+----------------------------------------------------------+---------------------------------------------+---------------------|
| **10. Schema + Computed**    | Table schema, generated columns, text search setup       | PostgreSQL schema design, tsvector          | Blocks Task 11-13   |
| **11. Load Archive to DB**   | Bulk JSON loader, PostgreSQL inserts, array handling     | Data engineering, batch processing          | Blocks Task 12      |
| **12. Embedding Generation** | Batch embedding, API/library integration, error handling | ML integration, batch processing            | Blocks Task 13, 16  |
| **13. Database Indexes**     | GIN/BRIN/HNSW indexes, performance tuning               | PostgreSQL indexing, vector search          | Blocks Task 13.5, 16 |
| **13.5. Vector Search Demo** | CLI demo with formatted output, similarity search       | Python CLI, user-facing tools               | None (showcase)     |
| **16. RAG Retrieval**        | Hybrid search query, time-bounded filtering, RRF ranking | Vector search, query design                 | Blocks Task 22 only |

**Key insight**: Intern's work ONLY blocks Task 22 (derivatives+RAG ablation). Task 21 (derivatives-only) validates hypothesis without waiting for intern. Demo (Task 13.5) is a showcase deliverable, not a production dependency.

---

## TODOs

### Wave 0: Blocker Resolution (MUST COMPLETE FIRST)

- [x] 0.1. Verify Binance Historical Data Availability ✓ DONE

  **What to do**:
  - Test Binance API for LUNA/LUNC OHLCV data from May 2022
  - Test Binance API for LUNA/LUNC funding rate from May 2022
  - Document exact symbol name (LUNA vs LUNC vs LUNA2)
  - Confirm data coverage for May 7-11 window

  **Evidence**:
  - Data downloaded to `poc_binance_api/data/` (excluded from git per .gitignore)
  - Symbol: LUNAUSDT (pre-crash symbol)
  - Coverage: Nov 2021 - May 2022 (including May 7-11 validation window)
  - Klines: 1-min granularity (7 monthly CSVs)
  - Funding rate: 8h intervals (7 monthly CSVs)
  - Metrics/OI: 5-min granularity (162 daily CSVs, ends May 12 when delisted)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple API verification task
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 0.2, 0.3)
  - **Blocks**: Wave 1 (all foundation tasks need confirmed data strategy)
  - **Blocked By**: None

  **References**:
  - Binance klines API: `https://fapi.binance.com/fapi/v1/klines?symbol=LUNCUSDT&interval=5m&startTime=1651651200000`
  - Binance funding rate API: `https://fapi.binance.com/fapi/v1/fundingRate?symbol=LUNCUSDT&startTime=1651651200000`

  **Acceptance Criteria**:
  - [x] OHLCV query returns data for May 2022 (status 200, non-empty response)
  - [x] Funding rate query returns data for May 2022 (status 200, non-empty response)
  - [x] Symbol name documented: LUNAUSDT (pre-crash)

  **QA Scenarios**:
  ```
  Scenario: Binance OHLCV API responds with historical data
    Tool: Bash (curl)
    Steps:
      1. curl "https://fapi.binance.com/fapi/v1/klines?symbol=LUNCUSDT&interval=5m&startTime=1651651200000&endTime=1651651200000&limit=1"
      2. Check response: jq '.[0]' should be non-empty array
    Expected Result: HTTP 200 + JSON array with at least 1 kline
    Evidence: .sisyphus/evidence/task-0.1-ohlcv-api-test.txt

  Scenario: Binance funding rate API responds
    Tool: Bash (curl)
    Steps:
      1. curl "https://fapi.binance.com/fapi/v1/fundingRate?symbol=LUNCUSDT&startTime=1651651200000&limit=1"
      2. Check response: jq '.[0].fundingTime' should be timestamp
    Expected Result: HTTP 200 + JSON with funding rate data
    Evidence: .sisyphus/evidence/task-0.1-funding-api-test.txt
  ```

  **Commit**: YES
  - Message: `docs: binance api verification`
  - Files: `docs/api-verification.md`

---

- [x] 0.3. Verify pgvector Docker Setup Works ✓ DONE

  **What to do**:
  - Create minimal Docker Compose with pgvector extension
  - Test pgvector extension loads correctly
  - Verify hybrid search query works (vector + tsvector)
  - Confirm connection pool from Python

  **Evidence**:
  - Created `docker-compose.test.yml` with `pgvector/pgvector:pg17` (current official image)
  - **PostgreSQL 17.9** running (latest stable)
  - **pgvector 0.8.2** extension verified (latest version)
  - Container running on port 5433 (healthy status)
  - Hybrid search tested: Created test table with `vector(3)` column, inserted 5 test vectors
  - Similarity query using `<->` operator returns ranked results ordered by distance
  - Note: `ankane/pgvector` deprecated - migrated to official `pgvector/pgvector` org image
  - Evidence files saved:
    - `.sisyphus/evidence/task-0.3-pgvector-start.txt`
    - `.sisyphus/evidence/task-0.3-hybrid-query.txt`
    - `.sisyphus/evidence/task-0.3-versions.txt`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Infrastructure verification
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Tasks 0.1, 0.2)
  - **Blocks**: Task 3 (full Docker setup)
  - **Blocked By**: None

  **References**:
  - pgvector Docker: `pgvector/pgvector:pg17` (official image, formerly ankane/pgvector)
  - Hybrid search SQL: See research findings (RRF pattern)

  **Acceptance Criteria**:
  - [x] Docker Compose runs without errors
  - [x] pgvector extension installed (`SELECT * FROM pg_extension WHERE extname='vector'`)
  - [x] Hybrid search query returns results (test with dummy data)

  **QA Scenarios**:
  ```
  Scenario: pgvector Docker container starts successfully
    Tool: Bash (docker)
    Steps:
      1. docker-compose up -d pgvector
      2. docker-compose exec pgvector psql -c "SELECT extname FROM pg_extension WHERE extname='vector'"
    Expected Result: Output shows "vector"
    Evidence: .sisyphus/evidence/task-0.3-pgvector-start.txt

  Scenario: pgvector hybrid search works
    Tool: Bash (docker + psql)
    Steps:
      1. Create test table with embedding column
      2. Insert dummy vector data
      3. Run hybrid search query (RRF pattern)
    Expected Result: Query returns ranked results
    Evidence: .sisyphus/evidence/task-0.3-hybrid-query.txt
  ```

  **Commit**: YES
  - Message: `test: pgvector docker verification`
  - Files: `docker-compose.test.yml`

---

- [ ] 3. Docker Compose Setup (pgvector + Langfuse)

  **What to do**:
  - Create docker-compose.yml with:
    - pgvector service (ankane/pgvector image)
    - Langfuse services (web + worker + postgres + clickhouse + redis + minio)
  - Configure environment variables (secrets as placeholders)
  - Create .env.example with required secrets
  - Document service endpoints: pgvector localhost:5432, Langfuse localhost:3000

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Infrastructure setup
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-2, 4-6)
  - **Blocks**: Tasks 12-13 (embedding + pgvector insertion)
  - **Blocked By**: Wave 0 (Task 0.3 verified pgvector setup)

  **References**:
  - Langfuse Docker docs: `https://langfuse.com/self-hosting/deployment/docker-compose`
  - pgvector Docker: `ankane/pgvector`

  **Acceptance Criteria**:
  - [ ] docker-compose.yml created with all services
  - [ ] .env.example created with placeholder secrets
  - [ ] docker-compose config validated (no syntax errors)

  **QA Scenarios**:
  ```
  Scenario: Docker Compose validates successfully
    Tool: Bash (docker)
    Steps:
      1. docker-compose config
    Expected Result: No errors, services listed
    Evidence: .sisyphus/evidence/task-3-docker-validate.txt
  ```

  **Commit**: YES
  - Message: `feat: docker compose setup`
  - Files: `docker-compose.yml, .env.example`

---

- [ ] 4. Configuration Files (API placeholders, thresholds)

  **What to do**:
  - Create `config/settings.yaml` with:
    - API endpoints (Binance, Wayback)
    - Placeholder keys: LLM_API_URL, LLM_API_KEY, EMBEDDING_MODEL_URL
    - Z-score thresholds: window=24h, threshold=2.5
    - RSS feed list (from verified feeds in Task 0.2)
    - Event windows: LUNA May 7-11, FTX Nov 6-12, Bybit Feb 21-22
  - Create config loader script

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Configuration setup
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-3, 5-6)
  - **Blocks**: All downstream scripts (need config)
  - **Blocked By**: Wave 0 (feeds verified in Task 0.2)

  **Acceptance Criteria**:
  - [ ] settings.yaml created with all placeholders
  - [ ] Config loader script works (yaml.load)
  - [ ] Placeholder keys documented for user to fill

  **QA Scenarios**:
  ```
  Scenario: Config loads successfully
    Tool: Bash (python)
    Steps:
      1. python -c "import yaml; yaml.safe_load(open('config/settings.yaml'))"
    Expected Result: No errors
    Evidence: .sisyphus/evidence/task-4-config-load.txt
  ```

  **Commit**: YES
  - Message: `feat: configuration setup`
  - Files: `config/settings.yaml, src/crypto_analyser/config.py`

---

- [ ] 5. LLM Client Wrapper with Placeholder Support

  **What to do**:
  - Create `src/llm_client.py` with:
    - OpenAI-compatible client wrapper
    - Load API_URL and API_KEY from config (placeholders)
    - Structured output support (response_format=json_schema)
    - Error handling for placeholder values
  - Create JSON schema for classification output

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: API wrapper setup
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4, 6)
  - **Blocks**: Tasks 17-18 (LLM classifier)
  - **Blocked By**: Wave 0

  **References**:
  - OpenRouter docs: `response_format={"type": "json_schema", "strict": true}`
  - JSON schema: `{"classification": str, "severity": int, "confidence": float, "rationale": str}`

  **Acceptance Criteria**:
  - [ ] llm_client.py created
  - [ ] Placeholder detection works (raises error if not filled)
  - [ ] JSON schema defined

  **QA Scenarios**:
  ```
  Scenario: LLM client placeholder detection works
    Tool: Bash (python)
    Steps:
      1. Set API_KEY placeholder value
      2. Call llm_client.analyze()
      3. Expect error: "API_KEY placeholder not filled"
    Expected Result: Error raised with placeholder message
    Evidence: .sisyphus/evidence/task-5-llm-placeholder.txt
  ```

  **Commit**: YES
  - Message: `feat: LLM client wrapper`
  - Files: `src/crypto_analyser/llm_client.py, schemas/classification.json`

---

- [ ] 6. Logging + Langfuse SDK Integration

  **What to do**:
  - Create `src/logging_config.py` with structured logging
  - Integrate Langfuse SDK:
    - Load Langfuse keys from config
    - Create trace wrapper for pipeline steps
    - Score attachment helper function
  - Create `src/tracing.py` for Langfuse decorators

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Observability setup
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-5)
  - **Blocks**: All downstream tasks (need logging)
  - **Blocked By**: Wave 0

  **References**:
  - Langfuse Python SDK: `from langfuse import Langfuse, observe`

  **Acceptance Criteria**:
  - [ ] Logging configured with file + console output
  - [ ] Langfuse SDK initialized (with placeholder support)
  - [ ] Trace wrapper created

  **QA Scenarios**:
  ```
  Scenario: Logging outputs to file
    Tool: Bash (python)
    Steps:
      1. python -c "from src.logging_config import get_logger; logger = get_logger(); logger.info('test')"
      2. Check logs/app.log exists
    Expected Result: log file created with test message
    Evidence: .sisyphus/evidence/task-6-logging.txt
  ```

  **Commit**: YES
  - Message: `feat: logging and Langfuse integration`
  - Files: `src/crypto_analyser/logging_config.py, src/crypto_analyser/tracing.py`

---

### Wave 2: Data Pipeline (MAX PARALLEL - 7 tasks)

- [x] 7. OHLCV Download Script (Binance Data Vision - FREE) ✓ DONE

  **What to do**:
  - Create `scripts/download_ohlcv.py`:
    - Download from Binance Data Vision (FREE, no API key needed)
    - URL: `https://data.binance.vision/data/futures/um/monthly/klines/LUNAUSDT/5m/`
    - Monthly zip files for May 2022
    - Parse CSV: timestamp, open, high, low, close, volume
    - Store to Parquet: `data/ohlcv/{symbol}_{month}.parquet`
  - Support multiple symbols: LUNA/LUNC, BTC, ETH

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple download script for free data
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8-13)
  - **Blocks**: Task 14 (Z-score computation)
  - **Blocked By**: Wave 1 (Task 1 project structure, Task 4 config)

  **References**:
  - Binance Data Vision: `https://data.binance.vision/`
  - Klines URL: `https://data.binance.vision/data/futures/um/monthly/klines/LUNAUSDT/5m/LUNAUSDT-5m-2022-05.zip`

  **Acceptance Criteria**:
  - [ ] Script downloads OHLCV for May 2022
  - [ ] Parquet file created with correct schema
  - [ ] FREE - no rate limit concerns

  **QA Scenarios**:
  ```
  Scenario: OHLCV download for LUNA May 2022
    Tool: Bash (python)
    Steps:
      1. python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05
      2. duckdb -c "SELECT COUNT(*) FROM read_parquet('data/ohlcv/LUNAUSDT_2022-05.parquet')"
    Expected Result: ~44640 rows (288 candles/day x ~31 days, minus delisting gaps)
    Evidence: .sisyphus/evidence/task-7-ohlcv-download.txt

  Scenario: Free data URL accessible
    Tool: Bash (curl)
    Steps:
      1. curl -sI "https://data.binance.vision/data/futures/um/monthly/klines/LUNAUSDT/5m/LUNAUSDT-5m-2022-05.zip"
      2. Check HTTP status = 200
    Expected Result: File exists
    Evidence: .sisyphus/evidence/task-7-ohlcv-url.txt
  ```

  **Commit**: YES
  - Message: `feat: OHLCV download from Binance Data Vision`
  - Files: `scripts/download_ohlcv.py`

---

- [x] 8. Funding Rate Download Script (Binance Data Vision - FREE) ✓ DONE

  **What to do**:
  - Create `scripts/download_funding.py`:
    - Download from Binance Data Vision (FREE, no API key needed)
    - URL: `https://data.binance.vision/data/futures/um/monthly/fundingRate/LUNAUSDT/`
    - Monthly CSV files: timestamp, funding rate
    - 8-hour intervals (3 funding events per day)
    - Store to Parquet: `data/funding/{symbol}_{month}.parquet`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple download script for free data
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9-13)
  - **Blocks**: Task 15 (derivatives context extractor)
  - **Blocked By**: Wave 1 (Task 1, Task 4)

  **References**:
  - Binance Data Vision: `https://data.binance.vision/`
  - Funding Rate URL: `https://data.binance.vision/data/futures/um/monthly/fundingRate/LUNAUSDT/LUNAUSDT-fundingRate-2022-05.zip`

  **Acceptance Criteria**:
  - [ ] Script downloads funding rate for May 2022
  - [ ] Parquet file created
  - [ ] FREE - no rate limit concerns

  **QA Scenarios**:
  ```
  Scenario: Funding rate download for LUNA May 2022
    Tool: Bash (python)
    Steps:
      1. python scripts/download_funding.py --symbol LUNAUSDT --month 2022-05
      2. duckdb -c "SELECT COUNT(*) FROM read_parquet('data/funding/LUNAUSDT_2022-05.parquet')"
    Expected Result: ~37 rows (12 days x 3 funding events/day, delisted May 12)
    Evidence: .sisyphus/evidence/task-8-funding-download.txt

  Scenario: Free data URL accessible
    Tool: Bash (curl)
    Steps:
      1. curl -sI "https://data.binance.vision/data/futures/um/monthly/fundingRate/LUNAUSDT/LUNAUSDT-fundingRate-2022-05.zip"
      2. Check HTTP status = 200
    Expected Result: File exists
    Evidence: .sisyphus/evidence/task-8-funding-url.txt
  ```

  **Commit**: YES
  - Message: `feat: funding rate download from Binance Data Vision`
  - Files: `scripts/download_funding.py`

---

- [x] 9. OI Download Script (Binance Data Vision - FREE) ✓ DONE

  **What to do**:
  - Create `scripts/download_oi.py`:
    - Download from Binance Data Vision: `https://data.binance.vision/data/futures/um/daily/metrics/LUNAUSDT/`
    - FREE historical data (no API key needed)
    - Coverage: May 1-12, 2022 (covers LUNA crash period)
    - Frequency: 5-minute intervals (288 observations/day)
    - Extract: `sum_open_interest`, `sum_open_interest_value`, long/short ratios
    - Store to Parquet: `data/oi/LUNAUSDT_2022-05.parquet`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple download script for free data
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-8, 10-13)
  - **Blocks**: Task 15 (derivatives context extractor)
  - **Blocked By**: Wave 1 (project structure, config)

  **References**:
  - Binance Data Vision: `https://data.binance.vision/`
  - Metrics URL: `https://data.binance.vision/data/futures/um/daily/metrics/LUNAUSDT/LUNAUSDT-metrics-2022-05-{day}.zip`
  - Fields: `sum_open_interest`, `sum_open_interest_value`, `count_long_short_ratio`

  **Acceptance Criteria**:
  - [ ] Script downloads OI for May 1-12, 2022
  - [ ] Parquet file created with OI data
  - [ ] 5-minute granularity preserved (~3456 rows for 12 days)

  **QA Scenarios**:
  ```
  Scenario: Binance Data Vision OI download
    Tool: Bash (python)
    Steps:
      1. python scripts/download_oi.py --symbol LUNAUSDT --start 2022-05-01 --end 2022-05-12
      2. duckdb -c "SELECT COUNT(*), MIN(create_time), MAX(create_time) FROM read_parquet('data/oi/LUNAUSDT_2022-05.parquet')"
    Expected Result: ~3456 rows, May 1-12 coverage
    Evidence: .sisyphus/evidence/task-9-oi-download.txt

  Scenario: Free data URL accessible
    Tool: Bash (curl)
    Steps:
      1. curl -sI "https://data.binance.vision/data/futures/um/daily/metrics/LUNAUSDT/LUNAUSDT-metrics-2022-05-09.zip"
      2. Check HTTP status = 200
    Expected Result: File exists and accessible
    Evidence: .sisyphus/evidence/task-9-oi-url.txt
  ```

  **Commit**: YES
  - Message: `feat: OI download from Binance Data Vision`
  - Files: `scripts/download_oi.py`

---

- [ ] 10. Define PostgreSQL Schema + Create Table — **INTERN TASK**

  **What to do**:
  - Design a PostgreSQL table schema for crypto news articles
  - Required columns: title, description, link, publication date, source, category, tickers
  - Figure out: what column types for each field? How to store arrays?
  - Create a computed column that combines title + description for search purposes — PostgreSQL can compute this automatically
  - Create a full-text search column using PostgreSQL's built-in text search — also computed automatically
  - Leave room for an embedding column (vector type) — will be filled later
  - Write the CREATE TABLE SQL and run it
  - Document your schema decisions

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Schema design
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (start immediately, no dependencies)
  - **Parallel Group**: Wave 2 (with Tasks 7-9)
  - **Blocks**: Task 11 (load data needs table), Task 12 (embedding column)
  - **Blocked By**: Wave 0 (pgvector extension confirmed) — ALREADY DONE

  **References**:
  - pgvector documentation: how to create vector columns
  - PostgreSQL array types: how to define TEXT[] columns
  - PostgreSQL generated columns: how to auto-compute derived values
  - PostgreSQL full-text search: tsvector type

  **Acceptance Criteria**:
  - [ ] Table created with all required columns
  - [ ] Array column for tickers works (test insert with array)
  - [ ] Computed content column auto-populates
  - [ ] Text search column auto-populates
  - [ ] Schema documented

  **QA Scenarios**:
  ```
  Scenario: Schema accepts test insert
    Tool: Bash (psql)
    Steps:
      1. Insert a test row with sample data
      2. Verify computed columns populated correctly
      3. Delete test row
    Expected Result: Insert succeeds, computed columns have values
    Evidence: .sisyphus/evidence/task-10-schema-test.txt

  Scenario: Text search works
    Tool: Bash (psql)
    Steps:
      1. Insert test article with known text
      2. Query using text search syntax
      3. Verify it returns the test article
    Expected Result: Text search query finds matching article
    Evidence: .sisyphus/evidence/task-10-textsearch.txt
  ```

  **Commit**: YES
  - Message: `feat: crypto_news table schema`
  - Files: `sql/schema.sql`, `docs/schema.md`

  ---
  **INTERN TASK** — First intern task! No dependencies, start immediately.

---

- [ ] 11. Load Local Archive to PostgreSQL — **INTERN TASK**

  **What to do**:
  - Locate the local archive directory containing historical crypto news JSON files
  - Understand the JSON structure — each file represents one day of articles
  - Figure out how to insert array data (the `currencies` field) into PostgreSQL
  - Handle edge cases: some description fields are null strings ("NULL"), some missing
  - Write a Python script that reads JSON files and inserts into PostgreSQL
  - Start with May 2022 data — other months can be added later
  - Verify: count rows inserted matches article count in source files
  - Make the script idempotent — can rerun without duplicating data

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Data loading script
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Task 10 schema is complete)
  - **Parallel Group**: Wave 2 (with Tasks 7-9, 12-13)
  - **Blocks**: Task 12 (embeddings need data)
  - **Blocked By**: Task 10 (schema/table must exist before inserting)

  **References**:
  - Archive location: `/Users/david/Dev/free-crypto-news/archive`
  - JSON files organized by year/month/day
  - PostgreSQL connection: check docker-compose.yml for credentials
  - Look at `psycopg2` or similar library for Python-PostgreSQL connection

  **Acceptance Criteria**:
  - [ ] May 2022 articles loaded (count matches source)
  - [ ] NULL descriptions handled correctly (not inserted as string "NULL")
  - [ ] Currencies array preserved as PostgreSQL array type
  - [ ] Script can rerun without duplicating rows

  **QA Scenarios**:
  ```
  Scenario: Archive data loaded successfully
    Tool: Bash (psql)
    Steps:
      1. Connect to pgvector database
      2. Count rows where pub_date is in May 2022
      3. Compare against article count from archive
    Expected Result: Row count matches expected articles for May 2022
    Evidence: .sisyphus/evidence/task-11-load-count.txt

  Scenario: Currencies array preserved
    Tool: Bash (psql)
    Steps:
      1. Query a row where currencies had multiple values
      2. Check the array column contains all tickers
    Expected Result: Array column has correct tickers
    Evidence: .sisyphus/evidence/task-11-array-check.txt
  ```

  **Commit**: YES
  - Message: `feat: load archive to postgresql`
  - Files: `scripts/load_archive.py`

  ---
  **INTERN TASK** — Runs after Task 10 (schema). Data engineering focus.

- [ ] 12. Generate Embeddings for Article Content — **INTERN TASK**

  **What to do**:
  - Read articles from PostgreSQL (use the content column from Task 10)
  - Choose an embedding model — check what's configured, or ask if unclear
  - Figure out how to call the embedding model (API or local library)
  - Process articles in batches — don't send one request per article
  - Handle rate limits if using an API — you may need to throttle
  - Handle errors — some articles might fail, log them but continue
  - Update each row's embedding column with the generated vector
  - Verify: sample rows and check embedding is populated with numbers

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Embedding generation
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES (after data loaded)
  - **Parallel Group**: Wave 2 (with Tasks 7-9, 13)
  - **Blocks**: Task 13 (indexes need embeddings), Task 16 (retrieval needs embeddings)
  - **Blocked By**: Task 10 (schema with embedding column), Task 11 (data loaded)

  **References**:
  - Config file: `config/settings.yaml` — check for embedding model settings
  - Embedding dimension: depends on model, ask if unclear
  - PostgreSQL vector update: how to update vector columns

  **Acceptance Criteria**:
  - [ ] Embeddings generated for May 2022 articles
  - [ ] Embedding column populated with vectors
  - [ ] Failed articles logged but didn't crash
  - [ ] Batch processing used (not one-by-one)

  **QA Scenarios**:
  ```
  Scenario: Embeddings populated
    Tool: Bash (psql)
    Steps:
      1. Count rows where embedding column is not null
      2. Should match total article count
    Expected Result: All rows have embeddings
    Evidence: .sisyphus/evidence/task-12-embedding-count.txt

  Scenario: Embedding dimension correct
    Tool: Bash (psql)
    Steps:
      1. Sample one embedding vector
      2. Count its dimensions
    Expected Result: Dimension matches model output size
    Evidence: .sisyphus/evidence/task-12-embedding-dim.txt
  ```

  **Commit**: YES
  - Message: `feat: embedding generation`
  - Files: `scripts/generate_embeddings.py`

---

- [ ] 13. Create Database Indexes for Fast Retrieval — **INTERN TASK**

  **What to do**:
  - Understand what indexes are needed:
    - Fast lookup by ticker (array column needs special index type)
    - Fast lookup by publication date (time-bounded queries)
    - Fast vector similarity search (embedding column)
    - Fast text search (textsearch column)
  - Research: what PostgreSQL index types for arrays? For time ranges? For vectors? For full-text?
  - Create indexes — think about parameters that affect performance
  - Verify: indexes created and queries use them
  - Document: which indexes you chose and why

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Index creation
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-12)
  - **Blocks**: Task 16 (retrieval needs indexes to be fast)
  - **Blocked By**: Task 12 (embeddings populated for vector index)

  **References**:
  - pgvector documentation: recommended index types and parameters
  - PostgreSQL GIN index: for array columns
  - PostgreSQL BRIN index: for time-series data
  - PostgreSQL GIN index: for tsvector columns

  **Acceptance Criteria**:
  - [ ] Index on tickers column created
  - [ ] Index on pub_date column created
  - [ ] Index on embedding column created (vector search)
  - [ ] Index on textsearch column created
  - [ ] Query performance documented

  **QA Scenarios**:
  ```
  Scenario: Ticker filter is fast
    Tool: Bash (psql)
    Steps:
      1. Query articles by ticker array
      2. Check query plan uses index
    Expected Result: Index scan in query plan
    Evidence: .sisyphus/evidence/task-13-ticker-index.txt

  Scenario: Vector search works
    Tool: Bash (psql)
    Steps:
      1. Run vector similarity query (nearest neighbors)
      2. Verify results returned in reasonable time
    Expected Result: Query returns ranked results
    Evidence: .sisyphus/evidence/task-13-vector-index.txt
  ```

  **Commit**: YES
  - Message: `feat: database indexes`
  - Files: `sql/indexes.sql`, `docs/indexes.md`

---

- [ ] 13.5. Vector Search Demo CLI — **INTERN SHOWCASE TASK**

  **What to do**:
  - Create `scripts/demo_retrieval.py` — a CLI tool to showcase your vector search pipeline
  - Features:
    - Accept query text via command line
    - Generate embedding from query text (use configured embedding model)
    - Execute pgvector similarity query directly (no retrieval function needed)
    - Display ranked results with formatted output:
      - Article title (truncated if too long)
      - Publication date and source
      - Snippet (first 100 chars of content)
      - Similarity score (0.0-1.0, computed as `1 - distance`)
      - Tickers mentioned (from currencies array)
    - Show performance metrics: latency, index type used, total rows
  - Use `rich` library for colored/formatted output
  - Include example queries in `docs/demo-guide.md`
  - Test queries: "Terra UST depeg", "LUNA price crash", "Bitcoin ETF approval", "Ethereum merge"

  **Recommended Agent Profile**:
  - **Category**: `quick` — Demo/CLI development
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: NO — runs after Task 13 (indexes) complete
  - **Parallel Group**: Wave 2 Track B (final intern task)
  - **Blocks**: None (demo is showcase, not production dependency)
  - **Blocked By**: Task 13 (HNSW index needed for fast search), Task 12 (embeddings populated)

  **References**:
  - CLI libraries: `argparse` (standard), `rich` (for colored output)
  - pgvector query: `SELECT ... ORDER BY embedding <-> query_vector LIMIT 10`
  - Task 0.3 evidence file shows example pgvector query syntax

  **Example Output**:
  ```
  $ python scripts/demo_retrieval.py --query "Terra UST depeg"

  🔍 Searching 9,000 crypto news articles from May 2022...

  Top 10 most similar articles:
  ────────────────────────────────────────────────────────────────
  1. [0.92] Terra's UST stablecoin loses dollar peg
     📅 CoinDesk | 2022-05-09 14:32 UTC
     💬 "UST, the algorithmic stablecoin at the heart..."
     🏷️  [UST, LUNA, TERRA]

  2. [0.88] LUNA price crashes 99% as Terra ecosystem unravels
     📅 Cointelegraph | 2022-05-09 18:45 UTC
     💬 "The collapse of Terra's dual-token system..."
     🏴️  [LUNA, UST]

  3. [0.85] Do Kwon addresses Terra community amid crisis
     📅 The Block | 2022-05-09 22:10 UTC
     💬 "Terra founder proposed a recovery plan..."
     🏴️  [LUNA, TERRA]
  ────────────────────────────────────────────────────────────────
  📊 Performance: 23ms latency | HNSW index used | 9,000 rows scanned
  ```

  **What This Demo Proves**:
  - Vector embeddings work (query → embedding → results)
  - pgvector similarity search works with `<->` operator
  - HNSW index provides fast retrieval (< 50ms)
  - All 9,000 May 2022 articles are searchable
  - Pipeline end-to-end: data → embeddings → index → search

  **Acceptance Criteria**:
  - [ ] `scripts/demo_retrieval.py` created and runnable
  - [ ] Query returns ranked results with similarity scores
  - [ ] Output formatted for readability (not raw JSON)
  - [ ] Performance metrics displayed (latency, index type)
  - [ ] Example queries documented in `docs/demo-guide.md`
  - [ ] Demo shows latency < 50ms for May 2022 data

  **QA Scenarios**:
  ```
  Scenario: Demo runs successfully
    Tool: Bash (python)
    Steps:
      1. python scripts/demo_retrieval.py --query "Terra UST depeg"
      2. Check output shows ranked articles with scores
    Expected Result: 10 articles returned with formatted output
    Evidence: .sisyphus/evidence/task-13.5-demo-run.txt

  Scenario: Demo shows performance metrics
    Tool: Bash (python)
    Steps:
      1. Run demo with any query
      2. Check output includes latency and "HNSW index"
    Expected Result: Shows "latency: Xms" and index type
    Evidence: .sisyphus/evidence/task-13.5-demo-perf.txt

  Scenario: Demo handles embedding API errors gracefully
    Tool: Bash (python)
    Steps:
      1. Run demo when embedding API is unavailable
      2. Check error message is user-friendly
    Expected Result: Shows "Embedding API error" message, no crash
    Evidence: .sisyphus/evidence/task-13.5-demo-error.txt
  ```

  **Commit**: YES
  - Message: `feat: vector search demo CLI`
  - Files: `scripts/demo_retrieval.py`, `docs/demo-guide.md`

  ---
  **INTERN SHOWCASE TASK** — Your final Wave 2 deliverable! Demo this to show: "I built a semantic search engine for crypto news."
  
  **Note**: This is a **basic vector search demo**. Task 16 (Wave 3) will build the production retrieval with time filtering, ticker filtering, and hybrid search for the ablation study.

---

### Wave 3: Detection + Classification

- [x] 14. Z-Score Computation Engine ✓ DONE

  **What to do**:
  - Create `src/crypto_analyser/zscore.py` (CLI shim `src/zscore.py`):
    - Load OHLCV data from Parquet
    - Compute rolling Z-score on price close (window=24h, from config)
    - Detect anomalies: |Z| > threshold (default from config)
    - Group per-bar flags into contiguous *episodes* (gap-tolerant,
      min-consecutive) per ADR-0001 — not a flat list of per-bar timestamps
    - Output: bulk file with `meta` + `episodes[]`, each episode carrying
      onset_ts, peak_ts, peak_z, severity, direction, close_onset,
      baseline_close, duration_bars
    - Store to: `data/anomalies/{symbol}_{start}_{end}.json` (gitignored)
  - Support configurable window (hours, optional `h` suffix), threshold,
    max-gap, min-consecutive (config + CLI overrides)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Statistical computation, needs careful implementation
  - **Skills**: none needed

  **Parallelization**:
  - **Phase**: 1 (can start immediately after Wave 2)
  - **Runs In Parallel With**: Task 16, Task 17
  - **Blocks**: Task 15 (needs anomaly timestamps)
  - **Blocked By**: Wave 2 (Task 7 OHLCV data)

  **References**:
  - Z-score formula: `(x - mean) / std` on rolling window
  - Window: 24h rolling (standard)

  **Acceptance Criteria**:
  - [ ] Z-score computed for OHLCV data
  - [ ] Anomalies detected (LUNA window should produce anomalies)
  - [ ] JSON output with timestamps and severity

  **QA Scenarios**:
  ```
  Scenario: Z-score detects LUNA anomalies
    Tool: Bash (python)
    Steps:
      1. python src/zscore.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --threshold 2.5
      2. jq '.episodes | length' data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json
    Expected Result: episodes > 0 (LUNA crash triggers; observed 5 at default config)
    Evidence: .sisyphus/evidence/task-14-zscore-luna.txt

  Scenario: Z-score window configurable
    Tool: Bash (python)
    Steps:
      1. python src/zscore.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --window 12h --threshold 3.0
      2. Check different episode count produced vs default-config run
    Expected Result: Config affects detection (observed 7 episodes, peak |Z| 5.07)
    Evidence: .sisyphus/evidence/task-14-zscore-config.txt
  ```

  **Commit**: YES
  - Message: `feat: Z-score anomaly detection`
  - Files: `src/zscore.py`

---

- [x] 15. Derivatives Context Extractor

  **What to do**:
  - Create `src/crypto_analyser/derivatives_context.py` (CLI shim as needed):
    - Read the bulk `episodes[]` file from Task 14 (not per-bar timestamps)
    - For each episode, anchor derivatives retrieval on `onset_ts` (the moment
      the deviation became statistically real; `peak_ts` is descriptive only)
    - Pull funding rate at `onset_ts` (or nearest 8h interval)
    - Pull OI at `onset_ts` (5-min granularity from Binance Data Vision)
    - Compute: funding_rate_current, funding_rate_avg_4h, oi_current, oi_change_4h
      (lookback window relative to each episode's `onset_ts`, not its duration)
    - Package as feature vector per episode: JSON keyed by `onset_ts`
    - Store to: `data/context/{symbol}_{start}_{end}_context.json` (gitignored)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Feature extraction
  - **Skills**: none needed

  **Parallelization**:
  - **Phase**: 2 (starts after Task 14 completes)
  - **Runs In Parallel With**: None (sequential after Task 14)
  - **Blocks**: Task 18 (LLM classifier needs derivatives features)
  - **Blocked By**: Task 14 (anomaly timestamps), Task 8 (funding data from Wave 2)

  **Acceptance Criteria**:
  - [x] Derivatives context extracted for anomalies (7 feature vectors for 7 episodes)
  - [x] OI data included (from Binance Data Vision 5-min parquet)
  - [x] Feature vector JSON output saved to `data/context/`

  **QA Scenarios**:
  ```
  Scenario: Derivatives context extraction
    Tool: Bash (python)
    Steps:
      1. python src/crypto_analyser/derivatives_context.py --anomalies data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json
      2. jq '.features[0].funding_rate_current' data/context/LUNAUSDT_2022-05-07_2022-05-11_context.json
    Expected Result: funding_rate_current value present
    Evidence: .sisyphus/evidence/task-15-derivatives-context.txt
  ```

  **Status**: DONE. 7 per-episode feature vectors written to
  `data/context/LUNAUSDT_2022-05-07_2022-05-11_context.json`. Forward-fill
  semantics for funding (8h step function) — `funding_rate_avg_4h` is a
  time-weighted mean over the ≤2 intervals active in the 4h lookback, never
  null. Field-name drift from prior plan revision (`.funding_rate` →
  `.funding_rate_current`) corrected to match the spec field list. Evidence:
  task-15-derivatives-context.txt.

  **Commit**: YES
  - Message: `feat: derivatives context extraction`
  - Files: `src/crypto_analyser/derivatives_context.py`

---

- [ ] 16. Build RAG Retrieval Query — **INTERN TASK**

  **What to do**:
  - Understand the goal: given an anomaly timestamp and ticker, retrieve relevant news
  - Requirements:
    - Filter by ticker (only articles mentioning the relevant crypto)
    - Filter by time window (articles within +/- 12 hours of anomaly)
    - Rank by relevance (combine vector similarity + text similarity)
  - Research: how to combine vector search and text search into one ranked result
  - Write a Python function in `src/crypto_analyser/retrieval.py` that:
    - Takes anomaly timestamp and ticker as inputs
    - Returns top 5-10 most relevant articles
    - Includes article metadata: title, description, pub_date, source, tickers
  - Create test script `scripts/test_retrieval.py` to validate your retrieval works
  - Test with sample anomaly: LUNA crash timestamp (2022-05-09), should return Terra-related articles
  - Document your approach in `docs/retrieval.md`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Retrieval logic needs thought — combining multiple ranking signals

  **Parallelization**:
  - **Phase**: 1 (can start immediately after Wave 2)
  - **Runs In Parallel With**: Task 14, Task 17
  - **Blocks**: Task 18 (LLM classifier needs RAG context), Task 22 (ablation run in Wave 4)
  - **Blocked By**: Task 13 (indexes created), Task 12 (embeddings populated)

  **References**:
  - Hybrid search concept: combining vector + keyword rankings (RRF)
  - PostgreSQL vector operators: how to compute similarity with `<->`
  - PostgreSQL text search: how to rank by relevance with `ts_rank`
  - Time-bounded query: `WHERE pub_date BETWEEN timestamp - 12h AND timestamp + 12h`

  **Acceptance Criteria**:
  - [ ] Retrieval returns articles filtered by ticker
  - [ ] Retrieval returns articles within time window
  - [ ] Results ranked by combined relevance score
  - [ ] Test script `scripts/test_retrieval.py` created and working
  - [ ] Test query for LUNA timestamp returns Terra-related articles
  - [ ] Approach documented in `docs/retrieval.md`

  **QA Scenarios**:
  ```
  Scenario: Retrieval filters by ticker
    Tool: Bash (python)
    Steps:
      1. python scripts/test_retrieval.py --ticker LUNA --date 2022-05-09
      2. Check all returned articles have LUNA in tickers array
    Expected Result: All results match ticker filter
    Evidence: .sisyphus/evidence/task-16-ticker-filter.txt

  Scenario: Retrieval bounds by time
    Tool: Bash (python)
    Steps:
      1. python scripts/test_retrieval.py --timestamp 2022-05-09T14:00:00
      2. Check all articles within +/- 12 hours
    Expected Result: All results within time window
    Evidence: .sisyphus/evidence/task-16-time-bound.txt

  Scenario: LUNA retrieval returns relevant articles
    Tool: Bash (python)
    Steps:
      1. python scripts/test_retrieval.py --ticker LUNA --timestamp 2022-05-09T14:00:00
      2. Check results contain Terra/UST keywords
    Expected Result: Top results are Terra-related
    Evidence: .sisyphus/evidence/task-16-luna-retrieval.txt
  ```

  **Commit**: YES
  - Message: `feat: RAG retrieval query`
  - Files: `src/crypto_analyser/retrieval.py`, `scripts/test_retrieval.py`, `docs/retrieval.md`

---

- [x] 17. LLM Classifier Prompt + Schema Definition ✓ DONE

  **What to do**:
  - Create `prompts/classification_prompt.md`:
    - System prompt: crypto anomaly classifier
    - User prompt template: inject derivatives features + RAG context
    - Classification categories: explained_derivatives, explained_news, unexplained, insufficient_data
  - Create JSON schema: `schemas/classification.json`:
    - Fields: classification, severity (1-10), confidence (0-1), rationale, news_relevance (optional)
  - Define prompt variants: derivatives-only vs derivatives+RAG

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Prompt design
  - **Skills**: none needed

  **Parallelization**:
  - **Phase**: 1 (can start immediately after Wave 1)
  - **Runs In Parallel With**: Task 14, Task 16
  - **Blocks**: Task 18 (classifier execution)
  - **Blocked By**: Wave 1 (Task 5 LLM client wrapper)

  **Acceptance Criteria**:
  - [ ] Classification prompt created
  - [ ] JSON schema defined
  - [ ] Prompt variants for ablation study documented

  **QA Scenarios**:
  ```
  Scenario: JSON schema validation
    Tool: Bash (jq)
    Steps:
      1. Validate schema structure
      2. Check required fields present
    Expected Result: Schema passes validation
    Evidence: .sisyphus/evidence/task-17-schema-validation.txt
  ```

  **Commit**: YES
  - Message: `feat: LLM classifier prompt and schema`
  - Files: `prompts/classification_prompt.md`, `schemas/classification.json`

---

- [ ] 18. Classifier Execution Wrapper

  **What to do**:
  - Create `src/crypto_analyser/classifier.py` (CLI shim as needed):
    - Read the bulk `episodes[]` file (Task 14) and the bulk derivatives-context
      file (Task 15); iterate episodes (do NOT expect per-timestamp input files —
      none exist)
    - Load episode + derivatives context + RAG context per episode
    - Build prompt from template (Task 17), keyed on `onset_ts`
    - Call LLM with structured output (response_format=json_schema)
    - Parse and validate response
    - Handle errors (schema validation failure)
  - Create variants: classify_derivatives_only(), classify_with_rag()
  - Store outputs (one file per episode, named by `{symbol}_{onset_ts}.json`):
    - Derivatives-only: `data/classifications/derivatives_only/{symbol}_{onset_ts}.json`
    - With RAG: `data/classifications/derivatives_rag/{symbol}_{onset_ts}.json`
    (both dirs gitignored as generated outputs)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: API wrapper execution
  - **Skills**: none needed

  **Parallelization**:
  - **Phase**: 3 (starts after Tasks 14, 15, 16, 17 complete)
  - **Runs In Parallel With**: None (sequential, needs all inputs)
  - **Blocks**: Task 19 (report generation)
  - **Blocked By**: Task 14 (anomalies), Task 15 (derivatives), Task 16 (RAG retrieval), Task 17 (prompt/schema)
  - **Blocks**: Task 19 (report generation)
  - **Blocked By**: Tasks 14-17 (all inputs needed)

  **Acceptance Criteria**:
  - [ ] Classifier produces valid JSON schema output
  - [ ] Both variants (derivatives-only + RAG) work
  - [ ] Error handling for schema failures
  - [ ] Outputs saved to correct paths (derivatives_only/ and derivatives_rag/)

  **QA Scenarios**:
  ```
  Scenario: LLM classifier structured output
    Tool: Bash (python) - requires filled API placeholder
    Steps:
      1. python src/crypto_analyser/classifier.py --anomalies data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json --mode derivatives_only
      2. ls data/classifications/derivatives_only/ | wc -l   # one file per episode
      3. jq '.classification' data/classifications/derivatives_only/LUNAUSDT_$(jq -r '.episodes[0].onset_ts' data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json).json
    Expected Result: One of classification categories, one classification file per episode
    Evidence: .sisyphus/evidence/task-18-classifier-output.txt

  Scenario: Schema validation failure handling
    Tool: Bash (python)
    Steps:
      1. Mock malformed LLM response
      2. Check classifier raises validation error
    Expected Result: Error raised with schema mismatch message
    Evidence: .sisyphus/evidence/task-18-schema-error.txt
  ```

  **Commit**: YES
  - Message: `feat: LLM classifier execution`
  - Files: `src/crypto_analyser/classifier.py`

---

- [ ] 19. JSON Report Generator

  **What to do**:
  - Create `src/crypto_analyser/report_generator.py`:
    - Aggregate all results: anomaly, derivatives, RAG, classification
    - Read from: `data/classifications/derivatives_only/` or `data/classifications/derivatives_rag/`
    - Generate JSON report per anomaly: `reports/{symbol}_{timestamp}_report.json`
    - Include: timestamp, Z-score, derivatives features, RAG context (optional), classification
    - Generate summary report: `reports/{symbol}_{start}_{end}_summary.json`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Report generation
  - **Skills**: none needed

  **Parallelization**:
  - **Phase**: 4 (starts after Task 18 completes)
  - **Runs In Parallel With**: None (final Wave 3 task)
  - **Blocks**: Wave 4 (validation)
  - **Blocked By**: Task 18 (classifications)

  **Acceptance Criteria**:
  - [ ] JSON reports generated for each anomaly
  - [ ] Summary report created
  - [ ] Valid JSON structure
  - [ ] Reports include all fields from intermediate files

  **QA Scenarios**:
  ```
  Scenario: Report generation
    Tool: Bash (python)
    Steps:
      1. python src/crypto_analyser/report_generator.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode derivatives_only
      2. jq '.episodes | length' reports/LUNAUSDT_2022-05-07_2022-05-11_summary.json
    Expected Result: Summary report with all anomalies
    Evidence: .sisyphus/evidence/task-19-report-generation.txt
  ```

  **Commit**: YES
  - Message: `feat: JSON report generator`
  - Files: `src/crypto_analyser/report_generator.py`

---

### Wave 4: Validation + Evaluation

- [ ] 20. Run Pipeline on LUNA May 7-11 Window

  **What to do**:
  - Create `scripts/run_pipeline.py`:
    - Execute full pipeline: OHLCV → Z-score → derivatives → RAG → classify → report
    - Run on LUNA May 7-11 2022 (pre-crash focus per user decision)
    - Validate: anomalies detected, classifications produced
    - Log all steps to Langfuse (trace creation)
  - Create orchestration script that chains all components

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integration testing, multi-step pipeline execution
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 21-24)
  - **Blocks**: Tasks 21-22 (ablation study)
  - **Blocked By**: Wave 3 (all components complete)

  **Acceptance Criteria**:
  - [ ] Pipeline runs end-to-end without errors
  - [ ] LUNA anomalies detected
  - [ ] Classifications produced for all anomalies
  - [ ] Reports generated

  **QA Scenarios**:
  ```
  Scenario: LUNA pipeline execution
    Tool: Bash (python)
    Steps:
      1. python scripts/run_pipeline.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11 --mode full
      2. ls reports/LUNAUSDT_*.json | wc -l
    Expected Result: Multiple report files created
    Evidence: .sisyphus/evidence/task-20-luna-pipeline.txt

  Scenario: Anomalies detected
    Tool: Bash (jq)
    Steps:
      1. jq '.episodes | length' reports/LUNAUSDT_2022-05-07_2022-05-11_summary.json
    Expected Result: episodes > 0
    Evidence: .sisyphus/evidence/task-20-anomaly-count.txt
  ```

  **Commit**: YES
  - Message: `feat: pipeline execution on LUNA`
  - Files: `scripts/run_pipeline.py, reports/LUNAUSDT_2022-05-07_2022-05-11_summary.json`

---

- [ ] 21. Ablation Study: Derivatives-Only Run

  **What to do**:
  - Run pipeline with `--mode derivatives_only` (skip RAG retrieval)
  - Classify anomalies using only derivatives features
  - Store results: `results/ablation_derivatives_only.json`
  - Log to Langfuse with mode marker
  - Run Ragas evaluation on results (if ground truth available)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Experiment execution, evaluation
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20, 22-24)
  - **Blocks**: Task 23 (Ragas comparison)
  - **Blocked By**: Task 20 (pipeline working)

  **Acceptance Criteria**:
  - [ ] Derivatives-only run completes
  - [ ] Classifications produced without RAG context
  - [ ] Results stored for comparison

  **QA Scenarios**:
  ```
  Scenario: Derivatives-only ablation run
    Tool: Bash (python)
    Steps:
      1. python scripts/run_pipeline.py --mode derivatives_only
      2. jq '.mode' results/ablation_derivatives_only.json
    Expected Result: "derivatives_only"
    Evidence: .sisyphus/evidence/task-21-derivatives-ablation.txt
  ```

  **Commit**: YES
  - Message: `feat: ablation study derivatives-only`
  - Files: `results/ablation_derivatives_only.json`

---

- [ ] 22. Ablation Study: Derivatives+RAG Run

  **What to do**:
  - Run pipeline with `--mode full` (include RAG retrieval)
  - Classify anomalies using derivatives + RAG context
  - Store results: `results/ablation_derivatives_rag.json`
  - Compare with derivatives-only results
  - Document improvement/differences in classifications

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Experiment execution, evaluation
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20-21, 23-24)
  - **Blocks**: Task 23 (Ragas comparison)
  - **Blocked By**: Task 20 (pipeline working) + Task 16 (RAG working)

  **Acceptance Criteria**:
  - [ ] Derivatives+RAG run completes
  - [ ] Classifications include news_relevance field
  - [ ] Results stored for comparison

  **QA Scenarios**:
  ```
  Scenario: Derivatives+RAG ablation run
    Tool: Bash (python)
    Steps:
      1. python scripts/run_pipeline.py --mode full
      2. jq '.mode' results/ablation_derivatives_rag.json
    Expected Result: "full"
    Evidence: .sisyphus/evidence/task-22-rag-ablation.txt

  Scenario: Classification includes news_relevance
    Tool: Bash (jq)
    Steps:
      1. jq '.classifications[0].news_relevance' results/ablation_derivatives_rag.json
    Expected Result: Field present (null if no relevant news, or float)
    Evidence: .sisyphus/evidence/task-22-news-relevance.txt
  ```

  **Commit**: YES
  - Message: `feat: ablation study derivatives+RAG`
  - Files: `results/ablation_derivatives_rag.json`

---

- [ ] 23. Ragas Evaluation + Comparison

  **What to do**:
  - Create `scripts/evaluate_ragas.py`:
    - Load both ablation results
    - Define Ragas metrics: Faithfulness, Answer Relevancy, (Context Recall if ground truth)
    - Run Ragas evaluation on both result sets
    - Compare metrics: derivatives-only vs derivatives+RAG
    - Store comparison: `results/ablation_comparison.json`
  - Document: which approach has higher faithfulness/relevance

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Ragas evaluation needs correct metric implementation
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20-22, 24)
  - **Blocks**: Task 24 (report finalization)
  - **Blocked By**: Tasks 21-22 (both ablation runs complete)

  **References**:
  - Ragas metrics from research: Faithfulness, Answer Relevancy
  - Ablation methodology from research findings

  **Acceptance Criteria**:
  - [ ] Ragas evaluation runs on both result sets
  - [ ] Comparison JSON produced
  - [ ] Metrics documented (faithfulness scores)

  **QA Scenarios**:
  ```
  Scenario: Ragas evaluation comparison
    Tool: Bash (python)
    Steps:
      1. python scripts/evaluate_ragas.py
      2. jq '.derivatives_only.faithfulness, .derivatives_rag.faithfulness' results/ablation_comparison.json
    Expected Result: Floats between 0.0 and 1.0 for both
    Evidence: .sisyphus/evidence/task-23-ragas-comparison.txt

  Scenario: Comparison shows improvement
    Tool: Bash (jq)
    Steps:
      1. jq '.improvement.faithfulness' results/ablation_comparison.json
    Expected Result: Difference between RAG and non-RAG scores
    Evidence: .sisyphus/evidence/task-23-improvement.txt
  ```

  **Commit**: YES
  - Message: `feat: Ragas evaluation and comparison`
  - Files: `scripts/evaluate_ragas.py, results/ablation_comparison.json`

---

- [ ] 24. JSON Report Finalization

  **What to do**:
  - Finalize all JSON reports:
    - Ensure valid JSON structure
    - Add metadata: execution timestamp, config used, data sources
    - Validate all required fields present
  - Create final summary: `reports/FINAL_PHASE1_SUMMARY.json`
  - Document key findings: anomaly count, classification distribution, ablation results

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Report cleanup
  - **Skills**: none needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 20-23)
  - **Blocks**: Final Verification Wave
  - **Blocked By**: Task 23 (ablation comparison)

  **Acceptance Criteria**:
  - [ ] All reports valid JSON
  - [ ] Metadata added
  - [ ] Final summary created

  **QA Scenarios**:
  ```
  Scenario: Report JSON validation
    Tool: Bash (jq)
    Steps:
      1. for f in reports/*.json; do jq empty "$f"; done
    Expected Result: No errors (all valid JSON)
    Evidence: .sisyphus/evidence/task-24-json-valid.txt

  Scenario: Final summary exists
    Tool: Bash
    Steps:
      1. jq '.anomalies_total, .classifications_total' reports/FINAL_PHASE1_SUMMARY.json
    Expected Result: Counts present
    Evidence: .sisyphus/evidence/task-24-final-summary.txt
  ```

  **Commit**: YES
  - Message: `feat: report finalization`
  - Files: `reports/FINAL_PHASE1_SUMMARY.json`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files. Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Check for: `as any`, empty catches, console.log, commented code, unused imports. Check AI slop: excessive comments, over-abstraction. Output: `Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task. Test cross-feature integration. Save evidence to `.sisyphus/evidence/final-qa/`. Output: `Scenarios [N/N pass] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec (no creep). Output: `Tasks [N/N compliant] | VERDICT`

---

## Commit Strategy

| After Wave | Message                                       | Files                                              | Verification   |
|------------+-----------------------------------------------+----------------------------------------------------+----------------|
| Wave 1     | `feat: project scaffolding and configuration` | pyproject.toml, docker-compose.yml, config/*       | duckdb test    |
| Wave 2     | `feat: data pipeline complete`                | scripts/download_*.py, scripts/embed_*.py          | coverage query |
| Wave 3     | `feat: detection and classification`          | src/crypto_analyser/zscore.py, src/crypto_analyser/classifier.py, src/crypto_analyser/retrieval.py | episode count  |
| Wave 4     | `feat: validation and ablation study`         | results/*.json, reports/*.json                     | jq validation  |

---

## Success Criteria

### Verification Commands
```bash
# Data coverage
duckdb -c "SELECT MIN(timestamp), MAX(timestamp) FROM read_parquet('data/luna_ohlcv.parquet')"
# Expected: 2022-05-07 to 2022-05-11

# Anomaly detection
python src/zscore.py --symbol LUNAUSDT --start 2022-05-07 --end 2022-05-11
# Expected: > 0 episodes (observed 5 at default config)
jq '.episodes | length' data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json

# LLM classifier (reads bulk episodes[], one classification file per episode)
python src/crypto_analyser/classifier.py --anomalies data/anomalies/LUNAUSDT_2022-05-07_2022-05-11.json --mode derivatives_only
# Expected: one of ["explained_derivatives","explained_news","unexplained","insufficient_data"] per episode

# Ragas metrics
jq '.derivatives_only.faithfulness' results/ablation_comparison.json
# Expected: float between 0.0 and 1.0
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Data pipeline downloads historical data
- [ ] Z-score detects anomalies for LUNA window
- [ ] LLM produces valid JSON schema
- [ ] Ablation study produces metrics
- [ ] JSON reports saved

---

*Plan generated: 2026-04-12*
*Tech stack validated: UV, DuckDB, pgvector, Langfuse, Ragas, OpenRouter*
*Validation window: May 7-11, 2022 (pre-crash focus)*
