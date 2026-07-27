---
version: alpha
name: Crypto Anomaly Analyser
description: Scientific editorial system for historical replay, live market observation, time-safe context assembly, and offline evaluation.
colors:
  primary: '#a33d2d'
  background: '#f3efe6'
  surface: '#fbf8f1'
  surface-strong: '#ffffff'
  ink: '#171916'
  ink-muted: '#5b605a'
  rule: '#b9b5aa'
  rule-light: '#ded9ce'
  anomaly: '#a33d2d'
  anomaly-dark: '#74291e'
  derivatives: '#245d78'
  derivatives-pale: '#dce8ed'
  news: '#556b43'
  news-pale: '#e2e8da'
  warning: '#8b641d'
  on-dark: '#fffaf0'
typography:
  display:
    fontFamily: Newsreader
    fontSize: 36px
    fontWeight: 400
    lineHeight: 0.96
    letterSpacing: -0.035em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Newsreader
    fontSize: 20px
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Source Sans 3
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: 0em
  body-md:
    fontFamily: Source Sans 3
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0em
  label:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: 0.12em
  data:
    fontFamily: IBM Plex Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: -0.02em
rounded:
  none: 0px
  sm: 2px
  md: 4px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 64px
  section: 128px
components:
  page:
    backgroundColor: '{colors.background}'
    textColor: '{colors.ink}'
  context-card:
    backgroundColor: '{colors.surface}'
    textColor: '{colors.ink}'
    rounded: '{rounded.sm}'
    padding: 24px
  paper-inset:
    backgroundColor: '{colors.surface-strong}'
    textColor: '{colors.ink-muted}'
  mode-button:
    backgroundColor: '{colors.surface}'
    textColor: '{colors.ink}'
    typography: '{typography.label}'
    rounded: '{rounded.sm}'
    padding: 12px
  primary-action:
    backgroundColor: '{colors.primary}'
    textColor: '{colors.on-dark}'
    typography: '{typography.label}'
    rounded: '{rounded.sm}'
    padding: 12px
  anomaly-marker:
    backgroundColor: '{colors.anomaly}'
    textColor: '{colors.on-dark}'
  anomaly-marker-hover:
    backgroundColor: '{colors.anomaly-dark}'
    textColor: '{colors.on-dark}'
  derivatives-context:
    backgroundColor: '{colors.derivatives-pale}'
    textColor: '{colors.derivatives}'
  news-context:
    backgroundColor: '{colors.news-pale}'
    textColor: '{colors.news}'
  caution-note:
    backgroundColor: '{colors.warning}'
    textColor: '{colors.on-dark}'
  rule:
    backgroundColor: '{colors.rule}'
    textColor: '{colors.ink}'
  rule-subtle:
    backgroundColor: '{colors.rule-light}'
    textColor: '{colors.ink}'
---

## Overview

A scientific editorial showcase rather than a marketing page or crypto trading terminal. It should feel like a guided research story: archival paper, rigorous annotation, measured conclusions, and visible uncertainty. Historical replay walks through one selected episode at a time: anomaly, time-safe market activity, hybrid retrieval, structured LLM output, then a compact explanation check. Live observation is a separate focused surface rendering backend-owned closed Binance bars and deterministic detector state over SSE; confirmed episodes add time-safe Binance market activity, current-news retrieval, structured LLM output, and PostgreSQL-backed replay. Favor a clear narrative over operational density. Audience is hiring teams and data/LLM practitioners with three to ten minutes. Emotional target is credible curiosity, not market hype.

## Colors

Warm paper is the dominant field. Deep ink carries narrative. Clay red marks price anomalies and must never imply trading advice. Cobalt is reserved for market activity; moss is reserved for news context. Use pale variants only as context backgrounds. Avoid exchange-style neon green/red.

## Typography

Newsreader carries investigation headings and key findings. Source Sans 3 carries explanatory prose. IBM Plex Mono labels timestamps, thresholds, metrics, and machine-generated verdicts. Every element uses one shared scale: 12px metadata, 14px detail, 16px primary reading text, 20px section headings, 28px findings, and 36px page-level values.

## Layout

Historical replay uses one continuous page presenting one episode at a time with Previous/Next navigation. A focused anomaly chart leads into three numbered columns: market activity, pre-onset RAG retrieval, and combined structured LLM analysis. Episode 01 is the chronological default; onset query parameters support direct links to other episodes. A compact explanation check follows cards, compares three context runs, and checks combined rationale with Ragas Faithfulness. Live observation uses a separate page with one absolute BTC price chart, one price detector, current funding and open-interest readings, a paginated 24-hour news ledger, and a day-based episode history launcher. Persisted BTC episodes reuse the replay page with a live data source. On small screens, stack all steps in reading order.

## Elevation & Depth

No shadows or glass effects. Depth comes from paper tones, hairline rules, and occasional full-ink sections. Interactive focus uses a two-pixel outline. Sticky chart remains flat and structurally anchored.

## Shapes

Corners are square or two pixels. Episode markers are circles because they represent points in time, not because the interface is soft. Avoid pills except compact categorical status marks.

## Components

