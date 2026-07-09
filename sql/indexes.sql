CREATE INDEX idx_articles_tickers ON crypto_news USING GIN (tickers);

CREATE INDEX idx_articles_textsearch ON crypto_news USING GIN (research);

CREATE INDEX idx_articles_pub_date ON crypto_news USING BRIN (date_pub) WITH (pages_per_range = 32);

CREATE INDEX idx_articles_embedding ON crypto_news USING HNSW ((((text_emb::real[])[1:2000])::vector(2000)) vector_cosine_ops) WITH (m = 16, ef_construction = 64);