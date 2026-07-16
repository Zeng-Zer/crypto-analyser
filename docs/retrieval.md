# Hybrid news retrieval

`crypto_analyser.rag.retrieval.retrieve_relevant_news()` retrieves historical news around an anomaly timestamp.

## Filters and ranking

Candidates must:

- match ticker aliases or full text (`LUNA`, `UST`, or `Terra` for LUNAUSDT);
- fall between the configured lookback start and episode onset;
- have an embedding for vector ranking or match the full-text query.

The end timestamp is the episode onset. Future articles are excluded to prevent look-ahead leakage.

PostgreSQL ranks vector and full-text candidates separately, then combines them with reciprocal rank fusion:

```text
score = 1 / (rrf_k + vector_rank) + 1 / (rrf_k + text_rank)
```

A candidate present in only one ranking receives only that ranking's term. Default `rrf_k` is 60.

Qwen3 embeddings remain stored at 4,096 dimensions. Queries use the same 2,000-dimensional expression as the HNSW index:

```sql
subvector(text_embedding, 1, 2000)::VECTOR(2000)
```

## Usage

Set `DATABASE_URL`, `LLM_API_URL`, and `LLM_API_KEY`, then run:

```bash
uv run crypto-analyser run \
  --symbol LUNAUSDT \
  --start 2022-05-07 \
  --end 2022-05-11 \
  --mode derivatives_rag \
  --skip-download
```

Unit and PostgreSQL integration tests verify ticker aliases, onset cutoff, ranking expression, and result ordering.

`crypto-analyser run --mode derivatives_rag` writes one `data/rag/*_rag.json` file per episode before classification. The LUNA experiment embeds only May 6–11 text matches; embedding all 172K archive rows is unnecessary for Milestone 1.
