from __future__ import annotations

import socket
import threading
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


def test_live_health_requires_database_and_fresh_closed_bar():
    state = {
        "ready": True,
        "bars": _bars(),
        "status": "Polling",
    }

    class Store:
        available = True

        def check(self):
            if not self.available:
                raise live.psycopg2.OperationalError("database unavailable")

    class Worker:
        def snapshot(self, **_kwargs):
            return state

    server = live.ThreadingHTTPServer(("127.0.0.1", 0), live._LiveHandler)
    server.episode_store = Store()
    server.market_worker = Worker()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/healthz"
        response = requests.get(url, timeout=2)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        state["bars"][-1]["closeTime"] -= live.HEALTH_MAX_BAR_AGE_MS + 1
        response = requests.get(url, timeout=2)
        assert response.status_code == 503
        assert response.json()["market"] == "stale"

        server.episode_store.available = False
        response = requests.get(url, timeout=2)
        assert response.status_code == 503
        assert response.json()["database"] == "unavailable"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_stream_rejects_connections_over_capacity():
    class Slots:
        def acquire(self, **_kwargs):
            return False

    server = live.ThreadingHTTPServer(("127.0.0.1", 0), live._LiveHandler)
    server.stream_slots = Slots()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = requests.get(f"http://127.0.0.1:{server.server_port}/api/live-stream", timeout=2)
        assert response.status_code == 503
        assert response.json() == {"error": "live stream capacity reached"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_server_bounds_all_http_connections():
    server = live._BoundedThreadingHTTPServer(("127.0.0.1", 0), live._LiveHandler, max_connections=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = requests.get(f"http://127.0.0.1:{server.server_port}/missing", timeout=2)
        assert response.status_code == 404
        assert server.request_slots.acquire(timeout=1) is True

        class RejectedRequest:
            closed = False

            def close(self):
                self.closed = True

        request = RejectedRequest()
        server.process_request(request, ("127.0.0.1", 1))
        assert request.closed is True
        server.request_slots.release()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


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
    assert event["detected_ts"] == _payload()["markets"]["price"][-1]["closeTime"] + 1
    assert set(event["markets"]) == {"price"}
    assert event["severity"] == "extreme"
    assert {"price_zscore", "drawdown_4h", "return_2h"} <= set(event["triggers"])


def test_backend_worker_triggers_one_analysis_without_browser():
    analysed = threading.Event()

    class Service:
        calls = []
        claimed = False

        def latest(self):
            return {}

        def market(self):
            return {}

        def claim(self, payload):
            if self.claimed:
                return None
            self.claimed = True
            return live.price_event(payload)

        def analyse_claimed(self, event):
            self.calls.append(event)
            analysed.set()

    service = Service()
    worker = live.LiveMarketWorker(service)
    bars = _bars(crash_bars=2)

    worker._set_bars(bars, connected=True, status="Streaming", error="")
    assert analysed.wait(1)
    worker._set_bars(bars, connected=True, status="Streaming", error="")

    assert len(service.calls) == 1
    assert service.calls[0]["bars"] == bars
    assert worker.snapshot()["detector"]["kind"] == "active"
    assert worker.snapshot()["analysis"] == {"loading": False, "error": ""}


def test_rest_reconciliation_advances_silent_websocket_feed(monkeypatch):
    class Service:
        def latest(self):
            return {}

        def market(self):
            return {}

    worker = live.LiveMarketWorker(Service())
    stale = _bars()
    latest = stale[-1]["ts"] + live.INTERVAL_MS
    fresh = [
        *stale[1:],
        {"ts": latest, "close": 40_123.0, "closeTime": latest + live.INTERVAL_MS - 1},
    ]
    worker._set_bars(stale, connected=True, status="Polling", error="")
    monkeypatch.setattr(worker, "_backfill", lambda: fresh)

    worker._reconcile("Polling")

    state = worker.snapshot()
    assert state["bars"][-1] == fresh[-1]
    assert state["connected"] is True
    assert state["status"] == "Polling"


def test_backend_accepts_only_closed_btc_five_minute_stream_bars():
    timestamp = _bars()[-1]["ts"]

    def payload(closed: bool = True, symbol: str = "BTCUSDT") -> dict:
        return {
            "e": "kline",
            "s": symbol,
            "k": {
                "t": timestamp,
                "T": timestamp + live.INTERVAL_MS - 1,
                "i": "5m",
                "c": "40000",
                "x": closed,
            },
        }

    assert live._stream_bar(payload(closed=False)) is None
    assert live._stream_bar(payload(symbol="ETHUSDT")) is None
    assert live._stream_bar(payload()) == {
        "ts": timestamp,
        "close": 40_000.0,
        "closeTime": timestamp + live.INTERVAL_MS - 1,
    }


def test_recent_backfill_detects_and_runs_combined_pipeline(monkeypatch):
    end = (
        int(datetime.now(tz=timezone.utc).timestamp() * 1000) // live.INTERVAL_MS * live.INTERVAL_MS
        - live.INTERVAL_MS
    )
    start = end - (live.WINDOW_BARS + 288 - 1) * live.INTERVAL_MS
    bars = [
        {
            "ts": start + index * live.INTERVAL_MS,
            "close": 10_000.0 if index == 574 else 9_000.0 if index == 575 else 40_000.0,
            "closeTime": start + (index + 1) * live.INTERVAL_MS - 1,
        }
        for index in range(576)
    ]
    monkeypatch.setattr(live, "fetch_price_history", lambda *_args: bars)

    class Service:
        claimed = []
        analysed = []

        def claim(self, payload):
            event = live.price_event(payload)
            self.claimed.append(event)
            return event

        def analyse_claimed(self, event):
            self.analysed.append(event)

    service = Service()
    result = live.backfill_recent_episodes(1, service, now_ms=end + live.INTERVAL_MS)

    assert result["detected"] == 1
    assert result["complete"] == 1
    assert result["failed"] == []
    assert len(service.claimed) == len(service.analysed) == 1
    assert service.claimed[0]["onset_ts"] == bars[-2]["ts"]


def test_recent_backfill_continues_after_one_claim_failure(monkeypatch):
    end = (
        int(datetime.now(tz=timezone.utc).timestamp() * 1000) // live.INTERVAL_MS * live.INTERVAL_MS
        - live.INTERVAL_MS
    )
    start = end - 575 * live.INTERVAL_MS
    bars = [
        {
            "ts": start + index * live.INTERVAL_MS,
            "close": 43_000.0 if index in {400, 401, 500, 501} else 40_000.0,
            "closeTime": start + (index + 1) * live.INTERVAL_MS - 1,
        }
        for index in range(576)
    ]
    monkeypatch.setattr(live, "fetch_price_history", lambda *_args: bars)

    class Service:
        claims = 0
        analysed = []

        def claim(self, payload):
            self.claims += 1
            if self.claims == 1:
                raise RuntimeError("database unavailable")
            return live.price_event(payload)

        def analyse_claimed(self, event):
            self.analysed.append(event)

    service = Service()
    result = live.backfill_recent_episodes(1, service, now_ms=end + live.INTERVAL_MS)

    assert result["detected"] == 2
    assert result["complete"] == 1
    assert result["failed"] == [
        {"event_reference": f"BTCUSDT_{bars[400]['ts']}", "error": "database unavailable"}
    ]
    assert service.analysed[0]["onset_ts"] == bars[500]["ts"]


def test_live_ragas_failure_is_stored_without_failing_analysis():
    def fail(*_args):
        raise RuntimeError("judge unavailable")

    service = live.LiveAnalysisService(
        live.PUBLIC_NEWS_API_URL,
        "https://llm.example/v1",
        "key",
        client=object(),
        judge_model="judge",
        faithfulness_scorer=fail,
    )
    event = live.price_event(_payload())
    derivatives = {
        "funding_rate_current": 0.0001,
        "funding_rate_avg_4h": 0.0001,
        "oi_current": 100_000.0,
        "oi_change_4h": 0.01,
    }

    evaluation = service._evaluate_faithfulness(event, derivatives, [], "Supported rationale.")

    assert evaluation["score"] is None
    assert evaluation["error"] == "judge unavailable"


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


def test_news_trust_header_is_loopback_only():
    assert live._news_headers("http://127.0.0.1:3000/api/news")["Sec-Fetch-Site"] == "same-site"
    assert "Sec-Fetch-Site" not in live._news_headers(live.PUBLIC_NEWS_API_URL)


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


def test_live_news_collects_paginated_24h_results(monkeypatch):
    onset = datetime.now(tz=timezone.utc).replace(microsecond=0)
    pages: list[tuple[str, int]] = []

    class Response:
        def __init__(self, page: int) -> None:
            self.page = page

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "articles": [
                    {
                        "title": f"Bitcoin page {self.page}",
                        "link": f"https://example.com/{self.page}",
                        "pubDate": (onset - timedelta(hours=self.page)).isoformat(),
                        "source": "Example",
                    },
                    {
                        "title": f"Unrelated Ethereum page {self.page}",
                        "link": f"https://example.com/eth-{self.page}",
                        "pubDate": (onset - timedelta(hours=self.page)).isoformat(),
                        "source": "Example",
                    },
                ],
                "pagination": {"hasMore": self.page == 1},
            }

    def get(_url: str, *, params: dict, **_kwargs):
        pages.append((params["category"], params["page"]))
        return Response(params["page"])

    monkeypatch.setattr(live.requests, "get", get)

    articles, _ = live.fetch_live_news(int(onset.timestamp() * 1000), "http://127.0.0.1:3000/api/news")

    assert pages == [("bitcoin", 1), ("bitcoin", 2), ("general", 1), ("general", 2)]
    assert [article["title"] for article in articles] == ["Bitcoin page 1", "Bitcoin page 2"]


def test_public_news_fallback_is_one_page_and_three_samples(monkeypatch):
    onset = datetime.now(tz=timezone.utc).replace(microsecond=0)
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "articles": [
                    {
                        "title": f"Bitcoin sample {index}",
                        "link": f"https://example.com/{index}",
                        "pubDate": (onset - timedelta(minutes=index)).isoformat(),
                    }
                    for index in range(5)
                ],
                "pagination": {"hasMore": True},
                "free_tier": True,
            }

    def get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr(live.requests, "get", get)

    articles, _ = live.fetch_live_news(int(onset.timestamp() * 1000), live.PUBLIC_NEWS_API_URL)

    assert calls == 1
    assert len(articles) == 3


