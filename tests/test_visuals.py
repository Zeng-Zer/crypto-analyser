from __future__ import annotations

import http.server
import json
import re
import threading
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from scripts.build_visual_data import _script_json, _web_url

ROOT = Path(__file__).resolve().parents[1]


def test_pages_frontend_has_backend_origin_injection_points():
    for name in ("index.html", "live.html"):
        source = (ROOT / "visuals" / name).read_text()
        assert "const API_ORIGIN='';" in source
        assert "https://backend.invalid" in source
        assert "${API_ORIGIN}/api/" in source
        assert "fetch(`/api/" not in source
    assert "EventSource(`${API_ORIGIN}/api/live-stream`)" in (ROOT / "visuals" / "live.html").read_text()


def test_news_url_filter_accepts_only_http_sources():
    assert _web_url("https://example.com/news") == "https://example.com/news"
    assert _web_url("javascript:alert(1)") is None
    assert _web_url(None) is None


def test_embedded_json_cannot_close_script_element():
    value = {"title": "</SCRIPT><script>alert(1)</script>"}
    serialized = _script_json(value)

    assert "<" not in serialized
    assert json.loads(serialized) == value


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def workbench_url():
    handler = partial(_QuietHandler, directory=ROOT / "visuals")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:
            pytest.fail(f"Chromium unavailable; run `uv run playwright install chromium`: {error}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser, workbench_url: str):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Scenario tests deep-link Episode 04; bare-URL default is verified separately below.
    page.goto(f"{workbench_url}/index.html?onset=1652136300000")
    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#replay-back")).to_be_hidden()
    yield page
    page.close()
    assert not errors, f"Browser errors: {errors}"


def test_analysis_starts_with_first_episode(browser: Browser, workbench_url: str):
    page = browser.new_page()
    page.goto(f"{workbench_url}/index.html")

    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#live-banner")).to_be_visible()
    expect(page.locator("#live-banner")).to_contain_text("Live BTCUSDT detection")
    expect(page.locator("#live-banner")).to_have_attribute("href", "live.html")
    expect(page.locator("#episode-position")).to_have_text("1 of 8")
    expect(page.get_by_role("button", name="Previous")).to_be_disabled()
    page.close()


def test_historical_query_does_not_enable_live_api(browser: Browser, workbench_url: str):
    page = browser.new_page()
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(f"{workbench_url}/index.html?onset=1652136300000")

    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    assert not [url for url in requests if "/api/live-history/" in url]
    page.close()


def test_live_workbench_is_read_only_backend_stream_viewer(browser: Browser, workbench_url: str):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    requests: list[str] = []
    saved = False
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.add_init_script(
        """
        window.__liveEvents = [];
        class ViewerEventSource {
          constructor(url) { this.url = url; this.listeners = {}; window.__liveEvents.push(this); }
          addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
          emit(name, event) { (this.listeners[name] || []).forEach(listener => listener(event)); }
          close() {}
        }
        window.EventSource = ViewerEventSource;
        window.WebSocket = class { constructor() { throw new Error('viewer must not open WebSocket'); } };
        window.__pushLiveState = state => window.__liveEvents[0].emit('message', {data: JSON.stringify(state)});
        window.__pushLiveError = () => window.__liveEvents[0].emit('error', {});
        """
    )

    start = 1_699_999_800_000
    bars = [
        {"ts": start + index * 300_000, "close": 40_000 + index, "closeTime": start + (index + 1) * 300_000 - 1}
        for index in range(300)
    ]
    news = {
        "articles": [
            {
                "id": f"latest-{index}",
                "title": f"Latest Bitcoin headline {index}",
                "description": "Current market coverage.",
                "link": f"https://example.com/latest-{index}",
                "date_pub": "2023-11-16T02:00:00+00:00",
                "source": "Example",
            }
            for index in range(1, 13)
        ],
        "retrieval": {"url": "http://127.0.0.1:3000/api/news", "candidate_count": 12},
        "cached": False,
    }
    activity = {
        "funding_rate_current": 0.0001,
        "funding_rate_avg_4h": 0.0001,
        "oi_current": 100_000,
        "oi_change_4h": 0.01,
        "funding_breach": False,
        "oi_breach": False,
        "fear_greed_value": 25,
        "fear_greed_classification": "Extreme Fear",
        "fear_greed_timestamp": 1_700_035_200_000,
        "fear_greed_status": "current",
        "source": {"url": "https://fapi.binance.com"},
        "cached": False,
    }

    def state(current_bars: list[dict], detector: dict, loading: bool = False) -> dict:
        return {
            "connected": True,
            "ready": True,
            "status": "Streaming",
            "error": "",
            "bars": current_bars,
            "detector": detector,
            "news": news,
            "news_error": "",
            "activity": activity,
            "activity_error": "",
            "analysis": {"loading": loading, "error": ""},
            "revision": len(current_bars),
        }

    def history_days(route):
        verdict = route.request.url.split("verdict=")[-1].split("&")[0]
        counts = {"explained": 1, "unexplained": 1, "all": 3}
        days = [{"day": "2023-11-16", "episode_count": counts[verdict]}] if saved else []
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"days": days}))

    def history_episodes(route):
        price_bars = [
            {"ts": ts, "close": close, "closeTime": ts + 299_999}
            for ts, close in (
                (next_open - 900_000, 8_000),
                (next_open - 600_000, 8_200),
                (next_open - 300_000, 8_500),
                (next_open, 10_000),
                (next_open + 300_000, 9_900),
                (next_open + 600_000, 9_500),
                (next_open + 900_000, 9_000),
            )
        ]
        episodes = [
            {
                "event_reference": f"BTCUSDT_{next_open}",
                "viewer_day": "2023-11-16",
                "onset_ts": next_open,
                "detected_ts": next_open + 600_000,
                "severity": "extreme",
                "status": "complete",
                "markets": {"price": {"baseline_close": 8_000, "close_onset": 10_000, "peak_z": 5.12}},
                "bars": price_bars,
                "analysis": {"classification": "explained_news"},
                "error": None,
            },
            {
                "event_reference": f"BTCUSDT_{next_open + 300_000}",
                "viewer_day": "2023-11-16",
                "onset_ts": next_open + 300_000,
                "detected_ts": next_open + 900_000,
                "severity": "high",
                "status": "complete",
                "markets": {"price": {"baseline_close": 10_000, "close_onset": 9_500, "peak_z": -4.25}},
                "bars": price_bars,
                "analysis": {"classification": "unexplained"},
                "error": None,
            },
            {
                "event_reference": f"BTCUSDT_{next_open + 600_000}",
                "viewer_day": "2023-11-16",
                "onset_ts": next_open + 600_000,
                "detected_ts": next_open + 1_200_000,
                "severity": "high",
                "status": "failed",
                "markets": {"price": {"baseline_close": 9_500, "close_onset": 9_000, "peak_z": -3.75}},
                "bars": price_bars,
                "analysis": None,
                "error": "upstream timeout",
            },
        ]
        verdict = route.request.url.split("verdict=")[-1].split("&")[0]
        if verdict == "explained":
            episodes = [episodes[0]]
        elif verdict == "unexplained":
            episodes = [episodes[1]]
        if not re.search(r"[?&]day=", route.request.url):
            episodes.reverse()
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"episodes": episodes}))

    page.route("**/api/live-history/days?**", history_days)
    page.route("**/api/live-history/episodes?**", history_episodes)
    page.route(
        "**/api/live-stream-status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"limited": True, "active": 6, "limit": 6}),
        ),
    )
    page.goto(f"{workbench_url}/live.html")
    assert page.evaluate("__liveEvents[0].url") == "/api/live-stream"

    clear = {
        "kind": "clear",
        "label": "No anomaly",
        "reading": {"close": bars[-1]["close"], "z": 1.2, "drawdown": 0, "change": 0, "triggers": []},
        "onsetTs": None,
    }
    page.evaluate("__pushLiveState", state(bars, clear))
    expect(page.locator("#runtime-state")).to_have_text("Live")
    page.evaluate("__pushLiveError()")
    expect(page.locator("#stream-toast")).to_be_visible()
    expect(page.locator("#stream-toast")).to_contain_text("Too many live connections")
    expect(page.locator("#reconnect")).to_have_count(0)
    expect(page.locator("#price-state")).to_have_text("No anomaly")
    expect(page.locator("#feed-status")).to_have_text("Streaming · 300 bars")
    expect(page.locator("#market-chart text").filter(has_text="$")) .to_have_count(5)
    expect(page.locator("#activity-state")).to_have_text("Normal")
    expect(page.locator("#activity-metrics")).to_contain_text("0.0100%")
    expect(page.locator("#activity-metrics")).to_contain_text("+1.00%")
    expect(page.locator("#activity-metrics")).to_contain_text("25 · Extreme Fear")
    expect(page.locator("#activity-metrics a")).to_have_text("Alternative.me ↗")
    activity["fear_greed_status"] = "stale"
    page.evaluate("__pushLiveState", state(bars, clear))
    expect(page.locator("#activity-error")).to_have_text("Fear & Greed refresh failed; showing cached daily value.")
    expect(page.locator("#activity-metrics")).to_contain_text("Stale daily value")
    activity["fear_greed_status"] = "current"
    page.evaluate("__pushLiveState", state(bars, clear))
    expect(page.locator("#activity-error")).to_be_empty()
    expect(page.locator("#ambient-status")).to_have_text("12 headlines · 90s")
    expect(page.locator("#ambient-list .ambient-item")).to_have_count(5)
    expect(page.locator("#news-position")).to_have_text("1 of 3")
    page.locator("#news-next").click()
    expect(page.locator("#ambient-list")).to_contain_text("Latest Bitcoin headline 10")
    expect(page.locator("#history-verdict")).to_have_value("all")
    expect(page.locator("#history-status")).to_have_text("No saved anomaly")
    expect(page.locator("#featured-explained-time")).to_have_text("No explained anomaly saved")
    page.evaluate(
        """() => {
          document.querySelector('#history-verdict').value = 'explained';
          dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
        }"""
    )
    expect(page.locator("#history-verdict")).to_have_value("all")

    next_open = start + 300 * 300_000
    potential_bars = [*bars, {"ts": next_open, "close": 10_000, "closeTime": next_open + 299_999}]
    potential = {
        "kind": "potential",
        "label": "Potential signal · needs second flagged bar",
        "reading": {"close": 10_000, "z": -12, "drawdown": -0.75, "change": -0.75, "triggers": ["Z-score"]},
        "onsetTs": next_open,
    }
    page.evaluate("__pushLiveState", state(potential_bars, potential))
    expect(page.locator("#price-state")).to_contain_text("Potential signal")

    active_bars = [
        *potential_bars,
        {"ts": next_open + 300_000, "close": 9_000, "closeTime": next_open + 599_999},
    ]
    active = {
        "kind": "active",
        "label": "Episode active",
        "reading": {"close": 9_000, "z": -10, "drawdown": -0.78, "change": -0.78, "triggers": ["Z-score"]},
        "onsetTs": next_open,
    }
    page.evaluate("__pushLiveState", state(active_bars, active, loading=True))
    expect(page.locator("#price-state")).to_have_text("Episode active")
    expect(page.locator("#history-status")).to_have_text("Analysing episode")
    expect(page.locator("#market-chart .episode-band")).to_have_count(1)
    expect(page.locator("#market-chart .episode-start-marker")).to_have_count(1)
    expect(page.locator("#market-chart .episode-start-label")).to_have_text("EPISODE START")

    saved = True
    page.evaluate("__pushLiveState", state(active_bars, active))
    expect(page.locator("#history-status")).to_have_text("3 saved")
    expect(page.locator("#history-day")).to_have_value("")
    summaries = page.locator("#history-list .history-card")
    expect(summaries).to_have_count(3)
    expect(page.locator("#history-list .history-divider")).to_have_count(1)
    expect(page.locator("#history-list .history-divider")).to_have_text("16 Nov 2023")
    assert page.evaluate("historyDayLabel(localDay(Date.now()))") == "Today"
    assert page.evaluate("historyDayLabel(adjacentDay(localDay(Date.now()), -1))") == "Yesterday"
    explained_summary = summaries.filter(has_text="Explained by news")
    expect(explained_summary).to_contain_text("$10,000.00")
    expect(explained_summary).to_contain_text("+25.00%")
    expect(explained_summary).to_contain_text("extreme")
    expect(explained_summary).to_contain_text("Z +5.12")
    expect(page.locator("#featured-explained-time")).to_contain_text("at")
    expect(page.locator("#featured-explained .cta-arrow")).to_have_text("→")
    expect(page.locator("#featured-explained")).not_to_have_class(re.compile("unavailable"))
    expect(page.locator("#featured-explained")).to_have_attribute(
        "href", re.compile(rf"index\.html\?source=live.*event=BTCUSDT_{next_open}")
    )
    page.locator("#featured-explained").hover()
    expect(page.locator("#featured-explained")).to_have_css("background-color", "rgb(163, 61, 45)")
    polling = state(active_bars, active)
    polling["status"] = "Polling"
    page.evaluate("__pushLiveState", polling)
    expect(page.locator("#runtime-state")).to_have_text("Live")
    expect(page.locator("#feed-status")).to_have_text("Polling · 302 bars")
    expect(explained_summary).not_to_contain_text(re.compile("onset", re.IGNORECASE))
    assert "onset" not in explained_summary.get_attribute("aria-label").lower()
    expect(explained_summary).not_to_contain_text("closed bars")
    expect(explained_summary.locator(".history-mini-line")).to_have_count(1)
    expect(explained_summary.locator(".history-mini-band")).to_have_count(1)
    expect(explained_summary.locator(".history-mini-label")).to_have_text("SIGNAL DETECTED")
    expect(explained_summary.locator(".history-mini-dot")).to_have_count(1)
    assert explained_summary.locator(".history-mini-chart").evaluate(
        """chart => {
          const path = chart.querySelector('.history-mini-line');
          const marker = chart.querySelector('.history-mini-dot');
          const endpoint = path.getPointAtLength(path.getTotalLength());
          return Math.hypot(endpoint.x - marker.cx.baseVal.value, endpoint.y - marker.cy.baseVal.value) < 0.01;
        }"""
    )
    assert explained_summary.locator(".history-card-verdict").evaluate(
        "element => parseFloat(getComputedStyle(element).fontSize) >= 18"
    )
    assert explained_summary.locator(".history-action").evaluate(
        "element => getComputedStyle(element).whiteSpace === 'nowrap' && element.scrollWidth <= element.clientWidth"
    )
    assert explained_summary.bounding_box()["height"] >= 130
    expect(explained_summary).to_have_attribute(
        "href", re.compile(rf"index\.html\?source=live.*event=BTCUSDT_{next_open}")
    )
    assert any("/api/live-history/episodes?" in url and "day=" not in url for url in requests)

    page.locator("#history-day").select_option("2023-11-16")
    expect(page.locator("#history-day")).to_have_value("2023-11-16")
    expect(summaries).to_have_count(3)
    expect(page.locator("#history-list .history-divider")).to_have_count(0)

    page.locator("#history-verdict").select_option("unexplained")
    expect(page.locator("#history-status")).to_have_text("1 unexplained")
    expect(summaries).to_have_count(1)
    expect(summaries.nth(0)).to_contain_text("Market normal · no causal news")

    page.locator("#history-verdict").select_option("all")
    expect(page.locator("#history-status")).to_have_text("3 saved")
    expect(page.locator("#history-day")).to_have_value("")
    expect(summaries).to_have_count(3)
    expect(summaries.nth(0)).to_contain_text("$9,000.00")
    expect(summaries.nth(0)).to_contain_text("high")
    expect(summaries.nth(0)).to_contain_text("Analysis failed")
    summaries.nth(0).click()
    expect(page.locator("#replay-back")).to_be_visible()
    page.locator("#replay-back").click()
    expect(page).to_have_url(re.compile(r"/live\.html"))
    expect(page.locator("#history-verdict")).to_have_value("all")

    forbidden = ("binance.com", "/api/live-analysis", "/api/live-news", "/api/live-derivatives")
    assert not [url for url in requests if any(value in url for value in forbidden)]
    script = (ROOT / "visuals" / "live.html").read_text()
    assert "WebSocket" not in script
    assert "/api/live-analysis" not in script
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    featured_box = page.locator("#featured-explained").bounding_box()
    assert featured_box is not None
    assert 44 <= featured_box["height"] <= 80

    page.close()
    assert not errors, f"Browser errors: {errors}"

