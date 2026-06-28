CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE crypto_news ADD COLUMN text_embedding vector(4096)
