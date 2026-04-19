# Crypto Analyzer

## What This Is

Historical crypto anomaly detection system that processes past market data to validate a hypothesis: derivatives market structure (funding rates, open interest) can classify price crashes better than lagging news feeds.

**Milestone 1 scope:** Entirely historical/backtesting-based. No Kafka, no WebSocket, no real-time infrastructure. Batch scripts process historical data, compute Z-scores, fetch derivatives context, and classify with LLM.

The core insight: **unexplained price moves** (where derivatives data show nothing unusual) often precede news by 30min-24h. This system validates that hypothesis on real historical events.

**Validation approach:** Ablation study comparing derivatives-only vs derivatives+RAG. Ragas evaluation quantifies which approach produces higher faithfulness and answer relevancy. This proves the hypothesis with measurable metrics, not just intuition.

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
├── Run B: Derivatives + RAG context (historical news)
└── Ragas evaluation comparing faithfulness, answer relevancy
```

**Deliverables:**
- Download scripts for historical data (OHLCV, funding rate, open interest) — **FREE via Binance Data Vision**
- Z-score computation on historical candles
- Feature extraction (derivatives context at anomaly timestamps)
- RAG pipeline for ablation comparison (Wayback Machine RSS → pgvector)
- LLM classifier with structured output
- Ablation study: derivatives-only vs derivatives+RAG with Ragas evaluation
- Validation on LUNA crash event (May 7-11, 2022 — pre-crash focus)
- Output: JSON reports with classifications + comparison metrics

**Skills showcased:**
1. Data engineering (batch processing, API orchestration, historical data pipelines)
2. LLM engineering (prompt design, structured output, evaluation)
3. RAG engineering (pgvector, hybrid search, embedding, retrieval)
4. MLOps/observability (Langfuse tracing, Ragas evaluation)
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
| **News RSS**      | Wayback Machine     | CDX API + archived RSS                 | FREE | Verify feeds     |

**Total Data Cost: $0**

### Validated

(None yet — ship to validate)

### Active

- [ ] Historical OHLCV data downloaded for target symbols (Binance Data Vision)
- [ ] Z-score computation detects anomalies in historical data (LUNA May 7-11)
- [ ] Feature extraction pulls funding rate and open interest at anomaly timestamps
- [ ] RAG pipeline built for ablation comparison (Wayback RSS → pgvector)
- [ ] LLM classifier produces structured verdicts: classification, severity, confidence, rationale
- [ ] Ablation run A: derivatives-only classification complete
- [ ] Ablation run B: derivatives+RAG classification complete
- [ ] Ragas evaluation produces faithfulness and answer relevancy metrics
- [ ] Comparison JSON shows derivatives-only vs derivatives+RAG results
- [ ] JSON reports output classification results for review

### Out of Scope

| Feature                                        | Reason                                                                          |
|------------------------------------------------+---------------------------------------------------------------------------------|
| Real-time infrastructure (Kafka, WebSocket)    | Milestone 2. Validate hypothesis first.                                         |
| ML classifier                                  | LLM works zero-shot. ML after accumulating labels.                              |
| Bull/Bear/Judge debate                         | Polish. Single classifier proves pipeline first.                                |
| RAG as primary signal                          | **Included for ablation comparison only** — proves derivatives outperform news. |
| Exchange inflows / on-chain data               | Start simple. Funding rate + OI only.                                           |
| Whale Alert / Options IV / Put-Call ratio      | Start simple. Add later if needed.                                              |
| Automated testing                              | Manual scripts for fast iteration. Agent-executed QA instead.                   |
| Discord alerts (real-time)                     | Milestone 2. JSON reports for Milestone 1.                                      |
| Fear & Greed Index                             | Daily granularity. May not correlate with 5-min price moves. Keep for later.    |
| More derivatives signals (basis, taker volume) | Start simple. Funding rate + OI only per "start simple" constraint.             |

## Context

**Resume project** built by a tech lead data engineer with an intern. The intern is junior with no experience and will be slow. Work must be structured so the intern never blocks the main developer.

**Differentiation from other crypto AI projects:** Most use price + news. News is lagging 15-60 minutes. This system uses derivatives market structure (funding rates, open interest) — concurrent or leading signals that explain price moves BEFORE news arrives.

**Scientific validation via ablation study:**
- Run A: Derivatives-only classification → expected: high faithfulness (derivatives explain anomalies)
- Run B: Derivatives + RAG (news context) → expected: lower faithfulness if news is irrelevant/lagging
- Ragas metrics quantify the difference → hypothesis validated with evidence, not intuition

**Why historical first:** Real-time infrastructure (Kafka, WebSocket) adds complexity before proving value. Historical data is real data. Validate the hypothesis on known events. If it works, real-time is just "run the same pipeline live."

**Validation window:** May 7-11, 2022 (pre-crash focus). LUNA delisted May 12, so validation focuses on the days before the crash when derivatives signals should have caught anomalies.

## Constraints

- **Intern blocking:** Intern tasks must be enrichment only, never on critical path. If intern is slow, main developer proceeds without waiting.
- **Simple first:** Fast iteration, manual scripts, no premature automation. One event (LUNA) validates hypothesis.
- **No real-time yet:** Milestone 1 is entirely batch/historical. No Kafka, no WebSocket, no streaming.
- **Start with two derivatives signals:** Funding rate and open interest only. Add more later.

## Key Decisions

| Decision                                    | Rationale                                                                                                                              | Outcome    |
|---------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------+------------|
| Historical-first, real-time later           | Validate hypothesis on known events before building streaming infrastructure. Complexity deferred.                                     | — Pending  |
| LLM first, ML later                         | No labeled training data. LLM works zero-shot. ML after accumulating labels.                                                           | — Pending  |
| Derivatives over news (primary)             | News is lagging 15-60 min. Derivatives are concurrent/leading.                                                                         | — Pending  |
| RAG included for ablation comparison        | Scientific methodology: compare derivatives-only vs derivatives+RAG. Ragas quantifies which is better. Proves hypothesis with metrics. | — Pending  |
| Single classifier before debate             | Debate is polish. Single LLM proves pipeline first.                                                                                    | — Pending  |
| Funding rate + OI only                      | Start simple. Two derivatives signals, add more if needed.                                                                             | — Pending  |
| Agent-executed QA (not automated tests)     | Faster iteration. Manual scripts for exploration phase. No test suite overhead.                                                        | — Pending  |
| LUNA first (May 7-11), FTX/Bybit enrichment | One event validates hypothesis. Intern validates others in parallel. Pre-crash focus (LUNA delisted May 12).                           | — Pending  |
| Binance Data Vision (FREE data)             | No API key, no rate limits. Historical OHLCV, funding, OI all free. Reduces complexity and cost.                                       | — Verified |

---
*Last updated: 2026-04-13 — synchronized with .sisyphus/plans/crypto-analyzer-phase1.md*
