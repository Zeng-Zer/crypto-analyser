from crypto_analyser.rag.embeddings import get_embeddings


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}


def test_get_embeddings_preserves_input_order(monkeypatch):
    monkeypatch.setattr("crypto_analyser.rag.embeddings.requests.post", lambda *args, **kwargs: _Response())

    assert get_embeddings(["first", "second"], "https://example.test/v1", "key") == [[1.0], [2.0]]
