from crypto_analyser.rag.embeddings import get_embeddings, get_unprocessed_articles


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}


def test_get_embeddings_preserves_input_order(monkeypatch):
    monkeypatch.setattr("crypto_analyser.rag.embeddings.requests.post", lambda *args, **kwargs: _Response())

    assert get_embeddings(["first", "second"], "https://example.test/v1", "key") == [[1.0], [2.0]]


def test_pending_articles_applies_date_and_text_filters():
    class Cursor:
        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [(7, "Terra depeg")]

    cursor = Cursor()
    assert get_unprocessed_articles(cursor, 20, "2022-05-06", "2022-05-12", "LUNA OR UST OR Terra") == [
        {"id": 7, "text": "Terra depeg"}
    ]
    assert "date_pub >=" in cursor.query
    assert "websearch_to_tsquery" in cursor.query
    assert cursor.params == (
        "2022-05-06",
        "2022-05-06",
        "2022-05-12",
        "2022-05-12",
        "LUNA OR UST OR Terra",
        "LUNA OR UST OR Terra",
        20,
    )