def test_history_range_uses_viewer_local_day():
    start, end = live._history_range("2026-10-25", "Europe/Paris")

    assert end - start == timedelta(hours=25)


def test_legacy_detection_respects_allowed_gap_between_flagged_bars():
    bars = _bars(0)
    bars[-3]["close"], bars[-2]["close"], bars[-1]["close"] = 10_000.0, 40_000.0, 9_000.0
    snapshot = {"onset_ts": bars[-3]["ts"], "bars": bars}

    assert live._legacy_detection_ts(snapshot) == bars[-1]["closeTime"] + 1


def test_history_verdict_rejects_unknown_filter():
    assert live._history_verdict("explained") == "explained"
    assert live._history_verdict("unexplained") == "unexplained"
    assert live._history_verdict("all") == "all"
    with pytest.raises(ValueError, match="verdict must be"):
        live._history_verdict("failed")


def test_live_news_ranking_fuses_vector_and_keyword_ranks(monkeypatch):
    event = live.price_event(_payload())
    articles = [
        {"id": "vector", "title": "Bitcoin market", "description": "", "date_pub": "2026-01-01T00:00:00+00:00"},
        {"id": "hybrid", "title": "Bitcoin crash selloff", "description": "", "date_pub": "2026-01-01T00:00:00+00:00"},
        {"id": "keyword", "title": "Bitcoin decline", "description": "", "date_pub": "2026-01-01T00:00:00+00:00"},
    ]
    embedded = []

    def embeddings(texts, *_args, **_kwargs):
        embedded.extend(texts)
        return [[1, 0], [1, 0], [0.8, 0.6], [0, 1]]

    monkeypatch.setattr(live, "get_embeddings", embeddings)

    ranked = live.rank_live_news(event, articles, "https://llm.example/v1", "key", "embedding")

    assert [article["id"] for article in ranked] == ["hybrid", "vector", "keyword"]
    assert ranked[0]["vector_rank"] == 2
    assert ranked[0]["text_rank"] == 1
    assert ranked[0]["rrf_score"] == pytest.approx(1 / 62 + 1 / 61)
    assert "crash price drop selloff decline" in embedded[0]


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


