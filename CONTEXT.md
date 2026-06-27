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
Band of the episode's peak |Z|: low (>=2.5), medium (>=3.0), high (>=4.0), extreme (>=5.0). Observed LUNA peak |Z| is 4.31, so the extreme band is currently never reached.
_Avoid_: priority, confidence

### Classification outcome

**Unexplained**:
An anomaly whose derivatives context (funding + OI) shows nothing unusual — the highest-priority signal and the validation of the project hypothesis (such moves often precede news by 30min-24h).
_Avoid_: orphan, mystery, unattributed