def test_live_history_replays_complete_and_failed_episodes(browser: Browser, workbench_url: str):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    start = 1_699_999_800_000
    bars = [
        {"ts": start + index * 300_000, "close": 40_000 + index, "closeTime": start + (index + 1) * 300_000 - 1}
        for index in range(300)
    ]
    onset = bars[-2]["ts"]
    snapshot = {
        "event_reference": f"BTCUSDT_{onset}",
        "symbol": "BTCUSDT",
        "onset_ts": onset,
        "detected_ts": onset + 600_000,
        "severity": "high",
        "triggers": ["price_zscore"],
        "markets": {
            "price": {
                "onset_ts": onset,
                "close_onset": bars[-2]["close"],
                "peak_z": -4.25,
                "duration_bars": 2,
                "onset_triggers": ["price_zscore"],
            }
        },
        "bars": bars,
    }
    analysis = {
        "classification": "explained_news",
        "derivatives": {
            "funding_rate_current": 0.0001,
            "oi_change_4h": 0.01,
            "fear_greed_value": 25,
            "fear_greed_classification": "Extreme Fear",
            "fear_greed_timestamp": onset - 3_600_000,
        },
        "retrieval": {"candidate_count": 6, "ranking": "hybrid_rrf", "rrf_k": 60},
        "articles": [
            {
                "title": "Bitcoin policy shock",
                "link": "https://example.com/news",
                "date_pub": datetime.fromtimestamp((onset + 300_000) / 1000, tz=timezone.utc).isoformat(),
                "rrf_score": 0.0328,
                "supporting": True,
            }
        ],
        "synthesis": {"reasons": ["Policy news after onset preceded detection."]},
        "verdicts": {
            "derivatives_only": {
                "classification": "unexplained",
                "synthesis": {"reasons": ["Market activity stayed normal."], "supporting_refs": []},
            },
            "news_only": {
                "classification": "explained_news",
                "synthesis": {"reasons": ["Policy news explains the move."], "supporting_refs": ["news_abc"]},
            },
            "derivatives_rag": {
                "classification": "explained_news",
                "synthesis": {"reasons": ["Policy news explains the move."], "supporting_refs": ["news_abc"]},
            },
        },
        "ragas": {"score": 0.97},
    }
    episodes = [
        {**snapshot, "status": "complete", "analysis": analysis, "error": None},
        {
            **snapshot,
            "event_reference": f"BTCUSDT_{onset + 300_000}",
            "onset_ts": onset + 300_000,
            "status": "failed",
            "analysis": None,
            "error": "live RAG/LLM failed: upstream timeout",
        },
        {
            **snapshot,
            "event_reference": f"BTCUSDT_{onset + 600_000}",
            "onset_ts": onset + 600_000,
            "status": "pending",
            "analysis": None,
            "error": None,
        },
        {
            **snapshot,
            "event_reference": f"BTCUSDT_{onset + 900_000}",
            "onset_ts": onset + 900_000,
            "status": "complete",
            "analysis": {**analysis, "ragas": {"score": None, "error": "judge unavailable"}},
            "error": None,
        },
    ]
    page.route(
        "**/api/live-history/episodes?**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"episodes": episodes})
        ),
    )

    page.goto(f"{workbench_url}/index.html?source=live&day=2023-11-16&timezone=Europe%2FParis")

    expect(page.locator("#episode-title")).to_have_text("BTCUSDT")
    expect(page.locator("#live-banner")).to_be_hidden()
    expect(page.locator("#replay-back")).to_be_visible()
    expect(page.locator("#replay-back")).to_have_attribute("href", "live.html")
    expect(page.locator("#episode-position")).to_have_text("1 of 4")
    expect(page.locator("#episode-status")).to_have_text("Complete")
    expect(page.locator("#trigger-badge")).to_be_hidden()
    expect(page.locator("#detected")).to_be_visible()
    expect(page.locator("#severity")).to_have_text("high · Z -4.25")
    assert page.locator("#onset").inner_text() != page.locator("#detected").inner_text()
    expect(page.locator(".verdict")).to_have_text("Explained by news")
    expect(page.locator("#explanation-check")).to_be_visible()
    expect(page.locator("#context-summary")).to_contain_text("at episode onset")
    expect(page.locator(".signal").filter(has_text="Fear & Greed")).to_contain_text("25 · Extreme Fear")
    expect(page.locator("#context-details")).to_contain_text("Fear & Greed observed")
    expect(page.locator("#rag-summary")).to_contain_text("Nearest article was 5 min before detection.")
    expect(page.locator("#rag-summary")).to_contain_text("RRF combines semantic and keyword ranking")
    expect(page.locator("#news-list .news-meta")).to_have_text(
        "Relevance 1 of 1 · RRF 0.0328 · 5 min before detection"
    )
    expect(page.locator("#news-list")).not_to_contain_text("Published")
    expect(page.locator("#news-list")).to_contain_text("Bitcoin policy shock")
    expect(page.locator("#reason-list")).to_contain_text("Policy news explains the move")
    expect(page.locator("#check-answer")).to_have_text("Yes — news changed the result.")
    expect(page.locator("#faithfulness-score")).to_have_text("97%")
    expect(page.locator("#price-chart .episode-band")).to_have_count(1)
    expect(page.locator("#price-chart .signal-line")).to_have_count(1)
    expect(page.locator("#price-chart .signal-label")).to_have_text("SIGNAL DETECTED")
    expect(page.locator("#price-chart text", has_text=re.compile(r"^(ONSET|DETECTED)$"))).to_have_count(0)
    head = page.locator(".anomaly-head").bounding_box()
    stats = page.locator("#anomaly-stats").bounding_box()
    chart = page.locator(".chart-wrap").bounding_box()
    assert head["y"] - (stats["y"] + stats["height"]) >= 11
    assert abs(chart["y"] - (head["y"] + head["height"])) < 1
    assert page.locator("#price-chart").evaluate(
        """chart => {
          const path = chart.querySelector('.price-line');
          const marker = chart.querySelector('.signal-marker');
          const endpoint = path.getPointAtLength(path.getTotalLength());
          return Math.hypot(endpoint.x - marker.cx.baseVal.value, endpoint.y - marker.cy.baseVal.value) < 0.01;
        }"""
    )
    assert page.locator("#price-chart .price-axis-label").evaluate_all(
        "labels => labels.every(label => label.getBBox().x >= 0)"
    )
    page.get_by_role("button", name="Next").click()
    expect(page.locator("#episode-title")).to_have_text("BTCUSDT")
    expect(page.locator("#episode-status")).to_have_text("Failed")
    expect(page.locator("#reason-list")).to_contain_text("upstream timeout")
    expect(page.locator("#explanation-check")).to_be_hidden()
    page.get_by_role("button", name="Next").click()
    expect(page.locator("#episode-status")).to_have_text("Pending")
    expect(page.locator(".verdict")).to_have_text("Analysis pending")
    expect(page.locator("#reason-list")).to_contain_text("Analysis is queued")
    page.get_by_role("button", name="Next").click()
    expect(page.locator("#episode-status")).to_have_text("Complete")
    expect(page.locator("#explanation-check")).to_be_visible()
    expect(page.locator("#faithfulness-score")).to_have_text("Unavailable")
    expect(page.locator("#faithfulness-meaning")).to_have_text("judge unavailable")
    page.goto(f"{workbench_url}/index.html?source=live&day=2023-11-16&timezone=Invalid%2FZone")
    expect(page.locator("#episode-title")).to_have_text("BTCUSDT")
    assert page.evaluate("zone === Intl.DateTimeFormat().resolvedOptions().timeZone")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.close()
    assert not errors, f"Browser errors: {errors}"


