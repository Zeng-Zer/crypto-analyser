# Crypto Analyzer (Milestone 1)

Historical batch pipeline that validates whether derivatives market structure (funding rate, open interest) classifies crypto price crashes better than lagging news feeds. LUNA crash (May 7-11, 2022) is the validation window.

## Language

### Detection

**Anomaly**:
A contiguous run of consecutive 5-min OHLCV bars whose rolling z-score on raw close price exceeds |Z|>threshold, with up to 2 non-flagged bars tolerated inside a run. One anomaly = one classifiable market moment.
_Avoid_: per-bar flag, single alert, Z-score reading

**Episode**:
Synonym for *Anomaly*. The unit that flows through derivatives fetch → LLM classification → report. Never a single bar.
_Avoid_: alert, event cluster

**Episode onset**:
The first flagged bar of an episode. The timestamp downstream tasks (Task 15 derivatives fetch, Task 18 classifier) key on.
_Avoid_: trigger time, anomaly start, detection time (imply a single instant)

**Severity**:
Band of the episode's peak |Z|: low (>=2.5), medium (>=3.0), high (>=4.0), extreme (>=5.0). Computed by Task 14 (z-score engine) and stored on each episode; downstream tasks read it verbatim — never LLM-emitted. Observed LUNA peak |Z| is 5.07 (ep0, the crash onset), so the extreme band IS reached (1 of 7 LUNA episodes); the remaining 6 are medium (3.04–3.98).
_Avoid_: priority, confidence

### Classification outcome

The four verdicts a classifier (LLM, Task 17/18) can return for an episode. The
LLM applies the "derivatives explain" rule as a rubric in the system prompt, not
as a deterministic default — see ADR-0003. `severity` is *not* in this list
because it is derived (see "Detection" above).

**Explained by derivatives**:
Funding rate magnitude or open-interest move breaches the rubric thresholds
(`funding_rate_mag >= 0.0005` OR `|oi_change_4h| >= 0.10`). The derivatives market
structure shows something unusual that coincides with the price anomaly.
_Avoid_: funded, attributable, market-driven

**Explained by news**:
News context (retrieved via RAG, Run B only) provides a credible explanation for
the price move that derivatives data did not. Reachable only when the LLM has
news text in scope; never in Run A.
_Avoid_: headline-driven, news-caused, reported

**Unexplained**:
Derivatives context shows nothing unusual AND no credible news explanation is
available. The highest-priority signal and the validation of the project
hypothesis — such moves often precede news by 30min-24h.
_Avoid_: orphan, mystery, unattributed

**Insufficient data**:
One or more derivatives feature values are null (e.g. funding snapshot missing
before the episode onset, or OI gap in the lookup window). The classifier
cannot responsibly pick another verdict; Ragas should not be run on these rows.
_Avoid_: unknown, unclear, inconclusive