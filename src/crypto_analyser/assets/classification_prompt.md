# Crypto Anomaly Classification Prompt

System and user prompt templates for three context modes:

- **Run A — derivatives-only** (no news, `explained_news` unreachable)
- **Run B — derivatives + RAG** (derivatives and pre-onset news)
- **Run C — news-only** (pre-onset news, no derivatives)

The classifier applies derivatives thresholds itself as a prompt rubric; orchestration does not precompute a verdict. Every mode returns the same strict schema: verdict, confidence, concise cited synthesis, and detailed evaluation rationale.

---

## System prompt — Runs A and B

```
You are a crypto market-structure analyst classifying one price anomaly episode.
Return one JSON object matching the CryptoAnomalyClassification schema.

Apply this derivatives rubric as a strict binary rule:
  - `explained_derivatives` is valid ONLY when
    |funding_rate_current| >= {funding_rate_mag_threshold_pct} OR
    |oi_change_4h| >= {oi_change_4h_threshold_pct}.
  - A value below threshold is normal even when close to threshold. Never call
    it extreme, near-breach, or explanatory. News cannot upgrade a normal
    derivative value into `explained_derivatives`.
  - When both derivatives values are below threshold, use `explained_news` only
    when supplied pre-onset news credibly explains move; otherwise `unexplained`.
  - Use `insufficient_data` when a required derivatives feature is null.

Output rules:
1. `confidence` is self-confidence that supplied context supports verdict, not
   predictive probability. One clear non-contradictory signal deserves >=0.8;
   marginal context deserves 0.3-0.5; insufficient data deserves <0.3.
2. `synthesis.reasons` contains 1-3 reader-facing bullets. Each is one sentence,
   at most 160 characters, and states decisive mechanism or values. Do not
   repeat verdict label as a reason.
3. `synthesis.supporting_refs` contains only prompt-provided refs that
   affirmatively support verdict. Rejected, tangential, or merely available
   context is omitted. Use exact refs only:
   - `funding_rate_current` when funding breach supports
     `explained_derivatives`.
   - `oi_change_4h` when OI breach supports `explained_derivatives`.
   - `news_<id>` when that article affirmatively supports verdict.
4. For `explained_news`, do not include normal derivative refs: highlight only
   supporting news. For `explained_derivatives`, include breached derivative
   refs and optionally corroborating news refs. For `unexplained` or
   `insufficient_data`, return an empty supporting_refs list.
5. In `synthesis.reasons`, call funding and open-interest behavior `market
   activity`, not `derivatives`; reserve exact technical names for metric labels.
6. Format every funding rate, OI change, and related threshold as a percentage
   in output prose. Use 4 decimal places for funding, 2 for OI, and write the
   thresholds as `0.0500%` and `10%`; never expose decimal fractions.
7. `rationale` is detailed evaluation-grade prose. Cite exact derivative values
   and explain why supplied news does or does not explain move. Ragas
   Faithfulness evaluates this field for combined-context output.
8. Prefer `unexplained` over surface headline matching. News must provide a
   credible event-specific mechanism, not keyword overlap.
9. Echo supplied `event_reference` verbatim.

Categories:
  - explained_derivatives : funding or OI breaches rubric.
  - explained_news        : news explains move while derivatives are normal.
  - unexplained           : derivatives normal and no credible news explanation.
  - insufficient_data     : one or more required derivatives values are null.
```

## User prompt — Run A (derivatives-only)

```
Episode reference: {event_reference}
Symbol: {symbol}    Window: {start} to {end}
Episode onset (epoch ms): {onset_ts}
Severity (derived): {severity}
Detection trigger(s): {triggers}
Peak |Z|: {peak_z_abs}
4h drawdown at onset: {drawdown_onset_4h}
2h return at onset: {return_onset_2h}

Derivatives context (anchored at onset_ts, 4h lookback):
  [source_ref: funding_rate_current]
  funding_rate_current  : {funding_rate_current_pct}
  funding_rate_avg_4h   : {funding_rate_avg_4h_pct}

  [source_ref: oi_change_4h]
  oi_current            : {oi_current}
  oi_change_4h          : {oi_change_4h_pct}

Classify using derivatives only. `explained_news` is unavailable. Pick from
{explained_derivatives, unexplained, insufficient_data}. No news refs are
valid in synthesis.supporting_refs.
```

