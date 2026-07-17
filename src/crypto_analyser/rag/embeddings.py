"""Generate embeddings for PostgreSQL news rows in batches."""

from __future__ import annotations

import time
from typing import Any

import psycopg2
import requests
from pgvector.psycopg2 import register_vector

DEFAULT_MODEL = "qwen3-embedding"


def get_unprocessed_articles(
    cursor: Any,
    limit: int,
    start: str | None = None,
    end: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT id, title_description
        FROM crypto_news
        WHERE text_embedding IS NULL
          AND title_description IS NOT NULL
          AND TRIM(title_description) != ''
          AND (%s IS NULL OR date_pub >= %s::TIMESTAMPTZ)
          AND (%s IS NULL OR date_pub < %s::TIMESTAMPTZ)
          AND (%s IS NULL OR research @@ websearch_to_tsquery('english', %s))
        ORDER BY id
        LIMIT %s
        """,
        (start, start, end, end, query, query, limit),
    )
    return [{"id": row[0], "text": row[1]} for row in cursor.fetchall()]


def get_embeddings(
    texts: list[str],
    api_url: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_attempts: int = 3,
) -> list[list[float]]:
    """Call an OpenAI-compatible embedding endpoint with bounded retries."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": texts}
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = requests.post(
                f"{api_url.rstrip('/')}/embeddings",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            vectors = [item["embedding"] for item in sorted(response.json()["data"], key=lambda item: item["index"])]
            if len(vectors) != len(texts):
                raise ValueError(f"embedding API returned {len(vectors)} vectors for {len(texts)} inputs")
            return vectors
        except requests.HTTPError as exc:
            last_error = exc
            if exc.response is None or exc.response.status_code != 429 or attempt == max_attempts - 1:
                break
            time.sleep(int(exc.response.headers.get("Retry-After", "10")))
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            time.sleep(2**attempt)

    raise RuntimeError(f"embedding request failed after {max_attempts} attempts: {last_error}")


def update_articles_with_vectors(cursor: Any, ids: list[int], vectors: list[list[float]]) -> None:
    cursor.executemany(
        "UPDATE crypto_news SET text_embedding = %s WHERE id = %s",
        zip(vectors, ids, strict=True),
    )


def generate_pending_embeddings(
    database_url: str,
    api_url: str,
    api_key: str,
    model: str,
    batch_size: int,
    max_attempts: int,
    start: str | None = None,
    end: str | None = None,
    query: str | None = None,
) -> int:
    """Embed pending rows matching optional date/text filters; return processed count."""
    connection = psycopg2.connect(database_url)
    register_vector(connection)
    processed = 0
    try:
        while True:
            with connection.cursor() as cursor:
                articles = get_unprocessed_articles(cursor, batch_size, start, end, query)
            if not articles:
                return processed

            vectors = get_embeddings(
                [article["text"] for article in articles],
                api_url,
                api_key,
                model=model,
                max_attempts=max_attempts,
            )
            with connection:
                with connection.cursor() as cursor:
                    update_articles_with_vectors(cursor, [article["id"] for article in articles], vectors)
            processed += len(articles)
            print(f"Embedded {processed} articles.")
    finally:
        connection.close()