def test_rag_changed_episode_can_be_opened_directly(page: Page):
    expect(page.get_by_text("Replay", exact=True)).to_be_visible()
    expect(page.locator("header button")).to_have_count(0)
    expect(page.locator("#episode-position")).to_have_text("4 of 8")
    expect(page.locator("#trigger-badge")).to_have_text("Price Z -3.52")
    expect(page.locator("#verdict")).to_have_text("Explained by news")
    github = page.get_by_role("link", name="View source on GitHub")
    expect(github).to_be_visible()
    expect(github).to_have_attribute("href", "https://github.com/Zeng-Zer/crypto-analyser")
    expect(github).to_have_attribute("rel", "noopener noreferrer")
    expect(github.locator("svg")).to_have_count(1)


def test_guided_story_replaces_operator_dashboard(page: Page):
    expect(page.get_by_role("heading", name="Anomaly detected")).to_be_visible()
    expect(page.get_by_role("heading", name="Market activity", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="News RAG", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="LLM analysis", exact=True)).to_be_visible()
    expect(page.locator(".story-head .step-no")).to_have_text(["02", "03", "04", "05"])
    expect(page.get_by_role("tab")).to_have_count(0)
    expect(page.get_by_label("Severity filter")).to_have_count(0)
    expect(page.get_by_role("button", name="15m")).to_have_count(0)
    expect(page.get_by_text("Continuity", exact=True)).to_have_count(0)


