# Agent Instructions for crypto-analyser

## Project Context

See `.sisyphus/PROJECT.md` for full project overview.

Key constraints:
- Milestone 1 is entirely batch/historical (no real-time)
- Symbol: LUNAUSDT (not LUNCUSDT)
- Data source: data.binance.vision (API limited to 30 days)
- Two derivatives signals: funding rate + open interest
- Python package manager: uv

## Graphify

This project has a knowledge graph in `graphify-out/` with code, documentation, community structure, and cross-file relationships.

- For codebase questions, run `graphify query "<question>"` first when `graphify-out/graph.json` exists.
- Use `graphify path "<A>" "<B>"` to trace relationships and `graphify explain "<concept>"` for focused inspection.
- Use `graphify-out/wiki/index.md` for broad navigation when present. Read `graphify-out/GRAPH_REPORT.md` for architecture reviews or when scoped queries are insufficient.
- Treat `EXTRACTED` edges as source-backed and `INFERRED` edges as hypotheses requiring verification against source before code changes.
- Dirty generated graph files are expected after hooks or incremental updates and are not a reason to skip Graphify.
- After modifying code or documentation, run `graphify update .` to keep the graph current.
