"""Semantic and anomaly-window retrieval from the historical news store."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

from crypto_analyser._paths import data_root
from crypto_analyser.rag.embeddings import DEFAULT_MODEL, get_embeddings

_INDEX_DIMENSIONS = 2000
_MAX_RESULTS = 100

_SEMANTIC_SEARCH_SQL = """
SELECT id, title, description, date_pub, source, tickers,
       subvector(text_embedding, 1, 2000)::VECTOR(2000)
           <=> %s::VECTOR(2000) AS distance
FROM crypto_news
WHERE text_embedding IS NOT NULL
ORDER BY subvector(text_embedding, 1, 2000)::VECTOR(2000)
         <=> %s::VECTOR(2000)
LIMIT %s
"""

_HYBRID_SEARCH_SQL = """
WITH vector_ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY subvector(text_embedding, 1, 2000)::VECTOR(2000)
                        <=> %(query_vector)s::VECTOR(2000)
           ) AS vector_rank
    FROM crypto_news
    WHERE date_pub BETWEEN %(start_time)s AND %(end_time)s
      AND (tickers && %(aliases)s::TEXT[]
           OR research @@ websearch_to_tsquery('english', %(text_query)s))
      AND text_embedding IS NOT NULL
    ORDER BY subvector(text_embedding, 1, 2000)::VECTOR(2000)
             <=> %(query_vector)s::VECTOR(2000)
    LIMIT %(candidate_limit)s
),
text_ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(
                   research,
                   websearch_to_tsquery('english', %(text_query)s)
               ) DESC
           ) AS text_rank
    FROM crypto_news
    WHERE date_pub BETWEEN %(start_time)s AND %(end_time)s
      AND (tickers && %(aliases)s::TEXT[]
           OR research @@ websearch_to_tsquery('english', %(text_query)s))
    ORDER BY ts_rank_cd(
        research,
        websearch_to_tsquery('english', %(text_query)s)
    ) DESC
    LIMIT %(candidate_limit)s
),
ranked AS (
    SELECT COALESCE(vector_ranked.id, text_ranked.id) AS id,
           vector_rank,
           text_rank,
           COALESCE(1.0::DOUBLE PRECISION / (%(rrf_k)s + vector_rank), 0.0)
             + COALESCE(1.0::DOUBLE PRECISION / (%(rrf_k)s + text_rank), 0.0)
               AS rrf_score
    FROM vector_ranked
    FULL OUTER JOIN text_ranked USING (id)
)
SELECT crypto_news.id,
       crypto_news.title,
       crypto_news.description,
       crypto_news.date_pub,
       crypto_news.source,
       crypto_news.tickers,
       ranked.vector_rank,
       ranked.text_rank,
       ranked.rrf_score