def test_context_is_plain_language_and_onset_safe(page: Page):
    expect(page.locator("#context-state")).to_have_text("Market activity normal")
    expect(page.locator("#context-summary")).to_contain_text("inside configured limits")
    expect(page.locator("#signal-grid")).to_contain_text("-0.0460%")
    expect(page.locator("#signal-grid")).to_contain_text("-1.2%")
    expect(page.locator("#signal-grid")).to_contain_text("Normal · limit")
    fear_greed = page.locator(".signal").filter(has_text="Fear & Greed")
    expect(fear_greed.locator("strong")).to_have_text(
        re.compile(r"^\d+ · (?:Extreme Fear|Fear|Neutral|Greed|Extreme Greed)$")
    )
    expect(fear_greed.get_by_role("link", name="Alternative.me ↗")).to_have_attribute(
        "href", "https://alternative.me/crypto/fear-and-greed-index/"
    )
    expect(fear_greed).not_to_have_class("signal supporting")

    expect(page.get_by_text("Technical details", exact=True)).to_be_visible()
    expect(page.locator("#context-details")).to_be_visible()
    expect(page.locator("#context-details")).to_contain_text("Funding observed")
    expect(page.locator("#context-details")).to_contain_text("Funding precise")
    expect(page.locator("#context-details")).to_contain_text("-0.046004%")
    expect(page.locator("#context-details")).to_contain_text("OI 4h precise")
    expect(page.locator("#context-details")).to_contain_text("-1.184047%")
    expect(page.locator("#context-details")).not_to_contain_text("Funding raw")


