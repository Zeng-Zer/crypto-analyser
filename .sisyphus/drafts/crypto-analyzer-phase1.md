# Draft: Crypto Analyzer Phase 1

> Superseded planning draft retained for provenance. Current implementation and conclusions are documented in [`.sisyphus/PROJECT.md`](../PROJECT.md), [`README.md`](../../README.md), and committed final reports.

## Requirements (confirmed)
- Historical anomaly detection for LUNA crash (May 7-11, 2022)
- Derivatives signals: funding rate + open interest only
- RAG pipeline for ablation comparison
- Agent-executed QA (no automated test suite)

## Technical Decisions
- **Intern tasks**: Assigned to human intern (offline) — Tasks 10-13, 16
- **API placeholders**: Fill during embedding setup (Task 12) — intern fills keys
- **Symbol for May 2022**: Check both LUNAUSDT and LUNCUSDT, document what works
- **News source**: Local archive `/Users/david/Dev/free-crypto-news/archive/` (no Wayback)
- **Storage**: DuckDB + Parquet for OHLCV, PostgreSQL for news

## Research Findings
- Local archive has 172,087 articles, May 2022 fully covered
- Daily JSON files: `archive/2022/05/2022-05-{DD}.json`
- Pre-extracted tickers in `currencies[]` array
- No enrichment needed — PostgreSQL computes derived columns at query time

## Open Questions
- Wave 0 execution: Should Tasks 0.1 and 0.3 run now?

## Scope Boundaries
- INCLUDE: OHLCV, funding rate, OI, news retrieval, Z-score, LLM classifier, ablation study
- EXCLUDE: Real-time infrastructure, ML classifier, Bull/Bear debate, sentiment enrichment, >2 derivatives signals

## Metis Review Outcome
- Intent: Build from Scratch (Greenfield)
- Plan structure: 24 tasks in 5 waves — approved
- Guardrails: enforced
- Risks: mitigated
- Ready for execution after Wave 0 verification