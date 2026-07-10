CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS crypto_news (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT NOT NULL,
    date_pub TIMESTAMPTZ,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    tickers TEXT[] NOT NULL DEFAULT '{}',
    title_description TEXT GENERATED ALWAYS AS (
        title || ' ' || COALESCE(description, '')
    ) STORED,
    research TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', title || ' ' || COALESCE(description, ''))
    ) STORED,
    sentiment VARCHAR(32),
    text_embedding VECTOR(4096),
    UNIQUE (link, date_pub)
);

-- Existing databases created by the earlier schema may not have this column.
ALTER TABLE crypto_news
    ADD COLUMN IF NOT EXISTS text_embedding VECTOR(4096);

CREATE INDEX IF NOT EXISTS idx_crypto_news_tickers
    ON crypto_news USING GIN (tickers);

CREATE INDEX IF NOT EXISTS idx_crypto_news_research
    ON crypto_news USING GIN (research);

CREATE INDEX IF NOT EXISTS idx_crypto_news_date_pub
    ON crypto_news USING BRIN (date_pub) WITH (pages_per_range = 32);

-- pgvector HNSW indexes support at most 2,000 vector dimensions. Qwen3 emits
-- 4,096 dimensions, so retrieval indexes and queries use the same first-2,000
-- expression. The full vector remains stored for future migration.
CREATE INDEX IF NOT EXISTS idx_crypto_news_embedding
    ON crypto_news USING HNSW (
        (subvector(text_embedding, 1, 2000)::VECTOR(2000)) vector_cosine_ops
    ) WITH (m = 16, ef_construction = 64);