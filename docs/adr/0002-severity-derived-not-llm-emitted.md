# Severity is derived from peak |Z|, not LLM-emitted

The `severity` field in the Task 17 classification schema is **derived from the
episode's peak |Z|**, not something the LLM is asked to judge or report. Task 14
(the z-score engine) already computes severity as a band on peak |Z| —
`low (≥2.5)`, `medium (≥3.0)`, `high (≥4.0)`, `extreme (≥5.0)` — and stores it on
each episode record in `episodes[]` (e.g. `data/anomalies/LUNAUSDT_*.json`). Downstream
tasks read it verbatim. The schema field's type is `string` with that exact enum
vocabulary (see CONTEXT.md), matching what's already in the data. The LLM is not
involved.

We did **not** ask the LLM to rate severity, and we did **not** adopt the
`critical | high | medium | low` vocabulary left over in `config/settings.yaml`'s
orphaned `llm.output_schema` block (which no code reads). Severity measures the
crash itself — how extreme the price deviation was — not a judgment about
classification quality, news relevance, or model confidence. Asking the LLM to
rate it would produce a vibes number uncorrelated with the underlying z-score,
drift run-to-run, and pollute the ablation comparison with categorical noise on
top of genuine `classification` differences.

CONTEXT.md previously carried a stale claim ("Observed LUNA peak |Z| is 4.31,
so the extreme band is currently never reached"). Corrected: the observed peak
is 5.07 (ep0, the crash onset), so one of seven LUNA episodes does hit `extreme`.
The obsolete `llm.output_schema` block in `config/settings.yaml` is deleted as
dead config — `LLMClient._load_schema()` reads only `schemas/classification.json`.

The pre-existing `llm_client.ClassificationResult` dataclass coerced
`severity=int(data["severity"])` and declared `severity: int`, matching the
deleted config block's earlier `severity: "string"  # critical|high|medium|low`
draft that itself drifted before merge. This patch flips the client to
`severity: str` / `severity=str(data["severity"])`, matching what the schema's
string enum now enforces. Without it, `LLMClient.classify()` crashes at
`int("extreme")` on the first LUNA episode.

Hard to reverse: schema, prompt, Task 18's flow, and the Wave-4 ablation
comparison all depend on which fields are LLM-emitted vs derived. Surprising
without context: a reader sees `severity` and `classification` side-by-side in
the schema and assumes both come from the LLM; the fact that one is verbatim
Task 14 data is invisible from the file alone. Real trade-off: deriving severity
loses the LLM's ability to flag "the peak |Z| was borderline" — but borderline
severity isn't a useful axis for crash classification, and CONTEXT.md already
defines severity as a peak-|Z| band, so the LLM had no business judging it
anyway.