def test_only_breached_metric_value_is_red(page: Page):
    page.get_by_role("button", name="Previous").click()
    funding = page.locator(".signal").filter(has_text="Funding rate")
    open_interest = page.locator(".signal").filter(has_text="Open interest")

    expect(funding).to_contain_text("Normal · limit")
    expect(funding.locator("strong")).to_have_css("color", "rgb(23, 25, 22)")
    expect(open_interest).to_contain_text("24.5%")
    expect(open_interest).to_contain_text("Breach · limit")
    expect(open_interest.locator("strong")).to_have_css("color", "rgb(163, 61, 45)")
    expect(funding).not_to_have_class("signal supporting")
    expect(open_interest).to_have_class("signal supporting")
    expect(open_interest).to_have_css("box-shadow", "none")
    expect(open_interest).to_have_css("outline-color", "rgb(139, 100, 29)")
    expect(open_interest).to_have_css("outline-width", "2px")


def test_market_activity_state_uses_green_for_normal_and_red_for_unusual(page: Page):
    state = page.locator("#context-state")
    expect(state).to_have_text("Market activity normal")
    expect(state).to_have_css("background-color", "rgb(85, 107, 67)")

    for _ in range(3):
        page.get_by_role("button", name="Previous").click()
    expect(state).to_have_text("Market activity unusual")
    expect(state).to_have_css("background-color", "rgb(163, 61, 45)")


