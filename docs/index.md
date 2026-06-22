Technical Documentation: crypto_news Table Indexing

This document summarizes the architecture choices made to optimize the database response times. The goal was to avoid full table reads (Sequential Scans) by applying specific indexes based on the data type.

Standard Index Choices

To avoid using standard B-Tree indexes, which do not fit all our use cases, we opted for GIN and BRIN indexes.

For the tickers column (which contains text arrays) and the research column (which contains tsvector formatted text), we implemented GIN indexes. This type of index works like an inverted dictionary. It is the most efficient way to quickly check if a specific tag or exact word is located inside a list or a long text.

For chronological filtering on the date_pub column, we used a BRIN index. Because articles are inserted chronologically into the database, they are stored in the same order on the hard drive. The BRIN index simply records the minimum and maximum values by physical blocks. This gives us an extremely lightweight index compared to a B-Tree, while being very fast for targeting date ranges.

Vector Index Implementation (HNSW) and Truncation

The most complex part was indexing the ai_emb column for similarity search. We chose an HNSW index, which allows for highly performant navigation between closely related vectors.

However, we ran into a technical limit: our model (Qwen3) generates 4096-dimensional vectors, but the pgvector extension limits index creation to 2000 dimensions for physical performance reasons.

To solve this blocker, we decided to directly truncate the vectors to 2000 dimensions in the index. This is possible without degrading the search quality thanks to the model's training method, Matryoshka Representation Learning. This technique concentrates the core semantics in the first dimensions of the vector. The dimensions beyond 2000 only contain negligible nuances for our use case. By cutting it at 2000 dimensions, we divide the server's memory consumption by two and speed up mathematical calculations, while keeping highly relevant results.

Note on Development Testing

During the validation phase of these indexes in the local environment, the execution plans (EXPLAIN ANALYZE) systematically showed Seq Scans instead of using our indexes.

This is a normal behavior of the PostgreSQL Query Planner: since our test table only contained about twenty articles, the engine decided it was faster to read the entire table at once rather than making the effort to consult an index. To generate proof that our indexes work for QA, we had to temporarily force their use by disabling sequential scanning via the SET enable_seqscan = off; command.