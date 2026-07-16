# Classification rule is a prompt rubric, not a deterministic default

The LLM applies the derivatives threshold rule itself. Orchestration passes raw
funding and open-interest features plus configured thresholds; it does not
precompute a verdict for the model to accept or override.

The rubric comes from packaged `assets/settings.yaml`:

- `|funding_rate_current| >= 0.0005`, or
- `|oi_change_4h| >= 0.10`

A deterministic default made rationales post-hoc explanations of an answer the
model was already given. Letting the model apply the visible rubric keeps the
rationale substantive and lets it handle missing data and news relevance.

Trade-off: model upgrades can change a verdict for identical inputs. That is
acceptable for this qualitative LLM evaluation, and tracked outputs preserve
exact observed runs. Direct verdict overlap remains the primary ablation metric;
Ragas measures rationale quality.