def test_orange_highlights_only_context_supporting_verdict(page: Page):
    expect(page.locator(".support-legend")).to_have_text("Orange = context supporting verdict")
    expect(page.locator(".signal.supporting")).to_have_count(0)
    supporting_news = page.locator(".news-item.supporting")
    expect(supporting_news).to_have_count(3)
    expect(supporting_news.first.locator(".news-title")).to_have_css("color", "rgb(139, 100, 29)")
    expect(supporting_news.first).to_have_css("box-shadow", "none")
    assert supporting_news.first.get_attribute("aria-label").endswith("supports verdict")


def test_rag_exposes_relevance_order_and_score(page: Page):
    summary = page.locator("#rag-summary")
    expect(summary.locator("span")).to_have_text("Nearest article was 1.7 h before detection.")
    expect(summary.locator("small")).to_have_text("RRF combines semantic and keyword ranking")
    expect(summary.locator("small")).to_have_css("font-size", "12px")
    articles = page.locator("#news-list .news-item")
    expect(articles).to_have_count(5)
    expect(articles.first.locator(".news-meta")).to_contain_text(
        "Relevance 1 of 5 · RRF 0.0325 · 6 h before detection"
    )
    expect(articles.nth(3).locator(".news-meta")).to_contain_text(
        "Relevance 4 of 5 · RRF 0.0317 · 1.7 h before detection"
    )
    expect(page.locator("#news-list")).to_contain_text("TerraUSD Stablecoin Plunges Below $0.95")
    source_links = page.locator("#news-list .news-title a")
    expect(source_links).to_have_count(5)
    expect(source_links.first).to_have_attribute("href", re.compile(r"^https://(?!cryptopanic\.com/)"))
    expect(source_links.first).to_have_attribute("target", "_blank")
    expect(source_links.first).to_have_attribute("rel", "noopener noreferrer")
    expect(source_links.first).to_have_css("text-decoration-line", "none")
    source_links.first.hover()
    expect(source_links.first).to_have_css("text-decoration-line", "underline")
    archive_links = page.locator("#news-list .news-title + .archive-row .archive-link")
    expect(archive_links).to_have_count(5)
    expect(archive_links.first).to_have_text("Archive ↗")
    expect(archive_links.first).to_have_attribute("href", re.compile(r"^https://cryptopanic\.com/news/"))
    expect(archive_links.first).to_have_css("font-size", "10px")
    expect(archive_links.first).to_have_css("text-decoration-line", "none")
    archive_links.first.hover()
    expect(archive_links.first).to_have_css("text-decoration-line", "underline")
    expect(page.locator("#news-list")).not_to_contain_text("Historical")
    expect(page.locator("#news-list")).not_to_contain_text("vector #")


