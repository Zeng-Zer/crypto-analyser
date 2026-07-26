from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone

import pytest
import requests

from crypto_analyser import live
from crypto_analyser.llm_client import ClassificationResult


def _bars(crash_bars: int = 0) -> list[dict[str, float | int]]:
    end = int(datetime.now(tz=timezone.utc).timestamp() * 1000) // live.INTERVAL_MS * live.INTERVAL_MS
    start = end - 300 * live.INTERVAL_MS
    closes = [40_000.0] * 300
    if crash_bars >= 1:
        closes[-1] = 10_000.0
    if crash_bars >= 2:
        closes[-2:] = [10_000.0, 9_000.0]
    return [
        {
            "ts": start + index * live.INTERVAL_MS,
            "close": close,
            "closeTime": start + (index + 1) * live.INTERVAL_MS - 1,
        }
        for index, close in enumerate(closes)
    ]


def _payload(crash_bars: int = 2) -> dict:
    return {
        "symbol": "BTCUSDT",
        "interval": "5m",
        "markets": {"price": _bars(crash_bars)},
    }


def test_live_server_rejects_occupied_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        with pytest.raises(RuntimeError, match="already in use"):
            live._ensure_port_available(port)


def test_future_bar_is_rejected_even_with_exact_interval_shape():
    bars = _bars()
    bars[-1] = {
        **bars[-1],
        "ts": bars[-1]["ts"] + live.INTERVAL_MS,
        "closeTime": bars[-1]["closeTime"] + live.INTERVAL_MS,
    }

    with pytest.raises(ValueError, match="closed 5-minute interval"):
        live._bars(bars, "spot")


def test_off_grid_bar_is_rejected():
    bars = _bars()
    bars[-1] = {
        **bars[-1],
        "ts": bars[-1]["ts"] + 1,
        "closeTime": bars[-1]["closeTime"] + 1,
    }

    with pytest.raises(ValueError, match="5-minute boundary"):
        live._bars(bars, "price")


def test_price_event_requires_two_flagged_closed_bars():
    with pytest.raises(live.NoConfirmedEpisodeError):
        live.price_event(_payload(crash_bars=1))

    event = live.price_event(_payload())

    assert event["onset_ts"] == _payload()["markets"]["price"][-2]["ts"]
    assert set(event["markets"]) == {"price"}
    assert event["severity"] == "extreme"
    assert {"price_zscore", "drawdown_4h", "return_2h"} <= set(event["triggers"])


def test_derivatives_are_anchored_at_or_before_onset(monkeypatch):
    onset = _payload()["markets"]["price"][-2]["ts"]
    calls: list[tuple[str, dict]] = []

    class Response:
        def __init__(self, payload: list[dict]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self) -> list[dict]:
            return self.payload

    def get(url: str, *, params: dict, **_kwargs):
        calls.append((url, params))
        if url.endswith("/fundingRate"):
            return Response(
                [
                    {"symbol": "BTCUSDT", "fundingTime": onset - 2 * 3_600_000, "fundingRate": "0.0004"},
                    {"symbol": "BTCUSDT", "fundingTime": onset - 8 * 3_600_000, "fundingRate": "0.0002"},
                    {"symbol": "BTCUSDT", "fundingTime": onset + 1, "fundingRate": "0.9"},
                ]
            )
        return Response(
            [
                {"symbol": "BTCUSDT", "timestamp": onset, "sumOpenInterest": "110"},
                {"symbol": "BTCUSDT", "timestamp": onset - 4 * 3_600_000, "sumOpenInterest": "100"},
                {"symbol": "BTCUSDT", "timestamp": onset + 1, "sumOpenInterest": "999"},
            ]
        )

    monkeypatch.setattr(live.requests, "get", get)

    features, source = live.fetch_derivatives(onset)

    assert features["funding_rate_current"] == pytest.approx(0.0004)
    assert features["funding_rate_avg_4h"] == pytest.approx(0.0003)
    assert features["oi_current"] == pytest.approx(110)
    assert features["oi_change_4h"] == pytest.approx(0.10)
    assert source["funding_time"] == onset - 2 * 3_600_000
    assert source["oi_time"] == onset
    assert all(params["endTime"] == onset for _, params in calls)


