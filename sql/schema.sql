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

-- Migrate databases created by the original schema without losing embeddings.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'crypto_news' AND column_name = 'ai_emb'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'crypto_news' AND column_name = 'text_embedding'
    ) THEN
        ALTER TABLE crypto_news RENAME COLUMN ai_emb TO text_embedding;
    END IF;
END
$$;

ALTER TABLE crypto_news
    ADD COLUMN IF NOT EXISTS text_embedding VECTOR(4096),
    ALTER COLUMN sentiment TYPE VARCHAR(32);

-- A partially migrated database can contain both names. Preserve whichever
-- canonical value already exists, otherwise copy the legacy value.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'crypto_news' AND column_name = 'ai_emb'
    ) THEN
        UPDATE crypto_news
        SET text_embedding = ai_emb
        WHERE text_embedding IS NULL AND ai_emb IS NOT NULL;
    END IF;
END
$$;

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

DROP INDEX IF EXISTS idx_articles_tickers;
DROP INDEX IF EXISTS idx_articles_textsearch;
DROP INDEX IF EXISTS idx_articles_pub_date;
DROP INDEX IF EXISTS idx_articles_embedding;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'crypto_news' AND column_name = 'ai_emb'
    ) THEN
        ALTER TABLE crypto_news DROP COLUMN ai_emb;
    END IF;
END
$$;