def test_reader_typography_uses_shared_scale(page: Page):
    expect(page.locator("#context-state")).to_have_css("font-size", "12px")
    expect(page.locator("#context-summary")).to_have_css("font-size", "16px")
    expect(page.locator(".signal span").first).to_have_css("font-size", "12px")
    expect(page.locator(".signal strong").first).to_have_css("font-size", "16px")
    expect(page.locator(".signal small").first).to_have_css("font-size", "12px")
    expect(page.locator(".always-details h3")).to_have_css("font-size", "12px")
    expect(page.locator(".detail-row span").first).to_have_css("font-size", "14px")
    expect(page.locator("#rag-summary span")).to_have_css("font-size", "16px")
    expect(page.locator(".news-meta").first).to_have_css("font-size", "11px")
    expect(page.locator(".news-title").first).to_have_css("font-size", "16px")
    expect(page.locator(".reason-title")).to_have_css("font-size", "12px")
    expect(page.locator("#reason-list li").first).to_have_css("font-size", "16px")
    expect(page.locator(".explanation-cell h3").first).to_have_css("font-size", "20px")
    expect(page.locator("#check-detail")).to_have_css("font-size", "14px")
    expect(page.locator(".check-row span").first).to_have_css("font-size", "14px")
    expect(page.locator(".faithfulness .label")).to_have_css("font-size", "12px")
    ragas_link = page.locator(".faithfulness .label a")
    expect(ragas_link).to_have_text("Ragas")
    expect(ragas_link).to_have_attribute("href", "https://www.ragas.io/")
    expect(ragas_link).to_have_attribute("rel", "noopener noreferrer")
    expect(ragas_link).to_have_css("text-decoration-line", "none")
    ragas_link.hover()
    expect(ragas_link).to_have_css("text-decoration-line", "underline")
    expect(page.locator("#faithfulness-score")).to_have_css("font-size", "36px")
    expect(page.locator("#faithfulness-meaning")).to_have_css("font-size", "14px")


def test_combined_llm_output_is_concise(page: Page):
    expect(page.locator(".classifier-note")).to_have_text(
        "Classifier interpretation of supplied context, not a causal finding."
    )
    reasons = page.locator("#reason-list li")
    expect(reasons).to_have_count(2)
    expect(reasons.first).to_contain_text("$0.95")
    expect(reasons.last).to_contain_text("market activity does not explain")
    expect(reasons.last).to_contain_text("Funding rate of -0.0460%")
    expect(reasons.last).to_contain_text("OI change of -1.18%")
    expect(reasons.last).not_to_contain_text("-0.00046004")
    expect(reasons.last).not_to_contain_text("-0.0118")
    expect(page.get_by_text("Schema validated", exact=True)).to_have_count(0)
    expect(page.get_by_text("Structured output", exact=True)).to_have_count(0)
    expect(page.get_by_text("self-confidence", exact=True)).to_have_count(0)
    expect(page.get_by_text("Raw rationale", exact=True)).to_have_count(0)


def test_previous_and_next_browse_all_episodes(page: Page):
    previous = page.get_by_role("button", name="Previous")
    position = page.locator("#episode-position")
    next_episode = page.get_by_role("button", name="Next")
    expect(position).to_have_css("border-left", "1px solid rgb(185, 181, 170)")
    expect(next_episode).to_have_css("border-left", "1px solid rgb(185, 181, 170)")

    previous.click()
    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#episode-position")).to_have_text("3 of 8")

    for _ in range(5):
        next_episode.click()
    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#episode-position")).to_have_text("8 of 8")
    expect(next_episode).to_be_disabled()
    expect(page.locator("#trigger-badge")).to_contain_text("4h drawdown")


def test_timestamps_use_browser_timezone(browser: Browser, workbench_url: str):
    context = browser.new_context(timezone_id="America/Los_Angeles")
    page = context.new_page()
    page.goto(f"{workbench_url}/index.html?onset=1652136300000")

    expect(page.locator("#onset")).to_contain_text("09 May 2022, 15:45")
    expect(page.locator("#onset")).to_contain_text("America/Los_Angeles")

    context.close()


def test_chart_is_tall_with_modest_bottom_spacing(page: Page):
    chart = page.locator(".chart-wrap").bounding_box()
    explanation = page.locator(".explanation-panel").bounding_box()
    main = page.locator("main").bounding_box()

    assert chart["height"] >= 340
    bottom_spacing = main["y"] + main["height"] - (explanation["y"] + explanation["height"])
    assert 23 <= bottom_spacing <= 25


