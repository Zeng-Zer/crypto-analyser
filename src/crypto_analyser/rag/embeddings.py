"""Generate embeddings for PostgreSQL news rows in batches."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import psycopg2
import requests
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from crypto_analyser._paths import repo_root

DEFAULT_MODEL = "qwen3-embedding"


def get_unprocessed_articles(cursor: Any, limit: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT id, title_description
        FROM crypto_news
        WHERE text_embedding IS NULL
          AND title_description IS NOT NULL
          AND TRIM(title_description) != ''
        ORDER BY id
        LIMIT %s
        """,
        (limit,),
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
) -> int:
    """Embed pending rows until none remain; return processed count."""
    connection = psycopg2.connect(database_url)
    register_vector(connection)
    processed = 0
    try:
        while True:
            with connection.cursor() as cursor:
                articles = get_unprocessed_articles(cursor, batch_size)
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


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="Generate embeddings for pending crypto-news rows")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)

    required = {name: os.getenv(name) for name in ("DATABASE_URL", "LLM_API_URL", "LLM_API_KEY")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error(f"required environment variables missing: {', '.join(missing)}")
    if args.batch_size < 1 or args.max_attempts < 1:
        parser.error("--batch-size and --max-attempts must be positive")

    try:
        count = generate_pending_embeddings(
            required["DATABASE_URL"],
            required["LLM_API_URL"],
            required["LLM_API_KEY"],
            args.model,
            args.batch_size,
            args.max_attempts,
        )
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Embedding generation complete: {count} rows updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