- **Runtime label:** Show Replay or Live as compact status; live status must reflect actual connection state.
- **Live price plate:** Backend backfills at least 24 hours of closed 5-minute BTCUSDT price bars, then appends only socket bars where Binance marks `x: true`. Keep bounded backend memory and send read-only snapshots to viewers with SSE. Plot absolute dollar price so existing points do not change when trailing window advances. Shade active episode through latest closed bar and mark its start when that point remains inside chart window.
- **Live detector state:** Backend applies existing 24-hour Z-score, 4-hour drawdown, and 2-hour return thresholds to price independent of browser sessions. Name reading as potential signal until two flagged closed bars satisfy episode minimum. Show active state without internal gap counters. Show missing warm-up explicitly.
- **Live market activity:** Refresh Binance funding rate and 4-hour open-interest change every 60 seconds without LLM calls. At confirmed episode, refetch both at or before detection and preserve null values.
- **Ambient live news:** Fetch Bitcoin headlines from preceding 24 hours through sibling `free-crypto-news`, refresh every 90 seconds, and paginate five headlines per page. Do not embed, classify, highlight as support, or imply market explanation.
- **Live combined analysis:** At confirmed price episode, backend anchors funding and OI at the first anomalous bar, filters news to the 24 hours ending when the detector confirms the episode, embedding-ranks top six, calls existing derivatives + RAG classifier once per event, then runs Ragas Faithfulness against supplied context. Persist onset and detection timestamps, pending, complete, and failed episodes, plus Ragas score or error in PostgreSQL without requiring an open browser. Keep live Ragas result audit-only; do not show it in replay.
- **Live history refill:** One-shot command applies unchanged detector to exact requested recent window plus 24-hour warm-up, then runs same combined news/RAG/LLM/Ragas pipeline for every detected BTC episode. Explicit event import may merge a documented, timestamped source corpus; reject sources published or modified after detector confirmation. Existing event references are skipped. Zero episodes is valid.
- **Live episode history:** Filter persisted episodes by result, defaulting to Explained; Unexplained and All remain available. Date defaults to All dates with matching episodes ordered newest first and grouped by horizontal viewer-local date dividers labelled Today, Yesterday, or `25 Jul 2026`; selecting one date narrows the cards and removes dividers. Show full-width episode cards with local anomaly-start time, severity, verdict, a small price chart ending when the anomaly began, and percentage price change with both prices. Keep internal `onset` terminology out of card copy. Render stored `unexplained` as reader-facing “Market normal · no causal news” without changing machine value. Each card deep-links to exact episode in the shared replay page, which switches data source without changing replay structure with Previous/Next navigation, focused episode chart, market activity, ranked news, candidate-to-ranked counts, and LLM result or failure state.
- **Episode navigator:** Previous/Next buttons browse all episodes while one episode remains the narrative focus.
- **Price plate:** Focused native SVG with close-price line, anomaly duration band, signal-detection marker, crosshair, and local-time axes. No analyst controls on the showcase view.
- **Market activity step:** Show funding rates, open-interest changes, and thresholds as percentages with plain-language normal/breach states. Technical details may add precision but still use percentages; raw fractions stay in machine artifacts.
- **RAG retrieval step:** Show every retrieved headline in relevance order with ordinal position, four-decimal reciprocal rank fusion (RRF) score, and age before signal detection. Explain that RRF combines semantic and keyword ranking; do not encode relevance with color.
- **LLM analysis step:** Show verdict plus one to three concise reason bullets from schema-validated synthesis. Do not show detailed rationale or self-confidence on Analysis.
- **Explanation check:** Follow selected anomaly through three short questions: whether news changed result, what each context returned, and how much rationale is backed by inputs. Show whether market activity alone and news alone explain move, then name combined primary outcome and state priority rule. Avoid repeated verdict labels, experimental labels, or special color accent. Show backed and not-directly-backed percentages plus formula; keep raw rationale out of UI.
- **News ledger:** Relevance position, RRF score, publication age, and headline separated by rules. Link titles to validated publisher URLs recovered from CryptoPanic archive pages, show the CryptoPanic URL as a separate fallback, and mark both as external links. Titles turn orange only when model marks article as affirmative supporting context.
- **Metric note:** State “X% of claims were directly backed by supplied market data and news” and complementary unbacked percentage. Explain backed claims ÷ all claims. State that not directly backed does not mean false and score does not verify result or cause.

## Do's and Don'ts

### Do
- Keep onset and detection timestamps plus threshold states visible.
- Make temporal safety explicit through publication age before detection.
- Call supplied material context; reserve evidence for context that supports a stated verdict.
- Pair every color encoding with text; one legend above source cards defines orange as context supporting verdict.
- State that one eight-episode LUNA case study does not prove causality or source superiority.
- Make Previous/Next, chart hover, keyboard focus, and reduced-motion modes work.
- Keep anomaly, context/RAG, LLM result, and explanation check in one continuous reading flow.
- Keep source timestamps visible. Keep detailed rationale and self-confidence in audit JSON, not reader UI.

### Don't
- Do not use a full-screen hero, dashboard side rails, filter panels, candlesticks, glowing charts, gradients, or generic crypto iconography.
- Do not present replay as live, invent connection health, or fabricate missing timestamps. Live status follows backend WebSocket and backfill events sent to viewer over SSE.
- Do not imply that live observation proves causes. Do not expose internal market-source distinctions as reader-facing complexity. Keep LLM credentials server-side.
- Do not place controlled context runs inside primary analysis cards; keep them in compact explanation check below.
- Do not expose funding rates, open-interest changes, or their thresholds as decimal fractions.
- Do not call LLM confidence predictive probability.
- Do not position Ragas metrics as model accuracy.
- Do not hide null or missing evidence.
