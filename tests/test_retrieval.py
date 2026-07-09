from datetime import datetime, timezone

import pytest

from crypto_analyser.rag import retrieval


class _Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params):
        self.connection.query = query
        self.connection.params = params

    def fetchall(self):
        return self.connection.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def cursor(self, **_kwargs):
        return _Cursor(self)


def test_hybrid_retrieval_uses_canonical_indexed_expression(monkeypatch):
    rows = [{"id": 1, "title": "Terra depeg", "tickers": ["LUNA"], "rrf_score": 0.03}]
    connection = _Connection(rows)
    monkeypatch.setattr(retrieval, "register_vector", lambda _connection: None)
    monkeypatch.setattr(retrieval, "get_embeddings", lambda *_args, **_kwargs: [[0.1] * 4096])

    result = retrieval.retrieve_relevant_news(
        datetime(2022, 5, 9, 14, tzinfo=timezone.utc),
        "luna",
        conn=connection,
        api_url="https://example.test/v1",
        api_key="key",
    )

    assert result == rows
    assert "subvector(text_embedding, 1, 2000)::VECTOR(2000)" in connection.query
    assert "ai_emb" not in connection.query
    assert connection.params["ticker"] == "LUNA"
    assert connection.params["start_time"] == datetime(2022, 5, 9, 2, tzinfo=timezone.utc)
    assert connection.params["end_time"] == datetime(2022, 5, 10, 2, tzinfo=timezone.utc)
    assert connection.params["query_vector"].dimensions() == 2000


def test_semantic_search_rejects_short_embedding():
    with pytest.raises(ValueError, match="2000 required"):
        retrieval.semantic_search(_Connection([]), [0.1] * 1999)
