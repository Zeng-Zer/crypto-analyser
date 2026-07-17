# `crypto_news` indexes

Packaged `crypto_analyser/assets/schema.sql` creates indexes matched to each query shape:

- **GIN on `tickers`** for array membership filters.
- **GIN on `research`** for PostgreSQL full-text search.
- **BRIN on `date_pub`** for chronological range filtering over append-ordered rows.
- **HNSW on `text_embedding`** for approximate cosine similarity.

## High-dimensional vectors

The embedding model emits 4,096 dimensions, while pgvector's HNSW `vector` operator class supports at most 2,000. The index therefore uses the first 2,000 dimensions:

```sql
(subvector(text_embedding, 1, 2000)::VECTOR(2000)) vector_cosine_ops
```

Retrieval queries must use the identical expression for PostgreSQL to use the index. The complete 4,096-dimensional vector remains stored, allowing later migration or quality comparison. Truncation is an explicit recall/latency tradeoff and should be measured during evaluation rather than assumed lossless.

## Development testing

PostgreSQL may choose a sequential scan for tiny fixture tables because that is cheaper than consulting an index. Index QA may temporarily use:

```sql
SET enable_seqscan = off;
EXPLAIN ANALYZE ...;
```

Do not disable sequential scans in application sessions.