def test_news_falls_back_to_public_api_and_rejects_post_onset_articles(monkeypatch):
    onset = datetime.now(tz=timezone.utc).replace(microsecond=0)
    calls: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "free_tier": True,
                "articles": [
                    {
                        "title": "Bitcoin market update",
                        "link": "https://example.com/pre-onset",
                        "description": "Published before detection.",
                        "pubDate": (onset - timedelta(minutes=10)).isoformat(),
                        "source": "Example",
                    },
                    {
                        "title": "Future explanation",
                        "link": "https://example.com/post-onset",
                        "pubDate": (onset + timedelta(seconds=1)).isoformat(),
                    },
                    {
                        "title": "Unsafe link",
                        "link": "javascript:alert(1)",
                        "pubDate": (onset - timedelta(minutes=5)).isoformat(),
                    },
                ],
            }

    def get(url: str, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("local app is down")
        return Response()

    monkeypatch.setattr(live.requests, "get", get)

    articles, retrieval = live.fetch_live_news(int(onset.timestamp() * 1000), "http://127.0.0.1:3000/api/news")

    assert calls == ["http://127.0.0.1:3000/api/news", live.PUBLIC_NEWS_API_URL]
    assert [article["title"] for article in articles] == ["Bitcoin market update"]
    assert retrieval["url"] == live.PUBLIC_NEWS_API_URL
    assert retrieval["free_tier"] is True


def test_live_news_ranking_uses_embedding_similarity(monkeypatch):
    event = live.price_event(_payload())
    articles = [
        {"id": "weak", "title": "Weak", "description": "", "date_pub": "2026-01-01T00:00:00+00:00"},
        {"id": "strong", "title": "Strong", "description": "", "date_pub": "2026-01-01T00:00:00+00:00"},
    ]
    monkeypatch.setattr(live, "get_embeddings", lambda *_args, **_kwargs: [[1, 0], [0, 1], [1, 0]])

    ranked = live.rank_live_news(event, articles, "https://llm.example/v1", "key", "embedding")

    assert [article["id"] for article in ranked] == ["strong", "weak"]
    assert ranked[0]["relevance_score"] == 1.0


def test_latest_news_is_cached_without_embedding_or_llm_calls(monkeypatch):
    calls = 0
    article = {
        "id": "latest",
        "title": "Latest Bitcoin headline",
        "description": "Current market coverage.",
        "link": "https://example.com/latest",
        "date_pub": datetime.now(tz=timezone.utc).isoformat(),
        "source": "Example",
    }

    def fetch(*_args):
        nonlocal calls
        calls += 1
        return [article], {"url": live.PUBLIC_NEWS_API_URL, "free_tier": True, "candidate_count": 1}

    class Client:
        def classify(self, *_args):
            raise AssertionError("ambient news must not call LLM")

    monkeypatch.setattr(live, "fetch_live_news", fetch)
    monkeypatch.setattr(live, "get_embeddings", lambda *_args: pytest.fail("ambient news must not embed"))
    service = live.LiveAnalysisService(
        live.PUBLIC_NEWS_API_URL,
        "https://llm.example/v1",
        "key",
        client=Client(),
    )

    first = service.latest()
    second = service.latest()

    assert first["articles"] == [article]
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls == 1


def test_live_analysis_combines_derivatives_and_news_and_is_cached(monkeypatch):
    article = {
        "id": "abc",
        "title": "Bitcoin selloff follows policy shock",
        "description": "A policy announcement triggered broad risk selling.",
        "link": "https://example.com/article",
        "date_pub": datetime.now(tz=timezone.utc).isoformat(),
        "source": "Example",
        "relevance_score": 0.9,
    }
    monkeypatch.setattr(
        live,
        "fetch_live_news",
        lambda *_args: ([article], {"url": "http://127.0.0.1:3000/api/news", "free_tier": False, "candidate_count": 1}),
    )
    monkeypatch.setattr(live, "rank_live_news", lambda _event, articles, *_args: articles)
    monkeypatch.setattr(
        live,
        "fetch_derivatives",
        lambda *_args: (
            {
                "funding_rate_current": 0.0001,
                "funding_rate_avg_4h": 0.0001,
                "oi_current": 100_000.0,
                "oi_change_4h": 0.01,
            },
            {"url": live.BINANCE_FUTURES_API_URL, "funding_time": 1, "oi_time": 2},
        ),
    )

    class Client:
        calls = 0
        system_prompt = ""
        user_prompt = ""

        def classify(self, prompt: str, reference: str, system_prompt: str) -> ClassificationResult:
            self.calls += 1
            self.user_prompt = prompt
            self.system_prompt = system_prompt
            return ClassificationResult.from_dict(
                {
                    "event_reference": reference,
                    "classification": "explained_news",
                    "confidence": 0.9,
                    "synthesis": {
                        "reasons": ["A pre-onset policy shock provides an event-specific explanation."],
                        "supporting_refs": ["news_abc"],
                    },
                    "rationale": "The supplied article reports a policy shock before onset.",
                },
                reference,
            )

    client = Client()
    service = live.LiveAnalysisService(
        "http://127.0.0.1:3000/api/news",
        "https://llm.example/v1",
        "key",
        client=client,
    )

    first = service.analyse(_payload())
    second = service.analyse(_payload())

    assert first["classification"] == "explained_news"
    assert first["articles"][0]["supporting"] is True
    assert first["derivatives"]["funding_rate_current"] == pytest.approx(0.0001)
    assert first["cached"] is False
    assert second["cached"] is True
    assert client.calls == 1
    assert "funding_rate_current  : 0.0100%" in client.user_prompt
    assert "untrusted data" in client.system_prompt


def test_failed_llm_validation_is_not_retried_for_same_event(monkeypatch):
    monkeypatch.setattr(
        live,
        "fetch_derivatives",
        lambda *_args: (
            {
                "funding_rate_current": 0.0001,
                "funding_rate_avg_4h": 0.0001,
                "oi_current": 100_000.0,
                "oi_change_4h": 0.01,
            },
            {"url": live.BINANCE_FUTURES_API_URL, "funding_time": 1, "oi_time": 2},
        ),
    )
    monkeypatch.setattr(
        live,
        "fetch_live_news",
        lambda *_args: ([], {"url": live.PUBLIC_NEWS_API_URL, "free_tier": True, "candidate_count": 0}),
    )

    class Client:
        calls = 0

        def classify(self, _prompt: str, reference: str, _system_prompt: str) -> ClassificationResult:
            self.calls += 1
            return ClassificationResult.from_dict(
                {
                    "event_reference": reference,
                    "classification": "explained_news",
                    "confidence": 0.9,
                    "synthesis": {"reasons": ["Invalid uncited explanation."], "supporting_refs": ["news_missing"]},
                    "rationale": "Invalid uncited explanation.",
                },
                reference,
            )

    client = Client()
    service = live.LiveAnalysisService(
        live.PUBLIC_NEWS_API_URL,
        "https://llm.example/v1",
        "key",
        client=client,
    )

    for _ in range(2):
        with pytest.raises(RuntimeError, match="unavailable supporting refs"):
            service.analyse(_payload())

    assert client.calls == 1