FROM ranked
JOIN crypto_news USING (id)
ORDER BY ranked.rrf_score DESC, crypto_news.date_pub DESC NULLS LAST
LIMIT %(top_k)s
"""


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= _MAX_RESULTS:
        raise ValueError(f"limit must be between 1 and {_MAX_RESULTS}")


def _index_vector(vector: list[float]) -> Vector:
    if len(vector) < _INDEX_DIMENSIONS:
        raise ValueError(f"embedding has {len(vector)} dimensions; {_INDEX_DIMENSIONS} required")
    return Vector(vector[:_INDEX_DIMENSIONS])


def semantic_search(connection: Any, query_vector: list[float], limit: int = 10) -> list[dict[str, Any]]:
    """Return nearest articles using the same expression as the HNSW index."""
    _validate_limit(limit)
    vector = _index_vector(query_vector)
    register_vector(connection)
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(_SEMANTIC_SEARCH_SQL, (vector, vector, limit))
        return [dict(row) for row in cursor.fetchall()]


def search_news(
    query: str,
    database_url: str,
    api_url: str,
    api_key: str,
    *,
    limit: int = 10,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    """Embed a query and return semantically similar historical articles."""
    vector = get_embeddings([query], api_url, api_key, model=model)[0]
    connection = psycopg2.connect(database_url)
    try:
        return semantic_search(connection, vector, limit)
    finally:
        connection.close()


def retrieve_relevant_news(
    anomaly_timestamp: datetime,
    ticker: str,
    top_k: int = 10,
    window_hours: int = 12,
    conn: Any | None = None,
    dsn: str | None = None,
    rrf_k: int = 60,
    api_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve ticker- and time-filtered articles ranked by vector/text RRF."""
    ticker = ticker.strip().upper()
    _validate_limit(top_k)
    if not ticker:
        raise ValueError("ticker is required")
    if window_hours < 1:
        raise ValueError("window_hours must be positive")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if conn is None and not dsn:
        raise ValueError("conn or dsn is required")

    api_url = api_url or os.getenv("LLM_API_URL")
    api_key = api_key or os.getenv("LLM_API_KEY")
    if not api_url or not api_key:
        raise RuntimeError("LLM_API_URL and LLM_API_KEY are required")

    if anomaly_timestamp.tzinfo is None:
        anomaly_timestamp = anomaly_timestamp.replace(tzinfo=timezone.utc)
    start_time = anomaly_timestamp - timedelta(hours=window_hours)
    end_time = anomaly_timestamp
    aliases = [ticker]
    text_query = ticker
    if ticker == "LUNA":
        aliases = ["LUNA", "UST", "TERRA"]
        text_query = "LUNA OR UST OR Terra"
    query_vector = _index_vector(
        get_embeddings(
            [f"{text_query} price anomaly crypto news"],
            api_url,
            api_key,
            model=model or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL),
        )[0]
    )
    params = {
        "query_vector": query_vector,
        "text_query": text_query,
        "aliases": aliases,
        "start_time": start_time,
        "end_time": end_time,
        "candidate_limit": top_k * 5,
        "rrf_k": rrf_k,
        "top_k": top_k,
    }

    own_connection = conn is None
    connection = conn if conn is not None else psycopg2.connect(dsn)
    try:
        register_vector(connection)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(_HYBRID_SEARCH_SQL, params)
            return [dict(row) for row in cursor.fetchall()]
    finally:
        if own_connection:
            connection.close()


def write_episode_contexts(
    anomalies_path: Path,
    dsn: str,
    api_url: str,
    api_key: str,
    top_k: int = 5,
    window_hours: int = 24,
    output_dir: Path | None = None,
) -> list[Path]:
    """Retrieve news published by each episode onset and write classifier inputs."""
    anomalies = json.loads(anomalies_path.read_text(encoding="utf-8"))
    symbol = anomalies["meta"]["symbol"]
    ticker = symbol.removesuffix("USDT")
    output_dir = output_dir or data_root() / "rag"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for episode in anomalies["episodes"]:
        onset_ts = episode["onset_ts"]
        onset = datetime.fromtimestamp(onset_ts / 1000, tz=timezone.utc)
        articles = retrieve_relevant_news(
            onset,
            ticker,
            top_k=top_k,
            window_hours=window_hours,
            dsn=dsn,
            api_url=api_url,
            api_key=api_key,
        )
        serializable = [
            {**article, "date_pub": article["date_pub"].isoformat() if article.get("date_pub") else None}
            for article in articles
        ]
        block = "\n\n".join(
            f"[{article['date_pub']}] {article['title']}\n{article.get('description') or ''}"
            for article in serializable
        ) or "(No relevant news was published before this episode onset.)"
        path = output_dir / f"{symbol}_{onset_ts}_rag.json"
        path.write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "onset_ts": onset_ts,
                    "cutoff": onset.isoformat(),
                    "window": f"{window_hours}h before onset",
                    "k": top_k,
                    "articles": serializable,
                    "block": block,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        paths.append(path)
    return paths