def test_chart_hover_shows_and_hides_tooltip(page: Page):
    expect(page.locator("#price-chart text", has_text="SIGNAL DETECTED")).to_have_count(1)
    expect(page.locator("#chart-desc")).to_have_text(
        "Price around selected anomaly episode, with episode duration highlighted and signal detection marked."
    )
    chart = page.locator(".chart-hit")
    box = chart.bounding_box()
    assert box
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    tooltip = page.locator(".tooltip")
    expect(tooltip).to_have_class("tooltip visible")
    expect(tooltip).to_contain_text("$")

    page.mouse.move(0, 0)
    expect(tooltip).to_have_class("tooltip")


def test_skip_link_focuses_story(page: Page):
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Skip to episode story")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#story")).to_be_focused()


@pytest.mark.parametrize(
    ("path", "viewport"),
    [
        ("index.html", {"width": 1440, "height": 900}),
        ("index.html", {"width": 390, "height": 844}),
    ],
)
def test_layout_has_no_horizontal_overflow(
    browser: Browser, workbench_url: str, path: str, viewport: dict[str, int]
):
    page = browser.new_page(viewport=viewport)
    try:
        page.goto(f"{workbench_url}/{path}")
        expect(page.get_by_role("link", name="View source on GitHub")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:
        page.close()


def test_selected_anomaly_has_inline_explanation_check(page: Page):
    expect(page.get_by_role("link", name="Check this explanation")).to_have_count(0)
    expect(page.get_by_role("heading", name="Did news change the result?")).to_be_visible()
    expect(page.get_by_role("heading", name="Did each input support an explanation?")).to_be_visible()
    expect(page.get_by_role("heading", name="How much is backed by the inputs?")).to_be_visible()
    expect(page.locator("#check-answer")).to_have_text("Yes — news changed the result.")
    rows = page.locator("#context-results .check-row")
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("Market activity alone")
    expect(rows.nth(0)).to_contain_text("No")
    expect(rows.nth(1)).to_contain_text("News alone")
    expect(rows.nth(1)).to_contain_text("Yes")
    expect(rows.nth(2)).to_contain_text("With both")
    expect(rows.nth(2)).to_contain_text("Classifier selected news")
    expect(page.locator("#context-rule")).to_have_text(
        "Market activity stayed within its limits; the classifier selected news published before detection."
    )
    expect(page.locator("#faithfulness-score")).to_have_text("87%")
    expect(page.locator("#faithfulness-meter")).to_have_attribute("aria-valuenow", "87")
    expect(page.locator("#faithfulness-meaning")).to_have_text(
        "87% of claims were directly backed by supplied market data and news."
    )
    expect(page.locator("#faithfulness-unbacked")).to_have_text(
        "13% were not directly backed by those inputs."
    )
    expect(page.get_by_text("How calculated: Ragas splits", exact=False)).to_be_visible()
    expect(page.get_by_text("Not directly backed does not mean false.", exact=False)).to_be_visible()
    expect(page.locator("#evaluated-rationale")).to_have_count(0)
    expect(page.get_by_text("What was evaluated", exact=True)).to_have_count(0)
    expect(page.get_by_text("Analysis result", exact=True)).to_have_count(0)
    expect(page.get_by_text("Control run", exact=True)).to_have_count(0)

    page.get_by_role("button", name="Previous").click()
    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#check-answer")).to_have_text("No — result stayed the same.")
    expect(rows.nth(0)).to_contain_text("Yes")
    expect(rows.nth(1)).to_contain_text("Yes")
    expect(rows.nth(2)).to_contain_text("Classifier retained market activity")
    expect(page.locator("#context-rule")).to_have_text(
        "A funding or open-interest threshold breach made the classifier retain market activity."
    )
    expect(page.locator("#faithfulness-score")).to_have_text("57%")
    expect(page.locator("#faithfulness-meaning")).to_have_text(
        "57% of claims were directly backed by supplied market data and news."
    )
    expect(page.locator("#faithfulness-unbacked")).to_have_text(
        "43% were not directly backed by those inputs."
    )

    page.get_by_role("button", name="Previous").click()
    expect(page.locator("#episode-title")).to_have_text("LUNAUSDT")
    expect(page.locator("#faithfulness-score")).to_have_text("39%")
    expect(page.locator("#faithfulness-meaning")).to_have_text(
        "39% of claims were directly backed by supplied market data and news."
    )
    expect(page.locator("#faithfulness-unbacked")).to_have_text(
        "61% were not directly backed by those inputs."
    )
    expect(page.locator("#verdict")).to_have_text("Explained by market activity")
    reasons = page.locator("#reason-list")
    expect(reasons).to_contain_text("OI surged 11.58%")
    expect(reasons).to_contain_text("10% threshold")
    expect(reasons).to_contain_text("Funding rate of -0.0460%")
    expect(reasons).to_contain_text("0.0500% threshold")
    expect(reasons).not_to_contain_text("-0.00046")
    expect(reasons).not_to_contain_text("0.10 threshold")
    expect(reasons).not_to_contain_text("derivative")
