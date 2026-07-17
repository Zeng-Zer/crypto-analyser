# An anomaly is one contiguous episode, not one bar

A "Z-score anomaly" in this pipeline is a **contiguous episode**: a maximal run of
consecutive 5-min OHLCV bars whose rolling z-score on raw close price exceeds
|Z|>threshold, with up to 2 non-flagged bars tolerated inside a run before it
splits. The per-bar flag is an internal primitive; the episode is the unit that
flows through derivatives extraction at `onset_ts`, LLM classification,
reporting, and the evidence ablation.

We did **not** go per-bar. On a violent crash, raw-price z-score with a 24h
rolling window flags sustained deviation: the first several "anomalies" are
consecutive bars at the same z (~-2.6), each representing the same market state.
Classifying them one at a time produces near-duplicate verdicts that inflate
Ragas rows without adding evidence about the hypothesis ("derivatives explain
unexplained moves that precede news"). Grouping into episodes makes each
classification a distinct market moment.

This stays on-spec for the z-score target itself: raw close price, per
PROJECT.md (`(x - mean) / std` on price close). The output unit is an episode
rather than a per-bar record. This ADR settles the contract on one bulk file
with an `episodes[]` array; classification reads that batch and iterates.

Hard to reverse: changing the unit back to per-bar re-breaks the
downstream contract for Tasks 15/18/19 and the ablation. Surprising without
context: the plan calls them "Z-score anomalies," which reads as per-bar
threshold crossings. Real trade-off: per-bar is simpler code and a larger,
easier-to-hit `anomaly_count > 0` for DoD evidence; episodes are honest about
counting distinct classifiable moments and shrink the LLM/Ragas workload.