def test_seed_news_is_detection_safe_and_merged_for_explicit_event(monkeypatch):
    onset = datetime.now(tz=timezone.utc).replace(microsecond=0)
    detection = onset + timedelta(minutes=10)
    monkeypatch.setattr(
        live,
        "fetch_live_news",
        lambda *_args: ([], {"url": "http://127.0.0.1:3000/api/news", "candidate_count": 0}),
    )
    service = live.LiveAnalysisService(
        live.PUBLIC_NEWS_API_URL,
        "https://llm.example/v1",
        "key",
        client=object(),
        seed_articles=[
            {
                "title": "Strategy announced a Bitcoin sale",
                "description": "Strategy sold 3,588 BTC.",
                "link": "https://example.com/announcement",
                "pubDate": onset.isoformat(),
                "source": "Strategy",
            },
            {
                "title": "Future Bitcoin commentary",
                "link": "https://example.com/future",
                "pubDate": (detection + timedelta(seconds=1)).isoformat(),
            },
            {
                "title": "Naive Bitcoin timestamp",
                "link": "https://example.com/naive",
                "pubDate": onset.replace(tzinfo=None).isoformat(),
            },
            {
                "title": "Bitcoin article edited after detection",
                "link": "https://example.com/edited-after",
                "pubDate": (onset - timedelta(hours=1)).isoformat(),
                "dateModified": (detection + timedelta(seconds=1)).isoformat(),
            },
            {
                "title": "Macroeconomic release",
                "description": "Inflation slowed more than expected.",
                "link": "https://example.com/macro",
                "pubDate": (onset + timedelta(minutes=5)).isoformat(),
            },
        ],
    )

    event = {"onset_ts": int(onset.timestamp() * 1_000), "detected_ts": int(detection.timestamp() * 1_000)}
    articles, source = service._news_at_detection(event)

    assert [article["title"] for article in articles] == [
        "Macroeconomic release",
        "Strategy announced a Bitcoin sale",
    ]
    assert source["cutoff_ts"] == event["detected_ts"]
    assert source["seed_candidate_count"] == 2
    assert source["candidate_count"] == 2
    assert source["ranked_candidate_count"] == 2


