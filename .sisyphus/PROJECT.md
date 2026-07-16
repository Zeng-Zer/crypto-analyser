# Crypto Analyzer

## What This Is

Historical crypto anomaly detection system that processes past market data to validate a hypothesis: derivatives market structure (funding rates, open interest) can classify price crashes better than lagging news feeds.

**Milestone 1 scope:** Entirely historical/backtesting-based. No Kafka, no WebSocket, no real-time infrastructure. One CLI drives an in-process library pipeline that computes Z-scores, fetches derivatives context, and classifies with an LLM.

The core insight: **unexplained price moves** (where derivatives data show nothing unusual) often precede news by 30min-24h. This system validates that hypothesis on real historical events.

**Validation approach:** Three-way ablation comparing derivatives-only, derivatives+pre-onset RAG, and news-only. Direct verdict overlap and news timing test the hypothesis; Ragas measures rationale faithfulness and answer relevancy. LUNA is one case study, not general proof.

## Core Value

Detect and classify historical price anomalies. Prove the hypothesis works on real events (LUNA, FTX, Bybit).

If the classification is "unexplained," that's the highest priority signal — and the hypothesis is validated.

## Milestones

### Milestone 1: Historical Analysis (Current)

Complete, shippable project. Validates entire hypothesis without real-time complexity.

```
Historical OHLCV → Compute Z-score offline → Fetch derivatives at timestamp → LLM classify → JSON report

Ablation Study:
├── Run A: Derivatives-only classification
├── Run B: Derivatives + pre-onset RAG context
├── Run C: Pre-onset news only
└── Compare verdict overlap, news timing, faithfulness, answer relevancy
```

**Deliverables:**
- Historical data acquisition library using **FREE Binance Data Vision** archives
- Z-score computation on historical candles
- Feature extraction (derivatives context at anomaly timestamps)
- RAG pipeline for ablation comparison (local news archive → pgvector)
- LLM classifier with structured output
- Ablation study: derivatives-only vs derivatives+RAG with Ragas evaluation
- Validation on LUNA crash event (May 7-11, 2022 — pre-crash focus)
- Output: JSON reports with classifications + comparison metrics

**Skills showcased:**
1. Data engineering (batch processing, API orchestration, historical data pipelines)
2. LLM engineering (prompt design, structured output, evaluation)
3. RAG engineering (pgvector, hybrid search, embedding, retrieval)
4. LLM evaluation (Ragas faithfulness and answer relevancy)
5. Statistical analysis (Z-scores, feature engineering)
6. Scientific methodology (ablation study, hypothesis testing)

### Milestone 2: Real-time Infrastructure (Future, Optional)

Add streaming capabilities after Milestone 1 validates the approach.

- WebSocket ingestion for live price data
- Kafka streaming pipeline
- Real-time Z-score triggers
- Live Discord alerts

**Deferred** until Milestone 1 proves the hypothesis works.

## Requirements

### Data Sources (100% FREE)

| Data              | Source              | URL                                    | Cost | Coverage         |
|-------------------+---------------------+----------------------------------------+------+------------------|
| **OHLCV**         | Binance Data Vision | `data/futures/um/monthly/klines/`      | FREE | Full May 2022    |
| **Open Interest** | Binance Data Vision | `data/futures/um/daily/metrics/`       | FREE | May 1-12 (5-min) |
| **Funding Rate**  | Binance Data Vision | `data/futures/um/monthly/fundingRate/` | FREE | Full May 2022    |
| **News archive**  | Local JSON archive  | `../free-crypto-news/archive/`         | FREE | 2017–2026        |

**Total Data Cost: $0**

### Validated

- [x] Binance Data Vision provides FREE historical data for LUNAUSDT (May 2022)
  - Symbol: LUNAUSDT (pre-crash)
  - OHLCV: 1-min klines available
  - Funding rate: 8h intervals available
  - Open Interest: 5-min metrics (May 1-12, delisted after crash)
- [x] pgvector Docker setup verified and working
  - `pgvector/pgvector:pg17` (official image, migrated from deprecated ankane/pgvector)
  - PostgreSQL 17.9 + pgvector 0.8.2 (both current versions)
  - Hybrid search (vector similarity) tested and working

### Active

