# News schema

Canonical definition: [`src/crypto_analyser/assets/schema.sql`](../src/crypto_analyser/assets/schema.sql).

## `crypto_news`

| Column | Type | Purpose |
|---|---|---|
| `id` | `BIGSERIAL` | Primary key |
| `title` | `TEXT NOT NULL` | Article title |
| `description` | `TEXT` | Optional article description |
| `link` | `TEXT NOT NULL` | Source URL |
| `date_pub` | `TIMESTAMPTZ` | Publication timestamp |
| `source` | `TEXT NOT NULL` | Publisher/source label |
| `category` | `TEXT NOT NULL` | Archive category |
| `tickers` | `TEXT[] NOT NULL` | Referenced asset symbols |
| `sentiment` | `VARCHAR(32)` | Optional archive sentiment |
| `title_description` | generated `TEXT` | Combined embedding/search input |
| `research` | generated `TSVECTOR` | PostgreSQL full-text search document |
| `text_embedding` | `VECTOR(4096)` | Qwen3 embedding |

`(link, date_pub)` is unique, making archive loading idempotent. Generated columns are stored so they can be indexed. Index choices are documented in [`indexes.md`](indexes.md).

Applying the packaged schema migrates legacy `ai_emb` data to `text_embedding`, replaces legacy index names, and is idempotent.
