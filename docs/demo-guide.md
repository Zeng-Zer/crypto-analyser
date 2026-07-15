# Vector search demo

`scripts/demo_retrieval.py` embeds a text query and searches `crypto_news` by cosine distance.

## Prerequisites

- PostgreSQL with pgvector and `sql/schema.sql` applied;
- populated `text_embedding` values;
- `DATABASE_URL`, `LLM_API_URL`, and `LLM_API_KEY` in `.env`;
- dependencies installed with `uv sync --locked`.

## Usage

```bash
uv run python scripts/demo_retrieval.py --query "Terra UST depeg"
uv run python scripts/demo_retrieval.py --query "LUNA price crash" --limit 5
uv run python scripts/demo_retrieval.py --query "Bitcoin ETF approval"
uv run python scripts/demo_retrieval.py --query "Ethereum merge"
```

The table includes similarity, title/snippet, publication metadata, and tickers. The final line reports measured query latency, returned rows, and PostgreSQL's planned scan type.

PostgreSQL can choose a sequential scan for small tables. `HNSW` is printed only when `EXPLAIN` selects `idx_crypto_news_embedding`; no fixed latency is promised.
