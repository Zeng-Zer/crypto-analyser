import os
from datetime import datetime, timezone

import psycopg2
import pytest
from pgvector import Vector
from pgvector.psycopg2 import register_vector

from crypto_analyser.rag import retrieval


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_live_pgvector_retrieval(monkeypatch):
    connection = psycopg2.connect(os.environ["DATABASE_URL"])
    register_vector(connection)
    query_vector = [1.0] + [0.0] * 4095
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO crypto_news
                    (title, description, link, date_pub, source, category, tickers, text_embedding)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "Terra LUNA UST depeg",
                    "LUNA crash coverage",
                    "https://integration.test/luna",
                    datetime(2022, 5, 9, 14, tzinfo=timezone.utc),
                    "test",
                    "general",
                    ["LUNA", "UST"],
                    Vector(query_vector),
                    "Bitcoin ETF",
                    "Unrelated article",
                    "https://integration.test/btc",
                    datetime(2022, 5, 9, 14, tzinfo=timezone.utc),
                    "test",
                    "general",
                    ["BTC"],
                    Vector([-1.0] + [0.0] * 4095),
                ),
            )

        monkeypatch.setattr(retrieval, "get_embeddings", lambda *_args, **_kwargs: [query_vector])
        hybrid = retrieval.retrieve_relevant_news(
            datetime(2022, 5, 9, 14, tzinfo=timezone.utc),
            "LUNA",
            conn=connection,
            api_url="https://example.test/v1",
            api_key="key",
        )
        semantic = retrieval.semantic_search(connection, query_vector, limit=2)

        assert [row["title"] for row in hybrid] == ["Terra LUNA UST depeg"]
        assert semantic[0]["title"] == "Terra LUNA UST depeg"
    finally:
        connection.rollback()
        connection.close()
