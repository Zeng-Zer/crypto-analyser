# Hybrid news retrieval

`crypto_analyser.rag.retrieval.retrieve_relevant_news()` retrieves historical news around an anomaly timestamp.

## Filters and ranking

Candidates must:

- contain the requested ticker in `tickers`;
- fall within the configured window (12 hours before and after by default);
- have an embedding for vector ranking or match the full-text query.

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
uv run python scripts/test_retrieval.py \
  --ticker LUNA \
  --timestamp 2022-05-09T14:00:00+00:00
```

`--date 2022-05-09` searches around noon UTC. The script exits nonzero when any result violates the ticker/time filters or LUNA results lack LUNA/Terra/UST/depeg text.

Task 16's LUNA acceptance still requires a database populated with May 2022 LUNA articles and embeddings.
