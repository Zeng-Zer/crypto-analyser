# Crypto Anomaly Analyser

## What This Is

Historical crypto anomaly analysis comparing how derivatives market structure (funding rates, open interest) and pre-onset news affect structured LLM classifications.

**Milestone 1 scope:** Entirely historical/backtesting-based. No Kafka, WebSocket, or real-time infrastructure. One CLI drives an in-process library pipeline that computes anomaly episodes, fetches derivatives context, retrieves time-safe news, and classifies with an LLM.

The tested hypothesis is that derivatives can explain anomalous price moves when pre-onset news cannot. The LUNA case produced complementary evidence: each isolated source explained seven of eight episodes, with six overlaps and no episode unexplained by both sources. This does not establish source superiority or measure post-onset news delay.

**Comparison approach:** Three controlled context modes: derivatives-only, derivatives+pre-onset RAG, and news-only. Verdict changes test context contribution; Ragas Faithfulness checks whether combined-rationale claims follow from supplied context. It does not score verdict correctness or causality.

## Core Value

Reproducibly detect historical price-anomaly episodes, assemble time-safe derivatives/news context, and compare structured classifications without claiming more than one LUNA case supports.

## Milestones

### Milestone 1: Historical Analysis (Complete)

Complete LUNA case study that exercises the batch, RAG, classification, evaluation, and evidence-workbench paths.

```
Historical OHLCV → Compute Z-score offline → Fetch derivatives at timestamp → LLM classify → JSON report

Ablation Study:
├── Run A: Derivatives-only classification
├── Run B: Derivatives + pre-onset RAG context
├── Run C: Pre-onset news only
└── Compare verdicts; check combined rationale faithfulness
```

**Deliverables:**
- Historical data acquisition library using **FREE Binance Data Vision** archives
- Z-score computation on historical candles
- Feature extraction (derivatives context at anomaly timestamps)
- RAG pipeline for ablation comparison (local news archive → pgvector)
- LLM classifier with structured output
- Ablation study: derivatives-only vs derivatives+RAG with Ragas evaluation
- LUNA crash case study (May 7–11, 2022)
- Output: JSON reports with classifications + comparison metrics

**Skills showcased:**
1. Data engineering (batch processing, API orchestration, historical data pipelines)
2. LLM engineering (prompt design, structured output, evaluation)
3. RAG engineering (pgvector, hybrid search, embedding, retrieval)
4. LLM evaluation (Ragas Faithfulness on product output)
5. Statistical analysis (Z-scores, feature engineering)
6. Experimental methodology (controlled context comparison and explicit limitations)

### Milestone 2: Real-time Infrastructure (Future, Optional)

Candidate extension if external demand warrants live operation.

- WebSocket ingestion for live price data
- Kafka streaming pipeline
- Real-time Z-score triggers
- Live Discord alerts

**Not implemented.** Milestone 1 is historical and static.

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
  - OHLCV: pipeline uses 5-minute klines
  - Funding rate: 8h intervals available
  - Open Interest: 5-min metrics (May 1-12, delisted after crash)
- [x] PostgreSQL/pgvector development service and retrieval integration verified
  - Compose uses `pgvector/pgvector:pg17`
  - Hybrid retrieval combines vector and full-text ranks with reciprocal rank fusion

### Active

- [x] Historical OHLCV data downloaded for target symbols (Binance Data Vision)
- [x] Combined price-Z, 4h drawdown, and 2h return detection finds 8 episodes in LUNA May 7-11
- [x] Feature extraction pulls funding rate and open interest at episode onset
- [x] RAG pipeline loads local archive into pgvector and retrieves pre-onset news
- [x] LLM classifier produces structured verdicts, confidence, and rationale
- [x] Ablation run A: derivatives-only classification complete
- [x] Ablation run B: derivatives+RAG classification complete
- [x] Ablation run C: news-only classification complete
- [x] Ragas evaluation checks combined-output rationale Faithfulness
- [x] Comparison JSON records controlled verdicts and per-anomaly Faithfulness
- [x] Final JSON summary records findings and limitations