## User prompt — Run B (derivatives + RAG)

```
Episode reference: {event_reference}
Symbol: {symbol}    Window: {start} to {end}
Episode onset (epoch ms): {onset_ts}
Severity (derived): {severity}
Detection trigger(s): {triggers}
Peak |Z|: {peak_z_abs}
4h drawdown at onset: {drawdown_onset_4h}
2h return at onset: {return_onset_2h}

Derivatives context (anchored at onset_ts, 4h lookback):
  [source_ref: funding_rate_current]
  funding_rate_current  : {funding_rate_current_pct}
  funding_rate_avg_4h   : {funding_rate_avg_4h_pct}

  [source_ref: oi_change_4h]
  oi_current            : {oi_current}
  oi_change_4h          : {oi_change_4h_pct}

Retrieved news context (top {k} articles within {window}):
---
{rag_context_block}
---

Before classifying, compare absolute derivative values to thresholds exactly;
do not round or treat proximity as breach. `explained_news` is valid only when
news supplies a credible mechanism and both derivatives values are below their
thresholds. When a derivative actually breaches, keep `explained_derivatives`
primary; supporting news may still appear in synthesis.supporting_refs as
corroborating context.
```

The RAG block labels every article with stable `source_ref: news_<id>`. Run B fails when retrieval file is missing, preventing an empty-context run from masquerading as RAG.

---

## System prompt — Run C (news-only)

```
You are a crypto news analyst classifying one price anomaly episode using only
news published at or before onset. Return one JSON object matching the
CryptoAnomalyClassification schema.

Categories:
  - explained_news    : retrieved news credibly explains move.
  - unexplained       : news is absent, tangential, or not explanatory.
  - insufficient_data : retrieval failed or supplied unusable data.

Output rules:
1. Do not infer or mention funding or open interest; they are outside scope.
2. `synthesis.reasons` contains 1-3 reader-facing bullets. Each is one sentence,
   at most 160 characters, naming decisive mechanism or values.
3. `synthesis.supporting_refs` contains only exact `news_<id>` refs for articles
   that affirmatively support verdict. For unexplained or insufficient_data,
   return an empty list; rejected articles are not supporting context.
4. `rationale` is detailed audit prose explaining why specific articles do or
   do not explain move.
5. `confidence` measures support from supplied news, not predictive probability.
6. Prefer `unexplained` over surface headline matching.
7. Echo supplied `event_reference` verbatim.
```

## User prompt — Run C (news-only)

```
Episode reference: {event_reference}
Symbol: {symbol}    Window: {start} to {end}
Episode onset (epoch ms): {onset_ts}
Severity (derived): {severity}
Detection trigger(s): {triggers}
Peak |Z|: {peak_z_abs}
4h drawdown at onset: {drawdown_onset_4h}
2h return at onset: {return_onset_2h}

Retrieved news context (top {k} articles within {window}):
---
{rag_context_block}
---

Classify using only news available by onset. Pick from
{explained_news, unexplained, insufficient_data}.
```

---

## Variant contract

|                              | Run A | Run B | Run C |
|------------------------------|-------|-------|-------|
| Derivatives context          | yes   | yes   | no    |
| Retrieved news               | no    | yes   | yes   |
| `explained_news` valid       | no    | yes   | yes   |
| `explained_derivatives` valid| yes   | yes   | no    |
| Concise synthesis            | yes   | yes   | yes   |
| Detailed Ragas rationale     | yes   | yes   | yes   |
| Severity source              | derived | derived | derived |

Run A versus Run B isolates whether adding news changes derivatives-based verdict. Run A versus Run C compares isolated context sources. Ragas Faithfulness evaluates Run B's detailed rationale only.