- [x] Historical OHLCV data downloaded for target symbols (Binance Data Vision)
- [x] Z-score computation detects 5 episodes in LUNA May 7-11
- [x] Feature extraction pulls funding rate and open interest at episode onset
- [x] RAG pipeline loads local archive into pgvector and retrieves pre-onset news
- [x] LLM classifier produces structured verdicts, confidence, and rationale
- [x] Ablation run A: derivatives-only classification complete
- [x] Ablation run B: derivatives+RAG classification complete
- [x] Ablation run C: news-only classification complete
- [x] Ragas evaluation produces faithfulness and answer relevancy metrics
- [x] Comparison JSON records direct and Ragas metrics
- [x] Final JSON summary records findings and limitations

### Out of Scope

| Feature                                        | Reason                                                                          |
|------------------------------------------------+---------------------------------------------------------------------------------|
| Real-time infrastructure (Kafka, WebSocket)    | Milestone 2. Validate hypothesis first.                                         |
| ML classifier                                  | LLM works zero-shot. ML after accumulating labels.                              |
| Bull/Bear/Judge debate                         | Polish. Single classifier proves pipeline first.                                |
| RAG as production signal                       | Milestone 1 uses it only as ablation evidence.                                  |
| Exchange inflows / on-chain data               | Start simple. Funding rate + OI only.                                           |
| Whale Alert / Options IV / Put-Call ratio      | Start simple. Add later if needed.                                              |
| Real-time/load testing                         | Deferred until Milestone 2. Unit and integration tests cover Milestone 1.       |
| Discord alerts (real-time)                     | Milestone 2. JSON reports for Milestone 1.                                      |
| Fear & Greed Index                             | Daily granularity. May not correlate with 5-min price moves. Keep for later.    |
| More derivatives signals (basis, taker volume) | Start simple. Funding rate + OI only per "start simple" constraint.             |

## Context

**Resume project** built by a tech lead data engineer with an intern. The intern is junior with no experience and will be slow. Work must be structured so the intern never blocks the main developer.

**Differentiation from other crypto AI projects:** Most use price + news. News is lagging 15-60 minutes. This system uses derivatives market structure (funding rates, open interest) — concurrent or leading signals that explain price moves BEFORE news arrives.

**Scientific validation via ablation study:**
- Run A: derivatives-only classification
- Run B: derivatives + news published by episode onset
- Run C: news-only classification
- Direct verdict overlap and publication timing test source utility; Ragas measures generated-rationale quality
- LUNA result: each isolated source explained 4/5 episodes, with one derivatives-only early move and one news-only move

**Why historical first:** Real-time infrastructure (Kafka, WebSocket) adds complexity before proving value. Historical data is real data. Validate the hypothesis on known events. If it works, real-time is just "run the same pipeline live."

**Validation window:** May 7-11, 2022 (pre-crash focus). LUNA delisted May 12, so validation focuses on the days before the crash when derivatives signals should have caught anomalies.

## Constraints

- **Intern blocking:** Intern tasks must be enrichment only, never on critical path. If intern is slow, main developer proceeds without waiting.
- **Simple first:** One CLI, direct function composition, and focused tests. One event (LUNA) validates the workflow.
- **No real-time yet:** Milestone 1 is entirely batch/historical. No Kafka, no WebSocket, no streaming.
- **Start with two derivatives signals:** Funding rate and open interest only. Add more later.

## Key Decisions

| Decision                                    | Rationale                                                                                                                              | Outcome    |
|---------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------+------------|
| Historical-first, real-time later           | Validate hypothesis on known events before building streaming infrastructure. Complexity deferred.                                     | — Pending  |
| LLM first, ML later                         | No labeled training data. LLM works zero-shot. ML after accumulating labels.                                                           | — Pending  |
| Derivatives over news (primary)             | LUNA shows complementary evidence; one early move was derivatives-only. More events required.                                          | — Inconclusive |
| RAG included for ablation comparison        | Three-way ablation separates derivatives, combined context, and news-only evidence.                                                     | — Verified |
| Single classifier before debate             | Debate is polish. Single LLM proves pipeline first.                                                                                    | — Pending  |
| Funding rate + OI only                      | Start simple. Two derivatives signals, add more if needed.                                                                             | — Pending  |
| Unit + integration tests                    | Library functions are tested directly; CLI routing and PostgreSQL retrieval have integration coverage.                                | — Verified |
| LUNA first (May 7-11), FTX/Bybit enrichment | One event validates hypothesis. Intern validates others in parallel. Pre-crash focus (LUNA delisted May 12).                           | — Pending  |
| Binance Data Vision (FREE data)             | No API key, no rate limits. Historical OHLCV, funding, OI all free. Reduces complexity and cost.                                       | — Verified |

---
*Last updated: 2026-07-15 — LUNA three-way ablation complete*
