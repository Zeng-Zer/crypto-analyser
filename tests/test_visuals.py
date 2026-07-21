from __future__ import annotations

import http.server
import json
import re
import threading
from functools import partial
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from scripts.build_visual_data import _script_json, _web_url

ROOT = Path(__file__).resolve().parents[1]


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
    expect(page.locator("#episode-title")).to_have_text("Episode 04")
    yield page
    page.close()
    assert not errors, f"Browser errors: {errors}"


def test_analysis_starts_with_first_episode(browser: Browser, workbench_url: str):
    page = browser.new_page()
    page.goto(f"{workbench_url}/index.html")

    expect(page.locator("#episode-title")).to_have_text("Episode 01")
    expect(page.locator("#episode-position")).to_have_text("1 of 8")
    expect(page.get_by_role("button", name="Previous")).to_be_disabled()
    page.close()


def test_rag_changed_episode_can_be_opened_directly(page: Page):
    expect(page.get_by_text("Replay", exact=True)).to_be_visible()
    expect(page.locator("header button")).to_have_count(0)
    expect(page.locator("#episode-position")).to_have_text("4 of 8")
    expect(page.locator("#trigger-badge")).to_have_text("Price Z -3.52")
    expect(page.locator("#verdict")).to_have_text("Explained by news")


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
    expect(summary.locator("span")).to_have_text("Nearest article was 1.7 h before onset.")
    expect(summary.locator("small")).to_have_text("RRF combines semantic and keyword ranking")
    expect(summary.locator("small")).to_have_css("font-size", "12px")
    articles = page.locator("#news-list .news-item")
    expect(articles).to_have_count(5)
    expect(articles.first.locator(".news-meta")).to_contain_text(
        "Relevance 1 of 5 · RRF 0.0325 · 6 h before onset"
    )
    expect(articles.nth(3).locator(".news-meta")).to_contain_text(
        "Relevance 4 of 5 · RRF 0.0317 · 1.7 h before onset"
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
    expect(page.locator(".news-title").first).to_have_css("font-size", "16px")
    expect(page.locator(".reason-title")).to_have_css("font-size", "12px")
    expect(page.locator("#reason-list li").first).to_have_css("font-size", "16px")
    expect(page.locator(".explanation-cell h3").first).to_have_css("font-size", "20px")
    expect(page.locator("#check-detail")).to_have_css("font-size", "14px")
    expect(page.locator(".check-row span").first).to_have_css("font-size", "14px")
    expect(page.locator(".faithfulness .label")).to_have_css("font-size", "12px")
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
    expect(page.locator("#episode-title")).to_have_text("Episode 03")
    expect(page.locator("#episode-position")).to_have_text("3 of 8")

    for _ in range(5):
        next_episode.click()
    expect(page.locator("#episode-title")).to_have_text("Episode 08")
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
        "Price around selected signal detection time, with episode duration highlighted."
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
        "Market activity stayed within its limits; the classifier selected pre-onset news."
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
    expect(page.locator("#episode-title")).to_have_text("Episode 03")
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
    expect(page.locator("#episode-title")).to_have_text("Episode 02")
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
