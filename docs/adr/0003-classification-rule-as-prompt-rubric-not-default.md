# Classification rule is a prompt rubric, not a deterministic Task 18 default

The LLM applies the "derivatives explain a crash" threshold rule **itself**, by
reading the rule as a rubric in the system prompt. Task 18 does **not** precompute
a default classification for the LLM to accept or override. The LLM receives the
raw features (`funding_rate_current`, `funding_rate_avg_4h`, `oi_current`,
`oi_change_4h`, and in Run B the RAG news context), applies the rubric, picks the
category, and writes a substantive rationale defending its pick against the cited
feature values.

The rubric lives in `config/settings.yaml` under
`anomaly_detection.derivatives_thresholds` (target values: `funding_rate_mag ≥
0.0005` OR `|oi_change_4h| ≥ 0.10` → derivatives unusual). It is injected into the
system prompt verbatim, so a future reader of the prompt can see exactly what rule
the LLM is being asked to apply.

We did **not** compute a deterministic default in Task 18 and ask the LLM to
accept-or-override. The override design was tested and rejected: when the LLM
accepts a precomputed default, its rationale degenerates into post-hoc apology
prose ("Default accepted; funding below threshold") that Ragas evaluates to high
faithfulness meaninglessly. With only 7 LUNA episodes calibrated so the rule
mostly explains them, overrides would be few — the rationale showcase would
mostly collapse, defeating the project's LLM-learning goal (the rationale output
is the actual showcase field). Forcing rich rationale via prompt instructions
("on accept, cite specific feature values") only partially mitigates — the LLM
still knows the answer is the precomputed default, so the justification is
qualitatively different from doing the classification work itself.

Reproducibility cost: same input, different model version → different verdict.
Acceptable here because (a) LUNA is n=7, so the Wave-4 ablation has no
statistical power regardless of design — it's a qualitative narrative; and (b)
the project is explicitly an LLM-learning vehicle, and model-version drift is a
real thing worth encountering. The ablation stays clean: Run A (derivatives +
rubric) vs Run B (derivatives + rubric + RAG news + the extra `explained_news`
category reachable). `explained_news` remains the one category where LLM judgment
is genuinely irreducible — it requires reading news prose and judging its
semantic relevance to the price move, which no threshold rule can do.

`confidence` stays LLM-reported (consistent with the spec, supporting the future
Bull/Bear/Judge debate layer in Milestone 2). The prompt anchors it: "rate your
confidence that your classification is well-supported by the cited feature
values" — anchored to evidence, not free-floating, to partially bound the known
miscalibration of LLM self-reported confidence.

Hard to reverse: schema semantics, prompt structure, Task 18 flow, ablation
design, and the future B/B/J integration all depend on this. Surprising without
context: a reader sees `classification` in the schema alongside a `threshold`
configured in YAML and assumes the classification is just the threshold gate;
the fact that the LLM applies the rubric with judgment (and may pick
`insufficient_data` on sparse data, `explained_derivatives` on a clean hairline
breach, or `unexplained` when the rule says no breach) is the point. Real
trade-off: reproducibility vs. rationale richness; given the LLM-learning
framing and n=7, rationale richness wins.