def test_explicit_event_requires_aware_times_and_matching_news_window(tmp_path):
    with pytest.raises(ValueError, match="include a timezone"):
        live._event_time("2026-07-06T11:00:00")

    news_file = tmp_path / "event.json"
    news_file.write_text(
        """{
          "window": {"start": "2026-07-06T10:00:00Z", "end": "2026-07-06T14:00:00Z"},
          "articles": [{
            "title": "Strategy Bitcoin sale",
            "link": "https://example.com/announcement",
            "pubDate": "2026-07-06T12:00:00Z"
          }],
          "timestampEvidence": {"url": "https://example.com/evidence", "note": "Published at noon UTC."}
        }"""
    )

    with pytest.raises(ValueError, match="window must match"):
        live.run_live_event(
            "2026-07-06T11:00:00Z",
            "2026-07-06T14:00:00Z",
            news_file,
            live.PUBLIC_NEWS_API_URL,
            "https://llm.example/v1",
            "key",
            "postgresql://db",
            "embedding",
            "model",
            "judge",
        )


def test_live_analysis_combines_derivatives_and_news_and_is_cached(monkeypatch):
    article = {
        "id": "abc",
        "title": "Bitcoin selloff follows policy shock",
        "description": "A policy announcement triggered broad risk selling.",
        "link": "https://example.com/article",
        "date_pub": datetime.now(tz=timezone.utc).isoformat(),
        "source": "Example",
        "vector_score": 0.9,
        "vector_rank": 1,
        "text_rank": 1,
        "rrf_score": 2 / 61,
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

    class Store:
        claimed_events = []
        completed = []

        def claim(self, event):
            if self.claimed_events:
                return False
            self.claimed_events.append(event)
            return True

        def get(self, _reference):
            return None

        def complete(self, reference, analysis):
            self.completed.append((reference, analysis))

        def failed(self, _reference, _error):
            raise AssertionError("successful analysis must not fail")

    class Client:
        calls = 0
        system_prompts = []
        user_prompts = []

        def classify(self, prompt: str, reference: str, system_prompt: str) -> ClassificationResult:
            self.calls += 1
            self.user_prompts.append(prompt)
            self.system_prompts.append(system_prompt)
            if "derivatives only" in prompt:
                classification, reasons, refs = "unexplained", ["Market activity stayed normal."], []
            else:
                classification = "explained_news"
                reasons = ["A pre-onset policy shock provides an event-specific explanation."]
                refs = ["news_abc"]
            return ClassificationResult.from_dict(
                {
                    "event_reference": reference,
                    "classification": classification,
                    "confidence": 0.9,
                    "synthesis": {"reasons": reasons, "supporting_refs": refs},
                    "rationale": "The supplied article reports a policy shock before onset.",
                },
                reference,
            )

    ragas_calls = []
    client, store = Client(), Store()
    service = live.LiveAnalysisService(
        "http://127.0.0.1:3000/api/news",
        "https://llm.example/v1",
        "key",
        client=client,
        store=store,
        judge_model="judge",
        faithfulness_scorer=lambda question, response, contexts: ragas_calls.append(
            (question, response, contexts)
        )
        or 0.87,
    )

    first = service.analyse(_payload())
    second = service.analyse(_payload())

    assert first["classification"] == "explained_news"
    assert first["verdicts"]["derivatives_only"]["classification"] == "unexplained"
    assert first["verdicts"]["news_only"]["classification"] == "explained_news"
    assert first["articles"][0]["supporting"] is True
    assert first["retrieval"]["ranking"] == "hybrid_rrf"
    assert first["retrieval"]["rrf_k"] == 60
    assert first["derivatives"]["funding_rate_current"] == pytest.approx(0.0001)
    assert first["ragas"]["score"] == pytest.approx(0.87)
    assert first["ragas"]["judge_model"] == "judge"
    assert first["rationale"] == "The supplied article reports a policy shock before onset."
    assert len(ragas_calls) == 1
    assert "news_abc" in ragas_calls[0][2][1]
    assert first["cached"] is False
    assert second["cached"] is True
    assert client.calls == 3
    assert len(store.claimed_events) == 1
    assert store.completed[0][0] == first["event_reference"]
    assert "funding_rate_current  : 0.0100%" in client.user_prompts[0]
    assert "Direction (derived): crash" in client.user_prompts[0]
    assert "Peak Z-score (signed):" in client.user_prompts[0]
    assert "untrusted data" in client.system_prompts[1]


def test_existing_pending_episode_is_not_retried_after_restart():
    reference = live.price_event(_payload())["event_reference"]

    class Store:
        def claim(self, _event):
            return False

        def get(self, event_reference):
            assert event_reference == reference
            return {"status": "pending", "analysis": None, "error": None}

    class Client:
        def classify(self, *_args):
            raise AssertionError("pending episode must not call LLM again")

    service = live.LiveAnalysisService(
        live.PUBLIC_NEWS_API_URL,
        "https://llm.example/v1",
        "key",
        client=Client(),
        store=Store(),
    )

    assert service.claim(_payload()) is None
    with pytest.raises(RuntimeError, match="already pending"):
        service.analyse(_payload())


def test_store_marks_interrupted_pending_episodes_failed(monkeypatch):
    executed = []

    class Cursor:
        rowcount = 2

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, query, params):
            executed.append((query, params))

    class Connection:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(live.psycopg2, "connect", lambda _url, **_kwargs: connection)

    count = live.LiveEpisodeStore("postgresql://db").fail_pending("analysis interrupted by backend restart")

    assert count == 2
    assert "WHERE status = 'pending'" in executed[0][0]
    assert executed[0][1] == ("analysis interrupted by backend restart",)
    assert connection.closed is True


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
