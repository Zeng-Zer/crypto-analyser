# An anomaly is one contiguous episode, not one bar

An anomaly in this pipeline is a **contiguous episode**: a maximal run of
5-min OHLCV bars where raw close price exceeds `|Z|>2.5`, price is at least
50% below its rolling 4-hour peak, or its 2-hour close-to-close return is at
most −25%, with up to 6 non-flagged bars (30 minutes) tolerated inside a run
before it splits. The per-bar flags are internal primitives; the
episode is the unit that flows through derivatives extraction at `onset_ts`,
LLM classification, reporting, and the controlled context comparison. Thirty minutes merges brief threshold
recoveries during one crash wave without joining the distinct multi-hour moves
observed in the LUNA window.

We did **not** go per-bar. On a violent crash, raw-price z-score with a 24h
rolling window flags sustained deviation: the first several "anomalies" are
consecutive bars at the same z (~-2.6), each representing the same market state.
Classifying them one at a time produces near-duplicate verdicts that inflate
Ragas rows without adding evidence about the hypothesis ("derivatives explain
unexplained moves that precede news"). Grouping into episodes makes each
classification a distinct market moment.

Raw-price Z-score remains the primary statistical trigger. A 4-hour drawdown
trigger complements it because rolling mean and standard deviation adapt during
a sustained collapse: LUNA's 11 May fall from roughly `$5` to `$0.50` never
crossed `|Z|>2.5`. A 2-hour return trigger captures fast material moves such as
the 29% fall on 10 May that missed both other thresholds. Episodes store
trigger and onset values so downstream
consumers can distinguish detection from causal explanation. Output remains one
bulk file with an `episodes[]` array.

Hard to reverse: changing the unit back to per-bar re-breaks the
downstream contract for Tasks 15/18/19 and the ablation. Surprising without
context: the plan calls them "Z-score anomalies," which reads as per-bar
threshold crossings. Real trade-off: per-bar is simpler code and a larger,
easier-to-hit `anomaly_count > 0` for DoD evidence; episodes are honest about
counting distinct classifiable moments and shrink the LLM/Ragas workload.