### Out of Scope

| Feature                                        | Reason                                                                          |
|------------------------------------------------+---------------------------------------------------------------------------------|
| Real-time infrastructure (Kafka, WebSocket)    | Not needed for the historical case study.                                       |
| ML classifier                                  | No labeled training set; structured LLM comparison is the current scope.        |
| Bull/Bear/Judge debate                         | Not needed for the controlled three-mode comparison.                            |
| RAG as production signal                       | Milestone 1 uses it only as ablation evidence.                                  |
| Exchange inflows / on-chain data               | Start simple. Funding rate + OI only.                                           |
| Whale Alert / Options IV / Put-Call ratio      | Start simple. Add later if needed.                                              |
| Real-time/load testing                         | Deferred until Milestone 2. Unit and integration tests cover Milestone 1.       |
| Discord alerts (real-time)                     | Milestone 2. JSON reports for Milestone 1.                                      |
| Fear & Greed Index                             | Daily granularity. May not correlate with 5-min price moves. Keep for later.    |
| More derivatives signals (basis, taker volume) | Start simple. Funding rate + OI only per "start simple" constraint.             |

## Context

**Collaboration:** David Zeng led the end-to-end pipeline and evidence workbench. Luc Zhang contributed the PostgreSQL news schema, embedding/indexing workflow, vector retrieval prototype, and time-bounded RAG retrieval.

**Project focus:** Compare concurrent derivatives context with news published by each episode onset, rather than treating retrieved news as automatically causal.

**Controlled context comparison:**
- Run A: derivatives-only classification
- Run B: derivatives + news published by episode onset
- Run C: news-only classification
- Verdict overlap records context-conditioned classifier changes; publication time is an onset-eligibility cutoff; Ragas measures combined-rationale support
- LUNA result: each isolated source explained 7/8 episodes; six overlapped, one was derivatives-only, and one was news-only

**Why historical first:** Fixed historical inputs make temporal cutoffs, classifications, and evaluation reproducible. Real-time operation would require separate ingestion, persistence, failure handling, and alerting work.

**Case window:** May 7–11, 2022. It includes the crisis period before LUNAUSDT derivatives data end around the May 12 delisting.

## Constraints

- **Simple first:** One CLI, direct function composition, and focused tests. One LUNA case exercises the workflow but does not validate general source superiority.
- **No real-time yet:** Milestone 1 is entirely batch/historical. No Kafka, no WebSocket, no streaming.
- **Start with two derivatives signals:** Funding rate and open interest only. Add more later.

## Key Decisions

| Decision                                    | Rationale                                                                                                                              | Outcome    |
|---------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------+------------|
| Historical-first, real-time later           | Make time cutoffs and comparisons reproducible before considering live infrastructure.                                                  | — Verified |
| LLM first, ML later                         | No labeled training data. LLM works zero-shot. ML after accumulating labels.                                                           | — Pending  |
| Derivatives over news (primary)             | LUNA shows complementary evidence; one early move was derivatives-only. More events required.                                          | — Inconclusive |
| RAG included for ablation comparison        | Three-way ablation separates derivatives, combined context, and news-only evidence.                                                     | — Verified |
| Single classifier before debate             | One structured classifier exercises the comparison without adding a debate layer.                                                      | — Verified |
| Funding rate + OI only                      | Start simple. Two derivatives signals, add more if needed.                                                                             | — Pending  |
| Unit + integration tests                    | Library functions are tested directly; CLI routing and PostgreSQL retrieval have integration coverage.                                | — Verified |
| LUNA first (May 7–11), FTX/Bybit enrichment | One event exercises the workflow; additional events are required for broader conclusions.                                               | — Partial  |
| Binance Data Vision archives                | Historical OHLCV, funding, and OI were available without an API key for the LUNA window.                                                | — Verified |

---
*Last updated: 2026-07-21 — public-claims audit complete*
