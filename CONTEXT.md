# Crypto Anomaly Analyser (Milestone 1)

Historical batch pipeline comparing how derivatives market structure (funding rate, open interest) and pre-onset news affect LLM classifications of crypto price anomalies. LUNA (May 7–11, 2022) is one case study, not general validation of source superiority.

## Language

### Detection

**Anomaly**:
A contiguous run of 5-min OHLCV bars where raw close price exceeds `|Z|>2.5`, price is at least 50% below its rolling 4-hour peak, or its 2-hour close-to-close return is at most −25%, with up to 6 non-flagged bars (30 minutes) tolerated inside a run. One anomaly = one classifiable market moment.
_Avoid_: per-bar flag, single alert, Z-score reading

**Episode**:
Synonym for *Anomaly*. The unit that flows through derivatives fetch → LLM classification → report. Never a single bar.
_Avoid_: alert, event cluster

**Detection trigger**:
Signal that admitted bars into an episode: `price_zscore`, `drawdown_4h`, `return_2h`, or a combination. Stored on every episode so low raw Z-scores during sustained collapses remain interpretable.
_Avoid_: cause, explanation

**Episode onset**:
The first flagged bar of an episode. Derivatives extraction, news cutoff, and classification key on this timestamp. The UI labels it “Signal detected” because the underlying decline may have begun earlier.
_Avoid_: crash start, causal onset

**Severity**:
Band of strongest normalized detection signal: low (>=1.0× threshold), medium (>=1.2×), high (>=1.6×), extreme (>=2.0×). Computed by detection and stored on each episode; downstream components read it verbatim — never LLM-emitted.
_Avoid_: priority, confidence

### Classification outcome

The four verdicts the LLM classifier can return for an episode. The
LLM applies the "derivatives explain" rule as a rubric in the system prompt, not
as a deterministic default — see ADR-0003. `severity` is *not* in this list
because it is derived (see "Detection" above).

**Classification synthesis**:
Concise reader-facing list of verdict reasons. Each reason names decisive mechanism or values and cites supporting context.
_Avoid_: summary, key findings, rationale

**Classification rationale**:
Detailed justification for a verdict against supplied feature values and retrieved context. It supports rationale-quality checks and audit, not primary display.
_Avoid_: summary, chain of thought, analysis trace

**Supporting context**:
Supplied derivatives metric or retrieved news article that affirmatively supports the classification synthesis. News rejected as tangential remains context but is not supporting context.
_Avoid_: decisive evidence, causal evidence, all context

**Explained by derivatives**:
Funding rate magnitude or open-interest move breaches the rubric thresholds
(`|funding rate| >= 0.0500%` OR `|4h open-interest change| >= 10%`). The derivatives market
structure shows something unusual that coincides with the price anomaly.
_Avoid_: funded, attributable, market-driven

**Explained by news**:
News context (retrieved via RAG, Runs B and C) provides a credible explanation
for the price move. Reachable only when the LLM has news text in scope; never
in Run A.
_Avoid_: headline-driven, news-caused, reported

**Unexplained**:
Derivatives context shows nothing unusual AND no credible pre-onset news explanation is available. This is the outcome relevant to the hypothesis that price can move before public explanation, but confirming that hypothesis requires post-onset publication timing or additional evidence not implemented here.
_Avoid_: orphan, mystery, unattributed

**Insufficient data**:
One or more derivatives feature values are null (e.g. funding snapshot missing
before the episode onset, or OI gap in the lookup window). The classifier
cannot responsibly pick another verdict; Ragas should not be run on these rows.
_Avoid_: unknown, unclear, inconclusive